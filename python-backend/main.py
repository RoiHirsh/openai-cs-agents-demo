from __future__ import annotations as _annotations

import json
import logging
import os
from typing import Any, Dict

from dotenv import load_dotenv
from chatkit.server import StreamingResult

load_dotenv()
from fastapi import Depends, FastAPI, Query, Request
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)

from twilio_whatsapp import (
    WhatsAppThreadMapper,
    build_public_request_url,
    load_twilio_whatsapp_config,
    send_whatsapp_message,
    validate_twilio_signature,
)

from airline.agents import (
    investments_faq_agent,
    onboarding_agent,
    scheduling_agent,
    triage_agent,
)
from airline.context import (
    AirlineAgentChatContext,
    AirlineAgentContext,
    create_initial_context,
    public_context,
)
from server import AirlineServer

app = FastAPI()

# Disable tracing for zero data retention orgs
os.environ.setdefault("OPENAI_TRACING_DISABLED", "1")

# CORS configuration (adjust as needed for deployment)
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_server = AirlineServer()
wa_thread_mapper = WhatsAppThreadMapper()


def get_server() -> AirlineServer:
    return chat_server


@app.post("/chatkit")
async def chatkit_endpoint(
    request: Request, server: AirlineServer = Depends(get_server)
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
    server: AirlineServer = Depends(get_server),
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
    server: AirlineServer = Depends(get_server),
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
    server: AirlineServer = Depends(get_server),
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


@app.post("/twilio/whatsapp/webhook")
async def twilio_whatsapp_webhook(
    request: Request,
    server: AirlineServer = Depends(get_server),
) -> Response:
    """
    Twilio WhatsApp inbound webhook.

    We validate the Twilio signature (when configured), run the existing agent
    flow for the inbound message, then send the agent's reply back via Twilio
    REST API (messages.create).
    """
    cfg = load_twilio_whatsapp_config()
    try:
        form = await request.form()
        wa_from = str(form.get("From") or "")
        body = str(form.get("Body") or "")
        # `To` is the Twilio WhatsApp number that received the message (e.g. sandbox number).
        wa_to = str(form.get("To") or "")
        message_sid = str(form.get("MessageSid") or "")

        if not wa_from or not body:
            return Response(
                content=json.dumps({"ok": False, "error": "Missing From/Body"}),
                status_code=400,
                media_type="application/json",
            )

        # Optional signature validation (recommended for deployed public URL).
        if cfg.auth_token and cfg.public_base_url:
            signature = request.headers.get("X-Twilio-Signature")
            full_url = build_public_request_url(
                public_base_url=cfg.public_base_url,
                path=request.url.path,
                query_params=dict(request.query_params),
            )
            if not validate_twilio_signature(
                auth_token=cfg.auth_token,
                signature_header=signature,
                full_url=full_url,
                form_params=form,
            ):
                return Response(
                    content=json.dumps({"ok": False, "error": "Invalid signature"}),
                    status_code=403,
                    media_type="application/json",
                )

        # Map WhatsApp number -> thread id (create on first message).
        thread_id = wa_thread_mapper.get(wa_from)
        assistant_text, thread_id = await server.process_plaintext_message(
            thread_id=thread_id,
            user_text=body,
            request_context={"request": request},
        )
        wa_thread_mapper.set(wa_from, thread_id)

        # Send outbound reply via Twilio REST API.
        if cfg.account_sid and cfg.auth_token:
            send_whatsapp_message(
                account_sid=cfg.account_sid,
                auth_token=cfg.auth_token,
                to=wa_from,
                body=assistant_text or "(no response)",
                whatsapp_from=cfg.whatsapp_from or wa_to or None,
                messaging_service_sid=cfg.messaging_service_sid,
            )

        return Response(
            content=json.dumps(
                {
                    "ok": True,
                    "thread_id": thread_id,
                    "message_sid": message_sid,
                }
            ),
            status_code=200,
            media_type="application/json",
        )
    except Exception:
        logger.exception("Unhandled exception in /twilio/whatsapp/webhook")
        return Response(
            content=json.dumps({"ok": False, "error": "Internal server error"}),
            status_code=500,
            media_type="application/json",
        )


__all__ = [
    "AirlineAgentChatContext",
    "AirlineAgentContext",
    "app",
    "chat_server",
    "create_initial_context",
    "investments_faq_agent",
    "onboarding_agent",
    "public_context",
    "scheduling_agent",
    "triage_agent",
]
