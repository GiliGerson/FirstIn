"""Telegram bot: button presses on alerts, commands, account linking and user approvals.

* Every chat is mapped to a user via profiles.telegram_chat_id (the owner also via TELEGRAM_CHAT_ID).
* New users connect from the dashboard with a one-time deep link: /start <code>.
* The owner approves new users with buttons on an approval request.
Messages to the owner are in Hebrew; messages to other users are in English."""

import os

from worker import db, settings as settings_mod, users
from worker.notify import alerts
from worker.notify import format as fmt
from worker.notify import telegram

SUMMARY_WORDS = ("סיכום", "/summary", "/today", "מה היה היום", "summary")
HELP_TEXT = ("👋 <b>FirstIn פעיל</b>\n"
             "• משרות מתאימות מגיעות לכאן מיד, וסיכום יומי ב-20:00.\n"
             "• כתבי <b>סיכום</b> (או /summary) — סיכום של היום עד עכשיו.\n"
             "• הכפתורים מתחת לכל משרה: הגשתי / שמור / לא רלוונטי.")
HELP_TEXT_EN = ("👋 <b>FirstIn is on</b>\n"
                "• Matching jobs arrive here right away, plus a daily digest at 20:00.\n"
                "• Send /summary for today's summary so far.\n"
                "• Use the buttons under each job: applied / save / not relevant.")


def dashboard_url() -> str:
    return os.environ.get("DASHBOARD_URL", "").rstrip("/")


def is_summary_request(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in SUMMARY_WORDS)


# ------------------------------------------------------------------ job buttons (per user)
def _user_job(user_id: str, job_id: int) -> dict | None:
    rows = db.execute(db.client().table("user_jobs").select("job_id,user_state,jobs(url,canonical_url,title)")
                      .eq("user_id", user_id).eq("job_id", job_id).limit(1)).data
    if not rows:
        return None
    job = rows[0]["jobs"] or {}
    return {"id": job_id, "url": job.get("url"), "canonical_url": job.get("canonical_url"), "title": job.get("title")}


def _set_state(user_id: str, job_id: int, fields: dict) -> None:
    db.execute(db.client().table("user_jobs").update(fields).eq("user_id", user_id).eq("job_id", job_id))


def _done_buttons(job: dict, label: str) -> list[list[dict]]:
    rows = [[{"text": label, "callback_data": "noop"}]]
    if fmt.job_link(job):
        rows.insert(0, [{"text": "🔗 פתח משרה", "url": fmt.job_link(job)}])
    return rows


def mark_applied(user_id: str, job: dict) -> None:
    client = db.client()
    _set_state(user_id, job["id"], {"user_state": "applied"})
    existing = db.execute(client.table("applications").select("id").eq("user_id", user_id)
                          .eq("job_id", job["id"]).limit(1)).data
    if not existing:
        app = db.execute(client.table("applications").insert(
            {"job_id": job["id"], "stage": "applied", "user_id": user_id})).data[0]
        db.execute(client.table("events").insert(
            {"application_id": app["id"], "type": "applied", "payload": {"via": "telegram"}}))


def handle_job_callback(user: users.User, query: dict) -> str:
    """Apply one alert-button press for this user; returns the toast text."""
    data = query.get("data", "")
    message = query.get("message") or {}
    kind, _, rest = data.partition(":")
    job_id_text, _, reason = rest.partition(":")
    if not job_id_text.isdigit():
        return "?"
    job = _user_job(user.user_id, int(job_id_text))
    if job is None:
        return "המשרה לא נמצאה"
    chat, msg_id = message.get("chat", {}).get("id"), message.get("message_id")

    if kind == "a":
        mark_applied(user.user_id, job)
        toast, buttons = "סומן כהוגש ✅", _done_buttons(job, "✅ הגשתי")
    elif kind == "s":
        _set_state(user.user_id, job["id"], {"user_state": "saved"})
        toast, buttons = "נשמר ⭐", _done_buttons(job, "⭐ נשמר")
    elif kind == "n":
        toast, buttons = "למה לא רלוונטי?", fmt.reason_buttons(job["id"])
    elif kind == "r" and reason in fmt.NOT_RELEVANT_REASONS:
        label = fmt.NOT_RELEVANT_REASONS[reason]
        _set_state(user.user_id, job["id"], {"user_state": "not_relevant", "not_relevant_reason": label})
        toast, buttons = "תודה, נלמד מזה 👍", _done_buttons(job, f"👎 לא רלוונטי · {label}")
    else:
        return "?"
    if chat and msg_id:
        telegram.edit_buttons(chat, msg_id, buttons)
    return toast


# ------------------------------------------------------------------ approvals (owner only)
def _email_of(user_id: str) -> str:
    try:
        return db.client().auth.admin.get_user_by_id(user_id).user.email or ""
    except Exception:
        return ""


