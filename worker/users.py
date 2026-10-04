"""Users (Supabase Auth + `profiles`). The owner runs the system; other users sign up in the
dashboard, are approved by the owner in Telegram, and then get their own scores and alerts."""

from dataclasses import dataclass, field

from worker import db
from worker.config import env, load_yaml

OWNER_MODEL = "claude-sonnet-5-5"


@dataclass
class User:
    user_id: str
    is_owner: bool = False
    status: str = "pending"
    telegram_chat_id: int | None = None
    gmail_enabled: bool = False
    scoring_model: str = "claude-haiku-4-5"
    daily_score_quota: int | None = 30
    display_name: str | None = None
    field_of_study: str | None = None
    education: str | None = None
    study_year: int | None = None
    languages: list[str] = field(default_factory=lambda: ["Hebrew", "English"])
    open_to: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> "User":
        values = {k: row[k] for k in cls.__dataclass_fields__ if k in row}
        # NULL means "no limit" for daily_score_quota, so None is kept; only languages needs a default
        if values.get("languages") is None:
            values.pop("languages", None)
        return cls(**values)

    @property
    def chat_id(self) -> str | None:
        """Where this user's Telegram messages go. The owner falls back to TELEGRAM_CHAT_ID."""
        if self.telegram_chat_id:
            return str(self.telegram_chat_id)
        return env("TELEGRAM_CHAT_ID") if self.is_owner else None

    def profile_facts(self) -> dict:
        """Education/year/languages for the scoring prompt. The owner's come from config/profile.yaml."""
        if self.is_owner:
            try:
                return load_yaml("profile")
            except FileNotFoundError:
                pass
        education = self.education or (f"{self.field_of_study} student" if self.field_of_study else "")
        return {"education": education, "year": self.study_year or "", "languages": self.languages,
                "open_to": self.open_to or "other tech roles"}


def _rows(query) -> list[dict]:
    return db.execute(query).data


def approved() -> list[User]:
    return [User.from_row(r) for r in _rows(
        db.client().table("profiles").select("*").eq("status", "approved").order("created_at"))]


def owner() -> User:
    rows = _rows(db.client().table("profiles").select("*").eq("is_owner", True).limit(1))
    if not rows:
        raise RuntimeError("No owner profile — run db/migrations/002_multi_user.sql")
    return User.from_row(rows[0])


def by_chat_id(chat_id: int | str) -> User | None:
    rows = _rows(db.client().table("profiles").select("*").eq("telegram_chat_id", int(chat_id)).limit(1))
    if rows:
        return User.from_row(rows[0])
    me = owner()
    return me if str(chat_id) == env("TELEGRAM_CHAT_ID") else None


def get(user_id: str) -> User | None:
    rows = _rows(db.client().table("profiles").select("*").eq("user_id", user_id).limit(1))
    return User.from_row(rows[0]) if rows else None


def update(user_id: str, fields: dict) -> None:
    db.execute(db.client().table("profiles").update(fields).eq("user_id", user_id))
