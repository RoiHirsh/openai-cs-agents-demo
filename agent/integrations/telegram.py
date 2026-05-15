"""Telegram Bot API helpers for team notifications."""
from __future__ import annotations

import logging
import os
from html import escape

import httpx

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def notifications_enabled() -> bool:
    return os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "").lower() in ("1", "true", "yes")


def escape_html(text: str | None) -> str:
    if not text:
        return ""
    return escape(str(text), quote=False)


async def send_telegram_message(text: str) -> bool:
    """Send HTML message to the team channel. Returns True on success."""
    if not notifications_enabled():
        logger.info("telegram_notification_disabled")
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_TEAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.warning("telegram_notification_failed missing TELEGRAM_BOT_TOKEN or TELEGRAM_TEAM_CHAT_ID")
        return False

    url = _TELEGRAM_API.format(token=token)
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10.0,
            )
        if res.status_code == 200:
            return True
        logger.error(
            "telegram_notification_failed HTTP %s: %s",
            res.status_code,
            res.text[:500],
        )
        return False
    except Exception:
        logger.exception("telegram_notification_failed")
        return False
