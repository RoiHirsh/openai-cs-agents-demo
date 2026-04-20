from __future__ import annotations as _annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from agents import RunContextWrapper, function_tool

from .context import LucentiveAgentChatContext
from .context_cache import set_lead_info, set_onboarding_state
from .scheduling import CALENDLY_BOOKING_URL, compute_scheduling_context
from integrations.supabase_client import get_supabase_client

# Import here to avoid circular dependency — chatwoot is a top-level module
try:
    from integrations.chatwoot import trigger_human_handoff as _trigger_human_handoff
except ImportError:
    _trigger_human_handoff = None

logger = logging.getLogger(__name__)

# ─── Type definitions ─────────────────────────────────────────────────────────

AssetType = Literal["videos", "links", "all"]
Market = Literal["crypto", "gold", "silver", "forex"]
AssetItem = dict[str, str]  # {title: str, url: str}

# ─── Data loaders (Supabase-backed, 5-min TTL cache) ──────────────────────────

_CACHE_TTL = 300  # seconds

_BROKER_ASSETS_CACHE: dict[str, Any] | None = None
_BROKER_ASSETS_CACHE_TIME: float = 0

_COUNTRY_OFFERS_CACHE: dict[str, dict[str, Any]] | None = None
_COUNTRY_OFFERS_CACHE_TIME: float = 0

_RESULTS_VIDEOS_CACHE: dict[str, Any] | None = None
_RESULTS_VIDEOS_CACHE_TIME: float = 0


def _load_broker_assets_data() -> dict[str, Any]:
    """Load broker assets from Supabase. Reconstructs the nested dict used by get_broker_assets."""
    global _BROKER_ASSETS_CACHE, _BROKER_ASSETS_CACHE_TIME
    now = time.time()
    if _BROKER_ASSETS_CACHE is not None and now - _BROKER_ASSETS_CACHE_TIME < _CACHE_TTL:
        return _BROKER_ASSETS_CACHE
    try:
        sb = get_supabase_client()
        rows = sb.table("broker_assets").select("broker,purpose,asset_type,title,url,bot").eq("active", True).order("sort_order").execute().data
        data: dict[str, Any] = {}
        for row in rows:
            b, p, at = row["broker"], row["purpose"], row["asset_type"]
            asset = {"title": row["title"], "url": row["url"], "bot": row.get("bot")}
            data.setdefault(b, {})
            data[b].setdefault(p, {"links": [], "videos": []})
            if at == "link":
                data[b][p]["links"].append(asset)
            elif at == "video":
                data[b][p]["videos"].append(asset)
        _BROKER_ASSETS_CACHE = data
        _BROKER_ASSETS_CACHE_TIME = now
        logger.info("Loaded broker assets from Supabase (%d rows)", len(rows))
    except Exception as e:
        logger.error("Error loading broker assets from Supabase: %s", e)
        if _BROKER_ASSETS_CACHE is None:
            _BROKER_ASSETS_CACHE = {}
    return _BROKER_ASSETS_CACHE  # type: ignore[return-value]


def _load_country_offers_data() -> dict[str, dict[str, Any]]:
    """Load country offers from Supabase. Reconstructs the nested dict used by get_country_offers."""
    global _COUNTRY_OFFERS_CACHE, _COUNTRY_OFFERS_CACHE_TIME
    now = time.time()
    if _COUNTRY_OFFERS_CACHE is not None and now - _COUNTRY_OFFERS_CACHE_TIME < _CACHE_TTL:
        return _COUNTRY_OFFERS_CACHE
    try:
        sb = get_supabase_client()
        rows = sb.table("country_offers").select("country_group,broker_name,bots,broker_notes,group_notes").eq("active", True).order("sort_order").execute().data
        data: dict[str, dict[str, Any]] = {}
        for row in rows:
            group = row["country_group"]
            data.setdefault(group, {"brokers": [], "notes": []})
            data[group]["brokers"].append({
                "name": row["broker_name"],
                "bots": row["bots"] or [],
                "notes": row["broker_notes"] or [],
            })
            if row["group_notes"] and not data[group]["notes"]:
                data[group]["notes"] = row["group_notes"]
        _COUNTRY_OFFERS_CACHE = data
        _COUNTRY_OFFERS_CACHE_TIME = now
        logger.info("Loaded country offers from Supabase (%d rows)", len(rows))
    except Exception as e:
        logger.error("Error loading country offers from Supabase: %s", e)
        if _COUNTRY_OFFERS_CACHE is None:
            _COUNTRY_OFFERS_CACHE = {}
    return _COUNTRY_OFFERS_CACHE  # type: ignore[return-value]


