"""FR4 / stage 2 step 8 — link application-update emails to applications and move their stage.

"We'd like to schedule an interview" → find the application for that company (and role) →
stage `interview` + a `stage_change` event + the email linked to it. If I applied without
pressing "applied", the confirmation email opens the application by itself."""

import re
from dataclasses import dataclass

from worker import db, users
from worker.discovery import companies as companies_repo
from worker.emails.classify import EmailClassification
from worker.pipeline.ingest import CompanyIndex
from worker.pipeline.normalize import normalize_title

# Classifier stage → application stage ("received" means the application exists, nothing more)
EMAIL_TO_STAGE = {
    "received": "applied", "screening": "screening", "interview": "interview",
    "home_assignment": "home_assignment", "offer": "offer", "rejected": "rejected",
}
PROGRESS = ["applied", "screening", "interview", "home_assignment", "offer"]
FINAL = {"offer", "rejected", "withdrawn"}
TITLE_MATCH_MIN = 0.34


@dataclass
class LinkResult:
    application_id: int
    job_id: int | None
    from_stage: str | None        # None when the application was created from this email
    to_stage: str
    created: bool = False

    @property
    def moved(self) -> bool:
        return self.from_stage is not None and self.from_stage != self.to_stage


def next_stage(current: str, incoming: str) -> str:
    """Never move backwards ("received" after "interview"), and leave final outcomes alone —
    except a rejection, which can close any open stage."""
    if current in FINAL or current == incoming:
        return current
    if incoming == "rejected":
        return "rejected"
    if current in PROGRESS and incoming in PROGRESS and PROGRESS.index(incoming) < PROGRESS.index(current):
        return current
    return incoming


def title_similarity(a: str | None, b: str | None) -> float:
    """Jaccard overlap of title words — "Student Developer" vs "Software Developer (Student)"."""
    wa = set(re.findall(r"\w+", normalize_title(a or "")))
    wb = set(re.findall(r"\w+", normalize_title(b or "")))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def best_by_title(rows: list[dict], role: str | None, title_of) -> dict | None:
    """The row whose title best matches `role`; with no role (or one row), the most recent row."""
    if not rows:
        return None
    if role:
        scored = sorted(((title_similarity(role, title_of(r)), r) for r in rows), key=lambda x: -x[0])
        if scored[0][0] >= TITLE_MATCH_MIN:
            return scored[0][1]
        return rows[0] if len(rows) == 1 else None
    return rows[0]


def _company_applications(company_id: int) -> list[dict]:
    # Gmail is read only for the owner, so updates always concern the owner's applications
    return db.execute(
        db.client().table("applications").select("id,stage,job_id,applied_at,jobs!inner(title,company_id)")
        .eq("user_id", users.owner().user_id).eq("jobs.company_id", company_id).order("applied_at", desc=True)
    ).data


def _company_jobs(company_id: int) -> list[dict]:
    return db.execute(
        db.client().table("jobs").select("id,title,user_state").eq("company_id", company_id)
        .order("first_seen_at", desc=True).limit(200)
    ).data


def _open_application(job_id: int, stage: str, applied_at: str | None = None) -> int:
    client = db.client()
    owner_id = users.owner().user_id
    db.execute(client.table("user_jobs").upsert(
        {"user_id": owner_id, "job_id": job_id, "user_state": "applied"}, on_conflict="user_id,job_id"))
    row = {"job_id": job_id, "stage": stage, "user_id": owner_id}
    if applied_at:
        row["applied_at"] = applied_at      # the email's date, not the day FirstIn read it
    app = db.execute(client.table("applications").insert(row)).data[0]
    event = {"application_id": app["id"], "type": "applied", "payload": {"via": "email"}}
    if applied_at:
        event["occurred_at"] = applied_at
    db.execute(client.table("events").insert(event))
    return app["id"]


def link_application_update(gmail_id: str, subject: str, result: EmailClassification,
                            received_at: str | None = None) -> LinkResult | None:
    """Apply one application_update email. Returns what changed, or None if it couldn't be matched."""
    incoming = EMAIL_TO_STAGE.get(result.application_stage)
    if not incoming or not result.company:
        return None
    company = CompanyIndex(companies_repo.all_companies()).find(result.company)

    link: LinkResult | None = None
    if company:
        app = best_by_title(_company_applications(company["id"]), result.role, lambda a: a["jobs"]["title"])
        if app:
            to = next_stage(app["stage"], incoming)
            if to != app["stage"]:
                db.execute(db.client().table("applications").update({"stage": to}).eq("id", app["id"]))
                db.execute(db.client().table("events").insert({
                    "application_id": app["id"], "type": "stage_change",
                    "payload": {"from": app["stage"], "to": to, "via": "email", "subject": subject},
                }))
            link = LinkResult(app["id"], app["job_id"], app["stage"], to)

    if link is None:
        # Applied outside FirstIn's buttons: open the application from this email
        if company is None:
            company = companies_repo.create_pending(result.company)
        job = best_by_title(_company_jobs(company["id"]), result.role, lambda j: j["title"]) if result.role else None
        if job is None:
            title = result.role or "משרה (מתוך מייל)"
            job = db.execute(db.client().table("jobs").insert({
                "company_id": company["id"], "title": title, "title_normalized": normalize_title(title),
                "status": "open", "user_state": "applied", "job_type": "other",
            })).data[0]
            db.execute(db.client().table("job_sources").upsert(
                {"job_id": job["id"], "source": "gmail", "source_url": ""}, on_conflict="job_id,source,source_url"))
        app_id = _open_application(job["id"], incoming, received_at)
        link = LinkResult(app_id, job["id"], None, incoming, created=True)

    db.execute(db.client().table("emails").update(
        {"linked_application_id": link.application_id, "linked_job_id": link.job_id}
    ).eq("gmail_message_id", gmail_id))
    return link
