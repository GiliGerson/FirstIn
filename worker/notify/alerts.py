"""FR3 — instant alerts and the daily digest, per user.

A job is sent to a user once: `user_jobs.notified_at` is set when it goes out, either as an
instant alert (score ≥ instant_threshold) or inside a digest (digest ≤ score < instant)."""

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from worker import db, settings as settings_mod, users
from worker.notify import format as fmt
from worker.notify import telegram

TZ = ZoneInfo("Asia/Jerusalem")
USER_JOB_FIELDS = (
    "job_id,match_score,match_reasons,red_flags,role_category,user_state,notified_at,"
    "jobs!inner(id,title,url,canonical_url,location,is_hybrid,is_remote,job_type,status,first_seen_at,"
    "companies(name),job_sources(source))"
)
DIGEST_DETAILED = 15   # jobs shown in full in the digest; the rest as short lines


@dataclass
class SendResult:
    sent: int = 0
    held_quiet: int = 0
    paused: bool = False
    no_chat: bool = False


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def in_quiet_hours(now: datetime, quiet: dict | None) -> bool:
    if not quiet or not quiet.get("start") or not quiet.get("end"):
        return False
    start, end, t = _parse_hhmm(quiet["start"]), _parse_hhmm(quiet["end"]), now.astimezone(TZ).time()
    if start > end:                     # crosses midnight, e.g. 23:00–08:00
        return t >= start or t < end
    return start <= t < end


def is_paused(settings: dict, now: datetime) -> bool:
    paused_until = settings.get("paused_until")
    return bool(paused_until) and datetime.fromisoformat(paused_until) > now


def flatten(row: dict) -> dict:
    """user_jobs row + its job → one dict shaped like the old `jobs` rows the formatter expects."""
    job = row["jobs"]
    return {**job, "id": row["job_id"], "match_score": row["match_score"],
            "match_reasons": row["match_reasons"], "red_flags": row["red_flags"],
            "role_category": row["role_category"], "user_state": row["user_state"]}


def _user_jobs(user_id: str):
    return (db.client().table("user_jobs").select(USER_JOB_FIELDS)
            .eq("user_id", user_id).eq("jobs.status", "open"))


def _mark_notified(user_id: str, job_ids: list[int]) -> None:
    if job_ids:
        db.execute(db.client().table("user_jobs").update({"notified_at": db.now_iso()})
                   .eq("user_id", user_id).in_("job_id", job_ids))


def pending_instant(user_id: str, threshold: int) -> list[dict]:
    rows = db.execute(_user_jobs(user_id).eq("user_state", "new").is_("notified_at", "null")
                      .gte("match_score", threshold).order("match_score", desc=True).limit(50)).data
    return [flatten(r) for r in rows]


def send_instant(user: users.User | None = None, now: datetime | None = None) -> SendResult:
    now = now or datetime.now(TZ)
    user = user or users.owner()
    result = SendResult()
    settings = settings_mod.get_active(user)
    if settings is None:
        return result
    if not user.chat_id:
        result.no_chat = True
        return result
    if is_paused(settings, now):
        result.paused = True
        return result
    quiet = settings.get("quiet_hours") or {}
    override = quiet.get("override_score", 90)
    quiet_now = in_quiet_hours(now, quiet)
    for job in pending_instant(user.user_id, settings["instant_threshold"]):
        if quiet_now and job["match_score"] < override:
            result.held_quiet += 1      # goes out on the first run after quiet hours
            continue
        telegram.send(fmt.job_alert(job), fmt.job_buttons(job), chat_id=user.chat_id)
        _mark_notified(user.user_id, [job["id"]])   # one by one — a failure mid-way never re-sends
        result.sent += 1
    return result


