"""Search settings (FR10), one active preset per user in `search_settings`.

The owner's preset is seeded from config/*.yaml on first use; other users create theirs in the
dashboard's onboarding. `base()` is the user-independent filter used when collecting jobs."""

from worker import db
from worker.config import load_yaml

SETTINGS_COLUMNS = (
    "roles", "include_keywords", "exclude_keywords", "job_types", "locations",
    "accept_hybrid", "accept_remote", "max_days_per_week", "instant_threshold",
    "digest_threshold", "sources", "linkedin_queries", "quiet_hours",
)

DEFAULT_INCLUDE = ["student", "סטודנט", "סטודנטית", "intern", "internship", "part-time", "part time",
                   "חלקית", "משרה חלקית"]
DEFAULT_QUIET_HOURS = {"start": "23:00", "end": "08:00", "override_score": 90}


def seed_from_yaml() -> dict:
    profile = load_yaml("profile")
    settings = load_yaml("settings")
    notif = settings.get("notifications", {})
    rules = settings.get("rule_filter", {})
    return {
        "preset_name": "default",
        "is_active": True,
        "roles": profile.get("target_roles", []),
        "include_keywords": rules.get("include_keywords", DEFAULT_INCLUDE),
        "exclude_keywords": rules.get("exclude_keywords", []),
        "job_types": profile.get("job_types", []),
        "locations": profile.get("locations", []),
        "accept_hybrid": profile.get("accept_hybrid", True),
        "accept_remote": profile.get("accept_remote", True),
        "max_days_per_week": profile.get("max_days_per_week", 3),
        "instant_threshold": notif.get("instant_threshold", 75),
        "digest_threshold": notif.get("digest_threshold", 50),
        "sources": settings.get("sources", {}),
        "linkedin_queries": settings.get("linkedin", {}).get("public_scrape", {}).get("queries", []),
        "quiet_hours": notif.get("quiet_hours", DEFAULT_QUIET_HOURS),
    }


def get_active(user=None) -> dict | None:
    """The user's active preset (the owner's by default). The owner's is created from the YAML seed
    if missing; other users without a preset (onboarding not finished) get None."""
    from worker import users  # local import: users → config only, avoids a cycle at import time

    user = user or users.owner()
    rows = db.execute(db.client().table("search_settings").select("*")
                      .eq("user_id", user.user_id).eq("is_active", True).limit(1)).data
    if rows:
        return rows[0]
    if not user.is_owner:
        return None
    row = {**seed_from_yaml(), "user_id": user.user_id}
    return db.execute(db.client().table("search_settings").insert(row)).data[0]


def base() -> dict:
    """User-independent filter for collecting jobs: Israel, student/intern/part-time, not senior.
    Cities, job types and personal keywords are applied per user afterwards."""
    return {"include_keywords": DEFAULT_INCLUDE, "exclude_keywords": [],
            "job_types": ["student", "part_time", "internship"], "locations": [], "accept_remote": True}


def profile() -> dict:
    """The owner's static profile facts (kept for backwards compatibility)."""
    return load_yaml("profile")
