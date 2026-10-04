"""Rule filter (FR2 stage 1) — free and fast; runs before any LLM call.

A job passes when it is in Israel, in one of my cities (or remote/unspecified), looks like a
student / intern / part-time job, and isn't senior."""

import re
from dataclasses import dataclass

from worker.models import RawJob
from worker.pipeline.normalize import canonical_city, job_type, workplace_flags

# Always disqualifying, even for "student" titles
HARD_EXCLUDE = ["senior", "sr", "principal", "staff", "director", "head of", "vp", "team lead", "tech lead",
                "group lead", "lead", "architect", "בכיר", "בכירה", "ראש צוות", "מנהל צוות"]
# Disqualifying only when the title has no student/intern marker ("Product Manager (Student)" is fine)
SOFT_EXCLUDE = ["manager", "מנהל", "מנהלת"]
# Phrases in a description that make a job student/part-time even if the title doesn't say so.
# Not "student position": full-time postings say "experience ... as an intern, in a student position".
STRONG_DESCRIPTION_PHRASES = ["this is a student position", "this is a part-time position",
                              "part-time position", "part time position", "internship program", "משרה חלקית"]
YEARS_RE = re.compile(r"(\d+)\s*\+?\s*(?:years?|yrs)\s+(?:of\s+)?(?:[\w-]+\s+){0,3}experience", re.I)
MAX_YEARS = 2


def _word_re(words: list[str]) -> re.Pattern | None:
    words = [w for w in words if w]
    if not words:
        return None
    parts = [rf"\b{re.escape(w)}\b" if w[0].isascii() else re.escape(w) for w in words]
    return re.compile("|".join(parts), re.IGNORECASE)


@dataclass
class FilterResult:
    passed: bool
    reason: str            # why it failed, or "ok"
    job_type: str = "other"
    city: str | None = None


class RuleFilter:
    def __init__(self, settings: dict):
        self.include_re = _word_re(settings.get("include_keywords") or [])
        self.exclude_re = _word_re((settings.get("exclude_keywords") or []) + HARD_EXCLUDE)
        self.soft_re = _word_re(SOFT_EXCLUDE)
        self.strong_desc_re = _word_re(STRONG_DESCRIPTION_PHRASES)
        self.cities = {c.lower() for c in settings.get("locations") or []}
        self.accept_remote = settings.get("accept_remote", True)
        wanted = {t.replace("-", "_") for t in settings.get("job_types") or []}
        self.job_types = wanted or {"student", "part_time", "internship"}

    def check(self, job: RawJob) -> FilterResult:
        if not job.is_israel:
            return FilterResult(False, "not_israel")

        jtype = job_type(job.title, job.employment_type)
        is_student_title = jtype in ("student", "internship")
        marked = (
            (self.include_re and (self.include_re.search(job.title)
                                  or (job.employment_type and self.include_re.search(job.employment_type))))
            or jtype != "other"
            or (job.description and self.strong_desc_re.search(job.description[:4000]))
        )
        if not marked:
            return FilterResult(False, "not_student_or_part_time")
        if jtype == "other":
            jtype = "part_time" if "part" in (job.employment_type or "").lower() else "student"
        if jtype not in self.job_types:
            return FilterResult(False, "job_type_disabled", jtype)

        if self.exclude_re and self.exclude_re.search(job.title):
            return FilterResult(False, "excluded_keyword", jtype)
        if not is_student_title and self.soft_re and self.soft_re.search(job.title):
            return FilterResult(False, "manager_role", jtype)
        if not is_student_title and job.description:
            # Student postings often say "2+ years left in your degree" — only check non-student titles
            years = [int(m.group(1)) for m in YEARS_RE.finditer(job.description)]
            if years and min(years) > MAX_YEARS:
                return FilterResult(False, "requires_experience", jtype)

        city = canonical_city(job.location)
        _, remote = workplace_flags(job.workplace, job.location)
        if city and self.cities and city.lower() not in self.cities and not (remote and self.accept_remote):
            return FilterResult(False, "outside_my_area", jtype, city)
        return FilterResult(True, "ok", jtype, city)
