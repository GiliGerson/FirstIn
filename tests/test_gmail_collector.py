import base64
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import httplib2
from googleapiclient.errors import HttpError

from worker.collectors import gmail

FIXTURES = Path(__file__).parent / "fixtures"


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode().rstrip("=")


def raw_message(**overrides) -> dict:
    """A Gmail API message in format=full, multipart/alternative with an attachment."""
    msg = {
        "id": "18f0abc",
        "threadId": "18f0abc",
        "internalDate": "1759219200000",  # 2025-09-30 08:00:00 UTC
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "LinkedIn Job Alerts <JobAlerts-noreply@linkedin.com>"},
                {"name": "Subject", "value": "3 new jobs for student software developer"},
            ],
            "parts": [
                {"mimeType": "multipart/alternative", "parts": [
                    {"mimeType": "text/plain", "body": {"data": b64("שלום — plain body")}},
                    {"mimeType": "text/html", "body": {"data": b64("<p>html body</p>")}},
                ]},
                {"mimeType": "text/plain", "filename": "cv.txt", "body": {"attachmentId": "x"}},
            ],
        },
    }
    msg.update(overrides)
    return msg


class ParseMessageTests(unittest.TestCase):
    def test_headers_bodies_and_date(self):
        email = gmail.parse_message(raw_message())
        self.assertEqual(email.gmail_id, "18f0abc")
        self.assertEqual(email.from_name, "LinkedIn Job Alerts")
        self.assertEqual(email.from_addr, "jobalerts-noreply@linkedin.com")  # lower-cased
        self.assertEqual(email.sender_domain, "linkedin.com")
        self.assertEqual(email.subject, "3 new jobs for student software developer")
        self.assertEqual(email.text, "שלום — plain body")  # unicode + missing base64 padding
        self.assertEqual(email.html, "<p>html body</p>")
        self.assertEqual(email.received_at, datetime(2025, 9, 30, 8, 0, tzinfo=timezone.utc))

    def test_single_part_message(self):
        raw = raw_message(payload={
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": "a@b.com"}],
            "body": {"data": b64("just text")},
        })
        email = gmail.parse_message(raw)
        self.assertEqual(email.text, "just text")
        self.assertEqual(email.html, "")
        self.assertEqual(email.subject, "")

    def test_build_query(self):
        since = datetime(2025, 9, 30, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(gmail.build_query(since), "after:1759219200 -in:sent -in:drafts")


class FakeBatch:
    """Stands in for googleapiclient's BatchHttpRequest: replays recorded responses."""

    def __init__(self, callback, responses):
        self.callback, self.responses, self.ids = callback, responses, []

    def add(self, request, request_id):
        self.ids.append(request_id)

    def execute(self):
        for request_id in self.ids:
            self.callback(request_id, self.responses[request_id], None)


def metadata_message(msg_id: str) -> dict:
    """A Gmail API message in format=metadata: headers + snippet, no bodies."""
    return {
        "id": msg_id, "threadId": msg_id, "internalDate": "1759219200000",
        "snippet": "Thank you for applying to Acme",
        "payload": {"mimeType": "multipart/alternative", "headers": [
            {"name": "From", "value": "Acme Recruiting <jobs@acme.com>"},
            {"name": "Subject", "value": "Your application"},
        ]},
    }


class FetchTests(unittest.TestCase):
    def make_service(self, pages, responses):
        service = mock.MagicMock()
        service.new_batch_http_request.side_effect = lambda callback: FakeBatch(callback, responses)
        messages = service.users.return_value.messages.return_value
        messages.list.return_value.execute.side_effect = pages
        return service, messages

    def test_paginates_and_fetches_metadata_in_batches(self):
        responses = {i: metadata_message(i) for i in ("a", "b", "c")}
        service, messages = self.make_service([
            {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "p2"},
            {"messages": [{"id": "c"}]},
        ], responses)

        result = gmail.fetch_messages(service, datetime(2025, 9, 30, tzinfo=timezone.utc))

        self.assertEqual([m.gmail_id for m in result], ["a", "b", "c"])
        self.assertEqual(messages.list.call_count, 2)
        self.assertEqual(messages.list.call_args_list[1].kwargs["pageToken"], "p2")
        self.assertEqual(messages.get.call_args.kwargs["format"], "metadata")
        # With no bodies, the snippet stands in for the text (used by the pre-filter)
        self.assertEqual(result[0].text, "Thank you for applying to Acme")
        self.assertEqual(result[0].from_addr, "jobs@acme.com")

    def test_batches_of_10(self):
        ids = [f"m{i}" for i in range(25)]
        service, _ = self.make_service([{"messages": [{"id": i} for i in ids]}],
                                       {i: metadata_message(i) for i in ids})
        with mock.patch("worker.collectors.gmail.time.sleep"):
            result = gmail.fetch_messages(service, datetime(2025, 9, 30, tzinfo=timezone.utc))
        self.assertEqual(len(result), 25)
        self.assertEqual(service.new_batch_http_request.call_count, 3)

    def test_rate_limited_requests_are_retried(self):
        rate_limited = HttpError(
            httplib2.Response({"status": 429}),
            json.dumps({"error": {"message": "Too many concurrent requests for user.",
                                  "errors": [{"reason": "rateLimitExceeded"}]}}).encode(),
        )
        calls = {"n": 0}

        class FlakyBatch(FakeBatch):
            def execute(self):
                calls["n"] += 1
                for request_id in self.ids:
                    if calls["n"] == 1 and request_id == "b":
                        self.callback(request_id, None, rate_limited)
                    else:
                        self.callback(request_id, self.responses[request_id], None)

        responses = {i: metadata_message(i) for i in ("a", "b")}
        service = mock.MagicMock()
        service.new_batch_http_request.side_effect = lambda callback: FlakyBatch(callback, responses)
        sleeps = []

        result = gmail.fetch_metadata(service, ["a", "b"], sleep=sleeps.append)

        self.assertEqual([m.gmail_id for m in result], ["a", "b"])
        self.assertEqual(sleeps, [1])

    def test_fetch_full_retries_on_quota_error(self):
        quota = HttpError(
            httplib2.Response({"status": 403}),
            json.dumps({"error": {"message": "Quota exceeded for quota metric 'Total Query Cost'",
                                  "errors": [{"reason": "rateLimitExceeded"}]}}).encode(),
        )
        service = mock.MagicMock()
        request = service.users.return_value.messages.return_value.get.return_value
        request.execute.side_effect = [quota, quota, raw_message()]
        sleeps = []

        email = gmail.fetch_full(service, "18f0abc", sleep=sleeps.append)

        self.assertEqual(email.gmail_id, "18f0abc")
        self.assertEqual(sleeps, [2, 4])

    def test_fetch_full_does_not_retry_other_errors(self):
        not_found = HttpError(httplib2.Response({"status": 404}), b'{"error": {"message": "Not Found"}}')
        service = mock.MagicMock()
        service.users.return_value.messages.return_value.get.return_value.execute.side_effect = not_found
        with self.assertRaises(HttpError):
            gmail.fetch_full(service, "x", sleep=lambda s: None)


if __name__ == "__main__":
    unittest.main()
