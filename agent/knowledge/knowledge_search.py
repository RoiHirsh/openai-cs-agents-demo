"""
Handoff scenario helpers for the agent runtime.

get_handoff_scenarios() returns the list of active handoff scenarios from
Supabase, cached in memory with a 5-minute TTL. Injected into the agent
system prompt at runtime so the agent uses its own judgment to match.
"""
from __future__ import annotations

import logging
import time

from integrations.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# ─── Handoff scenarios cache ──────────────────────────────────────────────────
# Fetched from Supabase once and cached in memory. Refreshed every 5 minutes.
# Injected into agent system prompt as plain text — no embedding/similarity used.

HANDOFF_CACHE_TTL = 300  # seconds

_handoff_scenarios: list[dict] = []
_handoff_fetched_at: float = 0.0

_DEFAULT_HANDOFF_RESPONSE = "Please wait one sec"


def get_handoff_scenarios() -> list[dict]:
    """
    Return the list of active handoff scenarios from Supabase, each as a dict
    with 'scenario' and 'default_response' keys.

    Uses an in-memory cache with a 5-minute TTL so the DB is not queried on
    every message. On cache miss or expiry, fetches fresh data from Supabase.
    Returns stale cache on fetch error so a DB hiccup never breaks the agent.
    """
    global _handoff_scenarios, _handoff_fetched_at
    now = time.time()
    if now - _handoff_fetched_at > HANDOFF_CACHE_TTL:
        try:
            sb = get_supabase_client()
            result = (
                sb.table("handoff_triggers")
                .select("scenario,default_response")
                .eq("active", True)
                .order("created_at")
                .execute()
            )
            _handoff_scenarios = [
                {
                    "scenario": row["scenario"],
                    "default_response": row.get("default_response") or _DEFAULT_HANDOFF_RESPONSE,
                }
                for row in result.data if row.get("scenario")
            ]
            _handoff_fetched_at = now
            logger.debug("[knowledge] Refreshed handoff scenarios cache (%d rows)", len(_handoff_scenarios))
        except Exception as exc:
            logger.warning("[knowledge] Failed to refresh handoff scenarios: %s", exc)
            # Keep stale cache — a DB hiccup should never break agent responses
    return _handoff_scenarios

