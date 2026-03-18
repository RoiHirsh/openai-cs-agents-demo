from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlencode

from twilio.request_validator import RequestValidator
from twilio.rest import Client

# Seconds to wait after the last message before processing (debounce).
# Set TWILIO_WHATSAPP_DEBOUNCE_SECONDS to override (e.g. 1, 2, 3).
_DEBOUNCE_SECONDS_DEFAULT = 2
try:
    DEBOUNCE_SECONDS = max(
        1,
        min(5, int(os.getenv("TWILIO_WHATSAPP_DEBOUNCE_SECONDS", str(_DEBOUNCE_SECONDS_DEFAULT)))),
    )
except ValueError:
    DEBOUNCE_SECONDS = _DEBOUNCE_SECONDS_DEFAULT


@dataclass(frozen=True)
class TwilioWhatsAppConfig:
    account_sid: str
    auth_token: str
    whatsapp_from: str | None = None
    messaging_service_sid: str | None = None
    public_base_url: str | None = None


def load_twilio_whatsapp_config() -> TwilioWhatsAppConfig:
    return TwilioWhatsAppConfig(
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", "").strip(),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", "").strip(),
        whatsapp_from=os.getenv("TWILIO_WHATSAPP_FROM", "").strip() or None,
        messaging_service_sid=os.getenv("TWILIO_MESSAGING_SERVICE_SID", "").strip() or None,
        public_base_url=os.getenv("PUBLIC_BASE_URL", "").strip() or None,
    )


def build_public_request_url(
    *,
    public_base_url: str,
    path: str,
    query_params: Mapping[str, str] | None = None,
) -> str:
    base = public_base_url.rstrip("/")
    url = f"{base}{path}"
    if query_params:
        url = f"{url}?{urlencode(query_params)}"
    return url


def validate_twilio_signature(
    *,
    auth_token: str,
    signature_header: str | None,
    full_url: str,
    form_params: Mapping[str, Any],
) -> bool:
    if not signature_header:
        return False
    validator = RequestValidator(auth_token)
    # Twilio sends form-encoded params; values are strings.
    params = {k: "" if v is None else str(v) for k, v in dict(form_params).items()}
    return bool(validator.validate(full_url, params, signature_header))


def send_whatsapp_message(
    *,
    account_sid: str,
    auth_token: str,
    to: str,
    body: str,
    whatsapp_from: str | None = None,
    messaging_service_sid: str | None = None,
) -> str:
    client = Client(account_sid, auth_token)
    kwargs: dict[str, Any] = {"to": to, "body": body}
    if messaging_service_sid:
        kwargs["messaging_service_sid"] = messaging_service_sid
    else:
        if not whatsapp_from:
            raise ValueError("TWILIO_WHATSAPP_FROM is required when no Messaging Service SID is set.")
        kwargs["from_"] = whatsapp_from
    msg = client.messages.create(**kwargs)
    return getattr(msg, "sid", "")


class WhatsAppThreadMapper:
    """
    In-memory mapper from WhatsApp user number -> ChatKit thread id.

    For production, replace with a persistent store (DB/Redis). For this demo,
    in-memory is enough and supports the Sandbox flow.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._map: dict[str, str] = {}

    def get(self, wa_from: str) -> str | None:
        with self._lock:
            return self._map.get(wa_from)

    def set(self, wa_from: str, thread_id: str) -> None:
        with self._lock:
            self._map[wa_from] = thread_id


# Type for async callback (wa_from, combined_text) -> None (runs agent and sends reply).
FlushCallback = Callable[[str, str], Awaitable[None]]


class WhatsAppMessageCoalescer:
    """
    Debounces and coalesces WhatsApp messages per user so that:
    - We wait DEBOUNCE_SECONDS after the last message before running the agent.
    - Quick bursts (e.g. "I", "want", "to ask") are sent to the agent as one combined message.
    - If a new message arrives while we're processing, we cancel the current run and
      merge that batch with new messages, then re-debounce and run once with the full set.
    """

    def __init__(self) -> None:
        self._user_states: dict[str, _UserCoalescerState] = {}
        self._states_lock = asyncio.Lock()

    async def _get_or_create_state(self, wa_from: str) -> "_UserCoalescerState":
        async with self._states_lock:
            if wa_from not in self._user_states:
                self._user_states[wa_from] = _UserCoalescerState()
            return self._user_states[wa_from]

    async def add_message(
        self,
        wa_from: str,
        body: str,
        flush_callback: FlushCallback,
    ) -> None:
        state = await self._get_or_create_state(wa_from)
        async with state.lock:
            state.last_flush_callback = flush_callback
            state.pending.append(body)

            if state.processing_task is not None:
                # Cancel current run; merge batch back into pending and re-debounce.
                state.pending = state.current_batch + state.pending
                state.current_batch = []
                state.processing_task.cancel()
                state.processing_task = None

            if state.debounce_task is not None:
                state.debounce_task.cancel()
            state.debounce_task = asyncio.create_task(
                self._debounce_wait(wa_from, state, flush_callback),
            )

    async def _debounce_wait(
        self,
        wa_from: str,
        state: "_UserCoalescerState",
        flush_callback: FlushCallback,
    ) -> None:
        try:
            await asyncio.sleep(DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            return

        async with state.lock:
            if not state.pending:
                state.debounce_task = None
                return
            batch = state.pending[:]
            state.pending.clear()
            state.current_batch = batch
            state.debounce_task = None

            processing_task = asyncio.create_task(
                self._run_and_send(wa_from, batch, flush_callback),
            )
            state.processing_task = processing_task

        asyncio.create_task(self._monitor_processing(wa_from, state, processing_task))

    @staticmethod
    async def _run_and_send(
        wa_from: str,
        batch: list[str],
        flush_callback: FlushCallback,
    ) -> None:
        combined = " ".join(batch).strip() or "(empty)"
        await flush_callback(wa_from, combined)

    async def _monitor_processing(
        self,
        wa_from: str,
        state: "_UserCoalescerState",
        processing_task: asyncio.Task[None],
    ) -> None:
        try:
            await processing_task
        except asyncio.CancelledError:
            pass
        except Exception:
            # Log but don't re-raise; cleanup below.
            pass

        async with state.lock:
            if state.processing_task is processing_task:
                state.processing_task = None
            # If we were cancelled, current_batch was already merged back in add_message.
            state.current_batch = []
            callback = state.last_flush_callback
            if state.pending and callback is not None:
                state.debounce_task = asyncio.create_task(
                    self._debounce_wait(wa_from, state, callback),
                )
            else:
                state.debounce_task = None


class _UserCoalescerState:
    def __init__(self) -> None:
        self.pending: list[str] = []
        self.debounce_task: asyncio.Task[None] | None = None
        self.processing_task: asyncio.Task[None] | None = None
        self.current_batch: list[str] = []
        self.last_flush_callback: FlushCallback | None = None
        self.lock = asyncio.Lock()

