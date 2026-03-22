from __future__ import annotations as _annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from chatkit.server import StreamingResult
import httpx
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from chatkit.types import ThreadMetadata
from server import ConversationState
from supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

from lucentive.agents import (
    investments_faq_agent,
    onboarding_agent,
    scheduling_agent,
    triage_agent,
)
from lucentive.context import (
    LucentiveAgentChatContext,
    LucentiveAgentContext,
    create_initial_context,
    public_context,
)
from server import LucentiveServer
from lucentive.context_cache import clear_thread_cache
from chatwoot import trigger_human_handoff
from knowledge import router as knowledge_router

app = FastAPI()

# Disable tracing for zero data retention orgs
os.environ.setdefault("OPENAI_TRACING_DISABLED", "1")

# CORS configuration (adjust as needed for deployment)
_DASHBOARD_ORIGIN = os.environ.get("DASHBOARD_ORIGIN", "")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://10.164.64.44:3000",
        # Allow any localhost or local network IP (for development)
        r"http://localhost:\d+",
        r"http://127\.0\.0\.1:\d+",
        r"http://10\.\d+\.\d+\.\d+:\d+",
        r"http://192\.168\.\d+\.\d+:\d+",
        # Dashboard Railway service (set DASHBOARD_ORIGIN env var in production)
        *([_DASHBOARD_ORIGIN] if _DASHBOARD_ORIGIN else []),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge_router)

chat_server = LucentiveServer()


def get_server() -> LucentiveServer:
    return chat_server


@app.post("/chatkit")
async def chatkit_endpoint(
    request: Request, server: LucentiveServer = Depends(get_server)
) -> Response:
    try:
        payload = await request.body()
        result = await server.process(payload, {"request": request})
        if isinstance(result, StreamingResult):
            return StreamingResponse(result, media_type="text/event-stream")
        if hasattr(result, "json"):
            return Response(content=result.json, media_type="application/json")
        return Response(content=result)
    except Exception:
        logger.exception("Unhandled exception in /chatkit endpoint")
        return Response(
            content=json.dumps({"error": "Internal server error"}),
            status_code=500,
            media_type="application/json",
        )


@app.get("/chatkit/state")
async def chatkit_state(
    thread_id: str = Query(...),
    server: LucentiveServer = Depends(get_server),
) -> Dict[str, Any]:
    try:
        return await server.snapshot(thread_id, {"request": None})
    except Exception:
        logger.exception("Unhandled exception in /chatkit/state endpoint", extra={"thread_id": thread_id})
        raise


@app.get("/chatkit/bootstrap")
async def chatkit_bootstrap(
    first_name: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    phone: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    new_lead: bool = Query(False),
    server: LucentiveServer = Depends(get_server),
) -> Dict[str, Any]:
    try:
        context = {
            "request": None,
            "lead_info": {
                "first_name": first_name,
                "email": email,
                "phone": phone,
                "country": country,
                "new_lead": new_lead,
            } if any([first_name, email, phone, country]) else None,
        }
        return await server.snapshot(None, context)
    except Exception:
        logger.exception(
            "Unhandled exception in /chatkit/bootstrap endpoint",
            extra={
                "first_name": first_name,
                "country": country,
                "new_lead": new_lead,
            },
        )
        raise


@app.get("/chatkit/state/stream")
async def chatkit_state_stream(
    thread_id: str = Query(...),
    server: LucentiveServer = Depends(get_server),
):
    try:
        thread = await server.ensure_thread(thread_id, {"request": None})
        queue = server.register_listener(thread.id)

        async def event_generator():
            try:
                initial = await server.snapshot(thread.id, {"request": None})
                yield f"data: {json.dumps(initial, default=str)}\n\n"
                while True:
                    data = await queue.get()
                    yield f"data: {data}\n\n"
            except Exception:
                logger.exception("Exception in state stream event generator", extra={"thread_id": thread.id})
                raise
            finally:
                server.unregister_listener(thread.id, queue)

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception:
        logger.exception("Unhandled exception in /chatkit/state/stream endpoint", extra={"thread_id": thread_id})
        raise


@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}


from chatwoot import _CHATWOOT_BASE  # single source of truth