def send_digest(user: users.User | None = None, now: datetime | None = None) -> int:
    """Daily digest (20:00): mid-score jobs not sent yet. Returns the number of jobs included."""
    now = now or datetime.now(TZ)
    user = user or users.owner()
    settings = settings_mod.get_active(user)
    if settings is None or not user.chat_id or is_paused(settings, now):
        return 0
    jobs = [flatten(r) for r in db.execute(
        _user_jobs(user.user_id).eq("user_state", "new").is_("notified_at", "null")
        .gte("match_score", settings["digest_threshold"]).lt("match_score", settings["instant_threshold"])
        .order("match_score", desc=True).limit(200)
    ).data]
    if not jobs:
        telegram.send("🌙 <b>סיכום יומי</b>\nאין היום משרות חדשות בציון בינוני.", silent=True, chat_id=user.chat_id)
        return 0
    header = (f"🌙 <b>סיכום יומי · {now:%d/%m}</b>\n{len(jobs)} משרות בציון "
              f"{settings['digest_threshold']}–{settings['instant_threshold'] - 1}:")
    blocks = [fmt.digest_line(j) for j in jobs[:DIGEST_DETAILED]]
    rest = jobs[DIGEST_DETAILED:]
    if rest:
        blocks.append("<b>עוד משרות:</b>\n" + "\n".join(
            f"• {j['match_score']} · {telegram.esc(j['title'])} — {telegram.esc((j.get('companies') or {}).get('name', ''))}"
            for j in rest))
    for message in telegram.split_message(blocks, header):
        telegram.send(message, silent=True, chat_id=user.chat_id)
    _mark_notified(user.user_id, [j["id"] for j in jobs])
    return len(jobs)


def today_summary(user: users.User | None = None, now: datetime | None = None, top: int = 10) -> list[str]:
    """On-demand "what happened today so far" (Telegram: "סיכום"). Read-only — it doesn't mark
    anything as notified, so the 20:00 digest is unaffected."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    user = user or users.owner()
    since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    settings = settings_mod.get_active(user) or settings_mod.base() | {"instant_threshold": 75, "digest_threshold": 50}
    client = db.client()
    jobs = [flatten(r) for r in db.execute(
        _user_jobs(user.user_id).gte("created_at", since).order("match_score", desc=True).limit(500)).data]
    emails = db.execute(
        client.table("emails").select("from_addr,subject,category,summary").eq("user_id", user.user_id)
        .gte("received_at", since).in_("category", ["recruiter_outreach", "application_update"])
        .order("received_at")
    ).data
    applied = db.execute(client.table("applications").select("id").eq("user_id", user.user_id)
                         .gte("applied_at", since)).data

    high = [j for j in jobs if (j["match_score"] or 0) >= settings["instant_threshold"]]
    mid = [j for j in jobs if settings["digest_threshold"] <= (j["match_score"] or 0) < settings["instant_threshold"]]
    header = (f"📊 <b>סיכום עד כה · {now:%d/%m %H:%M}</b>\n"
              f"🆕 משרות חדשות היום: <b>{len(jobs)}</b> ({len(high)} בהתאמה גבוהה, {len(mid)} בינונית)\n"
              f"✅ הגשות היום: <b>{len(applied)}</b>\n"
              f"📬 עדכונים במייל: <b>{len(emails)}</b>")
    blocks = []
    relevant = [j for j in jobs if (j["match_score"] or 0) >= settings["digest_threshold"]]
    if relevant:
        blocks.append("<b>המשרות הכי מתאימות מהיום:</b>\n\n" + "\n\n".join(fmt.digest_line(j) for j in relevant[:top]))
        if len(relevant) > top:
            blocks.append(f"ועוד {len(relevant) - top} משרות — בדשבורד.")
    elif jobs:
        blocks.append("היום נמצאו רק משרות בציון נמוך.")
    else:
        blocks.append("עוד לא נמצאו היום משרות חדשות.")
    for e in emails:
        icon = "📩" if e["category"] == "recruiter_outreach" else "📬"
        blocks.append(f"{icon} {telegram.esc(e['subject'])}\n    <i>{telegram.esc(e['summary'] or '')}</i>")
    return telegram.split_message(blocks, header)


def pipeline_note(link) -> str | None:
    """One line for the alert about what happened to the application card (step 8)."""
    if link is None:
        return "לא מצאתי הגשה מתאימה במעקב — אפשר לעדכן ידנית בדשבורד."
    stage = fmt.STAGE_HE_APP.get(link.to_stage, link.to_stage)
    if link.created:
        return f"פתחתי כרטיס חדש במעקב ההגשות (שלב: {stage})."
    if link.moved:
        return f"הכרטיס במעקב ההגשות עבר ל: {stage}."
    return "המייל קושר להגשה במעקב."


def send_email_alert(category: str, from_name: str, subject: str, summary: str, stage: str = "none",
                     pipeline_note: str | None = None) -> None:
    """FR4: recruiter outreach and application updates always alert immediately (owner's Gmail)."""
    text = fmt.email_alert(category, from_name, subject, summary, stage)
    if pipeline_note:
        text += f"\n\n🗂 {telegram.esc(pipeline_note)}"
    telegram.send(text)
