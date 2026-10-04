import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from worker import users
from worker.pipeline import personalize as p
from worker.pipeline.score import JobScore

TZ = ZoneInfo("Asia/Jerusalem")
NOW = datetime(2026, 10, 4, 15, 0, tzinfo=TZ)
SETTINGS = {"include_keywords": ["student", "intern"], "exclude_keywords": [], "job_types": ["student", "internship"],
            "locations": ["Tel Aviv"], "accept_remote": True, "roles": ["Software Developer"],
            "max_days_per_week": 3, "accept_hybrid": True}


def job(job_id, title="Student Developer", location="Tel Aviv"):
    return {"id": job_id, "title": title, "description": "", "location": location, "is_hybrid": None,
            "is_remote": None, "job_type": "student", "url": None, "canonical_url": None,
            "first_seen_at": NOW.isoformat(), "companies": {"name": "Acme", "priority": "normal"}}


def score(value=80):
    return JobScore(is_student_or_part_time=True, role_category="Software Developer", match_score=value,
                    reasons=["fits"], red_flags=[], requirements=["Python"], location="Tel Aviv",
                    hybrid=None, days_per_week=None)


class PersonalizeTests(unittest.TestCase):
    def run_user(self, user, jobs, scored_today=0):
        with mock.patch.object(p.settings_mod, "get_active", return_value=SETTINGS), \
             mock.patch.object(p, "candidates", return_value=jobs), \
             mock.patch.object(p, "scored_today", return_value=scored_today), \
             mock.patch.object(p, "score_job", return_value=score()) as scorer, \
             mock.patch.object(p.db, "client"), mock.patch.object(p.db, "execute") as execute:
            report = p.personalize_user(user, llm=mock.MagicMock(), now=NOW)
        return report, scorer, execute

    def test_filters_by_the_users_cities_and_scores_with_their_model(self):
        user = users.User(user_id="u2", status="approved", scoring_model="claude-haiku-4-5", daily_score_quota=30)
        report, scorer, execute = self.run_user(user, [job(1), job(2, location="Haifa")])
        self.assertEqual((report.considered, report.scored), (2, 1))
        self.assertEqual(report.rejected["outside_my_area"], 1)
        self.assertEqual(scorer.call_args.kwargs["model"], "claude-haiku-4-5")
        saved = execute.call_args.args[0]   # the upsert query object (mocked)
        self.assertIsNotNone(saved)

    def test_daily_quota_limits_scoring(self):
        user = users.User(user_id="u2", status="approved", daily_score_quota=30)
        report, scorer, _ = self.run_user(user, [job(i) for i in range(5)], scored_today=28)
        self.assertEqual((report.scored, report.waiting_for_quota), (2, 3))
        self.assertEqual(scorer.call_count, 2)

    def test_owner_has_no_quota(self):
        owner = users.User(user_id="o", is_owner=True, status="approved", scoring_model="claude-sonnet-5-5",
                           daily_score_quota=None)
        report, _, _ = self.run_user(owner, [job(i) for i in range(40)])
        self.assertEqual((report.scored, report.waiting_for_quota), (40, 0))

    def test_user_without_settings_is_skipped(self):
        with mock.patch.object(p.settings_mod, "get_active", return_value=None):
            report = p.personalize_user(users.User(user_id="x"), llm=mock.MagicMock(), now=NOW)
        self.assertEqual(report.skipped, "no_settings")

    def test_job_to_raw_maps_job_type_to_employment_type(self):
        raw = p.job_to_raw({**job(1), "job_type": "internship", "is_remote": True})
        self.assertEqual((raw.employment_type, raw.workplace, raw.company, raw.is_israel),
                         ("Internship", "remote", "Acme", True))


class UserTests(unittest.TestCase):
    def test_from_row_and_chat_id(self):
        u = users.User.from_row({"user_id": "a", "status": "approved", "telegram_chat_id": 5,
                                 "daily_score_quota": None, "unknown_column": 1})
        self.assertEqual((u.user_id, u.chat_id, u.daily_score_quota), ("a", "5", None))  # NULL = no limit
        self.assertEqual(u.languages, ["Hebrew", "English"])
        self.assertIsNone(users.User(user_id="b").chat_id)

    def test_profile_facts_for_other_users(self):
        u = users.User(user_id="b", field_of_study="Computer Science", study_year=3)
        facts = u.profile_facts()
        self.assertEqual((facts["education"], facts["year"]), ("Computer Science student", 3))


if __name__ == "__main__":
    unittest.main()
