"""FR9 — system health: alert me when a source fails 3 runs in a row, and when it recovers."""

from worker import db
from worker.notify import telegram

FAILURES_TO_ALERT = 3
SOURCE_NAMES_HE = {"gmail": "Gmail", "ats": "סריקת אתרי הגיוס", "discovery": "גילוי חברות"}


class HealthMonitor:
    def __init__(self):
        self.alerted: set[str] = set()   # collectors currently reported as failing

    def recent_runs(self, collector: str) -> list[dict]:
        return db.execute(
            db.client().table("runs").select("errors,finished_at")
            .eq("collector", collector).not_.is_("finished_at", "null")
            .order("started_at", desc=True).limit(FAILURES_TO_ALERT)
        ).data

    def check(self, collector: str) -> None:
        runs = self.recent_runs(collector)
        name = SOURCE_NAMES_HE.get(collector, collector)
        failing = len(runs) == FAILURES_TO_ALERT and all(r["errors"] for r in runs)
        if failing and collector not in self.alerted:
            self.alerted.add(collector)
            error = str(runs[0]["errors"][0].get("error", runs[0]["errors"][0]))[:300]
            hint = ""
            if collector == "gmail" and ("token" in error.lower() or "invalid_grant" in error.lower()):
                hint = "\n\nכנראה שהחיבור ל-Gmail פג — צריך לחבר מחדש (תגידי ל-Claude Code)."
            telegram.send(f"⚠️ <b>{name} נכשל {FAILURES_TO_ALERT} פעמים ברצף</b>\n"
                          f"<code>{telegram.esc(error)}</code>{hint}")
        elif runs and not runs[0]["errors"] and collector in self.alerted:
            self.alerted.discard(collector)
            telegram.send(f"✅ {name} חזר לעבוד.", silent=True)
