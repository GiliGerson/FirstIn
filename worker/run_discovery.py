"""Company discovery: seed list (config/companies.yaml) + companies first seen in jobs.

The ingest pipeline stores only jobs that pass the rule filter, and creates a `pending`
company for every unknown company name — so every pending company already has at least one
relevant job. Paid web searches are capped per run.

Usage:
    .venv/bin/python -m worker.run_discovery                     # seed + pending companies
    .venv/bin/python -m worker.run_discovery --max-searches 60
    .venv/bin/python -m worker.run_discovery --no-search         # free token probing only
    .venv/bin/python -m worker.run_discovery --retry-unsupported # also re-check companies not found before
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import anthropic

from worker import db
from worker.collectors.http import make_client
from worker.config import load_yaml
from worker.discovery import companies as repo
from worker.discovery.finder import SearchBudget, find_company, normalize_name

WORKERS = 4  # companies checked in parallel (each also probes up to 8 URLs at once)


def _job_location(company_id: int) -> str | None:
    """An example location from the company's stored jobs — a hint for the web search."""
    rows = db.execute(db.client().table("jobs").select("location").eq("company_id", company_id).limit(1)).data
    return rows[0]["location"] if rows else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-searches", type=int, default=40, help="cap on paid web searches this run")
    parser.add_argument("--no-search", action="store_true", help="free token probing only")
    parser.add_argument("--retry-unsupported", action="store_true",
                        help="search again for companies where no ATS was found before")
    args = parser.parse_args()

    existing = repo.all_companies()
    known = repo.known_name_keys(existing)

    # Task: (name, location, careers_url, discovered_via, priority, existing_row_or_None)
    todo = []
    for entry in load_yaml("companies").get("companies", []) or []:
        todo.append((entry["name"], None, entry.get("careers_url"), "seed", entry.get("priority", "normal"), None))

    seen, queue = set(known), []
    rechecks = repo.pending(existing) + (repo.unresolved(existing) if args.retry_unsupported else [])
    for c in rechecks:
        queue.append((c["name"], _job_location(c["id"]), c["careers_url"], c["discovered_via"], c["priority"], c))
    for item in todo:
        key = normalize_name(item[0])
        if key and key not in seen:
            seen.add(key)
            queue.append(item)
    print(f"{len(queue)} חברות לבדיקה ({len(known)} כבר ברשימה)\n")

    client = make_client()
    llm = None if args.no_search else anthropic.Anthropic()
    budget = SearchBudget(args.max_searches)

    def find(task):
        name, location, careers_url, *_ = task
        try:
            return find_company(client, llm, name, location, careers_url, budget)
        except Exception as e:  # one company must not stop the run
            return e

    stats = Counter()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for task, result in zip(queue, pool.map(find, queue)):
            name, _, _, via, priority, existing_row = task
            if isinstance(result, Exception):
                stats["error"] += 1
                print(f"  ⚠ {name}: שגיאה ({type(result).__name__}: {result})")
                continue
            if result.method == "deferred":
                stats["deferred"] += 1
                print(f"  ⏸ {name}: לא נמצא בניחוש — יחפש ברשת בריצה הבאה")
                continue
            if existing_row:
                row = repo.update_found(existing_row, result)
            else:
                row = repo.save_found(result, via, priority)
            det = result.detection
            if row is None:
                stats["alias"] += 1
                owner = repo.board_owner(result)
                if existing_row and owner:
                    repo.merge_into(existing_row, owner)   # same company under another name
                print(f"  ↔ {name}: זו {owner['name'] if owner else 'חברה קיימת'} ({det.ats}/{det.token}) — אוחדו")
            elif row["ats_status"] == "ok":
                stats[result.method] += 1
                extra = f", {result.probe.israel_jobs} משרות בישראל" if result.probe else ""
                print(f"  ✅ {name}: {det.ats}/{det.token} (דרך {result.method}{extra})")
            else:
                stats["unsupported"] += 1
                reason = f"{det.ats} — עוד לא נתמך" if det else "לא נמצאה מערכת גיוס נתמכת"
                print(f"  ➖ {name}: {reason} → רק דרך LinkedIn/מייל")
    print(f"\nסיכום: {dict(stats)} · חיפושי רשת: {args.max_searches - budget.remaining}")


if __name__ == "__main__":
    main()
