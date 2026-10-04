"""Shared HTTP client for public ATS endpoints and careers pages."""

import time

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
RETRY_STATUSES = {429, 500, 502, 503, 504}


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9,he;q=0.8"},
        follow_redirects=True,
    )


def get(client: httpx.Client, url: str, attempts: int = 3, sleep=None, **kwargs) -> httpx.Response:
    """GET with retries on rate limits, server errors and dropped connections."""
    sleep = sleep or time.sleep
    for attempt in range(attempts):
        try:
            response = client.get(url, **kwargs)
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
        else:
            if response.status_code not in RETRY_STATUSES or attempt == attempts - 1:
                return response
        sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")
