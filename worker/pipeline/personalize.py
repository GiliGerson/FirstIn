"""Per-user filtering and scoring: shared `jobs` → each user's `user_jobs`.

For every approved user: recent open jobs the user hasn't seen yet → the user's rule filter
(cities, job types, keywords) → Claude score with the user's model → `user_jobs`.
Non-owner users have a daily scoring quota; jobs beyond it wait for the next day."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic

from worker import db, settings as settings_mod, users
from worker.models import RawJob
from worker.pipeline.filter import RuleFilter
from worker.pipeline.score import build_system_prompt, score_job

TZ = ZoneInfo("Asia/Jerusalem")
LOOKBACK_DAYS = 14
WORKERS = 4
JOB_FIELDS = ("id,title,description,location,is_hybrid,is_remote,job_type,url,canonical_url,"
              "first_seen_at,companies(name,priority)")
# jobs.job_type → the employment-type words the rule filter recognizes
EMPLOYMENT_TYPE = {"student": "Student", "internship": "Internship", "part_time": "Part time"}


@dataclass
class PersonalizeReport:
    user_id: str
    considered: int = 0
    rejected: Counter = field(default_factory=Counter)
    scored: int = 0
    waiting_for_quota: int = 0
    failures: int = 0
    skipped: str | None = None          # why the user was skipped (no settings yet...)


def job_to_raw(row: dict) -> RawJob:
    workplace = "remote" if row.get("is_remote") else "hybrid" if row.get("is_hybrid") else None
    return RawJob(
        source="db", title=row["title"], company=(row.get("companies") or {}).get("name", ""),
        location=row.get("location"), description=row.get("description"), url=row.get("url"),
        canonical_url=row.get("canonical_url"), workplace=workplace,
        employment_type=EMPLOYMENT_TYPE.get(row.get("job_type") or ""), is_israel=True,
    )


def _seen_job_ids(user_id: str) -> set[int]:
    ids, start, page = set(), 0, 1000
    while True:
        batch = db.execute(db.client().table("user_jobs").select("job_id").eq("user_id", user_id)
                           .range(start, start + page - 1)).data
        ids.update(r["job_id"] for r in batch)
        if len(batch) < page:
            return ids
        start += page


def candidates(user_id: str, now: datetime) -> list[dict]:
    """Recent open jobs this user hasn't been given yet, newest first."""
    since = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows = db.execute(db.client().table("jobs").select(JOB_FIELDS).eq("status", "open")
                      .gte("first_seen_at", since).order("first_seen_at", desc=True).limit(2000)).data
    seen = _seen_job_ids(user_id)
    return [r for r in rows if r["id"] not in seen]


def scored_today(user_id: str, now: datetime) -> int:
    midnight = now.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return db.execute(db.client().table("user_jobs").select("job_id", count="exact")
                      .eq("user_id", user_id).gte("scored_at", midnight).limit(1)).count or 0


def personalize_user(user: users.User, llm: anthropic.Anthropic, now: datetime | None = None) -> PersonalizeReport:
    now = now or datetime.now(TZ)
    report = PersonalizeReport(user.user_id)
    settings = settings_mod.get_active(user)
    if settings is None:
        report.skipped = "no_settings"
        return report

    rule_filter = RuleFilter(settings)
    passed = []
    for row in candidates(user.user_id, now):
        report.considered += 1
        verdict = rule_filter.check(job_to_raw(row))
        if verdict.passed:
            passed.append(row)
        else:
            report.rejected[verdict.reason] += 1
    if user.daily_score_quota is not None:
        room = max(0, user.daily_score_quota - scored_today(user.user_id, now))
        report.waiting_for_quota = max(0, len(passed) - room)
        passed = passed[:room]
    if not passed:
        return report

    system_prompt = build_system_prompt(settings, user.profile_facts(), "Hebrew" if user.is_owner else "English")

    def run(row):
        favorite = (row.get("companies") or {}).get("priority") == "favorite"
        try:
            return score_job(llm, system_prompt, job_to_raw(row), favorite=favorite, model=user.scoring_model)
        except anthropic.APIError:
            return None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        scores = list(pool.map(run, passed))

    rows = []
    for row, score in zip(passed, scores):
        if score is None:
            report.failures += 1          # not stored → retried on the next run
            continue
        rows.append({
            "user_id": user.user_id, "job_id": row["id"], "match_score": score.match_score,
            "match_reasons": score.reasons, "red_flags": score.red_flags,
            "requirements": score.requirements, "role_category": score.role_category,
            "scored_at": now.isoformat(),
        })
    if rows:
        db.execute(db.client().table("user_jobs").upsert(rows, on_conflict="user_id,job_id", ignore_duplicates=True))
    report.scored = len(rows)
    return report


def run_all(llm: anthropic.Anthropic | None = None) -> list[PersonalizeReport]:
    llm = llm or anthropic.Anthropic()
    return [personalize_user(u, llm) for u in users.approved()]
