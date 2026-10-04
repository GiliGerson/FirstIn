import socket
import unittest

import httpx

from worker.collectors import http
from worker.models import safe_url


def fake_resolve(ip):
    return lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


class SafeUrlTests(unittest.TestCase):
    def test_only_http_links(self):
        self.assertEqual(safe_url(" https://jobs.lever.co/x "), "https://jobs.lever.co/x")
        for bad in ("javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x", "//evil.com", "ftp://x", "", None):
            self.assertIsNone(safe_url(bad), bad)


class PublicUrlGuardTests(unittest.TestCase):
    def test_public_host_allowed(self):
        http.check_public_url("https://boards-api.greenhouse.io/v1", resolve=fake_resolve("104.18.0.1"))

    def test_private_and_local_hosts_blocked(self):
        for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "::1", "0.0.0.0"):
            with self.assertRaises(http.BlockedURL, msg=ip):
                http.check_public_url("http://example.com/", resolve=fake_resolve(ip))

    def test_non_web_schemes_blocked(self):
        for url in ("file:///etc/passwd", "ftp://x.com/", "gopher://x"):
            with self.assertRaises(http.BlockedURL, msg=url):
                http.check_public_url(url, resolve=fake_resolve("104.18.0.1"))

    def test_client_checks_every_request_and_get_does_not_retry_blocked(self):
        client = http.make_client()
        calls = []
        with self.assertRaises(http.BlockedURL):
            http.get(client, "http://localhost:8080/admin", sleep=calls.append)
        self.assertEqual(calls, [])   # no retries for a refused URL


if __name__ == "__main__":
    unittest.main()
