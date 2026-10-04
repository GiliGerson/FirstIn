import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from worker import users
from worker.notify import alerts, bot
from worker.notify import format as fmt
from worker.notify import telegram

TZ = ZoneInfo("Asia/Jerusalem")
JOB = {
    "id": 7, "title": "Student <Developer> & AI", "url": "https://jobs.lever.co/acme/1",
    "location": "Tel Aviv", "is_hybrid": True, "is_remote": False, "job_type": "student",
    "role_category": "AI Engineer", "match_score": 88,
    "match_reasons": ["מתאים לה", "תל אביב", "AI", "רביעית"], "red_flags": ["לא ברור כמה ימים"],
    "companies": {"name": "Acme"}, "job_sources": [{"source": "linkedin"}, {"source": "lever"}, {"source": "lever"}],
}


class FormatTests(unittest.TestCase):
    def test_job_alert(self):
        text = fmt.job_alert(JOB)
        self.assertIn("🟢 <b>88</b>", text)
        self.assertIn("Student &lt;Developer&gt; &amp; AI", text)   # HTML-escaped
        self.assertIn("📍 Tel Aviv (היברידי)", text)
        self.assertIn("🏷 משרת סטודנט · AI Engineer", text)
        self.assertEqual(text.count("✅"), 3)                      # at most 3 reasons
        self.assertIn("⚠️ לא ברור כמה ימים", text)
        self.assertIn("🔎 מקור: Lever + LinkedIn", text)

    def test_buttons(self):
        rows = fmt.job_buttons(JOB)
        self.assertEqual(rows[0][0]["url"], JOB["url"])
        self.assertEqual([b["callback_data"] for b in rows[1]], ["a:7", "s:7", "n:7"])
        self.assertEqual(len(fmt.job_buttons({**JOB, "url": None})), 1)
        reasons = [b["callback_data"] for row in fmt.reason_buttons(7) for b in row]
        self.assertEqual(reasons, ["r:7:loc", "r:7:hours", "r:7:role", "r:7:company", "r:7:other"])

    def test_email_alerts(self):
        self.assertIn("פנייה ממגייס/ת", fmt.email_alert("recruiter_outreach", "Dana", "Hi", "סיכום"))
        self.assertIn("זימון לראיון", fmt.email_alert("application_update", "HR", "Interview", "x", "interview"))

    def test_split_message(self):
        blocks = ["a" * 30, "b" * 30, "c" * 30]
        self.assertEqual(telegram.split_message(blocks, "H", limit=64), ["H\n\n" + "a" * 30, "b" * 30 + "\n\n" + "c" * 30])


OWNER = users.User(user_id="owner-1", is_owner=True, status="approved", telegram_chat_id=42)
OTHER = users.User(user_id="user-2", status="approved", telegram_chat_id=77,
                   scoring_model="claude-haiku-4-5", daily_score_quota=30)


