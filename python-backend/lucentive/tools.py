from __future__ import annotations as _annotations

import json
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

# Broker links database (for future use when asset_type="links" or "all")
BROKER_LINKS: dict[BrokerId, list[AssetItem]] = {
    "bybit": [
        {"title": "Bybit Referral Program", "url": "https://bybit.com/en/invite?ref=BYQLKL"},
        {"title": "Bybit Invite to Copy Trade", "url": "https://i.bybit.com/1Zabpd4n?action=inviteToCopy"},
    ],
    "vantage": [
        {
            "title": "Vantage Registration",
            "url": "https://www.vantagemarkets.com/forex-trading/forex-trading-account/?affid=7361340",
        },
        {
            "title": "Vantage Copy Trade (Crypto - Dave)",
            "url": "https://vantageapp.onelink.me/qaPD?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7361340%7Cplatform-copytrading&deep_link_sub1=spid-820189",
        },
        {
            "title": "Vantage Copy Trade (Gold - Dave)",
            "url": "https://vantageapp.onelink.me/qaPD?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7361340%7Cplatform-copytrading&deep_link_sub1=spid-795666",
        },
        {
            "title": "Vantage Copy Trade (Forex - Dave)",
            "url": "https://vantageapp.onelink.me/qaPD?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7361340%7Cplatform-copytrading&deep_link_sub1=spid-828839",
        },
    ],
    "pu_prime": [
        {
            "title": "PU Prime Registration",
            "url": "https://www.puprime.partners/forex-trading-account/?affid=7525953",
        },
        {
            "title": "PU Prime Copy Trade (Silver - Adi)",
            "url": "https://puprime.onelink.me/O5Jx?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7525953%7Cplatform-copytrading&deep_link_sub1=spid-825967&campaignCode=1pHJLS6RBENRLbA7/b+Ayg==",
        },
        {
            "title": "PU Prime Copy Trade (Gold - Adi No Swap)",
            "url": "https://puprime.onelink.me/O5Jx?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7525953%7Cplatform-copytrading&deep_link_sub1=spid-825948&campaignCode=1pHJLS6RBENRLbA7/b+Ayg==",
        },
    ],
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


@function_tool(
    name_override="get_broker_assets",
    description_override="Return broker tutorial videos (and optionally other assets) for a given broker and onboarding purpose."
)
async def get_broker_assets(
    broker: str,
    purpose: str,
    asset_type: Optional[str] = None,
    market: Optional[str] = None,
) -> str:
    """
    Get broker assets (videos and/or links) for a given broker and purpose.
    
    Args:
        broker: Broker name (Bybit, Vantage, PU Prime) - case-insensitive
        purpose: Which onboarding step - "registration", "copy_trade_start", 
                "copy_trade_open_account", "copy_trade_connect"
        asset_type: Type of assets requested - "videos" (default), "links", or "all"
        market: Optional market type for future filtering - "crypto", "gold", "silver", "forex"
    
    Returns:
        JSON string with structure:
        {
            "ok": true/false,
            "broker": "normalized_broker_name",
            "purpose": "purpose_value",
            "assets": [{"title": "...", "url": "..."}, ...],
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
            "assets": [],
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
            "assets": [],
            "error": "UNSUPPORTED_PURPOSE"
        }
        print(f"      [ERROR] Unsupported purpose: {purpose}")
        return json.dumps(result)
    
    # Cast to Purpose type for type checking
    purpose_typed: Purpose = purpose_lower  # type: ignore
    
    # Determine asset type (default to "videos")
    asset_type_str: AssetType = (asset_type or "videos").lower().strip()  # type: ignore
    
    # Validate asset type
    valid_asset_types: set[str] = {"videos", "links", "all"}
    if asset_type_str not in valid_asset_types:
        result = {
            "ok": False,
            "broker": broker_id,
            "purpose": purpose_typed,
            "assets": [],
            "error": "UNSUPPORTED_ASSET_TYPE"
        }
        print(f"      [ERROR] Unsupported asset_type: {asset_type_str}")
        return json.dumps(result)
    
    # Get assets based on asset_type
    assets: list[AssetItem] = []
    
    if asset_type_str == "videos":
        # Return videos for the given purpose
        videos = BROKER_VIDEOS[broker_id].get(purpose_typed, [])
        assets = videos[:3]  # Cap to 3
    elif asset_type_str == "links":
        # For now, links are not purpose-specific, return all links (capped to 3)
        # Future: can add purpose-specific link mapping if needed
        all_links = BROKER_LINKS[broker_id]
        assets = all_links[:3]
    else:  # asset_type_str == "all"
        # Return both videos and links
        videos = BROKER_VIDEOS[broker_id].get(purpose_typed, [])
        all_links = BROKER_LINKS[broker_id]
        # Combine and cap to 3 total
        combined = videos + all_links
        assets = combined[:3]
    
    result = {
        "ok": True,
        "broker": broker_id,
        "purpose": purpose_typed,
        "assets": assets,
        "error": None
    }
    
    print(f"      [SUCCESS] Returning {len(assets)} asset(s) for {broker_id} (purpose={purpose_typed}, asset_type={asset_type_str})")
    return json.dumps(result)
