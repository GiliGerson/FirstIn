"""FirstIn local scheduler — runs everything on a timetable (PRD FR1, FR3, FR9).

    Gmail                    every 15 minutes
    ATS boards               every 60 minutes
    Personalize (per user)   after every collection + every 30 minutes (new users' first jobs)
    Instant alerts           every 5 minutes, per user (also releases alerts held during quiet hours)
    Approval requests        every 2 minutes (new users who finished onboarding)
    Daily digest             20:00
    Company discovery        daily at 12:00 (pending companies, capped web searches)
    Telegram buttons         continuously, in a background thread

After the Mac sleeps, missed runs are merged into a single run on wake (coalesce).
Started by launchd at login — see scripts/service.sh.

Run in the foreground: .venv/bin/python -m worker.scheduler
"""

import logging
import subprocess
import sys
import threading
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from worker import run_ats, run_gmail, users
from worker.health import HealthMonitor
from worker.notify import alerts, bot, telegram
from worker.pipeline import personalize

TZ = "Asia/Jerusalem"
DISCOVERY_MAX_SEARCHES = 20

log = logging.getLogger("firstin")
health = HealthMonitor()


def job_gmail() -> None:
    since = run_gmail.resolve_since(None)
    result = run_gmail.run(since)
    report = result.ingest_report
    log.info("gmail: scanned=%d relevant=%d new_jobs=%d errors=%d", result.scanned, len(result.relevant),
             len(report.new) if report else 0, len(result.errors))
    health.check("gmail")
    job_personalize()


def job_ats() -> None:
    scans, report = run_ats.run()
    failed = sum(1 for s in scans if s.error)
    log.info("ats: companies=%d failed=%d new_jobs=%d", len(scans), failed, len(report.new) if report else 0)
    health.check("ats")
    job_personalize()


def job_personalize() -> None:
    """Filter + score new shared jobs for every approved user, then send their alerts."""
    for r in personalize.run_all():
        if r.scored or r.failures or r.waiting_for_quota:
            log.info("personalize %s: considered=%d scored=%d waiting_quota=%d failures=%d",
                     r.user_id[:8], r.considered, r.scored, r.waiting_for_quota, r.failures)
    job_alerts()


def job_alerts() -> None:
    for user in users.approved():
        try:
            result = alerts.send_instant(user)
        except Exception:
            log.exception("alerts for %s failed", user.user_id[:8])
            continue
        if result.sent or result.held_quiet:
            log.info("alerts %s: sent=%d held_quiet=%d", user.user_id[:8], result.sent, result.held_quiet)


def job_digest() -> None:
    for user in users.approved():
        try:
            log.info("digest %s: %d jobs", user.user_id[:8], alerts.send_digest(user))
        except Exception:
            log.exception("digest for %s failed", user.user_id[:8])


def job_approvals() -> None:
    """New users who finished onboarding → approval request to the owner (Telegram buttons)."""
    sent = bot.request_approvals()
    if sent:
        log.info("approvals: %d request(s) sent", sent)


def job_discovery() -> None:
    # A subprocess keeps discovery's thread pool and prints out of the scheduler's process
    done = subprocess.run([sys.executable, "-m", "worker.run_discovery",
                           "--max-searches", str(DISCOVERY_MAX_SEARCHES)],
                          capture_output=True, text=True, timeout=3600)
    log.info("discovery: exit=%d %s", done.returncode, done.stdout.strip().splitlines()[-1:] or "")


def bot_loop(stop: threading.Event) -> None:
    offset, backoff = None, 5
    while not stop.is_set():
        try:
            offset = bot.poll_once(offset)
            backoff = 5
        except Exception as e:  # network down, Mac waking up...
            log.warning("bot: %s: %s — retrying in %ds", type(e).__name__, e, backoff)
            stop.wait(backoff)
            backoff = min(backoff * 2, 300)


def safe(fn):
    """A failing job is logged and retried at its next slot — it never stops the scheduler."""
    def wrapper():
        try:
            fn()
        except Exception:
            log.exception("%s failed", fn.__name__)
    wrapper.__name__ = fn.__name__
    return wrapper


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stdout, force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    scheduler = BlockingScheduler(timezone=TZ, job_defaults={
        "coalesce": True, "max_instances": 1, "misfire_grace_time": 3600,
    })
    now = datetime.now()
    scheduler.add_job(safe(job_gmail), "interval", minutes=15, next_run_time=now, id="gmail")
    scheduler.add_job(safe(job_ats), "interval", minutes=60, next_run_time=now, id="ats")
    scheduler.add_job(safe(job_alerts), "interval", minutes=5, id="alerts")
    scheduler.add_job(safe(job_approvals), "interval", minutes=2, next_run_time=now, id="approvals")
    scheduler.add_job(safe(job_personalize), "interval", minutes=30, id="personalize")   # newly approved users
    scheduler.add_job(safe(job_digest), "cron", hour=20, minute=0, id="digest")
    scheduler.add_job(safe(job_discovery), "cron", hour=12, minute=0, id="discovery")

    stop = threading.Event()
    threading.Thread(target=bot_loop, args=(stop,), daemon=True, name="telegram-bot").start()
    log.info("FirstIn scheduler started")
    try:
        telegram.send("🟢 FirstIn התחיל לרוץ.", silent=True)
    except Exception:
        log.warning("could not send startup message")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        stop.set()
        time.sleep(0.5)
        log.info("FirstIn scheduler stopped")


if __name__ == "__main__":
    main()
