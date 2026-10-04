import unittest
from unittest import mock

import httpx

from worker.collectors.common import BoardProbe
from worker.discovery import detector, finder
from worker.pipeline.keywords import looks_student
from worker.pipeline.locations import is_israel


class DetectorTests(unittest.TestCase):
    def test_urls(self):
        cases = {
            "https://boards.greenhouse.io/similarweb": ("greenhouse", "similarweb"),
            "https://job-boards.greenhouse.io/wizinc/jobs/123": ("greenhouse", "wizinc"),
            "https://jobs.lever.co/spotify/abc-123": ("lever", "spotify"),
            "https://jobs.eu.lever.co/acme": ("lever", "acme"),
            "https://jobs.ashbyhq.com/monday.com/uuid": ("ashby", "monday.com"),
            "https://www.comeet.com/jobs/examplecorp/57.001/student/AB.123": ("comeet", "examplecorp/57.001"),
            "https://jobs.smartrecruiters.com/Visa1/7438": ("smartrecruiters", "Visa1"),
            "https://intel.wd1.myworkdayjobs.com/en-US/External": ("workday", "intel.wd1.myworkdayjobs.com/en-US/External"),
        }
        for url, expected in cases.items():
            found = detector.detect_in_text(url)
            self.assertEqual((found.ats, found.token), expected, url)

    def test_embeds_in_html(self):
        html = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acmeco"></script>'
        self.assertEqual(detector.detect_in_text(html).token, "acmeco")
        html = "<script>COMEET_WIDGET({ 'company-uid': 'A1.00B' })</script>"
        found = detector.detect_in_text(html)
        self.assertEqual(found.token, "?/A1.00B")
        self.assertTrue(found.needs_resolving)
        self.assertFalse(found.supported)
        # Pages that embed the Comeet API token next to the UID
        html = """COMEET.init({"token": "0000AAAA1111BBBB2222CCCC3333", "company-uid": "41.009"})"""
        self.assertEqual(detector.detect_in_text(html).token, "41.009:0000AAAA1111BBBB2222CCCC3333")
        html = "const COMPANY_UID = '59.004'; const TOKEN = '0000AAAA1111BBBB2222CCCC3333DDDD4444';"
        self.assertEqual(detector.detect_in_text(html).token, "59.004:0000AAAA1111BBBB2222CCCC3333DDDD4444")
        self.assertIsNone(detector.detect_in_text("<html>nothing</html>"))

    def test_reserved_path_segments_are_not_tokens(self):
        self.assertIsNone(detector.detect_in_text("https://boards.greenhouse.io/embed"))

    def test_supported_flag(self):
        self.assertTrue(detector.Detection("comeet", "a/B1.000").supported)
        self.assertFalse(detector.Detection("workday", "x").supported)

    def test_follows_careers_link(self):
        pages = {
            "https://acme.com/": '<a href="/careers">Careers</a> <a href="/blog">Blog</a>',
            "https://acme.com/careers": '<iframe src="https://jobs.lever.co/acme"></iframe>',
        }
        client = httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text=pages.get(str(r.url), "")) if str(r.url) in pages
            else httpx.Response(404)))
        found = detector.detect(client, "https://acme.com/")
        self.assertEqual((found.ats, found.token), ("lever", "acme"))


