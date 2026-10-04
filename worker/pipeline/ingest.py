"""Ingest pipeline (PRD flow 1): RawJob → base rule filter → company match → de-dup → `jobs`.

`jobs` is a catalog shared by all users. Ingest applies only the user-independent filter (Israel,
student/intern/part-time, not senior); each user's cities, job types, scores and alerts are
handled afterwards by `personalize` (→ `user_jobs`).

De-dup (FR1): the same job from LinkedIn, email and an ATS becomes one `jobs` row with several
`job_sources`. Match on canonical URL first, then on company + normalized title + location."""

import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from postgrest.exceptions import APIError

from worker import db, settings as settings_mod
from worker.discovery import companies as companies_repo
from worker.discovery.finder import NAME_NOISE, core_name
from worker.models import RawJob
from worker.pipeline.filter import RuleFilter
from worker.pipeline.normalize import normalize_location, normalize_title, workplace_flags

# The scheduler may run Gmail and ATS ingests at the same time; serialize them so two runs
# never create the same pending company or job concurrently.
_INGEST_LOCK = threading.Lock()
UNIQUE_VIOLATION = "23505"


@dataclass
class NewJob:
    raw: RawJob
    row: dict                         # the inserted `jobs` row
    company: dict


@dataclass
class IngestReport:
    received: int = 0
    rejected: Counter = field(default_factory=Counter)
    duplicates: int = 0               # already in the DB (source added / last_seen updated)
    new: list[NewJob] = field(default_factory=list)
    new_companies: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ company matching
def _words(name: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in NAME_NOISE]


