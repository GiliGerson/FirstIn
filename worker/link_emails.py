"""Link stored application-update emails that aren't linked to an application yet (backfill for
step 8). Re-reads each email from Gmail and re-classifies it; no Telegram alerts are sent.

Usage: .venv/bin/python -m worker.link_emails
"""

import anthropic

from worker import db
from worker.collectors import gmail
from worker.emails.classify import classify
from worker.emails.link_to_job import link_application_update
from worker.notify.format import STAGE_HE_APP


def main() -> None:
    rows = db.execute(
        db.client().table("emails").select("gmail_message_id,subject")
        .eq("category", "application_update").is_("linked_application_id", "null").order("received_at")
    ).data
    print(f"{len(rows)} עדכוני הגשה בלי קישור")
    service, llm = gmail.get_service(), anthropic.Anthropic()
    for row in rows:
        email = gmail.fetch_full(service, row["gmail_message_id"])
        result = classify(llm, email)
        link = link_application_update(row["gmail_message_id"], email.subject, result,
                                       email.received_at.isoformat()) if result else None
        if link is None:
            print(f"  ➖ {row['subject']}: לא נמצאה התאמה")
            continue
        stage = STAGE_HE_APP.get(link.to_stage, link.to_stage)
        action = "כרטיס חדש" if link.created else ("עבר" if link.moved else "קושר")
        print(f"  ✅ {result.company} · {result.role or '—'} → {action} (שלב: {stage})")


if __name__ == "__main__":
    main()
