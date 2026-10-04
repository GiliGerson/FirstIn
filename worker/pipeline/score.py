"""LLM scorer (FR2 stage 2) — Claude Sonnet 5.5 rates each job against my profile.

Sonnet rather than Haiku (the PRD's first choice): Haiku's Hebrew reasons had invented words and
mixed alphabets, and these reasons are what I read in every alert. ~$0.009 per job at low effort."""

from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from worker.models import RawJob

MODEL = "claude-sonnet-5-5"
EFFORT = "low"   # a short structured judgment — low effort keeps cost and latency down
# If a request is declined, the API re-runs it on a fallback model inside the same call
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Scoring needs the role and requirements, not the full benefits/EEO boilerplate.
MAX_DESCRIPTION_CHARS = 8000
FAVORITE_BONUS = 10


class JobScore(BaseModel):
    is_student_or_part_time: bool
    role_category: str = Field(description="One of the target roles, or a short name of another category")
    match_score: int = Field(description="0-100")
    reasons: list[str] = Field(description="2-3 short reasons why this fits (or doesn't), in the requested language")
    red_flags: list[str] = Field(description="Short red flags, e.g. 'requires 5 days a week'. Empty if none")
    requirements: list[str] = Field(description="Key requirements/skills in English, e.g. Python, SQL")
    location: Optional[str]
    hybrid: Optional[bool]
    days_per_week: Optional[int] = Field(description="Required days per week if stated, else null")


def build_system_prompt(settings: dict, profile: dict, language: str = "Hebrew") -> str:
    roles = "\n".join(f"  {i}. {r}" for i, r in enumerate(settings.get("roles") or [], 1))
    return f"""You screen job postings for one candidate and rate how well each fits her.

Candidate:
- Education: {profile.get("education", "")}, year {profile.get("year", "")}
- Looking for: {", ".join(settings.get("job_types") or [])} positions (she is a full-time student)
- Target roles, in priority order:
{roles}
  Open to: {profile.get("open_to", "other tech roles")}
- Locations: {", ".join(settings.get("locations") or [])}. Hybrid OK: {settings.get("accept_hybrid")}. \
Remote OK: {settings.get("accept_remote")}.
- Can work at most {settings.get("max_days_per_week")} days per week.
- Languages: {", ".join(profile.get("languages") or [])}

Scoring guide (match_score 0-100):
- 85-100: a student/intern/part-time tech role in her top target roles, in her area, feasible for a student.
- 70-84: a good student/part-time tech role, lower-priority category or a minor concern.
- 50-69: partially relevant (non-core role, e.g. IT support/NOC/QA, or unclear feasibility).
- 0-49: not a student/part-time role, not tech, requires experience she doesn't have, or outside her area.
If the job needs more than {settings.get("max_days_per_week")} days per week, add a red flag and lower the score.

Read carefully:
- "X days in office" in a hybrid full-time job is NOT X days of work per week. Only count days of \
work when the posting says the job itself is part-time / student / a number of days per week.
- A job that requires a completed degree or years of prior experience is not a student job, even if \
it says student or intern experience counts toward those years. Score it at most 40.
- Do not assume facts the posting doesn't state (days per week, student eligibility, location).

Judge only from the posting; when the description is missing, rate from title, company and location \
and say so in the reasons.

{_style(language)}
reasons = the 2-3 main points that decide the score (fit or mismatch); red_flags = concrete problems only."""


def _style(language: str) -> str:
    if language == "Hebrew":
        return ("Writing style for reasons and red_flags: short, simple, natural Hebrew (up to ~12 words each), "
                "about the candidate in third person (\"מתאים לה\", \"דורש\"). Keep technical terms and role "
                "names in English (NOC, VLSI, SQL, Product Analyst). Never mix in other alphabets or invented words.")
    return ("Writing style for reasons and red_flags: short, plain English (up to ~12 words each), "
            "about the candidate in third person (\"fits her goals\", \"requires\").")


def build_user_message(job: RawJob) -> str:
    description = (job.description or "")[:MAX_DESCRIPTION_CHARS] or "(no description available)"
    return (
        f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location or 'unknown'}\n"
        f"Employment type: {job.employment_type or 'unknown'}\nWorkplace: {job.workplace or 'unknown'}\n\n"
        f"Description:\n{description}"
    )


def score_job(client: anthropic.Anthropic, system_prompt: str, job: RawJob,
              favorite: bool = False, model: str = MODEL) -> JobScore | None:
    messages = [{"role": "user", "content": build_user_message(job)}]
    if model == MODEL:
        # Sonnet 5.5 (the owner): low effort + server-side fallback if a request is declined
        response = client.beta.messages.parse(
            model=MODEL, max_tokens=2048, system=system_prompt, messages=messages,
            output_format=JobScore, output_config={"effort": EFFORT},
            betas=[FALLBACK_BETA], fallbacks="default",
        )
    else:
        # Cheaper model for other users (Haiku 4.5 takes no effort / fallback parameters)
        response = client.messages.parse(
            model=model, max_tokens=1024, system=system_prompt, messages=messages, output_format=JobScore,
        )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return None
    result = response.parsed_output
    score = max(0, min(100, result.match_score))
    if favorite:
        score = min(100, score + FAVORITE_BONUS)  # FR8: favorite companies get a bonus
    result.match_score = score
    return result
