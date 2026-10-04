"""Shared HTTP client for public ATS endpoints and careers pages.

URLs come from outside (web search results, company pages, ATS data), so every request —
including each redirect hop — must go to a public internet host over http(s). This stops a
malicious URL from making the worker reach services on this computer or the home network (SSRF)."""

import ipaddress
import socket
import time
from urllib.parse import urlsplit

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
RETRY_STATUSES = {429, 500, 502, 503, 504}


class BlockedURL(httpx.RequestError):
    """Refused before connecting: not http(s), or the host resolves to a non-public address."""


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not ip.is_multicast


def check_public_url(url: str, resolve=socket.getaddrinfo) -> None:
    parts = urlsplit(str(url))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockedURL(f"blocked non-web URL: {parts.scheme or '?'}://")
    try:
        infos = resolve(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as e:
        raise BlockedURL(f"cannot resolve {parts.hostname}") from e
    if not infos or not all(_is_public_ip(info[4][0]) for info in infos):
        raise BlockedURL(f"blocked non-public host: {parts.hostname}")


def _guard(request: httpx.Request) -> None:
    check_public_url(str(request.url))


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9,he;q=0.8"},
        follow_redirects=True,
        max_redirects=5,
        event_hooks={"request": [_guard]},   # runs for the first request and every redirect
    )


def get(client: httpx.Client, url: str, attempts: int = 3, sleep=None, **kwargs) -> httpx.Response:
    """GET with retries on rate limits, server errors and dropped connections."""
    sleep = sleep or time.sleep
    for attempt in range(attempts):
        try:
            response = client.get(url, **kwargs)
        except BlockedURL:
            raise                      # never retry a refused URL
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
        else:
            if response.status_code not in RETRY_STATUSES or attempt == attempts - 1:
                return response
        sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")
