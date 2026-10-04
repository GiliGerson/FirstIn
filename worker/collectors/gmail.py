"""Gmail collector — read-only access (gmail.readonly). Never sends or deletes mail."""

import base64
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from worker.config import path_from_env

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass
class EmailMessage:
    gmail_id: str
    thread_id: str
    received_at: datetime
    from_name: str
    from_addr: str
    subject: str
    text: str
    html: str

    @property
    def sender_domain(self) -> str:
        return self.from_addr.rpartition("@")[2].lower()


# ------------------------------------------------------------------ auth
def get_credentials(interactive: bool = True) -> Credentials:
    token_path = path_from_env("GMAIL_TOKEN_PATH")
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError("Gmail token missing or revoked — run: .venv/bin/python scripts/gmail_auth.py")
        flow = InstalledAppFlow.from_client_secrets_file(str(path_from_env("GMAIL_CREDENTIALS_PATH")), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
    fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())
    return creds


def get_service(interactive: bool = False):
    return build("gmail", "v1", credentials=get_credentials(interactive), cache_discovery=False)


# ------------------------------------------------------------------ parsing (pure — unit tested)
def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _collect_bodies(part: dict, out: dict) -> None:
    mime = part.get("mimeType", "")
    data = part.get("body", {}).get("data")
    if data and mime in ("text/plain", "text/html") and not part.get("filename"):
        out.setdefault(mime, _decode(data))
    for sub in part.get("parts", []) or []:
        _collect_bodies(sub, out)


def parse_message(raw: dict) -> EmailMessage:
    """Convert a Gmail API message into an EmailMessage.

    With format=full the text/html bodies are filled; with format=metadata only the
    headers are available, so `text` holds Gmail's short snippet instead."""
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    bodies: dict = {}
    _collect_bodies(payload, bodies)
    if not bodies and raw.get("snippet"):
        bodies["text/plain"] = raw["snippet"]
    received = datetime.fromtimestamp(int(raw.get("internalDate", "0")) / 1000, tz=timezone.utc)
    return EmailMessage(
        gmail_id=raw["id"],
        thread_id=raw.get("threadId", ""),
        received_at=received,
        from_name=name,
        from_addr=addr.lower(),
        subject=headers.get("subject", ""),
        text=bodies.get("text/plain", ""),
        html=bodies.get("text/html", ""),
    )


def build_query(since: datetime) -> str:
    # Gmail's `after:` accepts epoch seconds. Skip mail I sent myself.
    return f"after:{int(since.timestamp())} -in:sent -in:drafts"


# ------------------------------------------------------------------ fetching
def list_message_ids(service, query: str) -> list[str]:
    ids, page_token = [], None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, pageToken=page_token, maxResults=500
        ).execute(num_retries=NETWORK_RETRIES)
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            return ids


BATCH_SIZE = 10       # Gmail rejects larger batches with "Too many concurrent requests"
BATCH_PAUSE = 0.3     # seconds between batches, to stay under the per-user concurrency limit
MAX_ATTEMPTS = 6
NETWORK_RETRIES = 3   # retries on timeouts / dropped connections


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, HttpError) and exc.resp.status in (429, 403) and "rate" in str(exc).lower()


def fetch_metadata(service, msg_ids: list[str], sleep=None) -> list[EmailMessage]:
    """Headers + snippet only, fetched in batches — cheap enough to pre-filter hundreds of emails.
    Rate-limited requests are retried with backoff."""
    sleep = sleep or time.sleep
    results: dict[str, EmailMessage] = {}
    pending = list(msg_ids)

    for attempt in range(MAX_ATTEMPTS):
        retry: list[str] = []
        errors: list[Exception] = []

        def on_response(request_id, response, exception):
            if exception is None:
                results[request_id] = parse_message(response)
            elif _is_rate_limited(exception):
                retry.append(request_id)
            else:
                errors.append(exception)

        for start in range(0, len(pending), BATCH_SIZE):
            if start:
                sleep(BATCH_PAUSE)
            batch = service.new_batch_http_request(callback=on_response)
            for msg_id in pending[start:start + BATCH_SIZE]:
                batch.add(
                    service.users().messages().get(
                        userId="me", id=msg_id, format="metadata", metadataHeaders=["From", "Subject"]
                    ),
                    request_id=msg_id,
                )
            batch.execute()
        if errors:
            raise errors[0]
        if not retry:
            break
        pending = retry
        sleep(2 ** attempt)
    else:
        raise RuntimeError(f"Gmail rate limit: {len(pending)} messages still failing after {MAX_ATTEMPTS} attempts")
    return [results[i] for i in msg_ids if i in results]


def execute_with_retry(request, sleep=None):
    """Execute one Gmail API request, backing off on per-minute quota errors."""
    sleep = sleep or time.sleep
    for attempt in range(MAX_ATTEMPTS):
        try:
            # num_retries: the client library itself retries timeouts and dropped connections
            return request.execute(num_retries=NETWORK_RETRIES)
        except HttpError as e:
            if not _is_rate_limited(e) or attempt == MAX_ATTEMPTS - 1:
                raise
            sleep(min(2 ** (attempt + 1), 30))


def fetch_full(service, msg_id: str, sleep=None) -> EmailMessage:
    request = service.users().messages().get(userId="me", id=msg_id, format="full")
    return parse_message(execute_with_retry(request, sleep))


def fetch_messages(service, since: datetime) -> list[EmailMessage]:
    """Metadata for every email since `since` (use fetch_full for the ones worth reading)."""
    return fetch_metadata(service, list_message_ids(service, build_query(since)))
