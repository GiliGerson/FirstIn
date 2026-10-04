"""Supabase client and small helpers shared by all collectors."""

import time
from datetime import datetime, timezone
from functools import lru_cache

import httpx
from supabase import Client, create_client

from worker.config import env


@lru_cache(maxsize=1)
def client() -> Client:
    return create_client(env("SUPABASE_URL"), env("SUPABASE_SECRET_KEY"))


def execute(query, attempts: int = 3, sleep=time.sleep):
    """Run a Supabase query, retrying dropped connections (idle keep-alive sockets get closed
    by the server during long collector runs)."""
    for attempt in range(attempts):
        try:
            return query.execute()
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
            sleep(1 + attempt)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_run(collector: str) -> int:
    row = execute(client().table("runs").insert({"collector": collector})).data[0]
    return row["id"]


def finish_run(run_id: int, items_found: int, errors: list) -> None:
    execute(client().table("runs").update(
        {"finished_at": now_iso(), "items_found": items_found, "errors": errors}
    ).eq("id", run_id))


def last_successful_run_start(collector: str) -> datetime | None:
    """Start time of the latest finished run with no errors (used for incremental fetching)."""
    rows = execute(
        client().table("runs").select("started_at")
        .eq("collector", collector).not_.is_("finished_at", "null").eq("errors", [])
        .order("started_at", desc=True).limit(1)
    ).data
    return datetime.fromisoformat(rows[0]["started_at"]) if rows else None
