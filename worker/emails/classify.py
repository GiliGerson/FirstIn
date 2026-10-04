"""LLM email classifier (FR4) — Claude Haiku 4.5 with structured output."""

from typing import Literal, Optional

import anthropic
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from worker.collectors.gmail import EmailMessage

MODEL = "claude-haiku-4-5"
# Classification only needs the start of the email; long HTML newsletters are cut here.
MAX_BODY_CHARS = 12000

Category = Literal["job_alert", "recruiter_outreach", "application_update", "other"]
Stage = Literal["received", "screening", "interview", "home_assignment", "offer", "rejected", "none"]

SYSTEM_PROMPT = """You sort the inbox of a computer-science student in Israel who is looking for \
student / part-time / internship tech jobs. Classify each email into exactly one category:

- job_alert: an automated list of one or more job postings (job boards, LinkedIn alerts, \
company newsletters listing open positions, university career-center job lists).
- recruiter_outreach: a real person (recruiter, hiring manager, founder) personally reaching out \
to her about a role or asking to talk.
- application_update: about an application she already submitted — confirmation of receipt, \
screening, interview scheduling, home assignment, offer, or rejection.
- other: anything else, including marketing, courses, events, generic newsletters, \
candidate-portal account emails (password resets, verification codes, account created), and \
programs that are not a job or internship (councils, volunteering, competitions).

Also extract the company and role if mentioned, the application stage (only for \
application_update, otherwise "none"), and a one-sentence summary in Hebrew."""


class EmailClassification(BaseModel):
    category: Category
    company: Optional[str] = Field(description="Company name, or null if unknown")
    role: Optional[str] = Field(description="Job title, or null if unknown")
    application_stage: Stage
    summary_he: str = Field(description="One-sentence summary in Hebrew")


def email_body_text(email: EmailMessage) -> str:
    if email.text.strip():
        return email.text
    if email.html:
        return BeautifulSoup(email.html, "html.parser").get_text("\n", strip=True)
    return ""


def build_user_message(email: EmailMessage) -> str:
    body = email_body_text(email)[:MAX_BODY_CHARS]
    return (
        f"From: {email.from_name} <{email.from_addr}>\n"
        f"Subject: {email.subject}\n"
        f"Date: {email.received_at:%Y-%m-%d}\n\n"
        f"{body}"
    )


def classify(client: anthropic.Anthropic, email: EmailMessage) -> EmailClassification | None:
    """Return the classification, or None if the model declined to answer."""
    response = client.messages.parse(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(email)}],
        output_format=EmailClassification,
    )
    if response.stop_reason == "refusal":
        return None
    return response.parsed_output
