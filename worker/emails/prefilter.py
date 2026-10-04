"""Cheap rule-based pre-filter (FR4): decides which emails are worth an LLM call."""

import re
from enum import Enum
from functools import lru_cache

from worker.collectors.gmail import EmailMessage
from worker.config import load_yaml

# LinkedIn job-alert senders — parsed directly, no LLM needed
LINKEDIN_ALERT_SENDERS = {
    "jobalerts-noreply@linkedin.com",
    "jobs-listings@linkedin.com",
    "jobs-noreply@linkedin.com",
}

# Senders whose mail is always job-related (ATS systems, job boards, career center)
KNOWN_SENDER_DOMAINS = (
    "drushim.co.il", "alljobs.co.il", "jobmaster.co.il", "comeet.co", "comeet.com",
    "greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com",
    "myworkday.com", "workday.com", "secrettelaviv.com",
)

# LinkedIn recruiter messages (InMail)
LINKEDIN_RECRUITER_SENDERS = {"inmail-hit-reply@linkedin.com", "hit-reply@linkedin.com"}

SUBJECT_KEYWORDS = [
    "job", "jobs", "position", "positions", "role", "roles", "opening", "openings",
    "intern", "interns", "internship", "internships", "student", "students",
    "interview", "interviews", "application", "applications", "applied",
    "recruiter", "recruiting", "recruitment", "hiring", "candidate", "candidates",
    "opportunity", "opportunities", "job offer", "assignment", "career", "careers",
    "משרה", "משרות", "ראיון", "מועמד", "גיוס", "מגייס", "סטודנט", "התמחות", "הצעת עבודה", "קורות חיים",
]
# Stronger phrases that justify a look even when the subject is generic
BODY_KEYWORDS = [
    "your application", "thank you for applying", "thanks for applying", "interview",
    "home assignment", "recruiter", "we'd like to", "we would like to", "next steps",
    "המועמדות שלך", "הגשת מועמדות", "ראיון", "מטלת בית", "מגייסת", "מגייס",
]

def _keyword_re(keywords: list[str]) -> re.Pattern:
    # English keywords match whole words only ("role" must not match "control", "intern" must not
    # match "international"). Hebrew words take attached prefixes (ה, ל, ב...), so match anywhere.
    parts = [rf"\b{re.escape(k)}\b" if k[0].isascii() else re.escape(k) for k in keywords]
    return re.compile("|".join(parts), re.IGNORECASE)


_SUBJECT_RE = _keyword_re(SUBJECT_KEYWORDS)
_BODY_RE = _keyword_re(BODY_KEYWORDS)
BODY_SCAN_CHARS = 3000


@lru_cache(maxsize=1)
def known_sender_domains() -> tuple[str, ...]:
    """Built-in senders + personal ones (e.g. my university's career center) from
    config/settings.yaml → email.extra_known_senders."""
    extra = (load_yaml("settings").get("email") or {}).get("extra_known_senders") or []
    return KNOWN_SENDER_DOMAINS + tuple(d.lower() for d in extra)


class Decision(str, Enum):
    LINKEDIN_ALERT = "linkedin_alert"   # parse jobs directly
    CLASSIFY = "classify"               # send to the LLM classifier
    SKIP = "skip"                       # not job-related — never stored


def decide(email: EmailMessage) -> Decision:
    sender = email.from_addr
    if sender in LINKEDIN_ALERT_SENDERS:
        return Decision.LINKEDIN_ALERT
    if sender in LINKEDIN_RECRUITER_SENDERS:
        return Decision.CLASSIFY
    if any(email.sender_domain == d or email.sender_domain.endswith("." + d) for d in known_sender_domains()):
        return Decision.CLASSIFY
    if email.sender_domain.endswith("linkedin.com"):
        # Other LinkedIn mail (notifications, newsletters) only if the subject is job-related
        return Decision.CLASSIFY if _SUBJECT_RE.search(email.subject) else Decision.SKIP
    if _SUBJECT_RE.search(email.subject):
        return Decision.CLASSIFY
    if _BODY_RE.search(email.text[:BODY_SCAN_CHARS]):
        return Decision.CLASSIFY
    return Decision.SKIP
