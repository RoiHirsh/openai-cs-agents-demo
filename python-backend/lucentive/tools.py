from __future__ import annotations as _annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional

from agents import function_tool

logger = logging.getLogger(__name__)

# Type definitions
BrokerId = Literal["bybit", "vantage", "pu_prime"]
Purpose = Literal["registration", "copy_trade_start", "copy_trade_open_account", "copy_trade_connect"]
AssetType = Literal["videos", "links", "all"]
Market = Literal["crypto", "gold", "silver", "forex"]

# Asset item structure
AssetItem = dict[str, str]  # {title: str, url: str}

# Cached data
_BROKER_ASSETS_DATA: dict[str, Any] | None = None
_COUNTRY_OFFERS_DATA: dict[str, dict[str, Any]] | None = None


def _load_broker_assets_data() -> dict[str, Any]:
    """Load broker assets (links + videos) from JSON file. Cached after first load."""
    global _BROKER_ASSETS_DATA
    if _BROKER_ASSETS_DATA is not None:
        return _BROKER_ASSETS_DATA
    json_file = Path(__file__).parent / "knowledge" / "broker_assets.json"
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            _BROKER_ASSETS_DATA = json.load(f)
        logger.info("Loaded broker assets from %s", json_file)
    except Exception as e:
        logger.error("Error loading broker assets: %s", e)
        _BROKER_ASSETS_DATA = {}
    return _BROKER_ASSETS_DATA


def _load_country_offers_data() -> dict[str, dict[str, Any]]:
    """Load country offers data from JSON file. Cached after first load."""
    global _COUNTRY_OFFERS_DATA
    if _COUNTRY_OFFERS_DATA is not None:
        return _COUNTRY_OFFERS_DATA
    json_file = Path(__file__).parent / "knowledge" / "country_offers.json"
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            _COUNTRY_OFFERS_DATA = json.load(f)
        logger.info("Loaded country offers data from %s", json_file)
    except Exception as e:
        logger.error("Error loading country offers data: %s", e)
        _COUNTRY_OFFERS_DATA = {}
    return _COUNTRY_OFFERS_DATA


def normalize_broker(broker_raw: str) -> Optional[BrokerId]:
    """Normalize broker name to canonical form."""
    b = broker_raw.strip().lower()
    if b == "bybit":
        return "bybit"
    if b == "vantage":
        return "vantage"
    if b in ("pu prime", "pu_prime", "puprime", "pu-prime"):
        return "pu_prime"
    return None


def normalize_country(country: str) -> Literal["AUSTRALIA", "CANADA", "UK", "OTHER"]:
    """Normalize country name to canonical country group."""
    if not country:
        return "OTHER"
    country_normalized = country.strip().lower()
    if country_normalized in ("australia", "au", "aus"):
        return "AUSTRALIA"
    if country_normalized in ("canada", "ca", "can"):
        return "CANADA"
    if country_normalized in ("united kingdom", "uk", "gb", "gbr", "great britain", "england", "scotland", "wales"):
        return "UK"
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

    Returns:
        JSON string with links and videos for the given broker/purpose.
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
        if purpose_lower == "copy_trade_connect" and market and len(purpose_links) > 1:
            links = pick_copy_trade_link_by_market(purpose_links, market)
        else:
            links = purpose_links[:1] if purpose_lower != "copy_trade_connect" else purpose_links[:3]

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

    Bots are derived from the union of all brokers' supported bots.
    When bot_preference is provided, only brokers that support that bot are returned.

    Args:
        country: Country name or code (case-insensitive).
        bot_preference: Optional bot name to filter brokers (e.g., "Gold", "Crypto").

    Returns:
        JSON string with bots (full list) and brokers (filtered if bot_preference given).
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

    # Derive full bot list from union of all brokers' bots (preserving order of first appearance)
    seen: set[str] = set()
    all_bots: list[str] = []
    for broker in brokers:
        for bot in broker.get("bots", []):
            if bot not in seen:
                seen.add(bot)
                all_bots.append(bot)

    # Filter brokers by bot_preference if provided
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
