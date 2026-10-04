"""`companies` table access."""

from worker import db
from worker.collectors.ats import SUPPORTED
from worker.discovery.finder import FindResult, normalize_name


def all_companies() -> list[dict]:
    rows, start, page = [], 0, 1000
    while True:
        batch = db.execute(db.client().table("companies").select("*").order("id").range(start, start + page - 1)).data
        rows += batch
        if len(batch) < page:
            return rows
        start += page


def known_name_keys(companies: list[dict]) -> set[str]:
    return {normalize_name(c["name"]) for c in companies}


def _board_taken(result: FindResult, exclude_id: int | None = None) -> bool:
    det = result.detection
    if not det:
        return False
    rows = db.execute(
        db.client().table("companies").select("id")
        .eq("ats_type", det.ats).eq("ats_token", det.token).limit(2)
    ).data
    return any(r["id"] != exclude_id for r in rows)


def _found_fields(result: FindResult) -> dict:
    det = result.detection
    return {
        "website": result.website,
        "careers_url": result.careers_url,
        "ats_type": det.ats if det else "unknown",
        "ats_token": det.token if det else None,
        "kind": result.kind,
        "ats_status": "ok" if det and det.supported else "unsupported",
    }


def save_found(result: FindResult, discovered_via: str, priority: str = "normal") -> dict | None:
    """Insert a company found by discovery. Returns the row, or None if its ATS board is already
    stored under another name (e.g. "Elbit Systems Israel" vs "Elbit Systems")."""
    if _board_taken(result):
        return None
    row = {
        "name": result.name,
        "priority": priority,
        "discovered_via": discovered_via,
        "scan_tier": "hourly" if priority == "favorite" else "daily",
        **_found_fields(result),
    }
    return db.execute(db.client().table("companies").insert(row)).data[0]


def update_found(company: dict, result: FindResult) -> dict | None:
    """Re-check of an `unsupported` company: store what was found this time."""
    if _board_taken(result, exclude_id=company["id"]):
        return None
    fields = {k: v for k, v in _found_fields(result).items() if v is not None or k == "ats_token"}
    return db.execute(db.client().table("companies").update(fields).eq("id", company["id"])).data[0]


def create_pending(name: str) -> dict:
    """A company first seen in a job (LinkedIn/email). Discovery looks for its ATS later."""
    row = {"name": name.strip(), "discovered_via": "job", "ats_type": "pending", "ats_status": "unsupported"}
    return db.execute(db.client().table("companies").insert(row)).data[0]


def pending(companies: list[dict]) -> list[dict]:
    return [c for c in companies if c["ats_type"] == "pending"]


def board_owner(result: FindResult) -> dict | None:
    det = result.detection
    if not det:
        return None
    rows = db.execute(
        db.client().table("companies").select("*").eq("ats_type", det.ats).eq("ats_token", det.token).limit(1)
    ).data
    return rows[0] if rows else None


def merge_into(duplicate: dict, target: dict) -> None:
    """`duplicate` is the same company as `target` under another name (e.g. "Upwind Security" vs
    "Upwind"): move its jobs to `target`, merging jobs that already exist there, then delete it."""
    client = db.client()
    target_jobs = db.execute(client.table("jobs").select("id,title_normalized,location")
                             .eq("company_id", target["id"])).data
    by_key = {(j["title_normalized"], j["location"] or ""): j["id"] for j in target_jobs}
    for job in db.execute(client.table("jobs").select("id,title_normalized,location")
                          .eq("company_id", duplicate["id"])).data:
        same = by_key.get((job["title_normalized"], job["location"] or ""))
        if same:
            for src in db.execute(client.table("job_sources").select("*").eq("job_id", job["id"])).data:
                db.execute(client.table("job_sources").upsert(
                    {**src, "job_id": same}, on_conflict="job_id,source,source_url"))
            db.execute(client.table("jobs").delete().eq("id", job["id"]))
        else:
            db.execute(client.table("jobs").update({"company_id": target["id"]}).eq("id", job["id"]))
    db.execute(client.table("companies").delete().eq("id", duplicate["id"]))


def unresolved(companies: list[dict]) -> list[dict]:
    """Companies worth another look: no ATS found at all, or a Comeet UID saved without its
    slug/API token (older runs stored those as "company/<UID>", which Comeet doesn't serve)."""
    return [
        c for c in companies
        if (c["ats_status"] == "unsupported" and c["ats_type"] == "unknown")
        or (c["ats_type"] == "comeet" and (c["ats_token"] or "").startswith(("company/", "?/")))
    ]


def scannable(companies: list[dict]) -> list[dict]:
    return [c for c in companies
            if c["ats_status"] != "unsupported" and c["priority"] != "blocked"
            and c["ats_type"] in SUPPORTED and c["ats_token"]]


def update(company_id: int, fields: dict) -> None:
    db.execute(db.client().table("companies").update(fields).eq("id", company_id))
