from __future__ import annotations as _annotations

import json
from datetime import datetime, timedelta, time, timezone

try:
    import pytz
    PYTZ_AVAILABLE = True
    print(f"[TOOLS MODULE] pytz imported successfully, version: {pytz.__version__}")
except ImportError as e:
    PYTZ_AVAILABLE = False
    print(f"[TOOLS MODULE] pytz import failed: {e}")
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        # Fallback for Python < 3.9
        try:
            from backports.zoneinfo import ZoneInfo
        except ImportError:
            ZoneInfo = None

from agents import RunContextWrapper, function_tool
from chatkit.types import ProgressUpdateEvent

from .context import AirlineAgentChatContext
from .context_cache import set_lead_info, set_onboarding_state, get_onboarding_state
from .scheduling import compute_call_availability_status

CALENDLY_BOOKING_URL = "https://calendly.com/lucentiveclub-support/30min"


def _parse_utc_stamp(s: str | None) -> datetime | None:
    """
    Parse timestamps like '2026-01-29 09:00:00 UTC' into an aware datetime (UTC).
    """
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S UTC")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@function_tool(
    name_override="get_scheduling_recommendation",
    description_override=(
        "Return the recommended next scheduling offer based on current service availability. "
        "Provides a user_safe_message that should be sent verbatim."
    ),
)
async def get_scheduling_recommendation(exclude_actions: list[str] | None = None) -> str:
    """
    Deterministic helper for the Scheduling Agent.

    This tool returns a single recommended_action plus a user_safe_message the agent should
    send verbatim, to avoid model-only branching mistakes.
    """
    now_utc = datetime.now(timezone.utc)
    status = compute_call_availability_status(now_utc)

    customer_service = status.get("customer_service")
    window_start = _parse_utc_stamp(status.get("window_start_utc"))

    minutes_until_open: int | None = None
    if customer_service == "currently_closed" and window_start is not None:
        delta_seconds = (window_start - now_utc).total_seconds()
        if delta_seconds > 0:
            # round up to be conservative (avoid understating wait)
            minutes_until_open = int((delta_seconds + 59) // 60)
        else:
            minutes_until_open = 0

    # Build an ordered list of allowed actions based on deterministic availability.
    if customer_service == "open":
        candidate_actions = ["offer_20_min", "offer_2_4_hours", "offer_calendly"]
    else:
        if minutes_until_open is not None and minutes_until_open <= 240:
            candidate_actions = ["offer_2_4_hours", "offer_calendly"]
        else:
            candidate_actions = ["offer_calendly"]

    # Allow the agent to step down deterministically on user decline.
    excluded = set()
    if isinstance(exclude_actions, list):
        excluded = {str(a) for a in exclude_actions if a}

    recommended_action = next((a for a in candidate_actions if a not in excluded), "offer_calendly")

    if recommended_action == "offer_20_min":
        user_safe_message = "I can have someone call you in about 20 minutes. Does that work?"
    elif recommended_action == "offer_2_4_hours":
        # Only say "We're closed" when we're actually closed; when open and stepping down from 20 min, don't.
        if customer_service == "currently_closed":
            user_safe_message = "We're closed right now, but I can have someone call you in 2-4 hours. Does that work?"
        else:
            user_safe_message = "I can have someone call you in 2-4 hours. Does that work?"
    else:
        user_safe_message = (
            "Let me help you schedule a call for later. "
            f"Here's our booking page where you can select a time that works for you: {CALENDLY_BOOKING_URL}\n\n"
            "In the meantime, do you have any questions or anything I can help you with?"
        )

    payload = {
        "now_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "recommended_action": recommended_action,
        "user_safe_message": user_safe_message,
        "minutes_until_open": minutes_until_open,
        "exclude_actions": list(excluded),
        "candidate_actions": candidate_actions,
        "availability": status,
    }
    return json.dumps(payload)


@function_tool(
    name_override="confrimation_call",
    description_override=(
        "Call this when the customer has accepted a callback time (e.g. said yes to '20 minutes' or '2-4 hours'). "
        "Returns a suggested_response to send to the user verbatim. After sending it, hand off to the Triage Agent."
    ),
)
async def confirm_callback() -> str:
    """
    Called when the user confirms a callback time slot. Returns JSON with the exact message
    the Scheduling Agent should send to the user, then the agent must hand off to Triage.
    """
    payload = {
        "suggested_response": "Great, someone from our team will call you within this timeframe.",
    }
    return json.dumps(payload)


@function_tool(
    name_override="get_calendly_booking_link",
    description_override="Get the Calendly booking link for scheduling a call when immediate callbacks are not available."
)
async def get_calendly_booking_link() -> str:
    """
    Returns the Calendly booking URL for customers to schedule calls.
    Use this when neither 20 minutes nor 2-4 hours callback options are available.
    
    Returns:
        A message with the Calendly booking link
    """
    return (
        f"You can schedule a call at your convenience using our booking page: {CALENDLY_BOOKING_URL}\n"
        "Simply select a time that works for you, and we'll call you at the scheduled time."
    )


@function_tool(
    name_override="update_onboarding_state",
    description_override="Update the onboarding state to track progress through the onboarding flow. Call this after each step is completed to persist the state."
)
async def update_onboarding_state(
    run_context: RunContextWrapper[AirlineAgentChatContext],
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
) -> str:
    """
    Update the onboarding state in the context.
    
    This tool programmatically updates the onboarding_state dictionary in the context,
    ensuring that progress through the onboarding flow is properly tracked and persisted.
    
    Args:
        step_name: Name of the step to add to completed_steps (e.g., "trading_experience", "bot_recommendation", "broker_selection", "budget_check", "profit_share_clarification", "instructions")
        trading_experience: User's trading experience level (e.g., "yes", "no", "beginner", "experienced")
        previous_broker: Name of the broker the user previously used (if any)
        trading_type: Type of trading the user did (e.g., "stocks", "forex", "crypto", "futures")
        bot_preference: User's chosen bot type from step 2a (e.g., "Gold", "Forex", "Crypto")
        broker_preference: User's chosen broker from step 2b (e.g., "Vantage", "PU Prime")
        budget_confirmed: Whether the user confirmed they have the minimum budget (True/False)
        budget_amount: The budget amount the user mentioned (if any)
        demo_offered: Whether a demo account was offered (True/False)
        instructions_provided: Whether instructions have been provided (True/False)
        onboarding_complete: Whether onboarding is fully complete - user has opened account AND set up copy trading (True/False)
    
    Returns:
        Confirmation message indicating the state was updated
    """
    print(f"   [TOOL EXEC] update_onboarding_state(step_name='{step_name}', trading_experience='{trading_experience}', previous_broker='{previous_broker}', trading_type='{trading_type}', bot_preference='{bot_preference}', broker_preference='{broker_preference}', budget_confirmed={budget_confirmed}, budget_amount={budget_amount}, demo_offered={demo_offered}, instructions_provided={instructions_provided}, onboarding_complete={onboarding_complete})")
    
    ctx = run_context.context.state
    
    # Initialize onboarding_state if it doesn't exist
    if ctx.onboarding_state is None:
        ctx.onboarding_state = {}
    
    # Initialize completed_steps list if it doesn't exist
    if "completed_steps" not in ctx.onboarding_state:
        ctx.onboarding_state["completed_steps"] = []
    
    # Update completed_steps if step_name is provided
    if step_name and step_name not in ctx.onboarding_state["completed_steps"]:
        ctx.onboarding_state["completed_steps"].append(step_name)
        print(f"      Added step '{step_name}' to completed_steps")
    
    # Update individual fields if provided
    if trading_experience is not None:
        ctx.onboarding_state["trading_experience"] = trading_experience
        print(f"      Updated trading_experience: {trading_experience}")
    
    if previous_broker is not None:
        ctx.onboarding_state["previous_broker"] = previous_broker
        print(f"      Updated previous_broker: {previous_broker}")
    
    if trading_type is not None:
        ctx.onboarding_state["trading_type"] = trading_type
        print(f"      Updated trading_type: {trading_type}")
    
    if bot_preference is not None:
        ctx.onboarding_state["bot_preference"] = bot_preference
        print(f"      Updated bot_preference: {bot_preference}")
    
    if broker_preference is not None:
        ctx.onboarding_state["broker_preference"] = broker_preference
        print(f"      Updated broker_preference: {broker_preference}")
    
    if budget_confirmed is not None:
        ctx.onboarding_state["budget_confirmed"] = budget_confirmed
        print(f"      Updated budget_confirmed: {budget_confirmed}")
    
    if budget_amount is not None:
        ctx.onboarding_state["budget_amount"] = budget_amount
        print(f"      Updated budget_amount: {budget_amount}")
    
    if demo_offered is not None:
        ctx.onboarding_state["demo_offered"] = demo_offered
        print(f"      Updated demo_offered: {demo_offered}")
    
    if instructions_provided is not None:
        ctx.onboarding_state["instructions_provided"] = instructions_provided
        print(f"      Updated instructions_provided: {instructions_provided}")
    
    if onboarding_complete is not None:
        ctx.onboarding_state["onboarding_complete"] = onboarding_complete
        print(f"      Updated onboarding_complete: {onboarding_complete}")
    
    # Cache the onboarding_state for persistence across handoffs
    thread_id = None
    if hasattr(run_context.context, 'thread') and run_context.context.thread:
        thread_id = run_context.context.thread.id
        if thread_id:
            set_onboarding_state(thread_id, ctx.onboarding_state.copy())
            print(f"      Cached onboarding_state for thread {thread_id}")
    
    # Return confirmation
    completed_steps = ctx.onboarding_state.get("completed_steps", [])
    return f"Onboarding state updated successfully. Completed steps: {', '.join(completed_steps) if completed_steps else 'none'}"


@function_tool(
    name_override="update_lead_info",
    description_override="Update lead info fields (e.g. country) in the conversation context so the UI variables reflect user corrections."
)
async def update_lead_info(
    run_context: RunContextWrapper[AirlineAgentChatContext],
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
    print(
        "   [TOOL EXEC] update_lead_info("
        f"first_name={first_name!r}, email={email!r}, phone={phone!r}, country={country!r}, new_lead={new_lead!r})"
    )

    ctx = run_context.context.state

    # Update individual fields if provided (ignore None so callers can update one field at a time)
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

    # Cache the lead info for persistence across handoffs
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
            print(f"      Cached lead info for thread {thread_id}: {lead_info_dict}")

    return (
        "Lead info updated successfully."
        f" first_name={ctx.first_name!r}, country={ctx.country!r}, new_lead={ctx.new_lead!r}"
    )
