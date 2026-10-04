"""Telegram notifications.

Usage:
    .venv/bin/python -m worker.run_notify              # send pending instant alerts
    .venv/bin/python -m worker.run_notify --digest     # send the daily digest now
    .venv/bin/python -m worker.run_notify --bot        # listen for button presses (Ctrl+C to stop)
"""

import argparse

from worker.notify import alerts, bot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--digest", action="store_true", help="send the daily digest")
    parser.add_argument("--bot", action="store_true", help="handle button presses until Ctrl+C")
    args = parser.parse_args()
    if args.bot:
        print("מאזינה ללחיצות על כפתורים... (Ctrl+C לעצירה)")
        offset = None
        while True:
            offset = bot.poll_once(offset)
    elif args.digest:
        print(f"סיכום יומי נשלח עם {alerts.send_digest()} משרות (לבעלת המערכת)")
    else:
        r = alerts.send_instant()
        if r.paused:
            print("ההתראות מושהות (paused_until)")
        else:
            print(f"נשלחו {r.sent} התראות · {r.held_quiet} ממתינות לסוף שעות השקט")


if __name__ == "__main__":
    main()
