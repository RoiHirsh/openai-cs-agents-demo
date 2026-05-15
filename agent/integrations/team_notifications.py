"""Team Telegram notifications (conversation started, human handoff, …)."""
from __future__ import annotations

import logging
import os
from typing import Any, Literal

from integrations.supabase_client import get_supabase_client
from integrations.telegram import escape_html, notifications_enabled, send_telegram_message

logger = logging.getLogger(__name__)

NotificationType = Literal[
    "conversation_started",
    "human_handoff",
    "error",
    "lead_qualified",
    "call_requested",
]


def build_chatwoot_url(conversation_id: str) -> str | None:
    base = os.getenv("CHATWOOT_APP_BASE_URL", "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/conversations/{conversation_id}"


def _claim_notification(conversation_id: str, event_type: str) -> bool:
    """Insert dedupe row. Returns True if this is the first claim for this pair."""
    try:
        sb = get_supabase_client()
        existing = (
            sb.table("team_notification_events")
            .select("id")
            .eq("conversation_id", conversation_id)
            .eq("event_type", event_type)
            .limit(1)
            .execute()
        )
        if existing.data:
            return False
        sb.table("team_notification_events").insert(
            {
                "conversation_id": conversation_id,
                "event_type": event_type,
            }
        ).execute()
        return True
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            return False
        logger.exception(
            "[telegram] claim_notification failed conversation_id=%s event_type=%s",
            conversation_id,
            event_type,
        )
        return False


def _format_conversation_started(payload: dict[str, Any]) -> str:
    name = escape_html(payload.get("contact_name") or "Unknown")
    phone = escape_html(payload.get("phone") or "—")
    inbox = escape_html(payload.get("inbox_name") or "WhatsApp")
    lines = [
        "🚀 <b>New conversation started</b>",
        f"Name: {name}",
        f"Phone: {phone}",
        f"Inbox: {inbox}",
    ]
    url = payload.get("chatwoot_url")
    if url:
        lines.append(f'<a href="{escape_html(url)}">Open in Chatwoot</a>')
    return "\n".join(lines)


def _format_human_handoff(payload: dict[str, Any]) -> str:
    name = escape_html(payload.get("contact_name") or "Unknown")
    phone = escape_html(payload.get("phone") or "—")
    reason = escape_html(payload.get("reason") or "AI requested human handoff")
    summary = escape_html(payload.get("summary") or "See Chatwoot conversation")
    lines = [
        "🚨 <b>Human handoff needed</b>",
        f"Name: {name}",
        f"Phone: {phone}",
        f"Reason: {reason}",
        f"Summary: {summary}",
    ]
    url = payload.get("chatwoot_url")
    if url:
        lines.append(f'<a href="{escape_html(url)}">Open in Chatwoot</a>')
    return "\n".join(lines)


def _build_message(payload: dict[str, Any]) -> str | None:
    ntype = payload.get("type")
    if ntype == "conversation_started":
        return _format_conversation_started(payload)
    if ntype == "human_handoff":
        return _format_human_handoff(payload)
    logger.warning("[telegram] unknown notification type: %s", ntype)
    return None


async def notify_team(payload: dict[str, Any]) -> None:
    """
    Send a team Telegram alert. Non-blocking callers should use asyncio.create_task.
    Dedupes by (conversation_id, type). Never raises.
    """
    if not notifications_enabled():
        logger.info("telegram_notification_disabled type=%s", payload.get("type"))
        return

    conversation_id = (payload.get("conversation_id") or "").strip()
    event_type = payload.get("type")
    if not conversation_id or not event_type:
        logger.warning(
            "telegram_notification_failed missing conversation_id or type payload=%s",
            payload,
        )
        return

    if not _claim_notification(conversation_id, str(event_type)):
        logger.info(
            "telegram_notification_skipped_duplicate conversation_id=%s event_type=%s",
            conversation_id,
            event_type,
        )
        return

    if not payload.get("chatwoot_url"):
        url = build_chatwoot_url(conversation_id)
        if url:
            payload = {**payload, "chatwoot_url": url}

    text = _build_message(payload)
    if not text:
        return

    ok = await send_telegram_message(text)
    if ok:
        logger.info(
            "telegram_notification_sent conversation_id=%s event_type=%s",
            conversation_id,
            event_type,
        )
    else:
        logger.error(
            "telegram_notification_failed conversation_id=%s event_type=%s",
            conversation_id,
            event_type,
        )
