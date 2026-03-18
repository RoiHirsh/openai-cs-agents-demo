"""Chatwoot API helpers shared across the application."""
from __future__ import annotations

import os

import httpx

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
        print("[handoff] CHATWOOT_API_TOKEN not set", flush=True)
        return {"ok": False, "error": "CHATWOOT_API_TOKEN not set"}

    print(f"[handoff] Starting handoff for conversation_id={conversation_id}", flush=True)

    async with httpx.AsyncClient() as client:
        headers = {"api_access_token": chatwoot_token}

        toggle_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/toggle_status",
            json={"status": "open"},
            headers=headers,
            timeout=10.0,
        )
        print(f"[handoff] Toggle status HTTP {toggle_res.status_code}: {toggle_res.text}", flush=True)

        assign_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/assignments",
            json={"assignee_id": 1},
            headers=headers,
            timeout=10.0,
        )
        print(f"[handoff] Assignment HTTP {assign_res.status_code}: {assign_res.text}", flush=True)

        priority_res = await client.patch(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}",
            json={"priority": "high"},
            headers=headers,
            timeout=10.0,
        )
        print(f"[handoff] Priority HTTP {priority_res.status_code}: {priority_res.text}", flush=True)

        label_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/labels",
            json={"labels": ["jump_in_chat"]},
            headers=headers,
            timeout=10.0,
        )
        print(f"[handoff] Label HTTP {label_res.status_code}: {label_res.text}", flush=True)

        note_res = await client.post(
            f"{_CHATWOOT_BASE}/conversations/{conversation_id}/messages",
            json={
                "content": "Handed off from AI agent. Please take over this conversation.",
                "message_type": "outgoing",
                "private": True,
            },
            headers=headers,
            timeout=10.0,
        )
        print(f"[handoff] Private note HTTP {note_res.status_code}: {note_res.text}", flush=True)

    return {"ok": True}
