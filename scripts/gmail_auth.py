"""One-time Gmail authorization: opens the browser, saves config/token.json (read-only scope).

Run: .venv/bin/python scripts/gmail_auth.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.collectors.gmail import get_service  # noqa: E402

if __name__ == "__main__":
    print("נפתח דפדפן — אשרי ל-FirstIn גישת קריאה בלבד ל-Gmail...")
    profile = get_service(interactive=True).users().getProfile(userId="me").execute()
    print(f"✅ Gmail מחובר: {profile['emailAddress']} ({profile['messagesTotal']} הודעות בתיבה)")
