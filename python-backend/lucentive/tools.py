from __future__ import annotations as _annotations

import json
from pathlib import Path
from typing import Literal, Optional

from agents import function_tool

# Type definitions
BrokerId = Literal["bybit", "vantage", "pu_prime"]
Purpose = Literal["registration", "copy_trade_start", "copy_trade_open_account", "copy_trade_connect"]
AssetType = Literal["videos", "links", "all"]
Market = Literal["crypto", "gold", "silver", "forex"]

# Asset item structure
AssetItem = dict[str, str]  # {title: str, url: str}

# Broker videos database
BROKER_VIDEOS: dict[BrokerId, dict[Purpose, list[AssetItem]]] = {
    "bybit": {
        "registration": [
            {"title": "Bybit sign up instructions", "url": "https://www.youtube.com/shorts/_xABSqSZZsg"},
        ],
        "copy_trade_start": [
            {"title": "Bybit start a copy trade", "url": "https://drive.google.com/file/d/1IHl8aaQyNfDSLqmzNJuJxODBLX2-WyCj/view?usp=drive_link"},
        ],
        "copy_trade_open_account": [],
        "copy_trade_connect": [],
    },
    "pu_prime": {
        "registration": [
            {"title": "PU Prime registration", "url": "https://drive.google.com/file/d/1Ej39VG4uJSWC_xnkSyyGJN_XCzPM2pvO/view?usp=drive_link"},
        ],
        "copy_trade_open_account": [
            {"title": "PU Prime open a copy trading account", "url": "https://drive.google.com/file/d/10UHdv8K59Lw6U-GutEI6f1TvJkIRplSR/view?usp=drive_link"},
        ],
        "copy_trade_connect": [
            {"title": "PU Prime how to connect to copy trade", "url": "https://drive.google.com/file/d/1o6yJMZ9_1wLS-A_mTN9Mzh_w3gJh6yCA/view?usp=drive_link"},
        ],
        "copy_trade_start": [],
    },
    "vantage": {
        "registration": [
            {"title": "Vantage how to register", "url": "https://drive.google.com/file/d/1kr0JYMPYrfO7BFvpWxghoel4ULmfm2d5/view?usp=drive_link"},
        ],
        "copy_trade_open_account": [
            {"title": "Vantage open a copy trading account", "url": "https://drive.google.com/file/d/1cQlEWHxw2Zx-cfhrWCU3CoV2kvjurJrX/view?usp=drive_link"},
        ],
        "copy_trade_connect": [
            {"title": "Vantage how to connect to copy trade", "url": "https://drive.google.com/file/d/11upZwKRE_eYaqjenyr41RTYPyuf58CBR/view?usp=drive_link"},
        ],
        "copy_trade_start": [],
    },
}

# Broker links database (purpose-specific referral/registration links)
BROKER_LINKS: dict[BrokerId, dict[Purpose, list[AssetItem]]] = {
    "bybit": {
        "registration": [
            {"title": "Bybit Referral Program", "url": "https://bybit.com/en/invite?ref=BYQLKL"},
        ],
        "copy_trade_connect": [
            {"title": "Bybit Invite to Copy Trade", "url": "https://i.bybit.com/1Zabpd4n?action=inviteToCopy"},
        ],
        "copy_trade_start": [],
        "copy_trade_open_account": [
            {"title": "Bybit Invite to Copy Trade", "url": "https://i.bybit.com/1Zabpd4n?action=inviteToCopy"},
        ],
    },
    "vantage": {
        "registration": [
            {"title": "Vantage Registration", "url": "https://www.vantagemarkets.com/forex-trading/forex-trading-account/?affid=7361340"},
        ],
        "copy_trade_connect": [
            # Multiple copy trade links for different markets - agent can pick based on market if provided
            {"title": "Vantage Copy Trade (Crypto - Dave)", "url": "https://vantageapp.onelink.me/qaPD?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7361340%7Cplatform-copytrading&deep_link_sub1=spid-820189"},
            {"title": "Vantage Copy Trade (Gold - Dave)", "url": "https://vantageapp.onelink.me/qaPD?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7361340%7Cplatform-copytrading&deep_link_sub1=spid-795666"},
            {"title": "Vantage Copy Trade (Forex - Dave)", "url": "https://vantageapp.onelink.me/qaPD?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7361340%7Cplatform-copytrading&deep_link_sub1=spid-828839"},
        ],
        "copy_trade_start": [],
        "copy_trade_open_account": [],
    },
    "pu_prime": {
        "registration": [
            {"title": "PU Prime Registration", "url": "https://www.puprime.partners/forex-trading-account/?affid=7525953"},
        ],
        "copy_trade_connect": [
            {"title": "PU Prime Copy Trade (Silver - Adi)", "url": "https://puprime.onelink.me/O5Jx?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7525953%7Cplatform-copytrading&deep_link_sub1=spid-825967&campaignCode=1pHJLS6RBENRLbA7/b+Ayg=="},
            {"title": "PU Prime Copy Trade (Gold - Adi No Swap)", "url": "https://puprime.onelink.me/O5Jx?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7525953%7Cplatform-copytrading&deep_link_sub1=spid-825948&campaignCode=1pHJLS6RBENRLbA7/b+Ayg=="},
        ],
        "copy_trade_start": [],
        "copy_trade_open_account": [],
    },
}


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


