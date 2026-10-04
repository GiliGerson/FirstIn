"""Greenhouse public job board API."""

import httpx

from worker.collectors.common import BoardNotFound, BoardProbe, html_to_text, parse_iso, probe_from_jobs
from worker.collectors.http import get
from worker.models import RawJob
from worker.pipeline.locations import is_israel

ATS = "greenhouse"
API = "https://boards-api.greenhouse.io/v1/boards/{token}"


def parse_jobs(data: dict, company: str) -> list[RawJob]:
    jobs = []
    for j in data.get("jobs", []):
        location = (j.get("location") or {}).get("name")
        offices = [o.get("name") for o in j.get("offices", []) if o.get("name")]
        jobs.append(RawJob(
            source=ATS,
            title=j["title"].strip(),
            company=company or j.get("company_name", ""),
            location=location,
            url=j.get("absolute_url"),
            canonical_url=j.get("absolute_url"),
            description=html_to_text(j.get("content"), escaped=True),
            posted_at=parse_iso(j.get("first_published") or j.get("updated_at")),
            source_job_id=str(j["id"]),
            is_israel=is_israel(location, *offices),
        ))
    return jobs


def fetch_jobs(client: httpx.Client, token: str, company: str, content: bool = True) -> list[RawJob]:
    params = {"content": "true"} if content else {}
    response = get(client, API.format(token=token) + "/jobs", params=params)
    if response.status_code == 404:
        raise BoardNotFound(f"greenhouse/{token}")
    response.raise_for_status()
    return parse_jobs(response.json(), company)


def probe(client: httpx.Client, token: str) -> BoardProbe | None:
    board = get(client, API.format(token=token))
    if board.status_code != 200:
        return None
    name = board.json().get("name")
    # Descriptions aren't needed to count Israel jobs — skip them to keep probing fast
    return probe_from_jobs(ATS, token, name, fetch_jobs(client, token, name or token, content=False))