_N8N_WEBHOOK_URL = "https://wlog.app.n8n.cloud/webhook/facebook-lead"




async def _handle_reset(phone_number: str, sb, server: LucentiveServer) -> Dict[str, Any]:
    """Full reset sequence for a lead. Dev-only (requires RESET_ENABLED=true)."""
    chatwoot_token = os.getenv("CHATWOOT_API_TOKEN", "")

    # Step 1: Load lead data before deleting
    lead_row: dict | None = None
    thread_id: str | None = None
    try:
        lead_res = sb.table("leads").select("*").eq("phone_number", phone_number).limit(1).execute()
        if lead_res.data:
            lead_row = lead_res.data[0]
            thread_id = lead_row.get("thread_id")
    except Exception:
        logger.exception("[reset] Failed to load lead data")

    # Step 2: Delete lead row from Supabase
    try:
        sb.table("leads").delete().eq("phone_number", phone_number).execute()
        logger.info("[reset] Deleted lead for %s", phone_number)
    except Exception:
        logger.exception("[reset] Failed to delete lead from Supabase")

    # Step 3: Delete thread row from Supabase
    try:
        sb.table("threads").delete().eq("phone_number", phone_number).execute()
        logger.info("[reset] Deleted thread for %s", phone_number)
    except Exception:
        logger.exception("[reset] Failed to delete thread from Supabase")

    # Step 4: Clear RAM caches
    if thread_id:
        try:
            clear_thread_cache(thread_id)
            server._state.pop(thread_id, None)
            await server.store.delete_thread(thread_id, {"request": None})
            logger.info("[reset] Cleared RAM caches for thread %s", thread_id)
        except Exception:
            logger.exception("[reset] Failed to clear RAM caches")

    # Step 5: Search and delete Chatwoot contact
    if chatwoot_token:
        try:
            async with httpx.AsyncClient() as client:
                search_res = await client.get(
                    f"{_CHATWOOT_BASE}/contacts/search",
                    params={"q": phone_number},
                    headers={"api_access_token": chatwoot_token},
                    timeout=10.0,
                )
                search_json = search_res.json()
                logger.info("[reset] Chatwoot search response: %s", search_json)
                payload = search_json.get("payload", [])
                # payload is a list of contacts in Chatwoot v2/v3
                contacts = payload if isinstance(payload, list) else payload.get("contacts", [])
                if contacts:
                    contact_id = contacts[0].get("id")
                    if contact_id:
                        delete_res = await client.delete(
                            f"{_CHATWOOT_BASE}/contacts/{contact_id}",
                            headers={"api_access_token": chatwoot_token},
                            timeout=10.0,
                        )
                        logger.info("[reset] Chatwoot delete status %s for contact %s", delete_res.status_code, contact_id)
                else:
                    logger.info("[reset] No Chatwoot contact found for %s", phone_number)
        except Exception:
            logger.exception("[reset] Failed to delete Chatwoot contact")
    else:
        logger.warning("[reset] CHATWOOT_API_TOKEN not set, skipping Chatwoot deletion")

    # Step 6: POST to n8n welcome webhook
    if lead_row:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    _N8N_WEBHOOK_URL,
                    json=[{
                        "full_name": lead_row.get("full_name", ""),
                        "phone_number": lead_row.get("phone_number", ""),
                        "email": lead_row.get("email", ""),
                        "country": lead_row.get("country", ""),
                        "investment_goal": lead_row.get("investment_goal", "saving_for_the_future"),
                    }],
                    timeout=10.0,
                )
                logger.info("[reset] Posted to n8n welcome webhook for %s", phone_number)
        except Exception:
            logger.exception("[reset] Failed to post to n8n welcome webhook")
    else:
        logger.warning("[reset] No lead data available to post to n8n")

    return {"ok": True}


class ApiContextRequest(BaseModel):
    phone_number: str
    message: str
    role: str


