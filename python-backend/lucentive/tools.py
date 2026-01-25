from __future__ import annotations as _annotations

import json
from typing import Literal, Optional

from agents import function_tool

# Type definitions
BrokerId = Literal["bybit", "vantage", "pu_prime"]
Purpose = Literal["registration", "copy_trade", "all"]
Market = Literal["crypto", "gold", "silver", "forex"]

# Broker link structure
BrokerLink = dict[str, str]  # {title: str, url: str}

# Broker links database
BROKER_LINKS: dict[BrokerId, list[BrokerLink]] = {
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


def pick_copy_trade_link(all_links: list[BrokerLink], market: Optional[str] = None) -> list[BrokerLink]:
    """Pick the best matching copy-trade link based on market preference."""
    copy_trade_links = [link for link in all_links if "copy trade" in link["title"].lower()]
    
    if not market:
        # Best-effort: return first copy-trade link
        return copy_trade_links[:1] if copy_trade_links else []
    
    # Try to match market in title (e.g., "(Crypto", "(Gold", etc.)
    market_lower = market.lower()
    for link in copy_trade_links:
        # Look for pattern like "(Crypto", "(Gold", etc.
        if f"({market_lower}" in link["title"].lower():
            return [link]
    
    # Fallback: return first copy-trade link if no match
    return copy_trade_links[:1] if copy_trade_links else []


@function_tool(
    name_override="get_broker_links",
    description_override="Return broker-specific links (registration or copy-trade) as {title,url} list. Returns 0-3 links depending on purpose and market."
)
async def get_broker_links(
    broker: str,
    purpose: Optional[str] = None,
    market: Optional[str] = None,
) -> str:
    """
    Get broker-specific links (registration or copy-trade) as a JSON array.
    
    Args:
        broker: Broker name (Bybit, Vantage, PU Prime) - case-insensitive
        purpose: Which links to return - "registration" (registration link only),
                "copy_trade" (best matching copy-trade link), or "all" (all links, max 3)
        market: Used for copy-trade links where market matters - "crypto", "gold", "silver", "forex"
    
    Returns:
        JSON string with structure:
        {
            "ok": true/false,
            "broker": "normalized_broker_name",
            "links": [{"title": "...", "url": "..."}, ...],
            "error": null or "UNSUPPORTED_BROKER"
        }
    """
    print(f"   [TOOL EXEC] get_broker_links(broker='{broker}', purpose='{purpose}', market='{market}')")
    
    # Normalize broker name
    broker_id = normalize_broker(broker)
    if not broker_id:
        result = {
            "ok": False,
            "broker": broker,
            "links": [],
            "error": "UNSUPPORTED_BROKER"
        }
        print(f"      [ERROR] Unsupported broker: {broker}")
        return json.dumps(result)
    
    # Get all links for this broker
    all_links = BROKER_LINKS[broker_id]
    
    # Determine purpose (default to "all")
    purpose_str = (purpose or "all").lower().strip()
    
    # Validate purpose (default to "all" if invalid)
    valid_purposes: set[str] = {"registration", "copy_trade", "all"}
    if purpose_str not in valid_purposes:
        print(f"      [WARNING] Invalid purpose '{purpose}', defaulting to 'all'")
        purpose_str = "all"
    
    # Filter links based on purpose
    links: list[BrokerLink] = []
    
    if purpose_str == "registration":
        # Return registration link only
        registration_links = [link for link in all_links if "registration" in link["title"].lower()]
        links = registration_links[:1]  # Max 1 registration link
    elif purpose_str == "copy_trade":
        # Return best matching copy-trade link
        links = pick_copy_trade_link(all_links, market)
    else:
        # "all" - return all links but cap to 3
        links = all_links[:3]
    
    result = {
        "ok": True,
        "broker": broker_id,
        "links": links,
        "error": None
    }
    
    print(f"      [SUCCESS] Returning {len(links)} link(s) for {broker_id} (purpose={purpose_str})")
    return json.dumps(result)