# ─── Normalisation helpers (Supabase-backed, 5-min TTL cache) ────────────────

_BROKERS_NORM_CACHE: list[dict] | None = None
_BROKERS_NORM_CACHE_TIME: float = 0

_COUNTRY_GROUPS_NORM_CACHE: list[dict] | None = None
_COUNTRY_GROUPS_NORM_CACHE_TIME: float = 0


def _load_brokers_for_norm() -> list[dict]:
    global _BROKERS_NORM_CACHE, _BROKERS_NORM_CACHE_TIME
    now = time.time()
    if _BROKERS_NORM_CACHE is not None and now - _BROKERS_NORM_CACHE_TIME < _CACHE_TTL:
        return _BROKERS_NORM_CACHE
    try:
        sb = get_supabase_client()
        _BROKERS_NORM_CACHE = sb.table("brokers").select("broker_id,display_name,aliases").eq("active", True).execute().data
        _BROKERS_NORM_CACHE_TIME = now
    except Exception as e:
        logger.error("Error loading brokers for normalization: %s", e)
        if _BROKERS_NORM_CACHE is None:
            _BROKERS_NORM_CACHE = []
    return _BROKERS_NORM_CACHE  # type: ignore[return-value]


def _load_country_groups_for_norm() -> list[dict]:
    global _COUNTRY_GROUPS_NORM_CACHE, _COUNTRY_GROUPS_NORM_CACHE_TIME
    now = time.time()
    if _COUNTRY_GROUPS_NORM_CACHE is not None and now - _COUNTRY_GROUPS_NORM_CACHE_TIME < _CACHE_TTL:
        return _COUNTRY_GROUPS_NORM_CACHE
    try:
        sb = get_supabase_client()
        _COUNTRY_GROUPS_NORM_CACHE = sb.table("country_groups").select("name,aliases").eq("active", True).execute().data
        _COUNTRY_GROUPS_NORM_CACHE_TIME = now
    except Exception as e:
        logger.error("Error loading country groups for normalization: %s", e)
        if _COUNTRY_GROUPS_NORM_CACHE is None:
            _COUNTRY_GROUPS_NORM_CACHE = []
    return _COUNTRY_GROUPS_NORM_CACHE  # type: ignore[return-value]


def normalize_broker(broker_raw: str) -> Optional[str]:
    """Normalize broker name to canonical broker_id using the brokers table."""
    b = broker_raw.strip().lower()
    for row in _load_brokers_for_norm():
        if b == row["broker_id"] or b == row["display_name"].lower():
            return row["broker_id"]
        if b in [a.lower() for a in (row.get("aliases") or [])]:
            return row["broker_id"]
    return None


def normalize_country(country: str) -> str:
    """Normalize country name to canonical country group using the country_groups table."""
    if not country:
        return "OTHER"
    c = country.strip().lower()
    for row in _load_country_groups_for_norm():
        if c == row["name"].lower():
            return row["name"]
        if c in [a.lower() for a in (row.get("aliases") or [])]:
            return row["name"]
    return "OTHER"


def pick_copy_trade_link_by_market(links: list[AssetItem], market: Optional[str] = None) -> list[AssetItem]:
    """Pick the best matching copy-trade link based on market preference."""
    if not market or not links:
        return links[:1] if links else []
    market_lower = market.lower()
    for link in links:
        title_lower = link["title"].lower()
        if f"({market_lower}" in title_lower or market_lower in title_lower:
            return [link]
    return links[:1] if links else []


# ─── Scheduling tool ──────────────────────────────────────────────────────────

