"""
Semantic search helpers for the agent runtime.

Two entry points:
  1. check_handoff_triggers(user_message) — called from process_plaintext_message
     BEFORE the agent runs. If a trigger matches, the caller sends the default
     response and triggers human handoff without ever running the AI agent.

  2. search_knowledge_tool — an @function_tool for the FAQ agent to call when
     answering questions. Replaces the old OpenAI FileSearchTool / vector store.
"""
from __future__ import annotations

from typing import Optional

import openai
from agents import function_tool

from supabase_client import get_supabase_client

# ─── Tunable thresholds ───────────────────────────────────────────────────────
# Adjust these constants to tune match sensitivity without hunting through logic.

HANDOFF_THRESHOLD = 0.82   # similarity score to trigger a human handoff
HANDOFF_COUNT     = 1      # only the top match is needed for handoff decisions

QA_THRESHOLD      = 0.78   # similarity score to inject a Q&A pair
QA_COUNT          = 3      # inject up to this many matching pairs per message


# ─── Embedding helpers ────────────────────────────────────────────────────────

def _embed_sync(text: str) -> list[float]:
    """Synchronous embedding — used for handoff check (called outside agent runner)."""
    client = openai.OpenAI()
    response = client.embeddings.create(model="text-embedding-3-small", input=text)
    return response.data[0].embedding


async def _embed_async(text: str) -> list[float]:
    """Async embedding — used inside the agent runner (function_tool context)."""
    client = openai.AsyncOpenAI()
    response = await client.embeddings.create(model="text-embedding-3-small", input=text)
    return response.data[0].embedding


# ─── Handoff check (synchronous, runs before agent) ──────────────────────────

def check_handoff_triggers(user_message: str) -> Optional[str]:
    """
    Check whether the user message matches a handoff trigger in Supabase.

    Returns the trigger's default_response string if matched, or None if no match.

    Caller pattern:
        default_resp = check_handoff_triggers(user_text)
        if default_resp:
            await trigger_human_handoff(conversation_id)
            return default_resp, thread_id
    """
    try:
        embedding = _embed_sync(user_message)
        sb = get_supabase_client()
        result = sb.rpc("match_handoff_triggers", {
            "query_embedding": embedding,
            "match_threshold": HANDOFF_THRESHOLD,
            "match_count": HANDOFF_COUNT,
        }).execute()
        if result.data:
            return result.data[0]["default_response"]
    except Exception as exc:
        # Never block a message because the handoff check failed
        import logging
        logging.getLogger(__name__).warning("[knowledge] handoff check failed: %s", exc)
    return None


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
        import logging
        logging.getLogger(__name__).warning("[knowledge] search failed: %s", exc)
        return "Knowledge base search is temporarily unavailable."
