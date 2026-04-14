"""Chatwoot API helpers shared across the application."""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_CHATWOOT_BASE = "https://chatwoot-chatwoot.spurtz.easypanel.host/api/v1/accounts/1"


async def trigger_human_handoff(conversation_id: str) -> dict:
    """
    Execute all Chatwoot API calls needed for a human handoff:
    1. Toggle conversation status to open
    2. Assign human agent (ID 1)
    3. Set priority to high
    4. Apply jump_in_chat label
    5. Post private note for the human agent
    """
    chatwoot_token = os.getenv("CHATWOOT_API_TOKEN", "")
    if not chatwoot_token:
        logger.warning("[handoff] CHATWOOT_API_TOKEN not set")
        return {"ok": False, "error": "CHATWOOT_API_TOKEN not set"}

    logger.info("[handoff] Starting handoff for conversation_id=%s", conversation_id)

    async with httpx.AsyncClient() as client:
        headers = {"api_access_token": chatwoot_token}

        toggle_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/toggle_status",
            json={"status": "open"},
            headers=headers,
            timeout=10.0,
        )
        logger.debug("[handoff] Toggle status HTTP %s: %s", toggle_res.status_code, toggle_res.text)
        if toggle_res.status_code >= 400:
            logger.error("[handoff] Toggle status failed: %s %s", toggle_res.status_code, toggle_res.text)

        # Assign to agent 7 (Laura) for personal notification
        assign_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/assignments",
            json={"assignee_id": 7},
            headers=headers,
            timeout=10.0,
        )
        logger.debug("[handoff] Agent assignment HTTP %s: %s", assign_res.status_code, assign_res.text)
        if assign_res.status_code >= 400:
            logger.error("[handoff] Agent assignment failed: %s %s", assign_res.status_code, assign_res.text)

        # Assign to team 1 (shared queue) as a separate call
        team_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/assignments",
            json={"team_id": 1},
            headers=headers,
            timeout=10.0,
        )
        logger.debug("[handoff] Team assignment HTTP %s: %s", team_res.status_code, team_res.text)
        if team_res.status_code >= 400:
            logger.error("[handoff] Team assignment failed: %s %s", team_res.status_code, team_res.text)

        priority_res = await client.patch(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}",
            json={"priority": "high"},
            headers=headers,
            timeout=10.0,
        )
        logger.debug("[handoff] Priority HTTP %s: %s", priority_res.status_code, priority_res.text)
        if priority_res.status_code >= 400:
            logger.error("[handoff] Priority update failed: %s %s", priority_res.status_code, priority_res.text)

        label_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/labels",
            json={"labels": ["jump_in_chat"]},
            headers=headers,
            timeout=10.0,
        )
        logger.debug("[handoff] Label HTTP %s: %s", label_res.status_code, label_res.text)
        if label_res.status_code >= 400:
            logger.error("[handoff] Label apply failed: %s %s", label_res.status_code, label_res.text)

        note_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/messages",
            json={
                "content": "Handed off from AI agent. Please take over this conversation. @Boss Admin",
                "message_type": "outgoing",
                "private": True,
            },
            headers=headers,
            timeout=10.0,
        )
        logger.debug("[handoff] Private note HTTP %s: %s", note_res.status_code, note_res.text)
        if note_res.status_code >= 400:
            logger.error("[handoff] Private note failed: %s %s", note_res.status_code, note_res.text)

    return {"ok": True}


async def fetch_chatwoot_messages(conversation_id: str) -> list[dict]:
    """
    Fetch the actual messages from a Chatwoot conversation.

    Returns a list of dicts with keys: id, role ("user"|"assistant"), content, created_at.
    Skips activity messages (type 2/3) and private notes.
    """
    chatwoot_token = os.getenv("CHATWOOT_API_TOKEN", "")
    if not chatwoot_token:
        logger.warning("[chatwoot] CHATWOOT_API_TOKEN not set — cannot fetch messages")
        return []

    async with httpx.AsyncClient() as client:
        headers = {"api_access_token": chatwoot_token}
        res = await client.get(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/messages",
            headers=headers,
            timeout=10.0,
        )
        if res.status_code != 200:
            logger.warning("[chatwoot] Messages fetch failed: %s %s", res.status_code, res.text[:200])
            return []

        data = res.json()
        # Chatwoot returns either {"payload": [...]} or {"payload": {"messages": [...]}}
        payload = data.get("payload", [])
        if isinstance(payload, dict):
            raw_msgs = payload.get("messages", [])
        elif isinstance(payload, list):
            raw_msgs = payload
        else:
            raw_msgs = []

        result = []
        for msg in raw_msgs:
            msg_type = msg.get("message_type")
            private = msg.get("private", False)
            content = (msg.get("content") or "").strip()

            # 0 = incoming (user), 1 = outgoing (bot/agent)
            # Skip activity (2), template (3), and private notes
            if msg_type not in (0, 1) or private or not content:
                continue

            result.append({
                "id": msg.get("id"),
                "role": "user" if msg_type == 0 else "assistant",
                "content": content,
                "created_at": msg.get("created_at") or 0,
            })

        result.sort(key=lambda x: x["created_at"])
        return result