def normalize_country(country: str) -> Literal["AUSTRALIA", "CANADA", "OTHER"]:
    """
    Normalize country name to canonical country group.
    
    Maps country names (case/spacing tolerant) to country groups:
    - "Australia", "AU", "AUS" → "AUSTRALIA"
    - "Canada", "CA", "CAN" → "CANADA"
    - Everything else → "OTHER"
    
    Args:
        country: Country name or code (case-insensitive, spacing-tolerant)
    
    Returns:
        Normalized country group: "AUSTRALIA", "CANADA", or "OTHER"
    """
    if not country:
        return "OTHER"
    
    country_normalized = country.strip().lower()
    
    # Australia variants
    if country_normalized in ("australia", "au", "aus"):
        return "AUSTRALIA"
    
    # Canada variants
    if country_normalized in ("canada", "ca", "can"):
        return "CANADA"
    
    # Everything else
    return "OTHER"


# Load country offers data
_COUNTRY_OFFERS_DATA: dict[str, dict[str, any]] | None = None


def _load_country_offers_data() -> dict[str, dict[str, any]]:
    """Load country offers data from JSON file. Cached after first load."""
    global _COUNTRY_OFFERS_DATA
    if _COUNTRY_OFFERS_DATA is not None:
        return _COUNTRY_OFFERS_DATA
    
    # Get the path to the knowledge directory relative to this file
    current_file = Path(__file__)
    knowledge_dir = current_file.parent / "knowledge"
    json_file = knowledge_dir / "country_offers.json"
    
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            _COUNTRY_OFFERS_DATA = json.load(f)
        print(f"      [INFO] Loaded country offers data from {json_file}")
        return _COUNTRY_OFFERS_DATA
    except FileNotFoundError:
        print(f"      [ERROR] Country offers file not found: {json_file}")
        _COUNTRY_OFFERS_DATA = {}
        return _COUNTRY_OFFERS_DATA
    except json.JSONDecodeError as e:
        print(f"      [ERROR] Invalid JSON in country offers file: {e}")
        _COUNTRY_OFFERS_DATA = {}
        return _COUNTRY_OFFERS_DATA
    except Exception as e:
        print(f"      [ERROR] Error loading country offers data: {e}")
        _COUNTRY_OFFERS_DATA = {}
        return _COUNTRY_OFFERS_DATA


