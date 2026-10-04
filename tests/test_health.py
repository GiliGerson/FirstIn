import unittest
from unittest import mock

from worker import scheduler
from worker.health import HealthMonitor

FAIL = {"errors": [{"error": "HttpError 403"}], "finished_at": "x"}
OK = {"errors": [], "finished_at": "x"}


class HealthTests(unittest.TestCase):
    def run_check(self, monitor, runs):
        with mock.patch.object(monitor, "recent_runs", return_value=runs), \
             mock.patch("worker.health.telegram.send") as send:
            monitor.check("gmail")
        return send

    def test_alerts_once_after_three_failures_then_on_recovery(self):
        m = HealthMonitor()
        self.run_check(m, [FAIL, FAIL]).assert_not_called()                 # only 2 runs so far
        send = self.run_check(m, [FAIL, FAIL, FAIL])
        self.assertIn("Gmail נכשל 3 פעמים ברצף", send.call_args.args[0])
        self.run_check(m, [FAIL, FAIL, FAIL]).assert_not_called()           # no repeat alerts
        recovered = self.run_check(m, [OK, FAIL, FAIL])
        self.assertIn("חזר לעבוד", recovered.call_args.args[0])

    def test_no_alert_when_one_run_succeeded(self):
        self.run_check(HealthMonitor(), [FAIL, OK, FAIL]).assert_not_called()

    def test_gmail_token_hint(self):
        runs = [{"errors": [{"error": "RefreshError: invalid_grant"}], "finished_at": "x"}] * 3
        send = self.run_check(HealthMonitor(), runs)
        self.assertIn("החיבור ל-Gmail פג", send.call_args.args[0])


class SchedulerTests(unittest.TestCase):
    def test_safe_wrapper_swallows_errors(self):
        def boom():
            raise RuntimeError("x")
        with self.assertLogs("firstin", level="ERROR"):
            scheduler.safe(boom)()   # must not raise


if __name__ == "__main__":
    unittest.main()
