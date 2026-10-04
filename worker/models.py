"""Shared data model: every collector emits RawJob objects; the pipeline (stage 1, step 3)
normalizes, de-duplicates, filters and scores them."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RawJob:
    source: str                       # job_source enum value: linkedin / greenhouse / gmail / ...
    title: str
    company: str
    location: Optional[str] = None
    url: Optional[str] = None
    canonical_url: Optional[str] = None
    description: Optional[str] = None
    posted_at: Optional[datetime] = None
    source_job_id: Optional[str] = None
    country: Optional[str] = None     # ISO code when the source provides it (e.g. "IL")
    employment_type: Optional[str] = None   # raw ATS value: "Intern", "Part time", "FullTime"...
    workplace: Optional[str] = None   # raw ATS value: "remote" / "hybrid" / "on-site"
    is_israel: bool = False
