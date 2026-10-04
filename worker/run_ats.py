"""ATS run: fetch every scannable company's board → ingest pipeline (filter, de-dup, score,
save) → mark jobs that disappeared from a board as closed.

Usage:
    .venv/bin/python -m worker.run_ats
    .venv/bin/python -m worker.run_ats --preview      # don't update companies/runs
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from worker import db
from worker.collectors.ats import COLLECTORS
from worker.collectors.common import BoardNotFound
from worker.collectors.http import make_client
from worker.discovery import companies as repo
from worker.models import RawJob
from worker.pipeline import ingest, personalize
from worker.pipeline.keywords import looks_student

COLLECTOR = "ats"
WORKERS = 8


@dataclass
class CompanyScan:
    company: dict
    jobs: list[RawJob] = field(default_factory=list)
    error: str | None = None

    @property
    def israel_jobs(self) -> list[RawJob]:
        return [j for j in self.jobs if j.is_israel]

    @property
    def student_jobs(self) -> list[RawJob]:
        return [j for j in self.israel_jobs if looks_student(j.title, j.employment_type)]


def scan_company(client, company: dict) -> CompanyScan:
    collector = COLLECTORS[company["ats_type"]]
    try:
        return CompanyScan(company, collector.fetch_jobs(client, company["ats_token"], company["name"]))
    except BoardNotFound:
        return CompanyScan(company, error="board_not_found")
    except Exception as e:
        return CompanyScan(company, error=f"{type(e).__name__}: {e}")


def record(scan: CompanyScan) -> None:
    c = scan.company
    if scan.error == "board_not_found":
        repo.update(c["id"], {"ats_status": "failing"})
        return
    if scan.error:
        return
    fields = {"ats_status": "ok"}
    if scan.student_jobs:
        fields["last_student_job_at"] = db.now_iso()
        if c["scan_tier"] == "daily":
            fields["scan_tier"] = "every_3h"
    repo.update(c["id"], fields)


def run(preview: bool = False) -> tuple[list[CompanyScan], ingest.IngestReport | None]:
    companies = repo.scannable(repo.all_companies())
    run_id = None if preview else db.start_run(COLLECTOR)
    started = db.now_iso()
    client = make_client()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        scans = list(pool.map(lambda c: scan_company(client, c), companies))
    errors = [{"company": s.company["name"], "error": s.error} for s in scans if s.error]
    report = None
    if not preview:
        try:
            report = ingest.ingest([job for s in scans if not s.error for job in s.jobs])
            for scan in scans:
                record(scan)
                if not scan.error:
                    ingest.close_missing(scan.company["id"], scan.company["ats_type"], started)
        except Exception as e:
            errors.append({"error": f"ingest: {type(e).__name__}: {e}"})
            raise
        finally:
            db.finish_run(run_id, sum(len(s.jobs) for s in scans), errors)
    return scans, report


def print_report(scans: list[CompanyScan]) -> None:
    ok = [s for s in scans if not s.error]
    print(f"\nנסרקו {len(scans)} חברות ({len(ok)} הצליחו)")
    print(f"  משרות בסה\"כ: {sum(len(s.jobs) for s in ok)} · בישראל: {sum(len(s.israel_jobs) for s in ok)}"
          f" · סטודנט/התמחות/חלקית בישראל: {sum(len(s.student_jobs) for s in ok)}")
    for s in sorted(ok, key=lambda s: -len(s.student_jobs)):
        if s.student_jobs:
            print(f"\n  {s.company['name']} ({s.company['ats_type']}):")
            for j in s.student_jobs:
                print(f"    • {j.title} — {j.location}")
    failed = [s for s in scans if s.error]
    if failed:
        print(f"\n⚠ {len(failed)} חברות נכשלו:")
        for s in failed:
            print(f"  {s.company['name']} ({s.company['ats_type']}/{s.company['ats_token']}): {s.error}")


def print_personalize(reports: list) -> None:
    for r in reports:
        if r.skipped:
            continue
        print(f"  משתמש {r.user_id[:8]}: נבדקו {r.considered} · דורגו {r.scored}"
              f" · ממתינות למכסה {r.waiting_for_quota} · נכשלו {r.failures}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", action="store_true", help="don't write to the database")
    args = parser.parse_args()
    scans, report = run(preview=args.preview)
    print_report(scans)
    if report:
        ingest.print_report(report)
        print_personalize(personalize.run_all())


if __name__ == "__main__":
    main()
