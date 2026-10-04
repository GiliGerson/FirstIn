"""Split a LinkedIn Job Alert email into individual jobs.

The plain-text part is the most stable format: each job is a block of lines
(title / company / location / optional extras) followed by a "View job: <url>" line.
The HTML part is used as a fallback."""

import re

from bs4 import BeautifulSoup

from worker.collectors.gmail import EmailMessage
from worker.models import RawJob
from worker.pipeline.locations import is_israel

JOB_ID_RE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?\s]*?-)?(\d{6,})")
VIEW_JOB_RE = re.compile(r"^\s*View job:\s*(\S+)", re.IGNORECASE)
SEPARATOR_RE = re.compile(r"^[-=_\s]{10,}$")

# Lines that are LinkedIn decorations, not job fields
NOISE_RE = re.compile(
    r"^(actively recruiting|easy apply|promoted|be an early applicant|apply with resume.*|"
    r"this company is actively hiring|\d+ (school |company )?alum(ni|s)?\b.*|\d+ connections?.*|"
    r"\d+ applicants?.*|(new|\d+ (minutes?|hours?|days?|weeks?) ago)|view job|see all jobs.*|"
    r"manage alerts.*|your job alert.*|new jobs.*|jobs? similar to.*|.*\bmatch(es)? your preferences.*|"
    r"top job picks.*|linkedin|\$.*|<[^>]+>.*)$",
    re.IGNORECASE,
)


def canonical_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def _is_noise(line: str) -> bool:
    return not line or bool(NOISE_RE.match(line))


def _job_from_lines(lines: list[str], job_id: str, url: str) -> RawJob | None:
    fields = [line for line in lines if not _is_noise(line)]
    if len(fields) < 2:
        return None
    title, company = fields[0], fields[1]
    location = fields[2] if len(fields) > 2 else None
    # Some alerts put "Company · Location" on one line
    if " · " in company and location is None:
        company, _, location = company.partition(" · ")
    return RawJob(
        source="linkedin", title=title.strip(), company=company.strip(),
        location=location.strip() if location else None,
        url=url, canonical_url=canonical_url(job_id), source_job_id=job_id,
    )


def _paragraphs(lines: list[str]) -> list[list[str]]:
    paras, current = [], []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paras.append(current)
            current = []
    if current:
        paras.append(current)
    return paras


def parse_text(text: str) -> list[RawJob]:
    """Each job block looks like:

        Title
        Company
        Location
        <blank>
        12 connections / This company is actively hiring / ...   (optional extras)
        View job: https://www.linkedin.com/comm/jobs/view/<id>/...
    """
    jobs, block = [], []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = VIEW_JOB_RE.match(line)
        if match:
            id_match = JOB_ID_RE.search(match.group(1))
            if id_match:
                # The job is the last paragraph that isn't only decorations; earlier
                # paragraphs are email headers ("Your job alert for ...").
                paras = [p for p in _paragraphs(block) if not all(_is_noise(x) for x in p)]
                if paras:
                    job = _job_from_lines(paras[-1][:3], id_match.group(1), match.group(1))
                    if job:
                        jobs.append(job)
            block = []
        elif SEPARATOR_RE.match(line):
            block = []
        else:
            block.append(line)
    return _dedupe(jobs)


def parse_html(html: str) -> list[RawJob]:
    soup = BeautifulSoup(html, "html.parser")
    anchors_by_id: dict[str, list] = {}
    for a in soup.find_all("a", href=True):
        m = JOB_ID_RE.search(a["href"])
        if m:
            anchors_by_id.setdefault(m.group(1), []).append(a)

    jobs = []
    for job_id, anchors in anchors_by_id.items():
        # Climb to the largest ancestor that still contains links to this job only
        container = anchors[0]
        while container.parent is not None:
            ids = {JOB_ID_RE.search(x["href"]).group(1)
                   for x in container.parent.find_all("a", href=True) if JOB_ID_RE.search(x["href"])}
            if ids != {job_id}:
                break
            container = container.parent
        lines = [s.strip() for s in container.stripped_strings]
        # Put the title (the longest link text) first
        title = max((a.get_text(" ", strip=True) for a in anchors), key=len, default="")
        if title:
            lines = [title] + [line for line in lines if line != title]
        job = _job_from_lines(lines, job_id, anchors[0]["href"])
        if job:
            jobs.append(job)
    return _dedupe(jobs)


def _dedupe(jobs: list[RawJob]) -> list[RawJob]:
    seen, out = set(), []
    for job in jobs:
        if job.source_job_id not in seen:
            seen.add(job.source_job_id)
            out.append(job)
    return out


ALERT_IN_ISRAEL_RE = re.compile(r"job alert for .+ in israel", re.IGNORECASE)


def parse_alert(email: EmailMessage) -> list[RawJob]:
    jobs = parse_text(email.text) if email.text else []
    if not jobs and email.html:
        jobs = parse_html(email.html)
    # "Your job alert for student in Israel" — every job in it is in Israel, even when the
    # location is a town we don't recognize ("Kfar Yona")
    alert_in_israel = bool(ALERT_IN_ISRAEL_RE.search(email.text[:500] or email.subject))
    for job in jobs:
        job.is_israel = alert_in_israel or is_israel(job.location)
    return jobs
