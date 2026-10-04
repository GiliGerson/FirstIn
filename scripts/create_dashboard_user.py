#!/usr/bin/env python3
"""Create my dashboard login (Supabase Auth) and grant it access (dashboard_owners).

Asks for a password with hidden input — the password is sent only to Supabase, never stored.
Standard library only. Run: python3 scripts/create_dashboard_user.py"""

import getpass
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from setup_env import read_env  # noqa: E402

MIN_PASSWORD = 10


def request(env, method, path, body=None, extra_headers=None):
    key = env["SUPABASE_SECRET_KEY"]
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    headers.update(extra_headers or {})
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(env["SUPABASE_URL"].rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, text


def find_user(env, email):
    status, body = request(env, "GET", "/auth/v1/admin/users?per_page=1000")
    if status != 200:
        raise SystemExit(f"❌ לא הצלחתי לקרוא משתמשים מ-Supabase ({status}): {body}")
    return next((u for u in body.get("users", []) if u.get("email", "").lower() == email.lower()), None)


def main():
    env = read_env()
    print("=" * 60)
    print("  FirstIn · יצירת משתמש לדשבורד")
    print("=" * 60)
    email = input("  המייל שלך (שם המשתמש לדשבורד): ").strip()
    while True:
        password = getpass.getpass(f"  בחרי סיסמה (לפחות {MIN_PASSWORD} תווים, ההקלדה מוסתרת): ")
        if len(password) < MIN_PASSWORD:
            print(f"  ✗ קצרה מדי — לפחות {MIN_PASSWORD} תווים.")
            continue
        if getpass.getpass("  הקלידי שוב לאימות: ") != password:
            print("  ✗ הסיסמאות לא זהות, נסי שוב.")
            continue
        break

    user = find_user(env, email)
    if user:
        status, body = request(env, "PUT", f"/auth/v1/admin/users/{user['id']}",
                               {"password": password, "email_confirm": True})
        action = "עודכנה הסיסמה"
    else:
        status, body = request(env, "POST", "/auth/v1/admin/users",
                               {"email": email, "password": password, "email_confirm": True})
        action = "נוצר משתמש"
    if status not in (200, 201):
        raise SystemExit(f"❌ שגיאה ({status}): {body}")
    user_id = body["id"]

    status, body = request(env, "POST", "/rest/v1/dashboard_owners?on_conflict=user_id",
                           {"user_id": user_id}, {"Prefer": "resolution=merge-duplicates"})
    if status not in (200, 201, 204):
        raise SystemExit(f"❌ המשתמש נוצר אבל לא קיבל הרשאה ({status}): {body}\n"
                         "   האם הרצת את db/migrations/001_dashboard_access.sql?")
    print(f"\n  ✅ {action} והרשאה ניתנה. אפשר להיכנס לדשבורד עם {email}.")
    print("  חזרי ל-Claude Code וכתבי: סיימתי")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n  הופסק.")
        sys.exit(1)
