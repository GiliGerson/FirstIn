"""Gmail run: fetch new mail → pre-filter → classify / parse LinkedIn alerts → save to `emails`.

Usage:
    .venv/bin/python -m worker.run_gmail              # since the last successful run (first run: 14 days)
    .venv/bin/python -m worker.run_gmail --days 30    # explicit look-back window
    .venv/bin/python -m worker.run_gmail --preview    # don't write anything to the DB
"""

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import anthropic

from worker import db
from worker.collectors import gmail
from worker.emails import linkedin_alerts
from worker.emails import link_to_job
from worker.emails.classify import EmailClassification, classify
from worker.emails.prefilter import Decision, decide
from worker.models import RawJob
from worker.notify import alerts
from worker.pipeline import ingest

COLLECTOR = "gmail"
FIRST_RUN_DAYS = 14
OVERLAP = timedelta(minutes=10)
STORED_CATEGORIES = {"job_alert", "recruiter_outreach", "application_update"}


@dataclass
class ProcessedEmail:
    email: gmail.EmailMessage
    category: str
    summary: str
    company: str | None = None
    role: str | None = None
    application_stage: str = "none"
    jobs: list[RawJob] = field(default_factory=list)
    classification: EmailClassification | None = None


@dataclass
class GmailRunResult:
    scanned: int = 0
    decisions: Counter = field(default_factory=Counter)
    relevant: list[ProcessedEmail] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    ingest_report: ingest.IngestReport | None = None

    @property
    def jobs(self) -> list[RawJob]:
        return [job for p in self.relevant for job in p.jobs]


def process_email(email: gmail.EmailMessage, decision: Decision,
                  llm: anthropic.Anthropic) -> ProcessedEmail | None:
    if decision == Decision.SKIP:
        return None
    if decision == Decision.LINKEDIN_ALERT:
        jobs = linkedin_alerts.parse_alert(email)
        for job in jobs:
            job.posted_at = email.received_at   # alerts don't carry a posting date
        return ProcessedEmail(email, "job_alert", f"התראת LinkedIn עם {len(jobs)} משרות", jobs=jobs)
    result = classify(llm, email)
    if result is None:
        return None
    return ProcessedEmail(
        email, result.category, result.summary_he,
        company=result.company, role=result.role, application_stage=result.application_stage,
        classification=result,
    )


ALERT_CATEGORIES = {"recruiter_outreach", "application_update"}


def save_email(p: ProcessedEmail) -> bool:
    """Upsert the email; returns True if it wasn't stored before (i.e. it's new to FirstIn)."""
    seen = db.execute(db.client().table("emails").select("id")
                      .eq("gmail_message_id", p.email.gmail_id).limit(1)).data
    db.execute(db.client().table("emails").upsert({
        "gmail_message_id": p.email.gmail_id,
        "received_at": p.email.received_at.isoformat(),
        "from_addr": p.email.from_addr,
        "subject": p.email.subject,
        "category": p.category,
        "summary": p.summary,
    }, on_conflict="gmail_message_id"))
    return not seen


def run(since: datetime, preview: bool = False) -> GmailRunResult:
    result = GmailRunResult()
    run_id = None if preview else db.start_run(COLLECTOR)
    try:
        service = gmail.get_service()
        llm = anthropic.Anthropic()
        # Pre-filter on headers + snippet; download the full body only for candidates.
        emails = gmail.fetch_messages(service, since)
        result.scanned = len(emails)
        for email in emails:
            try:
                decision = decide(email)
                result.decisions[decision.value] += 1
                if decision == Decision.SKIP:
                    continue
                full = gmail.fetch_full(service, email.gmail_id)
                processed = process_email(full, decision, llm)
                if processed is None or processed.category not in STORED_CATEGORIES:
                    continue  # non-job mail is never stored (PRD §12)
                result.relevant.append(processed)
                if not preview and save_email(processed) and processed.category in ALERT_CATEGORIES:
                    note = None
                    if processed.category == "application_update" and processed.classification:
                        link = link_to_job.link_application_update(
                            email.gmail_id, email.subject, processed.classification,
                            email.received_at.isoformat())
                        note = alerts.pipeline_note(link)
                    alerts.send_email_alert(processed.category, email.from_name or email.from_addr,
                                            email.subject, processed.summary, processed.application_stage,
                                            pipeline_note=note)
            except Exception as e:  # one bad email must not stop the run
                result.errors.append({"gmail_id": email.gmail_id, "error": f"{type(e).__name__}: {e}"})
        if not preview and result.jobs:
            result.ingest_report = ingest.ingest(result.jobs)
    except Exception as e:
        result.errors.append({"error": f"{type(e).__name__}: {e}"})
    finally:
        if run_id is not None:
            db.finish_run(run_id, len(result.relevant), result.errors)
    return result


def resolve_since(days: int | None) -> datetime:
    now = datetime.now(timezone.utc)
    if days is not None:
        return now - timedelta(days=days)
    last = db.last_successful_run_start(COLLECTOR)
    return last - OVERLAP if last else now - timedelta(days=FIRST_RUN_DAYS)


def print_report(result: GmailRunResult, since: datetime) -> None:
    print(f"\nנסרקו {result.scanned} מיילים מאז {since:%d/%m/%Y %H:%M} (UTC)")
    print(f"  סינון מקדים: {dict(result.decisions)}")
    by_cat = Counter(p.category for p in result.relevant)
    print(f"  רלוונטיים: {len(result.relevant)} → {dict(by_cat)}")
    for p in sorted(result.relevant, key=lambda p: p.email.received_at):
        print(f"\n  [{p.category}] {p.email.received_at:%d/%m} · {p.email.from_name or p.email.from_addr}")
        print(f"    נושא: {p.email.subject}")
        print(f"    סיכום: {p.summary}")
        if p.application_stage != "none":
            print(f"    שלב: {p.application_stage}")
        for job in p.jobs:
            print(f"      • {job.title} — {job.company} ({job.location or '?'})")
    unique = {job.canonical_url or job.url for job in result.jobs}
    print(f"\nסה\"כ משרות שחולצו מהתראות: {len(result.jobs)} ({len(unique)} ייחודיות)")
    if result.ingest_report:
        ingest.print_report(result.ingest_report)
    if result.errors:
        print(f"\n⚠ {len(result.errors)} שגיאות:")
        for err in result.errors:
            print(f"  {err}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, help="look-back window in days")
    parser.add_argument("--preview", action="store_true", help="don't write to the database")
    args = parser.parse_args()
    since = resolve_since(args.days)
    result = run(since, preview=args.preview)
    print_report(result, since)


if __name__ == "__main__":
    main()
