"""Re-score a user's open jobs (FR10 "דירוג מחדש") — after changing settings or the scoring prompt.

Usage:
    .venv/bin/python -m worker.rescore              # the owner's open jobs that have no score yet
    .venv/bin/python -m worker.rescore --all        # every open job of the owner
"""

import argparse
from concurrent.futures import ThreadPoolExecutor

import anthropic

from worker import db, settings as settings_mod, users
from worker.pipeline.personalize import job_to_raw
from worker.pipeline.score import build_system_prompt, score_job

WORKERS = 4
FIELDS = ("job_id,match_score,jobs!inner(id,title,description,location,is_hybrid,is_remote,job_type,url,"
          "canonical_url,status,companies(name,priority))")


def open_jobs(user: users.User, unscored_only: bool) -> list[dict]:
    query = (db.client().table("user_jobs").select(FIELDS).eq("user_id", user.user_id)
             .eq("jobs.status", "open"))
    if unscored_only:
        query = query.is_("match_score", "null")
    return db.execute(query.limit(5000)).data


def rescore(user: users.User, rows: list[dict]) -> int:
    settings = settings_mod.get_active(user)
    system_prompt = build_system_prompt(settings, user.profile_facts(), "Hebrew" if user.is_owner else "English")
    llm = anthropic.Anthropic()

    def run(row):
        job = row["jobs"]
        favorite = (job.get("companies") or {}).get("priority") == "favorite"
        try:
            return score_job(llm, system_prompt, job_to_raw(job), favorite=favorite, model=user.scoring_model)
        except anthropic.APIError:
            return None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        scores = list(pool.map(run, rows))
    done = 0
    for row, score in zip(rows, scores):
        if score is None:
            continue
        db.execute(db.client().table("user_jobs").update({
            "match_score": score.match_score, "match_reasons": score.reasons, "red_flags": score.red_flags,
            "requirements": score.requirements, "role_category": score.role_category, "scored_at": db.now_iso(),
        }).eq("user_id", user.user_id).eq("job_id", row["job_id"]))
        done += 1
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="re-score every open job, not only unscored ones")
    args = parser.parse_args()
    owner = users.owner()
    rows = open_jobs(owner, unscored_only=not args.all)
    print(f"מדרגת מחדש {len(rows)} משרות...")
    print(f"✅ עודכנו {rescore(owner, rows)} משרות")


if __name__ == "__main__":
    main()