class QuietHoursTests(unittest.TestCase):
    QUIET = {"start": "23:00", "end": "08:00", "override_score": 90}

    def at(self, hh, mm=0):
        return datetime(2026, 9, 30, hh, mm, tzinfo=TZ)

    def test_overnight_window(self):
        self.assertTrue(alerts.in_quiet_hours(self.at(23, 30), self.QUIET))
        self.assertTrue(alerts.in_quiet_hours(self.at(3), self.QUIET))
        self.assertFalse(alerts.in_quiet_hours(self.at(8), self.QUIET))
        self.assertFalse(alerts.in_quiet_hours(self.at(14), self.QUIET))
        self.assertFalse(alerts.in_quiet_hours(self.at(3), {}))

    def test_same_day_window(self):
        q = {"start": "13:00", "end": "15:00"}
        self.assertTrue(alerts.in_quiet_hours(self.at(14), q))
        self.assertFalse(alerts.in_quiet_hours(self.at(16), q))

    def test_quiet_hours_hold_all_but_top_scores_and_send_to_the_users_chat(self):
        settings = {"instant_threshold": 75, "quiet_hours": self.QUIET, "paused_until": None}
        jobs = [{**JOB, "id": 1, "match_score": 95}, {**JOB, "id": 2, "match_score": 80}]
        with mock.patch.object(alerts.settings_mod, "get_active", return_value=settings), \
             mock.patch.object(alerts, "pending_instant", return_value=jobs) as pending, \
             mock.patch.object(alerts.telegram, "send") as send, \
             mock.patch.object(alerts, "_mark_notified") as mark:
            result = alerts.send_instant(OTHER, self.at(2))
        self.assertEqual((result.sent, result.held_quiet), (1, 1))
        pending.assert_called_once_with("user-2", 75)
        self.assertEqual(send.call_args.kwargs["chat_id"], "77")
        mark.assert_called_once_with("user-2", [1])

    def test_paused_and_unlinked_users_get_nothing(self):
        settings = {"instant_threshold": 75, "quiet_hours": {}, "paused_until": "2099-01-01T00:00:00+00:00"}
        with mock.patch.object(alerts.settings_mod, "get_active", return_value=settings), \
             mock.patch.object(alerts, "pending_instant") as pending:
            self.assertTrue(alerts.send_instant(OTHER, self.at(12)).paused)
            unlinked = users.User(user_id="u3", status="approved")
            self.assertTrue(alerts.send_instant(unlinked, self.at(12)).no_chat)
        pending.assert_not_called()

    def test_user_without_settings_is_skipped(self):
        with mock.patch.object(alerts.settings_mod, "get_active", return_value=None):
            self.assertEqual(alerts.send_instant(OTHER, self.at(12)).sent, 0)


class SummaryTests(unittest.TestCase):
    def test_today_summary(self):
        settings = {"instant_threshold": 75, "digest_threshold": 50}
        uj = lambda job_id, score: {"job_id": job_id, "match_score": score, "match_reasons": JOB["match_reasons"],
                                    "red_flags": [], "role_category": "AI", "user_state": "new",
                                    "jobs": {k: v for k, v in JOB.items() if k not in ("id", "match_score")}}
        emails = [{"from_addr": "hr@acme.com", "subject": "Interview", "category": "application_update",
                   "summary": "זימון לראיון"}]
        results = iter([[uj(1, 88), uj(2, 60), uj(3, 20)], emails, [{"id": 1}]])
        with mock.patch.object(alerts.settings_mod, "get_active", return_value=settings), \
             mock.patch.object(alerts.db, "client"), \
             mock.patch.object(alerts.db, "execute", side_effect=lambda q: mock.MagicMock(data=next(results))):
            text = "\n".join(alerts.today_summary(OWNER, datetime(2026, 10, 1, 13, 5, tzinfo=TZ)))
        self.assertIn("סיכום עד כה · 01/10 13:05", text)
        self.assertIn("משרות חדשות היום: <b>3</b> (1 בהתאמה גבוהה, 1 בינונית)", text)
        self.assertIn("הגשות היום: <b>1</b>", text)
        self.assertIn("📬 Interview", text)
        self.assertEqual(text.count("Student &lt;Developer&gt;"), 2)   # the score-20 job isn't listed

    def test_flatten(self):
        row = {"job_id": 9, "match_score": 70, "match_reasons": ["x"], "red_flags": [], "role_category": "AI",
               "user_state": "saved", "jobs": {"id": 9, "title": "T", "url": None}}
        flat = alerts.flatten(row)
        self.assertEqual((flat["id"], flat["title"], flat["match_score"], flat["user_state"]), (9, "T", 70, "saved"))


