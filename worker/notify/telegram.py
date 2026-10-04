"""Telegram Bot API client. Messages use HTML parse mode."""

import html
import time

import httpx

from worker.config import env

API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_CHARS = 4096


class TelegramError(Exception):
    pass


def esc(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def call(method: str, payload: dict | None = None, timeout: float = 30.0, attempts: int = 3) -> dict:
    url = API.format(token=env("TELEGRAM_BOT_TOKEN"), method=method)
    for attempt in range(attempts):
        try:
            response = httpx.post(url, json=payload or {}, timeout=timeout)
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
            continue
        data = response.json()
        if data.get("ok"):
            return data["result"]
        retry_after = (data.get("parameters") or {}).get("retry_after")
        if response.status_code == 429 and retry_after and attempt < attempts - 1:
            time.sleep(retry_after)
            continue
        raise TelegramError(f"{method}: {data.get('description')}")
    raise TelegramError(f"{method}: failed after {attempts} attempts")


def owner_chat_id() -> str:
    return env("TELEGRAM_CHAT_ID")


def send(text: str, buttons: list[list[dict]] | None = None, silent: bool = False,
         chat_id: str | int | None = None) -> dict:
    """Send to `chat_id` (a user's chat), or to the owner's chat by default."""
    payload = {
        "chat_id": chat_id or owner_chat_id(),
        "text": text[:MAX_MESSAGE_CHARS],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": silent,
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return call("sendMessage", payload)


def edit_buttons(message_chat_id: int, message_id: int, buttons: list[list[dict]]) -> None:
    call("editMessageReplyMarkup", {"chat_id": message_chat_id, "message_id": message_id,
                                     "reply_markup": {"inline_keyboard": buttons}})


def answer_callback(callback_id: str, text: str) -> None:
    call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def get_updates(offset: int | None, timeout: int = 25) -> list[dict]:
    payload = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    if offset is not None:
        payload["offset"] = offset
    return call("getUpdates", payload, timeout=timeout + 10)


def split_message(blocks: list[str], header: str = "", limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Pack text blocks into as few messages as possible without splitting a block."""
    messages, current = [], header
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit and current:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages
