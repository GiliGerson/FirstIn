import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from worker.collectors.gmail import EmailMessage
from worker.emails import classify, linkedin_alerts
from worker.emails.prefilter import Decision, decide

FIXTURES = Path(__file__).parent / "fixtures"


def make_email(from_addr="someone@example.com", subject="", text="", html="") -> EmailMessage:
    return EmailMessage("id1", "t1", datetime(2026, 9, 30, tzinfo=timezone.utc),
                        "Sender", from_addr, subject, text, html)


class PrefilterTests(unittest.TestCase):
    def test_linkedin_alert_sender(self):
        self.assertEqual(decide(make_email("jobalerts-noreply@linkedin.com")), Decision.LINKEDIN_ALERT)

    def test_known_ats_and_board_senders(self):
        for addr in ("no-reply@greenhouse.io", "jobs@mail.comeet.co", "info@drushim.co.il", "jobs@alljobs.co.il"):
            self.assertEqual(decide(make_email(addr)), Decision.CLASSIFY, addr)

    def test_linkedin_social_notifications_are_skipped(self):
        email = make_email("notifications-noreply@linkedin.com", subject="Dana reacted to your post")
        self.assertEqual(decide(email), Decision.SKIP)

    def test_subject_keywords_whole_words_only(self):
        self.assertEqual(decide(make_email(subject="Interview invitation")), Decision.CLASSIFY)
        self.assertEqual(decide(make_email(subject="הזמנה לראיון")), Decision.CLASSIFY)
        self.assertEqual(decide(make_email(subject="Take control of your budget")), Decision.SKIP)
        self.assertEqual(decide(make_email(subject="International shipping offer")), Decision.SKIP)

    def test_body_keywords(self):
        email = make_email(subject="Hello", text="Thank you for applying to Acme!")
        self.assertEqual(decide(email), Decision.CLASSIFY)

    def test_unrelated_mail_is_skipped(self):
        self.assertEqual(decide(make_email(subject="Your receipt", text="Thanks for your order")), Decision.SKIP)


class LinkedInAlertTests(unittest.TestCase):
    def test_parse_text(self):
        jobs = linkedin_alerts.parse_text((FIXTURES / "linkedin_alert.txt").read_text(encoding="utf-8"))
        self.assertEqual([(j.title, j.company, j.location) for j in jobs], [
            ("Student Software Developer", "Acme Cyber", "Tel Aviv-Yafo, Tel Aviv District, Israel"),
            ("AI Engineer Intern", "Nova AI", "Herzliya"),
            ("Product Analyst - Student Position", "BigCo Israel", "Ramat Gan"),
            ("Media Analyst (Student Position)", "Pixel Co", "Netanya"),
        ])
        self.assertEqual(jobs[0].canonical_url, "https://www.linkedin.com/jobs/view/4012345678/")
        self.assertEqual(jobs[0].source, "linkedin")
        self.assertEqual(jobs[0].source_job_id, "4012345678")

    def test_parse_html(self):
        jobs = linkedin_alerts.parse_html((FIXTURES / "linkedin_alert.html").read_text(encoding="utf-8"))
        self.assertEqual([(j.title, j.company, j.location) for j in jobs], [
            ("Student Software Developer", "Acme Cyber", "Tel Aviv-Yafo, Israel"),
            ("AI Engineer Intern", "Nova AI", "Herzliya, Israel"),
        ])

    def test_parse_alert_falls_back_to_html(self):
        html = (FIXTURES / "linkedin_alert.html").read_text(encoding="utf-8")
        email = make_email("jobalerts-noreply@linkedin.com", text="no jobs in plain text", html=html)
        self.assertEqual(len(linkedin_alerts.parse_alert(email)), 2)

    def test_parse_alert_marks_jobs_in_israel(self):
        text = (FIXTURES / "linkedin_alert.txt").read_text(encoding="utf-8")
        jobs = linkedin_alerts.parse_alert(make_email("jobalerts-noreply@linkedin.com", text=text))
        self.assertTrue(jobs and all(j.is_israel for j in jobs))
        # Without the "in Israel" header, fall back to the location text
        foreign = text.replace("in Israel", "in Europe").replace("Netanya", "Berlin")
        jobs = linkedin_alerts.parse_alert(make_email("jobalerts-noreply@linkedin.com", text=foreign))
        self.assertEqual([j.is_israel for j in jobs], [True, True, True, False])

    def test_job_id_from_slug_url(self):
        m = linkedin_alerts.JOB_ID_RE.search("https://www.linkedin.com/jobs/view/student-developer-at-acme-4012345678")
        self.assertEqual(m.group(1), "4012345678")


class ClassifyTests(unittest.TestCase):
    def fake_client(self, parsed, stop_reason="end_turn"):
        client = mock.MagicMock()
        client.messages.parse.return_value = mock.MagicMock(parsed_output=parsed, stop_reason=stop_reason)
        return client

    def test_returns_parsed_output_and_uses_haiku(self):
        parsed = classify.EmailClassification(
            category="application_update", company="Acme", role="Student Developer",
            application_stage="interview", summary_he="זימון לראיון",
        )
        client = self.fake_client(parsed)
        result = classify.classify(client, make_email(subject="Interview", text="Let's talk"))
        self.assertEqual(result.category, "application_update")
        kwargs = client.messages.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-haiku-4-5")
        self.assertIs(kwargs["output_format"], classify.EmailClassification)

    def test_refusal_returns_none(self):
        self.assertIsNone(classify.classify(self.fake_client(None, "refusal"), make_email()))

    def test_html_only_email_is_converted_to_text(self):
        email = make_email(html="<p>Hello <b>there</b></p>")
        self.assertIn("Hello\nthere", classify.build_user_message(email))


if __name__ == "__main__":
    unittest.main()