@function_tool(
    name_override="get_scheduling_context",
    description_override=(
        "Get current scheduling context: day, open/closed, why, which offers are available (20 min, 2–4 hours, Calendly), "
        "and reasons when an offer is unavailable. Use this context to respond in natural language; do not copy-paste messages."
    ),
)
async def get_scheduling_context(exclude_actions: list[str] | None = None) -> str:
    """
    Returns scheduling context only (no user-facing messages).
    Agent must use status_reason and reason_* to explain in natural language.
    """
    now_utc = datetime.now(timezone.utc)
    ctx = compute_scheduling_context(
        now_utc, exclude_actions=exclude_actions, calendly_link=CALENDLY_BOOKING_URL
    )
    out = json.dumps(ctx)
    logger.debug("[SCHEDULING TOOL] response: %s", out)
    return out


# ─── Onboarding tools ─────────────────────────────────────────────────────────

@function_tool(
    name_override="update_onboarding_state",
    description_override="Update the onboarding state to track progress through the onboarding flow. Call this after each step is completed to persist the state."
)
async def update_onboarding_state(
    run_context: RunContextWrapper[LucentiveAgentChatContext],
    step_name: str | None = None,
    trading_experience: str | None = None,
    previous_broker: str | None = None,
    trading_type: str | None = None,
    bot_preference: str | None = None,
    broker_preference: str | None = None,
    budget_confirmed: bool | None = None,
    budget_amount: float | None = None,
    demo_offered: bool | None = None,
    instructions_provided: bool | None = None,
    onboarding_complete: bool | None = None,
    has_broker_account: bool | None = None,
) -> str:
    """
    Update the onboarding state in the context.

    Args:
        step_name: Name of the step to add to completed_steps (e.g., "trading_experience", "bot_recommendation", "broker_selection", "budget_check", "profit_share_clarification", "has_broker_account", "instructions")
        trading_experience: User's trading experience level (e.g., "yes", "no", "beginner", "experienced")
        previous_broker: Optional prior broker the user mentions naturally (if any)
        trading_type: Optional prior trading type the user mentions naturally (e.g., "stocks", "forex", "crypto", "futures")
        bot_preference: User's chosen bot type from step 2a (e.g., "Gold", "Forex", "Crypto")
        broker_preference: User's chosen broker from step 2b (e.g., "Vantage", "PU Prime")
        budget_confirmed: Whether the user confirmed they have the minimum budget (True/False)
        budget_amount: The budget amount the user mentioned (if any)
        demo_offered: Whether a demo account was offered (True/False)
        instructions_provided: Whether instructions have been provided (True/False)
        onboarding_complete: Whether onboarding is fully complete - user has opened account AND set up copy trading (True/False)
        has_broker_account: Whether the user already has an account with the selected broker (True/False); used to skip registration when True
    """
    logger.debug("[TOOL EXEC] update_onboarding_state(step_name=%r, trading_experience=%r, previous_broker=%r, trading_type=%r, bot_preference=%r, broker_preference=%r, budget_confirmed=%s, budget_amount=%s, demo_offered=%s, instructions_provided=%s, onboarding_complete=%s, has_broker_account=%s)", step_name, trading_experience, previous_broker, trading_type, bot_preference, broker_preference, budget_confirmed, budget_amount, demo_offered, instructions_provided, onboarding_complete, has_broker_account)

    ctx = run_context.context.state

    if ctx.onboarding_state is None:
        ctx.onboarding_state = {}
    if "completed_steps" not in ctx.onboarding_state:
        ctx.onboarding_state["completed_steps"] = []

    if step_name and step_name not in ctx.onboarding_state["completed_steps"]:
        ctx.onboarding_state["completed_steps"].append(step_name)
        logger.debug("Added step %r to completed_steps", step_name)

    if trading_experience is not None:
        ctx.onboarding_state["trading_experience"] = trading_experience
    if previous_broker is not None:
        ctx.onboarding_state["previous_broker"] = previous_broker
    if trading_type is not None:
        ctx.onboarding_state["trading_type"] = trading_type
    if bot_preference is not None:
        ctx.onboarding_state["bot_preference"] = bot_preference
    if broker_preference is not None:
        ctx.onboarding_state["broker_preference"] = broker_preference
    if budget_confirmed is not None:
        ctx.onboarding_state["budget_confirmed"] = budget_confirmed
    if budget_amount is not None:
        ctx.onboarding_state["budget_amount"] = budget_amount
    if demo_offered is not None:
        ctx.onboarding_state["demo_offered"] = demo_offered
    if instructions_provided is not None:
        ctx.onboarding_state["instructions_provided"] = instructions_provided
    if onboarding_complete is not None:
        ctx.onboarding_state["onboarding_complete"] = onboarding_complete
    if has_broker_account is not None:
        ctx.onboarding_state["has_broker_account"] = has_broker_account

    thread_id = None
    if hasattr(run_context.context, 'thread') and run_context.context.thread:
        thread_id = run_context.context.thread.id
        if thread_id:
            set_onboarding_state(thread_id, ctx.onboarding_state.copy())
            logger.debug("Cached onboarding_state for thread %s", thread_id)

    completed_steps = ctx.onboarding_state.get("completed_steps", [])
    return f"Onboarding state updated successfully. Completed steps: {', '.join(completed_steps) if completed_steps else 'none'}"


