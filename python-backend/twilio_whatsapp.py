from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

from twilio.request_validator import RequestValidator
from twilio.rest import Client


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

