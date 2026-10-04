"""Lever public postings API (global and EU instances)."""

import httpx

from worker.collectors.common import BoardNotFound, BoardProbe, from_epoch_ms, probe_from_jobs
from worker.collectors.http import get
from worker.models import RawJob
from worker.pipeline.locations import is_israel

ATS = "lever"
APIS = ["https://api.lever.co/v0/postings/{token}", "https://api.eu.lever.co/v0/postings/{token}"]


def parse_jobs(data: list, company: str) -> list[RawJob]:
    jobs = []
    for j in data:
        categories = j.get("categories") or {}
        all_locations = categories.get("allLocations") or []
        location = categories.get("location")
        jobs.append(RawJob(
            source=ATS,
            title=j["text"].strip(),
            company=company,
            location=location,
            url=j.get("hostedUrl"),
            canonical_url=j.get("hostedUrl"),
            description="\n\n".join(filter(None, [j.get("descriptionPlain"), j.get("additionalPlain")])),
            posted_at=from_epoch_ms(j.get("createdAt")),
            source_job_id=j["id"],
            country=j.get("country"),
            employment_type=categories.get("commitment"),
            workplace=j.get("workplaceType"),
            is_israel=is_israel(location, *all_locations, country=j.get("country")),
        ))
    return jobs


def fetch_jobs(client: httpx.Client, token: str, company: str) -> list[RawJob]:
    for api in APIS:
        response = get(client, api.format(token=token), params={"mode": "json"})
        if response.status_code == 404:
            continue
        response.raise_for_status()
        return parse_jobs(response.json(), company)
    raise BoardNotFound(f"lever/{token}")


def probe(client: httpx.Client, token: str) -> BoardProbe | None:
    try:
        jobs = fetch_jobs(client, token, token)
    except BoardNotFound:
        return None
    return probe_from_jobs(ATS, token, None, jobs)  # Lever doesn't expose the company name