@function_tool(
    name_override="update_lead_info",
    description_override="Update lead info fields (e.g. country) in the conversation context so the UI variables reflect user corrections."
)
async def update_lead_info(
    run_context: RunContextWrapper[LucentiveAgentChatContext],
    first_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    country: str | None = None,
    new_lead: bool | None = None,
) -> str:
    """
    Update lead info fields in the context (and cache) so user corrections persist across handoffs.

    Typical usage: if user says "Actually I'm from Australia", call update_lead_info(country="Australia").
    """
    logger.debug("[TOOL EXEC] update_lead_info(first_name=%r, email=%r, phone=%r, country=%r, new_lead=%r)", first_name, email, phone, country, new_lead)

    ctx = run_context.context.state

    if first_name is not None and first_name.strip():
        ctx.first_name = first_name.strip()
    if email is not None and email.strip():
        ctx.email = email.strip()
    if phone is not None and phone.strip():
        ctx.phone = phone.strip()
    if country is not None and country.strip():
        ctx.country = country.strip()
    if new_lead is not None:
        ctx.new_lead = bool(new_lead)

    thread_id = None
    if hasattr(run_context.context, "thread") and run_context.context.thread:
        thread_id = run_context.context.thread.id
        if thread_id:
            lead_info_dict = {
                "first_name": ctx.first_name,
                "email": ctx.email,
                "phone": ctx.phone,
                "country": ctx.country,
                "new_lead": ctx.new_lead,
            }
            set_lead_info(thread_id, lead_info_dict)
            logger.debug("Cached lead info for thread %s: %s", thread_id, lead_info_dict)

    return (
        "Lead info updated successfully."
        f" first_name={ctx.first_name!r}, country={ctx.country!r}, new_lead={ctx.new_lead!r}"
    )


# ─── Broker / country tools ───────────────────────────────────────────────────

