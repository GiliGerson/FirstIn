"""Comeet — very common among Israeli startups. Two token formats:

- "<slug>/<UID>" (e.g. "checkmarx/C0.008"): the hosted careers page
  https://www.comeet.com/jobs/<slug>/<UID> embeds its data as JavaScript
  (COMPANY_DATA = {...}; COMPANY_POSITIONS_DATA = [...]). The slug must be right —
  a wrong slug returns a page without data.
- "<UID>:<API_TOKEN>": Comeet's official careers API, used when a company's own careers
  page embeds the Comeet widget/API token."""

import json
import re

import httpx

from worker.collectors.common import BoardNotFound, BoardProbe, html_to_text, parse_iso, probe_from_jobs
from worker.collectors.http import get
from worker.models import RawJob
from worker.pipeline.locations import is_israel

ATS = "comeet"
PAGE = "https://www.comeet.com/jobs/{token}"
API = "https://www.comeet.co/careers-api/2.0/company/{uid}/positions"
UID_RE = re.compile(r"^[0-9A-F]{2}\.[0-9A-F]{3}$")
HOSTED_URL_RE = re.compile(r"comeet\.com/jobs/([^/]+)/([0-9A-F]{2}\.[0-9A-F]{3})")


def extract_js_value(page: str, name: str):
    """Return the JSON value assigned to `name = ...` in the page, or None."""
    match = re.search(rf"\b{name}\s*=\s*", page)
    if not match:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(page, match.end())
    except json.JSONDecodeError:
        return None
    return value


def _description(position: dict) -> str:
    # Hosted page: custom_fields.details; careers API: details
    details = (position.get("custom_fields") or {}).get("details") or position.get("details") or []
    return "\n\n".join(
        f"{d.get('name', '')}\n{html_to_text(d.get('value'))}".strip() for d in details if d.get("value")
    )


def parse_page(page: str, company: str | None = None) -> tuple[str | None, list[RawJob]]:
    """Return (company name, jobs) from a Comeet careers page."""
    company_data = extract_js_value(page, "COMPANY_DATA") or {}
    positions = extract_js_value(page, "COMPANY_POSITIONS_DATA")
    if positions is None:
        raise BoardNotFound("comeet page has no COMPANY_POSITIONS_DATA")
    name = company_data.get("name")
    return name, parse_positions(positions, company or name)


def parse_positions(positions: list, company: str | None) -> list[RawJob]:
    jobs = []
    for p in positions:
        if p.get("is_internal"):
            continue
        loc = p.get("location") or {}
        url = p.get("url_active_page") or p.get("url_comeet_hosted_page")
        jobs.append(RawJob(
            source=ATS,
            title=p["name"].strip(),
            company=company or p.get("company_name") or "",
            location=loc.get("name"),
            url=url,
            canonical_url=p.get("url_comeet_hosted_page") or url,
            description=_description(p),
            posted_at=parse_iso(p.get("time_updated")),
            source_job_id=p.get("uid"),
            country=loc.get("country"),
            employment_type=p.get("employment_type"),
            workplace=p.get("workplace_type"),
            is_israel=is_israel(loc.get("name"), loc.get("city"), country=loc.get("country")),
        ))
    return jobs


def _fetch_api(client: httpx.Client, uid: str, api_token: str) -> list[dict]:
    response = get(client, API.format(uid=uid), params={"token": api_token, "details": "true"})
    if response.status_code in (401, 403, 404):
        raise BoardNotFound(f"comeet api {uid}")
    response.raise_for_status()
    return response.json()


def _fetch(client: httpx.Client, token: str) -> tuple[str | None, list[RawJob]]:
    if ":" in token:
        uid, api_token = token.split(":", 1)
        positions = _fetch_api(client, uid, api_token)
        name = next((p.get("company_name") for p in positions if p.get("company_name")), None)
        return name, parse_positions(positions, None)
    response = get(client, PAGE.format(token=token))
    if response.status_code == 404:
        raise BoardNotFound(f"comeet/{token}")
    response.raise_for_status()
    return parse_page(response.text)  # a wrong slug redirects to a page without data


def fetch_jobs(client: httpx.Client, token: str, company: str) -> list[RawJob]:
    jobs = _fetch(client, token)[1]
    for job in jobs:
        job.company = company
    return jobs


def probe(client: httpx.Client, token: str) -> BoardProbe | None:
    try:
        name, jobs = _fetch(client, token)
    except (BoardNotFound, httpx.HTTPError):
        return None
    return probe_from_jobs(ATS, token, name, jobs)


def resolve(client: httpx.Client, uid: str, api_token: str | None, slug_guesses: list[str]) -> str | None:
    """Turn a bare company UID (found in a careers-page widget) into a working token.

    With an API token, read the slug from any position's hosted-page URL (falling back to the
    API form when there are no positions). Otherwise try slugs guessed from the company name."""
    if api_token:
        try:
            positions = _fetch_api(client, uid, api_token)
        except (BoardNotFound, httpx.HTTPError):
            positions = None
        if positions is not None:
            for p in positions:
                m = HOSTED_URL_RE.search(p.get("url_comeet_hosted_page") or "")
                if m and m.group(2) == uid:
                    return f"{m.group(1)}/{uid}"
            return f"{uid}:{api_token}"
    for slug in slug_guesses:
        if probe(client, f"{slug}/{uid}"):
            return f"{slug}/{uid}"
    return None
