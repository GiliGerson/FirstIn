#!/usr/bin/env python3
"""Checks that every .env value exists (never prints values) and tests the connection to
Supabase, Telegram and the Claude API. Standard library only."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from setup_env import ENV_KEYS, ROOT, read_env  # noqa: E402

CLAUDE_MODEL = "claude-haiku-4-5"
TELEGRAM_TEXT = "FirstIn מחובר ✅"


def http(method, url, headers=None, body=None, timeout=30):
    """Return (status, parsed_json_or_text). Never raises on HTTP errors."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def check_env(env):
    print("── משתנים ב-.env ──")
    ok = True
    for key in ENV_KEYS:
        present = bool(env.get(key))
        ok &= present
        print("  {} {}".format("✅" if present else "❌", key))
    creds = ROOT / env.get("GMAIL_CREDENTIALS_PATH", "config/credentials.json")
    exists = creds.is_file()
    ok &= exists
    print("  {} קובץ Gmail OAuth ({})".format("✅" if exists else "❌", creds.relative_to(ROOT)))
    return ok


def check_supabase(env):
    key = env["SUPABASE_SECRET_KEY"]
    headers = {"apikey": key}
    if key.startswith("eyJ"):  # legacy service_role JWT
        headers["Authorization"] = "Bearer " + key
    url = env["SUPABASE_URL"].rstrip("/") + "/rest/v1/search_settings?select=id&limit=1"
    status, body = http("GET", url, headers)
    if status == 200:
        return True, "מחובר, והטבלאות מה-schema קיימות"
    msg = body.get("message", "") if isinstance(body, dict) else str(body)[:200]
    if status in (401, 403):
        return False, "המפתח נדחה ({}) — בדקי את SUPABASE_SECRET_KEY. {}".format(status, msg)
    if status == 404 or "search_settings" in msg:
        return False, "החיבור עובד אבל הטבלאות לא נמצאו — צריך להריץ את db/schema.sql ב-SQL Editor. ({})".format(msg)
    return False, "שגיאה {}: {}".format(status, msg)


def check_telegram(env):
    url = "https://api.telegram.org/bot{}/sendMessage".format(env["TELEGRAM_BOT_TOKEN"])
    status, body = http("POST", url, body={"chat_id": env["TELEGRAM_CHAT_ID"], "text": TELEGRAM_TEXT})
    if isinstance(body, dict) and body.get("ok"):
        return True, "ההודעה \"{}\" נשלחה — בדקי בטלגרם".format(TELEGRAM_TEXT)
    desc = body.get("description", "") if isinstance(body, dict) else str(body)[:200]
    return False, "שגיאה {}: {}".format(status, desc)


def check_claude(env):
    headers = {"x-api-key": env["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}
    body = {"model": CLAUDE_MODEL, "max_tokens": 10,
            "messages": [{"role": "user", "content": "Reply with the single word: pong"}]}
    status, resp = http("POST", "https://api.anthropic.com/v1/messages", headers, body)
    if status == 200 and isinstance(resp, dict):
        text = "".join(b.get("text", "") for b in resp.get("content", []))
        return True, "{} ענה: {}".format(CLAUDE_MODEL, text.strip())
    err = resp.get("error", {}).get("message", "") if isinstance(resp, dict) else str(resp)[:200]
    if status == 401:
        return False, "המפתח נדחה — בדקי את ANTHROPIC_API_KEY."
    if status == 400 and "credit" in err.lower():
        return False, "המפתח תקין אבל אין קרדיט בחשבון — צריך להוסיף אמצעי תשלום ב-console.anthropic.com → Billing."
    return False, "שגיאה {}: {}".format(status, err)


def main():
    env = read_env()
    if not env:
        print("❌ לא נמצא קובץ .env — הריצי קודם: python3 scripts/setup_env.py")
        return 1

    all_ok = check_env(env)
    print()
    print("── בדיקות חיבור ──")
    checks = [
        ("Supabase", check_supabase, ["SUPABASE_URL", "SUPABASE_SECRET_KEY"]),
        ("Telegram", check_telegram, ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]),
        ("Claude API", check_claude, ["ANTHROPIC_API_KEY"]),
    ]
    for name, fn, needed in checks:
        if not all(env.get(k) for k in needed):
            print("  ⏭  {}: דילגתי — חסר {}".format(name, ", ".join(k for k in needed if not env.get(k))))
            all_ok = False
            continue
        try:
            ok, detail = fn(env)
        except Exception as e:  # network / SSL errors
            ok, detail = False, "שגיאת רשת: {}".format(e)
        all_ok &= ok
        print("  {} {}: {}".format("✅" if ok else "❌", name, detail))

    print()
    print("✅ הכול מחובר!" if all_ok else "⚠ יש דברים לתקן (ראו למעלה).")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