@function_tool(
    name_override="get_broker_assets",
    description_override="Return broker referral/registration links and optional tutorial videos for a given broker and onboarding purpose. Always returns links (primary) and videos (optional helpers) together."
)
async def get_broker_assets(
    broker: str,
    purpose: str,
    asset_type: Optional[str] = None,
    market: Optional[str] = None,
) -> str:
    """
    Get broker assets (links and videos) for a given broker and purpose.

    Args:
        broker: Broker name (Bybit, Vantage, PU Prime) - case-insensitive
        purpose: Which onboarding step - "registration", "copy_trade_start",
                "copy_trade_open_account", "copy_trade_connect"
        asset_type: "all" (default), "links", or "videos"
        market: Optional market for copy_trade_connect - "crypto", "gold", "silver", "forex"
    """
    logger.debug("[TOOL EXEC] get_broker_assets(broker=%r, purpose=%r, asset_type=%r, market=%r)", broker, purpose, asset_type, market)

    broker_id = normalize_broker(broker)
    if not broker_id:
        logger.error("Unsupported broker: %s", broker)
        return json.dumps({"ok": False, "broker": broker, "purpose": purpose, "links": [], "videos": [], "error": "UNSUPPORTED_BROKER"})

    valid_purposes: set[str] = {"registration", "copy_trade_start", "copy_trade_open_account", "copy_trade_connect"}
    purpose_lower = purpose.lower().strip()
    if purpose_lower not in valid_purposes:
        logger.error("Unsupported purpose: %s", purpose)
        return json.dumps({"ok": False, "broker": broker_id, "purpose": purpose, "links": [], "videos": [], "error": "UNSUPPORTED_PURPOSE"})

    asset_type_str = (asset_type or "all").lower().strip()
    if asset_type_str not in {"videos", "links", "all"}:
        logger.error("Unsupported asset_type: %s", asset_type_str)
        return json.dumps({"ok": False, "broker": broker_id, "purpose": purpose_lower, "links": [], "videos": [], "error": "UNSUPPORTED_ASSET_TYPE"})

    broker_data = _load_broker_assets_data()
    broker_entry = broker_data.get(broker_id, {})
    purpose_entry = broker_entry.get(purpose_lower, {})

    links: list[AssetItem] = []
    if asset_type_str in ("links", "all"):
        purpose_links = purpose_entry.get("links", [])
        if purpose_lower == "copy_trade_connect":
            if market and purpose_links:
                market_lower = market.strip().lower()
                # 1. Prefer links explicitly tagged with this bot
                bot_specific = [l for l in purpose_links if (l.get("bot") or "").lower() == market_lower]
                if bot_specific:
                    links = bot_specific
                else:
                    # 2. Fall back to generic links (bot column is null/empty)
                    generic = [l for l in purpose_links if not l.get("bot")]
                    if generic:
                        links = generic
                    else:
                        # 3. Legacy title-text match as last resort
                        links = pick_copy_trade_link_by_market(purpose_links, market)
            else:
                links = purpose_links[:3]
        else:
            links = purpose_links[:1]

    videos: list[AssetItem] = []
    if asset_type_str in ("videos", "all"):
        videos = purpose_entry.get("videos", [])[:3]

    result = {
        "ok": True,
        "broker": broker_id,
        "purpose": purpose_lower,
        "links": links,
        "videos": videos,
        "error": None
    }

    logger.debug("Returning %d link(s) and %d video(s) for %s (purpose=%s)", len(links), len(videos), broker_id, purpose_lower)
    return json.dumps(result)


@function_tool(
    name_override="get_country_offers",
    description_override="Get available bots and brokers for a given country. Pass bot_preference to filter brokers to only those that support the selected bot."
)
async def get_country_offers(country: str, bot_preference: Optional[str] = None) -> str:
    """
    Get available trading bots and brokers for a given country.

    Args:
        country: Country name or code (case-insensitive).
        bot_preference: Optional bot name to filter brokers (e.g., "Gold", "Crypto").
    """
    logger.debug("[TOOL EXEC] get_country_offers(country=%r, bot_preference=%r)", country, bot_preference)

    if not country or not country.strip():
        logger.error("Country parameter is missing or empty")
        return json.dumps({"ok": False, "normalized_country_group": None, "bots": [], "brokers": [], "notes": [], "error": "MISSING_COUNTRY"})

    normalized_group = normalize_country(country)
    logger.debug("Input country: %r -> Normalized group: %r", country, normalized_group)

    country_data = _load_country_offers_data()

    if normalized_group not in country_data:
        logger.error("Country group %r not found in data", normalized_group)
        return json.dumps({"ok": False, "normalized_country_group": normalized_group, "bots": [], "brokers": [], "notes": [], "error": "COUNTRY_GROUP_NOT_FOUND"})

    offers = country_data[normalized_group]
    brokers = offers.get("brokers", [])
    notes = offers.get("notes", [])

    if not isinstance(brokers, list):
        return json.dumps({"ok": False, "normalized_country_group": normalized_group, "bots": [], "brokers": [], "notes": [], "error": "INVALID_DATA_SCHEMA: brokers must be a list"})
    for broker in brokers:
        if not isinstance(broker, dict) or "name" not in broker or "bots" not in broker:
            return json.dumps({"ok": False, "normalized_country_group": normalized_group, "bots": [], "brokers": [], "notes": [], "error": "INVALID_DATA_SCHEMA: each broker must have 'name' and 'bots' fields"})

    seen: set[str] = set()
    all_bots: list[str] = []
    for broker in brokers:
        for bot in broker.get("bots", []):
            if bot not in seen:
                seen.add(bot)
                all_bots.append(bot)

    if bot_preference:
        bot_lower = bot_preference.strip().lower()
        filtered_brokers = [b for b in brokers if any(bot.lower() == bot_lower for bot in b.get("bots", []))]
    else:
        filtered_brokers = brokers

    result = {
        "ok": True,
        "normalized_country_group": normalized_group,
        "bots": all_bots,
        "brokers": filtered_brokers,
        "notes": notes,
        "error": None
    }

    logger.debug("Returning %d bot(s) and %d broker(s) for %s (bot_preference=%r)", len(all_bots), len(filtered_brokers), normalized_group, bot_preference)
    return json.dumps(result)