def request_approvals() -> int:
    """Send the owner an approval request for every user who finished onboarding. Returns how many."""
    rows = db.execute(db.client().table("profiles").select("*").eq("status", "pending")
                      .eq("onboarding_done", True).is_("approval_requested_at", "null")).data
    for row in rows:
        user = users.User.from_row(row)
        prefs = settings_mod.get_active(user) or {}
        lines = [
            "🙋 <b>משתמש/ת חדש/ה מבקש/ת גישה ל-FirstIn</b>",
            f"שם: {telegram.esc(user.display_name or '—')}",
            f"מייל: {telegram.esc(_email_of(user.user_id) or '—')}",
            f"לימודים: {telegram.esc(user.field_of_study or '—')}" + (f", שנה {user.study_year}" if user.study_year else ""),
            f"תפקידים: {telegram.esc(', '.join(prefs.get('roles') or []) or '—')}",
            f"ערים: {telegram.esc(', '.join(prefs.get('locations') or []) or '—')}",
            f"טלגרם מחובר: {'כן' if user.telegram_chat_id else 'עוד לא'}",
            "",
            f"דירוג: {user.scoring_model}, עד {user.daily_score_quota} משרות ביום.",
        ]
        telegram.send("\n".join(lines), [[
            {"text": "✅ לאשר", "callback_data": f"u:ok:{user.user_id}"},
            {"text": "⛔ לדחות", "callback_data": f"u:no:{user.user_id}"},
        ]])
        users.update(user.user_id, {"approval_requested_at": db.now_iso()})
    return len(rows)


def handle_approval(owner: users.User, query: dict) -> str:
    _, action, user_id = query.get("data", "").split(":", 2)
    target = users.get(user_id)
    if target is None:
        return "המשתמש לא נמצא"
    message = query.get("message") or {}
    approve = action == "ok"
    users.update(user_id, {"status": "approved" if approve else "blocked"})
    if message.get("message_id"):
        telegram.edit_buttons(message["chat"]["id"], message["message_id"],
                              [[{"text": "✅ אושר/ה" if approve else "⛔ נדחה/תה", "callback_data": "noop"}]])
    if target.telegram_chat_id:
        if approve:
            telegram.send("🎉 <b>You're in!</b> Your FirstIn account was approved. Your first matching "
                          "jobs will arrive here within the hour.", chat_id=target.telegram_chat_id)
        else:
            telegram.send("Thanks for your interest in FirstIn. Access isn't available for your account "
                          "right now.", chat_id=target.telegram_chat_id)
    return "אושר ✅" if approve else "נדחה"


# ------------------------------------------------------------------ account linking
def link_account(chat_id: int, code: str) -> str:
    rows = db.execute(db.client().table("profiles").select("*").eq("telegram_link_code", code)
                      .gte("telegram_link_expires", db.now_iso()).limit(1)).data
    if not rows:
        return ("This link has expired. Open your FirstIn dashboard and press "
                "<b>Connect Telegram</b> again.")
    users.update(rows[0]["user_id"], {"telegram_chat_id": chat_id, "telegram_link_code": None,
                                      "telegram_link_expires": None})
    if rows[0]["status"] == "approved":
        return "✅ <b>Telegram connected!</b> Matching jobs will arrive here.\n\n" + HELP_TEXT_EN
    return ("✅ <b>Telegram connected!</b> Your account is waiting for approval — "
            "we'll message you here as soon as it's approved.")


def _not_a_user_text() -> str:
    url = dashboard_url()
    signup = f" Sign up at {url}" if url else " Sign up on the FirstIn website"
    return f"👋 This bot sends job alerts to FirstIn users.{signup}, then connect Telegram from your dashboard."


# ------------------------------------------------------------------ dispatch
def handle_update(update: dict) -> None:
    query = update.get("callback_query")
    if query:
        user = users.by_chat_id(query.get("from", {}).get("id", 0))
        data = query.get("data", "")
        if data == "noop":
            telegram.answer_callback(query["id"], "✓")
        elif user is None or user.status != "approved":
            telegram.answer_callback(query["id"], "⛔")
        elif data.startswith("u:"):
            telegram.answer_callback(query["id"], handle_approval(user, query) if user.is_owner else "⛔")
        else:
            telegram.answer_callback(query["id"], handle_job_callback(user, query))
        return

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") != "private" or "id" not in chat:
        return
    chat_id, text = chat["id"], (message.get("text") or "").strip()

    if text.startswith("/start ") and len(text.split()) == 2:
        telegram.send(link_account(chat_id, text.split()[1]), chat_id=chat_id)
        return
    user = users.by_chat_id(chat_id)
    if user is None:
        telegram.send(_not_a_user_text(), chat_id=chat_id)
        return
    if user.status != "approved":
        telegram.send("Your account is still waiting for approval — we'll message you here.", chat_id=chat_id)
        return
    if is_summary_request(text):
        for part in alerts.today_summary(user):
            telegram.send(part, chat_id=chat_id)
    elif text.startswith(("/start", "/help")) or text in ("עזרה", "?", "help"):
        telegram.send(HELP_TEXT if user.is_owner else HELP_TEXT_EN, chat_id=chat_id)


def poll_once(offset: int | None, timeout: int = 25) -> int | None:
    """Process pending updates; returns the next offset."""
    for update in telegram.get_updates(offset, timeout=timeout):
        offset = update["update_id"] + 1
        try:
            handle_update(update)
        except Exception as e:  # one bad update must not stop the bot
            print(f"⚠ update {update.get('update_id')}: {type(e).__name__}: {e}")
    return offset