class FinderTests(unittest.TestCase):
    def test_token_candidates(self):
        self.assertEqual(finder.token_candidates("Wiz"), ["wiz", "wizinc", "wizhq", "wizio", "wizcareers"])
        cands = finder.token_candidates("Cato Networks Ltd.")
        self.assertIn("catonetworks", cands)
        self.assertIn("cato-networks", cands)
        self.assertIn("cato", cands)
        self.assertIn("monday.com", finder.token_candidates("monday", website="https://www.monday.com"))
        self.assertEqual(finder.token_candidates("Ltd."), [])

    def test_probe_guesses_requires_israel_jobs_or_name_match(self):
        foreign = BoardProbe("lever", "acme", None, job_count=50, israel_jobs=0)
        local = BoardProbe("ashby", "acmehq", None, job_count=10, israel_jobs=3)

        def fake_probe(results):
            return lambda client, token: results.get(token)

        with mock.patch.dict(finder.PROBERS, {
            "greenhouse": fake_probe({}), "lever": fake_probe({"acme": foreign}), "ashby": fake_probe({"acmehq": local}),
        }):
            best = finder.probe_guesses(None, "Acme")
        self.assertEqual(best, local)

        named = BoardProbe("greenhouse", "acme", "Acme, Inc.", job_count=5, israel_jobs=0)
        with mock.patch.dict(finder.PROBERS, {
            "greenhouse": fake_probe({"acme": named}), "lever": fake_probe({}), "ashby": fake_probe({}),
        }):
            self.assertEqual(finder.probe_guesses(None, "Acme"), named)

        with mock.patch.dict(finder.PROBERS, {
            "greenhouse": fake_probe({}), "lever": fake_probe({"acme": foreign}), "ashby": fake_probe({}),
        }):
            self.assertIsNone(finder.probe_guesses(None, "Acme"))

        # An empty board with the right name is stale (company moved ATS)
        empty = BoardProbe("greenhouse", "acme", "Acme", job_count=0, israel_jobs=0)
        with mock.patch.dict(finder.PROBERS, {
            "greenhouse": fake_probe({"acme": empty}), "lever": fake_probe({}), "ashby": fake_probe({}),
        }):
            self.assertIsNone(finder.probe_guesses(None, "Acme"))

    def test_names_match_is_exact_on_core_name(self):
        self.assertTrue(finder._names_match("Wiz", "Wiz, Inc."))
        self.assertTrue(finder._names_match("Cato Networks", "Cato Networks Ltd."))
        self.assertFalse(finder._names_match("IAI - Israel Aerospace Industries", "i.AI"))
        self.assertFalse(finder._names_match("Via", "Viasat"))

    def test_find_company_uses_web_search_then_detector(self):
        search = finder.CareersSearch(website="https://acme.io", job_board_url="https://jobs.lever.co/acme",
                                      careers_url="https://acme.io/careers", kind="startup")
        with mock.patch.object(finder, "probe_guesses", return_value=None), \
             mock.patch.object(finder, "web_search", return_value=search):
            result = finder.find_company(httpx.Client(), mock.MagicMock(), "Acme", "Tel Aviv")
        self.assertEqual(result.method, "web_search")
        self.assertEqual((result.detection.ats, result.detection.token), ("lever", "acme"))
        self.assertEqual(result.kind, "startup")

    def test_find_company_without_search_is_deferred(self):
        with mock.patch.object(finder, "probe_guesses", return_value=None):
            self.assertEqual(finder.find_company(httpx.Client(), None, "Acme").method, "deferred")
            spent = finder.SearchBudget(0)
            result = finder.find_company(httpx.Client(), mock.MagicMock(), "Acme", budget=spent)
            self.assertEqual(result.method, "deferred")

    def test_search_budget(self):
        budget = finder.SearchBudget(2)
        self.assertEqual([budget.take() for _ in range(3)], [True, True, False])
        self.assertEqual(budget.remaining, 0)


class LocationAndKeywordTests(unittest.TestCase):
    def test_is_israel(self):
        self.assertTrue(is_israel("Tel Aviv-Yafo"))
        self.assertTrue(is_israel("Herzliya, Tel Aviv District, Israel"))
        self.assertTrue(is_israel(None, "Remote", country="IL"))
        self.assertTrue(is_israel("פתח תקווה"))
        self.assertFalse(is_israel("New York, NY", "London"))
        self.assertFalse(is_israel(None))

    def test_looks_student(self):
        for title in ["Software Engineering Student", "Data Intern", "Part-Time Developer",
                      "סטודנט/ית לפיתוח תוכנה", "Internship - AI"]:
            self.assertTrue(looks_student(title), title)
        for title in ["Internal Tools Engineer", "Senior Backend Engineer", "International Sales"]:
            self.assertFalse(looks_student(title), title)
        # ATS employment-type fields count too (Ashby writes "PartTime")
        self.assertTrue(looks_student("Data Analyst", "PartTime"))
        self.assertTrue(looks_student("Data Analyst", "Internship"))
        self.assertFalse(looks_student("Data Analyst", "FullTime"))


if __name__ == "__main__":
    unittest.main()