# ─── Results videos tool ─────────────────────────────────────────────────────

def _load_results_videos() -> dict[str, Any]:
    global _RESULTS_VIDEOS_CACHE, _RESULTS_VIDEOS_CACHE_TIME
    now = time.time()
    if _RESULTS_VIDEOS_CACHE is not None and now - _RESULTS_VIDEOS_CACHE_TIME < _CACHE_TTL:
        return _RESULTS_VIDEOS_CACHE
    try:
        sb = get_supabase_client()
        rows = sb.table("results_videos").select("market,url,updated_at").execute().data
        data = {row["market"]: {"url": row["url"], "updated_at": row.get("updated_at", "")} for row in rows}
        _RESULTS_VIDEOS_CACHE = data
        _RESULTS_VIDEOS_CACHE_TIME = now
        return data
    except Exception as e:
        logger.error("[results_videos] Failed to load: %s", e)
        return _RESULTS_VIDEOS_CACHE or {}


@function_tool(
    name_override="get_results_video",
    description_override="Get the latest results/performance video URL for a given trading market (gold, crypto, or forex).",
)
async def get_results_video(market: str) -> str:
    """Returns the public URL of the latest results video for the given market."""
    logger.debug("[TOOL EXEC] get_results_video(market=%r)", market)
    data = _load_results_videos()
    key = market.lower().strip()
    if key not in data:
        return json.dumps({"ok": False, "url": None, "error": f"No results video available for '{market}' yet."})
    entry = data[key]
    url = entry["url"]
    updated_at = entry.get("updated_at", "")
    if updated_at:
        ts = updated_at.replace(":", "").replace("-", "").replace("T", "").replace("Z", "")[:14]
        url = f"{url}?v={ts}"
    return json.dumps({"ok": True, "url": url, "market": key, "error": None})


# ─── Human handoff tool ───────────────────────────────────────────────────────

@function_tool(
    name_override="request_human_handoff",
    description_override=(
        "Hand off this conversation to a human agent. "
        "Triggers the human escalation sequence in Chatwoot."
    ),
)
async def request_human_handoff(context: RunContextWrapper[Any]) -> str:
    """
    Triggers a full human handoff sequence in Chatwoot:
    - Sets conversation status to open
    - Assigns human agent
    - Sets priority to high
    - Applies jump_in_chat label
    - Posts a private note for the human agent
    """
    conversation_id: str | None = None
    try:
        conversation_id = context.context.state.conversation_id
    except AttributeError:
        pass

    if not conversation_id:
        logger.warning("[handoff] request_human_handoff called but conversation_id is missing from context")
        return "handoff_failed: no conversation_id in context"

    if _trigger_human_handoff is None:
        logger.warning("[handoff] chatwoot module not available")
        return "handoff_failed: chatwoot module unavailable"

    await _trigger_human_handoff(conversation_id)
    return "handoff_complete"
