"""
Semantic search and knowledge helpers for the agent runtime.

Two entry points:

  1. get_handoff_scenarios() — returns the list of active handoff scenarios
     from Supabase, cached in memory with a 5-minute TTL. Injected into the
     agent system prompt at runtime so the agent uses its own judgment to match.

  2. search_knowledge_tool — an @function_tool for the FAQ agent to call when
     answering questions. Replaces the old OpenAI FileSearchTool / vector store.
"""
from __future__ import annotations

import logging
import time

import openai
from agents import function_tool

from supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# ─── Tunable thresholds ───────────────────────────────────────────────────────

QA_THRESHOLD = 0.72   # similarity score to inject a Q&A pair
QA_COUNT     = 3      # inject up to this many matching pairs per message

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


# ─── Async embedding helper ───────────────────────────────────────────────────

async def _embed_async(text: str) -> list[float]:
    """Async embedding used inside the agent runner (function_tool context)."""
    client = openai.AsyncOpenAI()
    response = await client.embeddings.create(model="text-embedding-3-small", input=text)
    return response.data[0].embedding


# ─── Knowledge search tool (async, used by FAQ agent) ────────────────────────

@function_tool(
    name_override="search_knowledge",
    description_override=(
        "Search the internal knowledge base for Q&A pairs that are relevant to the "
        "customer's question. Returns verified answers to use in your response. "
        "Call this tool silently in the background — do not mention it to the customer."
    ),
)
async def search_knowledge_tool(query: str) -> str:
    """
    Semantic search over qa_pairs in Supabase.

    Args:
        query: The customer's question or topic to search for.

    Returns a formatted block of relevant Q&A pairs, or a message indicating
    no matches were found.
    """
    try:
        embedding = await _embed_async(query)
        sb = get_supabase_client()
        result = sb.rpc("match_qa_pairs", {
            "query_embedding": embedding,
            "match_threshold": QA_THRESHOLD,
            "match_count": QA_COUNT,
        }).execute()

        if not result.data:
            return "No relevant entries found in the knowledge base for this query."

        lines = ["VERIFIED KNOWLEDGE BASE — use these answers with confidence if relevant:"]
        for row in result.data:
            lines.append(f"Q: {row['question']}")
            lines.append(f"A: {row['answer']}")
            lines.append("")
        return "\n".join(lines).strip()

    except Exception as exc:
        logger.warning("[knowledge] search failed: %s", exc)
        return "Knowledge base search is temporarily unavailable."