class CompanyIndex:
    """Find the `companies` row for a job's company name, creating a `pending` row if unknown
    (discovery then looks for its ATS — PRD §6.1.1 channel 1)."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.by_core = {core_name(r["name"]): r for r in rows if core_name(r["name"])}

    def find(self, name: str) -> dict | None:
        key = core_name(name)
        if not key:
            return None
        if key in self.by_core:
            return self.by_core[key]
        # "Upwind Security" → "Upwind": a stored name that is a whole-word prefix of this one
        words = _words(name)
        for row in self.rows:
            stored = _words(row["name"])
            if stored and len("".join(stored)) >= 4 and words[:len(stored)] == stored:
                return row
        return None

    def get_or_create(self, name: str, report: IngestReport) -> dict | None:
        row = self.find(name)
        if row is None and core_name(name):
            row = companies_repo.create_pending(name)
            self.rows.append(row)
            self.by_core[core_name(name)] = row
            report.new_companies.append(name)
        return row


# ------------------------------------------------------------------ jobs table
def load_jobs_index() -> tuple[dict, dict]:
    """(canonical_url → row, (company_id, title_normalized, location) → row) for all jobs."""
    rows, start, page = [], 0, 1000
    while True:
        batch = db.execute(
            db.client().table("jobs")
            .select("id,company_id,title_normalized,location,canonical_url,description,status")
            .order("id").range(start, start + page - 1)
        ).data
        rows += batch
        if len(batch) < page:
            break
        start += page
    by_url = {r["canonical_url"]: r for r in rows if r["canonical_url"]}
    by_key = {(r["company_id"], r["title_normalized"], r["location"] or ""): r for r in rows}
    return by_url, by_key


def add_source(job_id: int, raw: RawJob) -> None:
    db.execute(db.client().table("job_sources").upsert(
        {"job_id": job_id, "source": raw.source, "source_url": raw.url or "", "seen_at": db.now_iso()},
        on_conflict="job_id,source,source_url",
    ))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# ------------------------------------------------------------------ main entry
def ingest(raw_jobs: list[RawJob]) -> IngestReport:
    with _INGEST_LOCK:
        return _ingest(raw_jobs)


def _ingest(raw_jobs: list[RawJob]) -> IngestReport:
    report = IngestReport(received=len(raw_jobs))
    rule_filter = RuleFilter(settings_mod.base())
    companies = CompanyIndex(companies_repo.all_companies())
    by_url, by_key = load_jobs_index()
    batch_keys: set = set()
    batch_urls: set = set()

    for raw in raw_jobs:
        verdict = rule_filter.check(raw)
        if not verdict.passed:
            report.rejected[verdict.reason] += 1
            continue
        company = companies.get_or_create(raw.company, report)
        if company is None:
            report.rejected["no_company"] += 1
            continue
        if company["priority"] == "blocked":
            report.rejected["blocked_company"] += 1
            continue

        title_norm = normalize_title(raw.title)
        location = normalize_location(raw.location)
        key = (company["id"], title_norm, location or "")
        existing = by_url.get(raw.canonical_url) if raw.canonical_url else None
        existing = existing or by_key.get(key)
        if existing:
            report.duplicates += 1
            fields = {"last_seen_at": db.now_iso(), "status": "open"}
            if raw.description and not existing.get("description"):
                fields["description"] = raw.description   # e.g. ATS text for a job first seen on LinkedIn
                existing["description"] = raw.description
            db.execute(db.client().table("jobs").update(fields).eq("id", existing["id"]))
            add_source(existing["id"], raw)
            continue
        if key in batch_keys or (raw.canonical_url and raw.canonical_url in batch_urls):
            report.duplicates += 1          # same job twice in this batch (repeated LinkedIn alerts)
            continue
        batch_keys.add(key)
        if raw.canonical_url:
            batch_urls.add(raw.canonical_url)

        is_hybrid, is_remote = workplace_flags(raw.workplace, raw.location)
        row = {
            "company_id": company["id"],
            "title": raw.title,
            "title_normalized": title_norm,
            "description": raw.description or None,
            "url": raw.url,
            "canonical_url": raw.canonical_url,
            "location": location,
            "is_hybrid": is_hybrid,
            "is_remote": is_remote,
            "job_type": verdict.job_type,
            "posted_at": _iso(raw.posted_at),
        }
        try:
            row = db.execute(db.client().table("jobs").insert(row)).data[0]
        except APIError as e:
            if e.code != UNIQUE_VIOLATION:
                raise
            report.duplicates += 1      # stored meanwhile under another key — never lose the run
            continue
        add_source(row["id"], raw)
        by_key[key] = row
        if raw.canonical_url:
            by_url[raw.canonical_url] = row
        report.new.append(NewJob(raw, row, company))
    return report


REJECT_REASONS_HE = {
    "not_israel": "מחוץ לישראל",
    "not_student_or_part_time": "לא סטודנט/חלקית",
    "excluded_keyword": "בכיר/מוביל",
    "manager_role": "תפקיד ניהולי",
    "requires_experience": "דורש ניסיון",
    "outside_my_area": "מחוץ לאזור שלי",
    "job_type_disabled": "סוג משרה כבוי",
    "blocked_company": "חברה חסומה",
    "no_company": "בלי שם חברה",
}


def print_report(report: IngestReport) -> None:
    rejected = ", ".join(f"{REJECT_REASONS_HE.get(k, k)}: {v}" for k, v in report.rejected.most_common())
    print(f"\nעיבוד משרות: התקבלו {report.received} · נפסלו בסינון {sum(report.rejected.values())}"
          f" ({rejected or '—'})")
    print(f"  כבר קיימות (עודכנו): {report.duplicates} · חדשות במאגר: {len(report.new)}")
    if report.new_companies:
        print(f"  חברות חדשות שיחכו לגילוי: {len(report.new_companies)}")
    for n in report.new[:20]:
        print(f"    • {n.row['title']} — {n.company['name']} ({n.row['location'] or '?'})")


def close_missing(company_id: int, source: str, seen_since: str) -> int:
    """FR1: open jobs of this company that came from `source` (an ATS) but weren't seen in the
    scan that started at `seen_since` have disappeared from the board → status `closed`."""
    open_jobs = db.execute(
        db.client().table("jobs").select("id,last_seen_at")
        .eq("company_id", company_id).eq("status", "open").lt("last_seen_at", seen_since)
    ).data
    if not open_jobs:
        return 0
    ids = [j["id"] for j in open_jobs]
    from_source = {
        r["job_id"] for r in db.execute(
            db.client().table("job_sources").select("job_id").in_("job_id", ids).eq("source", source)
        ).data
    }
    if from_source:
        db.execute(db.client().table("jobs").update({"status": "closed"}).in_("id", list(from_source)))
    return len(from_source)
