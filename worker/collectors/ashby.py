"""Ashby public job board API."""

import httpx

from worker.collectors.common import BoardNotFound, BoardProbe, parse_iso, probe_from_jobs
from worker.collectors.http import get
from worker.models import RawJob
from worker.pipeline.locations import is_israel

ATS = "ashby"
API = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def _country(address: dict | None) -> str | None:
    return ((address or {}).get("postalAddress") or {}).get("addressCountry")


def parse_jobs(data: dict, company: str) -> list[RawJob]:
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        secondary = j.get("secondaryLocations") or []
        places = [j.get("location")] + [s.get("location") for s in secondary]
        countries = [_country(j.get("address"))] + [_country(s.get("address")) for s in secondary]
        jobs.append(RawJob(
            source=ATS,
            title=j["title"].strip(),
            company=company,
            location=j.get("location"),
            url=j.get("jobUrl"),
            canonical_url=j.get("jobUrl"),
            description=j.get("descriptionPlain") or "",
            posted_at=parse_iso(j.get("publishedAt")),
            source_job_id=j["id"],
            country=_country(j.get("address")),
            employment_type=j.get("employmentType"),
            workplace=j.get("workplaceType"),
            is_israel=is_israel(*places, *countries),
        ))
    return jobs


def fetch_jobs(client: httpx.Client, token: str, company: str) -> list[RawJob]:
    response = get(client, API.format(token=token))
    if response.status_code == 404:
        raise BoardNotFound(f"ashby/{token}")
    response.raise_for_status()
    return parse_jobs(response.json(), company)


def probe(client: httpx.Client, token: str) -> BoardProbe | None:
    try:
        jobs = fetch_jobs(client, token, token)
    except BoardNotFound:
        return None
    return probe_from_jobs(ATS, token, None, jobs)
