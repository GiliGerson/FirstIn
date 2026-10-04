import unittest
from unittest import mock

import httpx

from worker import db


class ExecuteRetryTests(unittest.TestCase):
    def test_retries_dropped_connection(self):
        query = mock.MagicMock()
        query.execute.side_effect = [httpx.RemoteProtocolError("Server disconnected"), "ok"]
        sleeps = []
        self.assertEqual(db.execute(query, sleep=sleeps.append), "ok")
        self.assertEqual(sleeps, [1])

    def test_gives_up_after_attempts(self):
        query = mock.MagicMock()
        query.execute.side_effect = httpx.ConnectError("down")
        with self.assertRaises(httpx.ConnectError):
            db.execute(query, attempts=2, sleep=lambda s: None)
        self.assertEqual(query.execute.call_count, 2)


if __name__ == "__main__":
    unittest.main()
