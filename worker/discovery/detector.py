"""ATS Detector (PRD §6.1): careers-page URL → (ats, token).

First looks at the URL itself, then at the page HTML (links, iframes, embed scripts),
then follows the page's own "careers/jobs" links one level deep."""

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from worker.collectors.ats import SUPPORTED
from worker.collectors.http import get

TOKEN = r"([A-Za-z0-9][A-Za-z0-9_.-]*)"
COMEET_UID = r"([0-9A-F]{2}\.[0-9A-F]{3})"

# (ats, pattern) in priority order; group 1 is the token
PATTERNS = [
    ("greenhouse", re.compile(r"greenhouse\.io/v1/boards/" + TOKEN)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?(?:[^\"'\s]*&)?for=" + TOKEN)),
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/" + TOKEN)),
    ("lever", re.compile(r"api(?:\.eu)?\.lever\.co/v0/postings/" + TOKEN)),
    ("lever", re.compile(r"jobs(?:\.eu)?\.lever\.co/" + TOKEN)),
    ("ashby", re.compile(r"api\.ashbyhq\.com/posting-api/job-board/" + TOKEN)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/" + TOKEN)),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/" + TOKEN)),
    ("workday", re.compile(r"([a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[A-Za-z0-9_-]+)")),
]
COMEET_PAGE_RE = re.compile(r"comeet\.(?:com|co)/jobs/" + TOKEN + "/" + COMEET_UID)
COMEET_UID_RE = re.compile(r"company[-_]?uid[\"']?\s*[:=,]\s*[\"']" + COMEET_UID, re.IGNORECASE)
COMEET_API_RE = re.compile(r"comeet\.co/careers-api/[\d.]+/company/" + COMEET_UID)
COMEET_UID_CONST_RE = re.compile(r"COMPANY_UID\s*=\s*[\"']" + COMEET_UID)
# The widget / API token that careers pages embed next to the company UID
COMEET_TOKEN_RE = re.compile(r"(?:[\"']token[\"']\s*:|\bTOKEN\s*=|[?&]token=)\s*[\"']?([0-9A-F]{20,})")

# Path segments that look like tokens but aren't
RESERVED_TOKENS = {"embed", "js", "v1", "v0", "api", "jobs", "job_board", "boards", "careers", "static"}
CAREER_LINK_RE = re.compile(r"career|jobs|join|positions|open-roles|work-with-us|hiring|דרושים|משרות", re.I)


@dataclass
class Detection:
    ats: str          # greenhouse / lever / ashby / comeet / smartrecruiters / workday
    token: str

    @property
    def supported(self) -> bool:
        return self.ats in SUPPORTED and not self.needs_resolving

    @property
    def needs_resolving(self) -> bool:
        """A Comeet UID found without its slug or API token."""
        return self.ats == "comeet" and self.token.startswith("?/")


def detect_in_text(text: str) -> Detection | None:
    """Find an ATS reference in a URL or an HTML document."""
    match = COMEET_PAGE_RE.search(text)
    if match:
        return Detection("comeet", f"{match.group(1)}/{match.group(2)}")
    for ats, pattern in PATTERNS:
        for match in pattern.finditer(text):
            token = match.group(1).rstrip(".")
            if token.lower() not in RESERVED_TOKENS:
                return Detection(ats, token)
    match = COMEET_UID_RE.search(text) or COMEET_API_RE.search(text) or COMEET_UID_CONST_RE.search(text)
    if match:
        # Only the UID is known; finder.resolve_comeet turns it into "slug/UID" or "UID:TOKEN"
        api_token = COMEET_TOKEN_RE.search(text)
        uid = match.group(1)
        return Detection("comeet", f"{uid}:{api_token.group(1)}" if api_token else f"?/{uid}")
    return None


def _career_links(page: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(page, "html.parser")
    base_host = urlparse(base_url).netloc
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if urlparse(href).netloc.endswith(base_host) and (
            CAREER_LINK_RE.search(href) or CAREER_LINK_RE.search(a.get_text(" ", strip=True))
        ):
            links.append(href.split("#")[0])
    return list(dict.fromkeys(links))[:5]


def detect(client: httpx.Client, url: str, follow_links: bool = True) -> Detection | None:
    found = detect_in_text(url)
    if found:
        return found
    try:
        response = get(client, url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    found = detect_in_text(str(response.url)) or detect_in_text(response.text)
    if found or not follow_links:
        return found
    for link in _career_links(response.text, str(response.url)):
        if link.rstrip("/") != url.rstrip("/"):
            found = detect(client, link, follow_links=False)
            if found:
                return found
    return None
