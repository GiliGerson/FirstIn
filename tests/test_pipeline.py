import unittest
from unittest import mock

from worker.models import RawJob
from worker.pipeline import normalize, score
from worker.pipeline.filter import RuleFilter
from worker.pipeline.ingest import CompanyIndex

SETTINGS = {
    "roles": ["Software Developer / Student Developer", "AI Engineer", "Product Analyst"],
    "include_keywords": ["student", "סטודנט", "intern", "internship", "part-time", "חלקית"],
    "exclude_keywords": ["sales"],
    "job_types": ["student", "part-time", "internship"],
    "locations": ["Tel Aviv", "Herzliya", "Ramat Gan", "Petah Tikva", "Ra'anana"],
    "accept_hybrid": True, "accept_remote": True, "max_days_per_week": 3,
}


def job(title, location="Tel Aviv-Yafo", company="Acme", **kw) -> RawJob:
    return RawJob(source="linkedin", title=title, company=company, location=location,
                  is_israel=kw.pop("is_israel", True), **kw)


class NormalizeTests(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(normalize.normalize_title("Software Engineer – Student Position"),
                         "software engineer student position")
        self.assertEqual(normalize.normalize_title("סטודנט/ית לפיתוח תוכנה"), "סטודנט לפיתוח תוכנה")
        self.assertEqual(normalize.normalize_title("סטודנט.ית קדם.ת רכש"), "סטודנט קדם רכש")
        self.assertEqual(normalize.normalize_title("C++ / C# Developer (Student)"), "c++ c# developer student")

    def test_same_job_from_two_sources_gets_same_key(self):
        a = (normalize.normalize_title("Security Analyst (Student Position)"),
             normalize.normalize_location("Tel Aviv-Yafo, Tel Aviv District, Israel"))
        b = (normalize.normalize_title("Security Analyst - Student Position"), normalize.normalize_location("Tel Aviv"))
        self.assertEqual(a, b)

    def test_locations(self):
        self.assertEqual(normalize.canonical_city("Herzliya, Tel Aviv District, Israel (Hybrid)"), "Herzliya")
        self.assertEqual(normalize.canonical_city("Israel - Raanana"), "Ra'anana")
        self.assertEqual(normalize.canonical_city("פתח תקווה"), "Petah Tikva")
        self.assertIsNone(normalize.canonical_city("Israel"))
        self.assertEqual(normalize.normalize_location("Center District, Israel (Hybrid)"), "Center District, Israel")

    def test_job_type_and_workplace(self):
        self.assertEqual(normalize.job_type("Data Intern"), "internship")
        self.assertEqual(normalize.job_type("Student Developer"), "student")
        self.assertEqual(normalize.job_type("Office Manager – Part-Time"), "part_time")
        self.assertEqual(normalize.job_type("Data Analyst", "PartTime"), "part_time")
        self.assertEqual(normalize.job_type("Data Analyst"), "other")
        self.assertEqual(normalize.workplace_flags("hybrid", None), (True, False))
        self.assertEqual(normalize.workplace_flags(None, "Herzliya (Hybrid)"), (True, False))
        self.assertEqual(normalize.workplace_flags(None, "Tel Aviv"), (None, None))


class RuleFilterTests(unittest.TestCase):
    def setUp(self):
        self.f = RuleFilter(SETTINGS)

    def check(self, j):
        return self.f.check(j)

    def test_passes_student_job_in_my_area(self):
        r = self.check(job("Software Engineering Student"))
        self.assertTrue(r.passed)
        self.assertEqual((r.job_type, r.city), ("student", "Tel Aviv"))

    def test_student_manager_title_is_ok(self):
        self.assertTrue(self.check(job("Technical Product Manager (Student Position)")).passed)

    def test_rejections(self):
        cases = {
            "not_israel": job("Student Developer", "London", is_israel=False),
            "not_student_or_part_time": job("Backend Engineer"),
            "excluded_keyword": job("Senior Student Program Lead"),
            "outside_my_area": job("Student Developer", "Haifa"),
        }
        for reason, j in cases.items():
            self.assertEqual(self.check(j).reason, reason, j.title)
        self.assertEqual(self.check(job("Sales Development Intern")).reason, "excluded_keyword")

    def test_remote_outside_area_is_ok(self):
        self.assertTrue(self.check(job("Student Developer", "Haifa", workplace="remote")).passed)

    def test_unspecified_israel_location_passes(self):
        self.assertTrue(self.check(job("Student Developer", "Israel")).passed)

    def test_part_time_via_employment_type_and_experience_rule(self):
        pt = job("Data Analyst", employment_type="Part time", description="1+ years of experience with SQL")
        self.assertTrue(self.check(pt).passed)
        senior_pt = job("Data Analyst", employment_type="Part time", description="5+ years of hands-on experience")
        self.assertEqual(self.check(senior_pt).reason, "requires_experience")
        manager_pt = job("Office Manager", employment_type="Part-time")
        self.assertEqual(self.check(manager_pt).reason, "manager_role")

    def test_student_titles_ignore_degree_years(self):
        j = job("QA Student", description="At least 2 years left of your degree. 3+ years of experience preferred")
        self.assertTrue(self.check(j).passed)

    def test_disabled_job_type(self):
        f = RuleFilter({**SETTINGS, "job_types": ["student"]})
        self.assertEqual(f.check(job("Data Intern")).reason, "job_type_disabled")


class CompanyIndexTests(unittest.TestCase):
    ROWS = [{"id": 1, "name": "Upwind", "priority": "normal"},
            {"id": 2, "name": "Via", "priority": "normal"},
            {"id": 3, "name": "Check Point Software", "priority": "normal"},
            {"id": 4, "name": "Wiz", "priority": "normal"}]

    def test_find(self):
        idx = CompanyIndex(list(self.ROWS))
        self.assertEqual(idx.find("Wiz, Inc.")["id"], 4)
        self.assertEqual(idx.find("Upwind Security")["id"], 1)       # whole-word prefix
        self.assertEqual(idx.find("Check Point Software Technologies")["id"], 3)
        self.assertIsNone(idx.find("Viasat"))                          # not a word prefix
        self.assertIsNone(idx.find("Via Transportation"))              # "via" too short to prefix-match
        self.assertEqual(idx.find("VIA")["id"], 2)                     # exact core name still works

    def test_unknown_company_becomes_pending(self):
        idx = CompanyIndex(list(self.ROWS))
        report = mock.MagicMock(new_companies=[])
        with mock.patch("worker.pipeline.ingest.companies_repo.create_pending",
                        return_value={"id": 9, "name": "Nova AI", "priority": "normal"}) as create:
            row = idx.get_or_create("Nova AI", report)
            again = idx.get_or_create("Nova AI Ltd", report)
        self.assertEqual(row["id"], 9)
        self.assertIs(again, row)
        create.assert_called_once_with("Nova AI")
        self.assertEqual(report.new_companies, ["Nova AI"])


class ScoreTests(unittest.TestCase):
    def result(self, value):
        return score.JobScore(is_student_or_part_time=True, role_category="AI Engineer", match_score=value,
                              reasons=["תפקיד AI"], red_flags=[], requirements=["Python"],
                              location="Tel Aviv", hybrid=True, days_per_week=None)

    def fake_client(self, parsed, stop_reason="end_turn"):
        client = mock.MagicMock()
        client.beta.messages.parse.return_value = mock.MagicMock(parsed_output=parsed, stop_reason=stop_reason)
        return client

    def test_uses_sonnet_with_fallback(self):
        client = self.fake_client(self.result(70))
        score.score_job(client, "sys", job("AI Student"))
        kwargs = client.beta.messages.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-sonnet-5-5")
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertEqual(kwargs["output_config"], {"effort": "low"})

    def test_clamps_and_favorite_bonus(self):
        j = job("AI Student")
        self.assertEqual(score.score_job(self.fake_client(self.result(130)), "sys", j).match_score, 100)
        self.assertEqual(score.score_job(self.fake_client(self.result(80)), "sys", j, favorite=True).match_score, 90)
        self.assertIsNone(score.score_job(self.fake_client(None, "refusal"), "sys", j))

    def test_prompt_contains_profile_and_rules(self):
        prompt = score.build_system_prompt(SETTINGS, {"education": "B.Sc. CS", "year": 2, "languages": ["Hebrew"]})
        self.assertIn("1. Software Developer / Student Developer", prompt)
        self.assertIn("at most 3 days per week", prompt)
        self.assertIn("Tel Aviv, Herzliya", prompt)

    def test_user_message_marks_missing_description(self):
        self.assertIn("(no description available)", score.build_user_message(job("AI Student")))


if __name__ == "__main__":
    unittest.main()