def pick_copy_trade_link_by_market(links: list[AssetItem], market: Optional[str] = None) -> list[AssetItem]:
    """Pick the best matching copy-trade link based on market preference."""
    if not market or not links:
        # Return first link if no market specified or no links
        return links[:1] if links else []
    
    # Try to match market in title (e.g., "(Crypto", "(Gold", etc.)
    market_lower = market.lower()
    for link in links:
        # Look for pattern like "(Crypto", "(Gold", etc.
        if f"({market_lower}" in link["title"].lower():
            return [link]
    
    # Fallback: return first link if no match
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
    Links are the primary assets (referral/registration URLs) that users need.
    Videos are optional helper explainers that accompany the links when available.
    
    Args:
        broker: Broker name (Bybit, Vantage, PU Prime) - case-insensitive
        purpose: Which onboarding step - "registration", "copy_trade_start", 
                "copy_trade_open_account", "copy_trade_connect"
        asset_type: Type of assets requested - "all" (default, returns links + videos), 
                   "links" (links only), or "videos" (videos only)
        market: Optional market type for copy_trade_connect links - "crypto", "gold", "silver", "forex"
               Used to pick the best matching copy trade link when multiple options exist
    
    Returns:
        JSON string with structure:
        {
            "ok": true/false,
            "broker": "normalized_broker_name",
            "purpose": "purpose_value",
            "links": [{"title": "...", "url": "..."}, ...],  // Primary: referral/registration URLs
            "videos": [{"title": "...", "url": "..."}, ...],  // Optional: explainer videos
            "error": null or error message
        }
    """
    print(f"   [TOOL EXEC] get_broker_assets(broker='{broker}', purpose='{purpose}', asset_type='{asset_type}', market='{market}')")
    
    # Normalize broker name
    broker_id = normalize_broker(broker)
    if not broker_id:
        result = {
            "ok": False,
            "broker": broker,
            "purpose": purpose,
            "links": [],
            "videos": [],
            "error": "UNSUPPORTED_BROKER"
        }
        print(f"      [ERROR] Unsupported broker: {broker}")
        return json.dumps(result)
    
    # Validate purpose
    valid_purposes: set[str] = {"registration", "copy_trade_start", "copy_trade_open_account", "copy_trade_connect"}
    purpose_lower = purpose.lower().strip()
    if purpose_lower not in valid_purposes:
        result = {
            "ok": False,
            "broker": broker_id,
            "purpose": purpose,
            "links": [],
            "videos": [],
            "error": "UNSUPPORTED_PURPOSE"
        }
        print(f"      [ERROR] Unsupported purpose: {purpose}")
        return json.dumps(result)
    
    # Cast to Purpose type for type checking
    purpose_typed: Purpose = purpose_lower  # type: ignore
    
    # Determine asset type (default to "all" to return both links and videos)
    asset_type_str: AssetType = (asset_type or "all").lower().strip()  # type: ignore
    
    # Validate asset type
    valid_asset_types: set[str] = {"videos", "links", "all"}
    if asset_type_str not in valid_asset_types:
        result = {
            "ok": False,
            "broker": broker_id,
            "purpose": purpose_typed,
            "links": [],
            "videos": [],
            "error": "UNSUPPORTED_ASSET_TYPE"
        }
        print(f"      [ERROR] Unsupported asset_type: {asset_type_str}")
        return json.dumps(result)
    
    # Get links for the given purpose
    links: list[AssetItem] = []
    if asset_type_str in ("links", "all"):
        purpose_links = BROKER_LINKS[broker_id].get(purpose_typed, [])
        
        # For copy_trade_connect, if market is specified, try to pick best matching link
        if purpose_typed == "copy_trade_connect" and market and len(purpose_links) > 1:
            links = pick_copy_trade_link_by_market(purpose_links, market)
        else:
            # Return first link (or all if only one) - cap to 1 for most purposes
            links = purpose_links[:1] if purpose_typed != "copy_trade_connect" else purpose_links[:3]
    
    # Get videos for the given purpose
    videos: list[AssetItem] = []
    if asset_type_str in ("videos", "all"):
        videos = BROKER_VIDEOS[broker_id].get(purpose_typed, [])
        videos = videos[:3]  # Cap to 3 videos
    
    result = {
        "ok": True,
        "broker": broker_id,
        "purpose": purpose_typed,
        "links": links,
        "videos": videos,
        "error": None
    }
    
    print(f"      [SUCCESS] Returning {len(links)} link(s) and {len(videos)} video(s) for {broker_id} (purpose={purpose_typed}, asset_type={asset_type_str})")
    return json.dumps(result)


@function_tool(
    name_override="get_country_offers",
    description_override="Get available bots and brokers for a given country. Returns structured JSON with bots, brokers, and any special notes or constraints."
)
async def get_country_offers(country: str) -> str:
    """
    Get available trading bots and brokers for a given country.
    
    This tool provides authoritative country-specific availability information.
    Always use this tool instead of hardcoding availability data.
    
    Args:
        country: Country name (e.g., "Australia", "Canada", "Israel") or country code (e.g., "AU", "CA")
                Case-insensitive and spacing-tolerant. Accepts common variants like "AU", "AUS", "CA", "CAN"
    
    Returns:
        JSON string with structure:
        {
            "ok": true/false,
            "normalized_country_group": "AUSTRALIA" | "CANADA" | "OTHER",
            "bots": ["Crypto", "Gold", ...],  // List of available bot names
            "brokers": [{"name": "ByBit", "notes": [...]}, ...],  // List of available brokers with optional notes
            "notes": ["PU Prime investment...", ...],  // General notes about availability
            "error": null or error message
        }
    """
    print(f"   [TOOL EXEC] get_country_offers(country='{country}')")
    
    # Validate input
    if not country or not country.strip():
        result = {
            "ok": False,
            "normalized_country_group": None,
            "bots": [],
            "brokers": [],
            "notes": [],
            "error": "MISSING_COUNTRY"
        }
        print(f"      [ERROR] Country parameter is missing or empty")
        return json.dumps(result)
    
    # Normalize country
    normalized_group = normalize_country(country)
    print(f"      [INFO] Input country: '{country}' -> Normalized group: '{normalized_group}'")
    
    # Load country offers data
    country_data = _load_country_offers_data()
    
    # Look up offers for normalized country group
    if normalized_group not in country_data:
        result = {
            "ok": False,
            "normalized_country_group": normalized_group,
            "bots": [],
            "brokers": [],
            "notes": [],
            "error": "COUNTRY_GROUP_NOT_FOUND"
        }
        print(f"      [ERROR] Country group '{normalized_group}' not found in data")
        return json.dumps(result)
    
    offers = country_data[normalized_group]
    
    # Validate and extract data
    bots = offers.get("bots", [])
    brokers = offers.get("brokers", [])
    notes = offers.get("notes", [])
    
    # Validate schema - ensure required keys exist
    required_keys = ["bots", "brokers", "notes"]
    missing_keys = [key for key in required_keys if key not in offers]
    if missing_keys:
        result = {
            "ok": False,
            "normalized_country_group": normalized_group,
            "bots": [],
            "brokers": [],
            "notes": [],
            "error": f"INVALID_DATA_SCHEMA: Missing keys: {', '.join(missing_keys)}"
        }
        print(f"      [ERROR] Invalid data schema - missing keys: {missing_keys}")
        return json.dumps(result)
    
    # Validate brokers structure
    if not isinstance(brokers, list):
        result = {
            "ok": False,
            "normalized_country_group": normalized_group,
            "bots": [],
            "brokers": [],
            "notes": [],
            "error": "INVALID_DATA_SCHEMA: brokers must be a list"
        }
        print(f"      [ERROR] Invalid brokers structure - must be a list")
        return json.dumps(result)
    
    # Validate each broker has required fields
    for broker in brokers:
        if not isinstance(broker, dict):
            result = {
                "ok": False,
                "normalized_country_group": normalized_group,
                "bots": [],
                "brokers": [],
                "notes": [],
                "error": "INVALID_DATA_SCHEMA: broker items must be objects"
            }
            print(f"      [ERROR] Invalid broker structure - must be objects")
            return json.dumps(result)
        if "name" not in broker:
            result = {
                "ok": False,
                "normalized_country_group": normalized_group,
                "bots": [],
                "brokers": [],
                "notes": [],
                "error": "INVALID_DATA_SCHEMA: broker missing 'name' field"
            }
            print(f"      [ERROR] Invalid broker structure - missing 'name' field")
            return json.dumps(result)
    
    # Build result
    result = {
        "ok": True,
        "normalized_country_group": normalized_group,
        "bots": bots,
        "brokers": brokers,
        "notes": notes,
        "error": None
    }
    
    print(f"      [SUCCESS] Returning {len(bots)} bot(s) and {len(brokers)} broker(s) for {normalized_group}")
    print(f"      [INFO] Bots: {', '.join(bots) if bots else 'none'}")
    print(f"      [INFO] Brokers: {', '.join(b.get('name', 'Unknown') for b in brokers) if brokers else 'none'}")
    if notes:
        print(f"      [INFO] Notes: {len(notes)} note(s)")
    
    return json.dumps(result)
