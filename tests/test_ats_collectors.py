import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

from worker.collectors import ashby, comeet, greenhouse, lever
from worker.collectors.common import BoardNotFound

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def mock_client(routes: dict[str, tuple[int, str]]) -> httpx.Client:
    """httpx client whose responses come from `routes` (URL prefix → (status, body))."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for prefix, (status, body) in routes.items():
            if url.startswith(prefix):
                return httpx.Response(status, text=body)
        return httpx.Response(404, text="Not Found")
    return httpx.Client(transport=httpx.MockTransport(handler))


class GreenhouseTests(unittest.TestCase):
    def test_parse(self):
        jobs = greenhouse.parse_jobs(json.loads(fixture("greenhouse_jobs.json")), "Acme")
        student, sales = jobs
        self.assertEqual(student.title, "Software Engineering Student")
        self.assertEqual(student.company, "Acme")
        self.assertEqual(student.source, "greenhouse")
        self.assertEqual(student.source_job_id, "111")
        self.assertEqual(student.description, "Join our\nR&D\nteam")  # double-escaped HTML decoded
        self.assertEqual(student.posted_at.date().isoformat(), "2026-09-20")
        self.assertTrue(student.is_israel)
        self.assertFalse(sales.is_israel)

    def test_fetch_and_probe(self):
        client = mock_client({
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs": (200, fixture("greenhouse_jobs.json")),
            "https://boards-api.greenhouse.io/v1/boards/acme": (200, '{"name": "Acme, Inc."}'),
        })
        self.assertEqual(len(greenhouse.fetch_jobs(client, "acme", "Acme")), 2)
        probe = greenhouse.probe(client, "acme")
        self.assertEqual((probe.company_name, probe.job_count, probe.israel_jobs), ("Acme, Inc.", 2, 1))
        self.assertIsNone(greenhouse.probe(client, "nobody"))
        with self.assertRaises(BoardNotFound):
            greenhouse.fetch_jobs(client, "nobody", "Nobody")


class LeverTests(unittest.TestCase):
    def test_parse(self):
        intern, android = lever.parse_jobs(json.loads(fixture("lever_postings.json")), "Acme")
        self.assertEqual(intern.title, "Data Analyst Intern")
        self.assertEqual(intern.employment_type, "Internship")
        self.assertEqual(intern.workplace, "hybrid")
        self.assertEqual(intern.country, "IL")
        self.assertEqual(intern.description, "Analyze data.\n\nEqual opportunity.")
        self.assertEqual(intern.posted_at, datetime(2025, 9, 30, 8, 0, tzinfo=timezone.utc))
        self.assertTrue(intern.is_israel)
        self.assertFalse(android.is_israel)

    def test_falls_back_to_eu_instance(self):
        client = mock_client({"https://api.eu.lever.co/v0/postings/acme": (200, fixture("lever_postings.json"))})
        self.assertEqual(len(lever.fetch_jobs(client, "acme", "Acme")), 2)
        with self.assertRaises(BoardNotFound):
            lever.fetch_jobs(client, "nobody", "Nobody")


class AshbyTests(unittest.TestCase):
    def test_parse_skips_unlisted_and_reads_secondary_locations(self):
        jobs = ashby.parse_jobs(json.loads(fixture("ashby_board.json")), "Acme")
        self.assertEqual([j.title for j in jobs], ["AI Engineer (Student)", "Security Engineer"])
        remote_il, ny = jobs
        self.assertTrue(remote_il.is_israel)          # Israel only via secondaryLocations
        self.assertEqual(remote_il.employment_type, "PartTime")
        self.assertEqual(remote_il.country, "USA")
        self.assertFalse(ny.is_israel)

    def test_probe(self):
        client = mock_client({"https://api.ashbyhq.com/posting-api/job-board/acme": (200, fixture("ashby_board.json"))})
        probe = ashby.probe(client, "acme")
        self.assertEqual((probe.job_count, probe.israel_jobs), (2, 1))
        self.assertIsNone(ashby.probe(client, "nobody"))


class ComeetTests(unittest.TestCase):
    def test_parse_page(self):
        name, jobs = comeet.parse_page(fixture("comeet_page.html"))
        self.assertEqual(name, "Acme Cyber")
        self.assertEqual([j.title for j in jobs], ["Student Developer", "Sales Manager"])  # internal skipped
        dev = jobs[0]
        self.assertEqual(dev.company, "Acme Cyber")
        self.assertEqual(dev.url, "https://acme.com/careers/78.66E/")
        self.assertEqual(dev.canonical_url, "https://www.comeet.com/jobs/acme/C0.008/student-developer/78.66E")
        self.assertEqual(dev.employment_type, "Part time")
        self.assertIn("semicolons ] inside strings", dev.description)
        self.assertIn("Requirements\nPython", dev.description)
        self.assertTrue(dev.is_israel)
        self.assertFalse(jobs[1].is_israel)

    def test_page_without_data_is_not_a_board(self):
        with self.assertRaises(BoardNotFound):
            comeet.parse_page("<html>no jobs here</html>")

    def test_fetch(self):
        client = mock_client({"https://www.comeet.com/jobs/acme/C0.008": (200, fixture("comeet_page.html"))})
        jobs = comeet.fetch_jobs(client, "acme/C0.008", "Acme")
        self.assertEqual(jobs[0].company, "Acme")
        with self.assertRaises(BoardNotFound):
            comeet.fetch_jobs(client, "gone/00.000", "Gone")


class ComeetResolveTests(unittest.TestCase):
    API_POSITIONS = json.dumps([{
        "name": "Student Developer", "uid": "78.66E", "company_name": "Acme Cyber",
        "location": {"name": "Tel Aviv", "country": "IL", "city": "Tel Aviv"},
        "url_comeet_hosted_page": "https://www.comeet.com/jobs/acme/C0.008/student-developer/78.66E",
        "details": [{"name": "Description", "value": "<p>Code</p>"}],
    }])

    def test_api_token_form(self):
        client = mock_client({"https://www.comeet.co/careers-api/2.0/company/C0.008/positions": (200, self.API_POSITIONS)})
        jobs = comeet.fetch_jobs(client, "C0.008:ABCDEF0123456789ABCDEF", "Acme")
        self.assertEqual((jobs[0].title, jobs[0].company, jobs[0].description), ("Student Developer", "Acme", "Description\nCode"))
        self.assertEqual(comeet.probe(client, "C0.008:ABCDEF0123456789ABCDEF").company_name, "Acme Cyber")

    def test_resolve_prefers_slug_from_api(self):
        client = mock_client({"https://www.comeet.co/careers-api/2.0/company/C0.008/positions": (200, self.API_POSITIONS)})
        self.assertEqual(comeet.resolve(client, "C0.008", "ABCDEF0123456789ABCDEF", []), "acme/C0.008")

    def test_resolve_keeps_api_form_without_positions(self):
        client = mock_client({"https://www.comeet.co/careers-api/2.0/company/C0.008/positions": (200, "[]")})
        self.assertEqual(comeet.resolve(client, "C0.008", "TOK123", []), "C0.008:TOK123")

    def test_resolve_by_slug_guess(self):
        client = mock_client({
            "https://www.comeet.com/jobs/acme/C0.008": (200, fixture("comeet_page.html")),
            "https://www.comeet.com/jobs/acmecyber/C0.008": (200, "<html>no data</html>"),
        })
        self.assertEqual(comeet.resolve(client, "C0.008", None, ["acmecyber", "acme"]), "acme/C0.008")
        self.assertIsNone(comeet.resolve(client, "C0.008", None, ["nope"]))


if __name__ == "__main__":
    unittest.main()