@app.post("/api/context")
async def api_context(body: ApiContextRequest) -> Dict[str, Any]:
    sb = get_supabase_client()

    # Look up thread_id from leads
    lead_res = sb.table("leads").select("thread_id").eq("phone_number", body.phone_number).limit(1).execute()
    if not lead_res.data:
        return {"ok": False, "error": "Lead not found"}

    thread_id = lead_res.data[0].get("thread_id")
    if not thread_id:
        return {"ok": False, "error": "No thread found for this lead"}

    # Load current input_items from threads
    thread_res = sb.table("threads").select("input_items").eq("thread_id", thread_id).limit(1).execute()
    input_items = []
    if thread_res.data:
        input_items = thread_res.data[0].get("input_items") or []

    # Append the injected message
    input_items.append({"role": body.role, "content": body.message})

    # Save back to Supabase
    sb.table("threads").update({
        "input_items": input_items,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("thread_id", thread_id).execute()

    return {"ok": True}


class ApiChatRequest(BaseModel):
    phone_number: str
    message: str
    conversation_id: str


@app.post("/api/chat")
async def api_chat(
    body: ApiChatRequest,
    server: LucentiveServer = Depends(get_server),
) -> Dict[str, Any]:
    sb = get_supabase_client()

    # Reset command (dev only)
    if os.getenv("RESET_ENABLED", "").lower() == "true" and body.message.strip().lower() == "/reset":
        return await _handle_reset(body.phone_number, sb, server)

    # Human handoff command (dev only — kept as manual override)
    if body.message.strip().lower() == "/human":
        await trigger_human_handoff(body.conversation_id)
        return {"reply": "Please hold on one sec while I check something for you."}

    # 1. Look up phone_number in leads table → get thread_id + lead profile
    lead_res = sb.table("leads").select("thread_id,full_name,email,country,phone_number,new_lead").eq("phone_number", body.phone_number).limit(1).execute()
    if not lead_res.data:
        return {"reply": "Sorry, I could not find your account."}
    lead_row = lead_res.data[0]
    thread_id: str | None = lead_row.get("thread_id")
    lead_info = {
        "first_name": lead_row.get("full_name"),
        "email": lead_row.get("email"),
        "phone": lead_row.get("phone_number"),
        "country": lead_row.get("country"),
        "new_lead": lead_row.get("new_lead") or False,
    }

    # 2. If thread_id exists, restore full state from threads table
    if thread_id:
        # Register thread in MemoryStore so _ensure_thread can find it
        # Without this it throws NotFoundError and creates a new thread every time
        await server.store.save_thread(
            ThreadMetadata(id=thread_id, created_at=datetime.now(timezone.utc)),
            {"request": None},
        )

        thread_res = sb.table("threads").select("input_items,context,current_agent_name").eq("thread_id", thread_id).limit(1).execute()
        if thread_res.data:
            row = thread_res.data[0]
            stored_context = row.get("context")
            server._state[thread_id] = ConversationState(
                input_items=row.get("input_items") or [],
                context=LucentiveAgentContext(**stored_context) if stored_context else create_initial_context(),
                current_agent_name=row.get("current_agent_name") or triage_agent.name,
            )

    # 2b. Inject conversation_id into context so handoff tool can use it
    if thread_id and thread_id in server._state:
        server._state[thread_id].context.conversation_id = body.conversation_id

    # 3. Run the agent
    reply, new_thread_id = await server.process_plaintext_message(
        thread_id=thread_id,
        user_text=body.message,
        request_context={"request": None},
        lead_info=lead_info,
    )

    # 4. Persist updated full state back to threads table
    current_state = server._state.get(new_thread_id)
    if current_state:
        sb.table("threads").upsert({
            "thread_id": new_thread_id,
            "phone_number": body.phone_number,
            "input_items": current_state.input_items,
            "context": current_state.context.model_dump(),
            "current_agent_name": current_state.current_agent_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

    # 5. If thread_id was new, save it back to the lead record
    if not thread_id:
        sb.table("leads").update({"thread_id": new_thread_id}).eq("phone_number", body.phone_number).execute()

    return {"reply": reply}



__all__ = [
    "LucentiveAgentChatContext",
    "LucentiveAgentContext",
    "app",
    "chat_server",
    "create_initial_context",
    "investments_faq_agent",
    "onboarding_agent",
    "public_context",
    "scheduling_agent",
    "triage_agent",
]