class BotTests(unittest.TestCase):
    def query(self, data, user_id=42):
        return {"id": "cb1", "data": data, "from": {"id": user_id},
                "message": {"chat": {"id": user_id}, "message_id": 5}}

    def test_unknown_or_pending_users_cannot_press_buttons(self):
        pending = users.User(user_id="p", status="pending", telegram_chat_id=999)
        for who in (None, pending):
            with mock.patch.object(bot.users, "by_chat_id", return_value=who), \
                 mock.patch.object(bot.telegram, "answer_callback") as answer, \
                 mock.patch.object(bot, "handle_job_callback") as handle:
                bot.handle_update({"callback_query": self.query("a:7", user_id=999)})
            handle.assert_not_called()
            answer.assert_called_once_with("cb1", "⛔")

    def test_only_the_owner_can_approve(self):
        with mock.patch.object(bot.users, "by_chat_id", return_value=OTHER), \
             mock.patch.object(bot.telegram, "answer_callback") as answer, \
             mock.patch.object(bot, "handle_approval") as approve:
            bot.handle_update({"callback_query": self.query("u:ok:someone", user_id=77)})
        approve.assert_not_called()
        answer.assert_called_once_with("cb1", "⛔")

    def test_not_relevant_asks_for_reason_then_saves_it_for_that_user(self):
        job = {"id": 7, "url": "https://x", "canonical_url": None, "title": "T"}
        with mock.patch.object(bot, "_user_job", return_value=job) as get_job, \
             mock.patch.object(bot, "_set_state") as set_state, \
             mock.patch.object(bot.telegram, "edit_buttons") as edit:
            self.assertEqual(bot.handle_job_callback(OTHER, self.query("n:7", 77)), "למה לא רלוונטי?")
            self.assertEqual(edit.call_args.args[2], fmt.reason_buttons(7))
            bot.handle_job_callback(OTHER, self.query("r:7:hours", 77))
        get_job.assert_called_with("user-2", 7)
        set_state.assert_called_once_with("user-2", 7, {"user_state": "not_relevant", "not_relevant_reason": "היקף שעות"})

    def test_applied_creates_application_for_that_user(self):
        job = {"id": 7, "url": None, "canonical_url": None, "title": "T"}
        with mock.patch.object(bot, "_user_job", return_value=job), \
             mock.patch.object(bot, "mark_applied") as applied, \
             mock.patch.object(bot.telegram, "edit_buttons"):
            self.assertEqual(bot.handle_job_callback(OTHER, self.query("a:7", 77)), "סומן כהוגש ✅")
        applied.assert_called_once_with("user-2", job)

    def test_bad_data(self):
        self.assertEqual(bot.handle_job_callback(OTHER, self.query("a:abc")), "?")

    def test_summary_request_words(self):
        for text in ["תן לי סיכום יומי", "סיכום", "/summary", "/today", "Summary"]:
            self.assertTrue(bot.is_summary_request(text), text)
        self.assertFalse(bot.is_summary_request("שלום"))

    def test_summary_goes_to_the_asking_user(self):
        with mock.patch.object(bot.users, "by_chat_id", return_value=OTHER), \
             mock.patch.object(bot.alerts, "today_summary", return_value=["part1", "part2"]) as summary, \
             mock.patch.object(bot.telegram, "send") as send:
            bot.handle_update({"message": {"chat": {"id": 77, "type": "private"}, "text": "/summary"}})
        summary.assert_called_once_with(OTHER)
        self.assertEqual([(c.args[0], c.kwargs["chat_id"]) for c in send.call_args_list], [("part1", 77), ("part2", 77)])

    def test_strangers_get_a_sign_up_hint(self):
        with mock.patch.object(bot.users, "by_chat_id", return_value=None), \
             mock.patch.object(bot.telegram, "send") as send:
            bot.handle_update({"message": {"chat": {"id": 5, "type": "private"}, "text": "hi"}})
        self.assertIn("Sign up", send.call_args.args[0])

    def test_start_with_code_links_the_account(self):
        with mock.patch.object(bot, "link_account", return_value="ok") as link, \
             mock.patch.object(bot.telegram, "send") as send:
            bot.handle_update({"message": {"chat": {"id": 5, "type": "private"}, "text": "/start abc123"}})
        link.assert_called_once_with(5, "abc123")
        send.assert_called_once_with("ok", chat_id=5)


if __name__ == "__main__":
    unittest.main()
