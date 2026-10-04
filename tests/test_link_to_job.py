import unittest
from unittest import mock

from worker.emails import link_to_job as l
from worker.emails.classify import EmailClassification
from worker.notify import alerts


def classification(stage, company="Acme", role="Student Developer"):
    return EmailClassification(category="application_update", company=company, role=role,
                               application_stage=stage, summary_he="x")


class StageRulesTests(unittest.TestCase):
    def test_moves_forward(self):
        self.assertEqual(l.next_stage("applied", "interview"), "interview")
        self.assertEqual(l.next_stage("screening", "home_assignment"), "home_assignment")

    def test_never_moves_backwards(self):
        self.assertEqual(l.next_stage("interview", "applied"), "interview")      # late "we got it"
        self.assertEqual(l.next_stage("home_assignment", "screening"), "home_assignment")

    def test_rejection_closes_any_open_stage_but_final_stays(self):
        self.assertEqual(l.next_stage("interview", "rejected"), "rejected")
        self.assertEqual(l.next_stage("ghosted", "interview"), "interview")      # they came back
        self.assertEqual(l.next_stage("offer", "rejected"), "offer")
        self.assertEqual(l.next_stage("rejected", "interview"), "rejected")


class MatchingTests(unittest.TestCase):
    def test_title_similarity(self):
        self.assertGreater(l.title_similarity("Student Developer", "Software Developer (Student)"), 0.5)
        self.assertEqual(l.title_similarity("Student Developer", "Account Executive"), 0)
        self.assertEqual(l.title_similarity(None, "x"), 0)

    def test_best_by_title(self):
        rows = [{"t": "Account Executive"}, {"t": "Software Developer - Student"}]
        title = lambda r: r["t"]
        self.assertEqual(l.best_by_title(rows, "Student Software Developer", title), rows[1])
        self.assertIsNone(l.best_by_title(rows, "Data Analyst", title))            # ambiguous → no guess
        self.assertEqual(l.best_by_title(rows[:1], "Data Analyst", title), rows[0])  # only one at that company
        self.assertEqual(l.best_by_title(rows, None, title), rows[0])              # no role → most recent
        self.assertIsNone(l.best_by_title([], "x", title))


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.db = mock.patch.object(l, "db").start()
        self.addCleanup(mock.patch.stopall)
        index = mock.MagicMock()
        index.find.return_value = {"id": 5, "name": "Acme"}
        mock.patch.object(l, "CompanyIndex", return_value=index).start()
        mock.patch.object(l.companies_repo, "all_companies", return_value=[]).start()

    def test_moves_existing_application(self):
        apps = [{"id": 1, "stage": "applied", "job_id": 9, "jobs": {"title": "Student Developer", "company_id": 5}}]
        with mock.patch.object(l, "_company_applications", return_value=apps):
            link = l.link_application_update("g1", "Interview", classification("interview"))
        self.assertEqual((link.application_id, link.from_stage, link.to_stage, link.moved), (1, "applied", "interview", True))
        updates = [c.args[0] for c in self.db.client.return_value.table.return_value.update.call_args_list]
        self.assertIn({"stage": "interview"}, updates)
        self.assertIn({"linked_application_id": 1, "linked_job_id": 9}, updates)

    def test_creates_application_when_none_exists(self):
        with mock.patch.object(l, "_company_applications", return_value=[]), \
             mock.patch.object(l, "_company_jobs", return_value=[{"id": 9, "title": "Student Developer"}]), \
             mock.patch.object(l, "_open_application", return_value=77) as open_app:
            link = l.link_application_update("g1", "We got it", classification("received"),
                                             "2026-09-23T10:00:00+00:00")
        open_app.assert_called_once_with(9, "applied", "2026-09-23T10:00:00+00:00")
        self.assertTrue(link.created)
        self.assertEqual(link.application_id, 77)

    def test_without_company_or_stage_nothing_happens(self):
        self.assertIsNone(l.link_application_update("g", "s", classification("none")))
        self.assertIsNone(l.link_application_update("g", "s", classification("interview", company=None)))


class PipelineNoteTests(unittest.TestCase):
    def test_notes(self):
        self.assertIn("עבר ל: ראיון", alerts.pipeline_note(l.LinkResult(1, 2, "applied", "interview")))
        self.assertIn("פתחתי כרטיס חדש", alerts.pipeline_note(l.LinkResult(1, 2, None, "applied", created=True)))
        self.assertIn("קושר", alerts.pipeline_note(l.LinkResult(1, 2, "interview", "interview")))
        self.assertIn("לא מצאתי", alerts.pipeline_note(None))


if __name__ == "__main__":
    unittest.main()
