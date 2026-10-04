"""Helpers shared by the ATS collectors."""

import html
from dataclasses import dataclass
from datetime import datetime, timezone

from bs4 import BeautifulSoup


class BoardNotFound(Exception):
    """The ATS has no board for this token (404) — the company may have moved ATS."""


@dataclass
class BoardProbe:
    """What we learn when checking whether a token is a real board."""
    ats: str
    token: str
    company_name: str | None
    job_count: int
    israel_jobs: int


def html_to_text(markup: str | None, escaped: bool = False) -> str:
    if not markup:
        return ""
    if escaped:  # Greenhouse returns HTML-escaped HTML
        markup = html.unescape(markup)
    return BeautifulSoup(markup, "html.parser").get_text("\n", strip=True)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def from_epoch_ms(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc) if value else None


def probe_from_jobs(ats: str, token: str, company_name: str | None, jobs: list) -> BoardProbe:
    return BoardProbe(ats, token, company_name, len(jobs), sum(1 for j in jobs if j.is_israel))
