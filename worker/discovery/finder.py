"""Company Auto-Discovery (PRD §6.1.1): company name → ATS board.

1. Free: guess tokens from the name and probe Greenhouse / Lever / Ashby.
   A guess only counts if the board has jobs in Israel (or its name matches) — this
   avoids attaching a same-named foreign company.
2. Paid (~$0.03–0.05): Claude Haiku with web search finds the job board / careers URL,
   then the ATS Detector reads it.
3. Otherwise the company is marked `unsupported` (LinkedIn/email only)."""

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

import anthropic
import httpx
from pydantic import BaseModel, Field

from worker.collectors import ashby, comeet, greenhouse, lever
from worker.collectors.common import BoardProbe
from worker.discovery.detector import Detection, detect

SEARCH_MODEL = "claude-haiku-4-5"
PROBERS = {"greenhouse": greenhouse.probe, "lever": lever.probe, "ashby": ashby.probe, "comeet": comeet.probe}

# Words dropped when turning a company name into ATS token guesses
NAME_NOISE = {
    "ltd", "inc", "llc", "corp", "corporation", "co", "company", "group", "israel", "il",
    "technologies", "technology", "tech", "software", "systems", "solutions", "labs", "the",
}


class SearchBudget:
    """Thread-safe cap on paid web searches per run."""

    def __init__(self, limit: int):
        self.remaining = limit
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True


@dataclass
class FindResult:
    name: str
    method: str                       # detector / probe / web_search / not_found / deferred (no search allowed)
    detection: Detection | None = None
    probe: BoardProbe | None = None
    website: str | None = None
    careers_url: str | None = None
    kind: str | None = None           # startup / enterprise


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def token_candidates(name: str, website: str | None = None) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in NAME_NOISE]
    if not words:
        return []
    joined, dashed = "".join(words), "-".join(words)
    candidates = [joined, dashed, words[0], joined + "inc", joined + "hq", joined + "io", joined + "careers"]
    if website:
        host = urlparse(website if "://" in website else "https://" + website).netloc.lower()
        host = host.removeprefix("www.")
        candidates += [host, host.split(".")[0]]
    return list(dict.fromkeys(c for c in candidates if len(c) >= 2))


def core_name(name: str) -> str:
    """Name without legal/generic words: "Wiz, Inc." → "wiz", "Cato Networks Ltd" → "catonetworks"."""
    return "".join(w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in NAME_NOISE)


def _names_match(company: str, board_name: str | None) -> bool:
    # Exact match on the core name only — substring matching attached "IAI - Israel Aerospace
    # Industries" to a UK board named "i.AI".
    return bool(board_name) and bool(core_name(company)) and core_name(company) == core_name(board_name)


def probe_guesses(client: httpx.Client, name: str, website: str | None = None) -> BoardProbe | None:
    """Try token guesses on the APIs that accept any token; return the best credible board."""
    tasks = [(ats, token) for token in token_candidates(name, website) for ats in ("greenhouse", "lever", "ashby")]

    def run(task):
        ats, token = task
        try:
            return PROBERS[ats](client, token)
        except httpx.HTTPError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        probes = [p for p in pool.map(run, tasks) if p is not None]
    # Credible = has Israel jobs, or is clearly this company's board and still in use.
    # An empty board usually means the company moved to another ATS.
    credible = [p for p in probes
                if p.israel_jobs > 0 or (p.job_count > 0 and _names_match(name, p.company_name))]
    return max(credible, key=lambda p: (p.israel_jobs, p.job_count), default=None)


class CareersSearch(BaseModel):
    website: Optional[str] = Field(description="Official company website, or null")
    job_board_url: Optional[str] = Field(
        description="URL of the company's job listings on an ATS (comeet.com/jobs/..., "
                    "boards.greenhouse.io/..., jobs.lever.co/..., jobs.ashbyhq.com/..., "
                    "smartrecruiters, myworkdayjobs), or null if none found")
    careers_url: Optional[str] = Field(description="Official careers page on the company site, or null")
    kind: Optional[Literal["startup", "enterprise"]] = Field(
        description="startup = young/private tech company; enterprise = large or public corporation")


SEARCH_PROMPT = """Find where the company "{name}" publishes its job openings{location_hint}.
Search the web. Prefer a job-board URL on an applicant-tracking system such as \
comeet.com/jobs, boards.greenhouse.io, job-boards.greenhouse.io, jobs.lever.co, jobs.ashbyhq.com, \
jobs.smartrecruiters.com or myworkdayjobs.com. Also give the official careers page and website. \
Only return URLs you actually saw in search results; use null when unsure."""


def web_search(llm: anthropic.Anthropic, name: str, location: str | None) -> CareersSearch | None:
    hint = f" (it has jobs in {location})" if location else " (an Israeli tech company or a company with an office in Israel)"
    response = llm.messages.parse(
        model=SEARCH_MODEL,
        max_tokens=2048,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        messages=[{"role": "user", "content": SEARCH_PROMPT.format(name=name, location_hint=hint)}],
        output_format=CareersSearch,
    )
    if response.stop_reason == "refusal":
        return None
    return response.parsed_output


def resolve_comeet(client: httpx.Client, detection: Detection, name: str,
                   website: str | None = None) -> Detection | None:
    """Make a Comeet detection scannable: prefer the hosted page ("slug/UID")."""
    already_usable = "/" in detection.token and not detection.needs_resolving  # "slug/UID"
    if detection.ats != "comeet" or already_usable:
        return detection
    if detection.needs_resolving:
        uid, api_token = detection.token[2:], None
    else:
        uid, api_token = detection.token.split(":", 1)
    token = comeet.resolve(client, uid, api_token, token_candidates(name, website))
    return Detection("comeet", token) if token else None


def find_company(client: httpx.Client, llm: anthropic.Anthropic | None, name: str,
                 location: str | None = None, careers_url: str | None = None,
                 budget: SearchBudget | None = None) -> FindResult:
    # A known careers URL (seed list / manual add) goes straight to the detector
    if careers_url:
        found = detect(client, careers_url)
        found = found and resolve_comeet(client, found, name)
        if found:
            return FindResult(name, "detector", found, careers_url=careers_url)

    probe = probe_guesses(client, name)
    if probe:
        return FindResult(name, "probe", Detection(probe.ats, probe.token), probe=probe)

    if llm is None or (budget is not None and not budget.take()):
        return FindResult(name, "deferred", careers_url=careers_url)

    search = web_search(llm, name, location)
    if search is None:
        return FindResult(name, "not_found", careers_url=careers_url)
    result = FindResult(name, "web_search", website=search.website,
                        careers_url=search.careers_url or careers_url, kind=search.kind)
    for url in filter(None, [search.job_board_url, search.careers_url]):
        found = detect(client, url)
        found = found and resolve_comeet(client, found, name, search.website)
        if found:
            result.detection = found
            return result
    # The website domain often is the ATS token (e.g. Ashby "monday.com")
    probe = probe_guesses(client, name, search.website) if search.website else None
    if probe:
        result.detection, result.probe = Detection(probe.ats, probe.token), probe
        return result
    result.method = "not_found"
    return result
