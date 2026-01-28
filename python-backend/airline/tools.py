from __future__ import annotations as _annotations

import json
import os
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

try:
    import httpx
except ImportError:
    httpx = None

from agents import RunContextWrapper, function_tool
from chatkit.types import ProgressUpdateEvent

from .context import AirlineAgentChatContext
from .context_cache import set_lead_info, set_onboarding_state, get_onboarding_state
from .scheduling import compute_call_availability_status


@function_tool(
    name_override="check_call_availability",
    description_override="Check customer service availability window and return current status with day, service status, and time information."
)
async def check_call_availability() -> str:
    """
    Check customer service availability based on business hours.
    Window: 11:00 Israel time to 20:00 Guatemala time (converted to UTC).
    Returns JSON with: day, customer_service status, and service_opens/service_closes information.
    No calls on Sundays.
    """
    print(f"   [TOOL EXEC] check_call_availability()")
    # Use timezone.utc which is always available
    now_utc = datetime.now(timezone.utc)
    print(f"      Current UTC time: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    status = compute_call_availability_status(now_utc)
    result = json.dumps(status)
    print(f"      Result: {result}")
    return result


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
    calendly_url = "https://calendly.com/lucentiveclub-support/30min"
    return (
        f"You can schedule a call at your convenience using our booking page: {calendly_url}\n"
        "Simply select a time that works for you, and we'll call you at the scheduled time."
    )


@function_tool(
    name_override="book_calendly_call",
    description_override="Book a Calendly appointment for a customer call using the Zapier MCP integration. Returns a booking link or confirmation."
)
async def book_calendly_call(
    customer_email: str | None = None,
    preferred_date: str | None = None,
    preferred_time: str | None = None,
) -> str:
    """
    Book a Calendly appointment through Zapier MCP.
    Uses the MCP endpoint to schedule a call for the customer.
    
    Args:
        customer_email: Customer's email address (optional)
        preferred_date: Preferred date in YYYY-MM-DD format (optional)
        preferred_time: Preferred time in HH:MM format (optional)
    
    Returns:
        Booking confirmation with link or details
    """
    print(f"   [TOOL EXEC] book_calendly_call(email='{customer_email}', date='{preferred_date}', time='{preferred_time}')")
    # Get MCP configuration from environment variables
    # Set these in your .env file:
    # ZAPIER_MCP_URL=https://mcp.zapier.com/api/mcp/mcp
    # ZAPIER_MCP_TOKEN=your_token_here
    mcp_url = os.getenv("ZAPIER_MCP_URL", "https://mcp.zapier.com/api/mcp/mcp")
    # Use environment variable if set, otherwise use provided token as fallback
    mcp_token = os.getenv("ZAPIER_MCP_TOKEN", "ZDY2ZDVjMzAtNzZjMS00NWZhLWE2OTctYzk0ZjA0Y2FjYmM4OjQ1NzNiZGM2LTg4ZjUtNDMzMi1hNGQ1LTU5ZmY0NzQxYjVmMQ==")
    
    if httpx is None:
        # Fallback if httpx not available - return a message about manual booking
        return (
            "I'll help you schedule a call. Please use this booking link to select a time that works for you: "
            "[Calendly booking link would be provided here]. "
            "Alternatively, I can have someone call you back during our business hours."
        )
    
    try:
        # MCP protocol uses JSON-RPC format
        # Call the MCP endpoint to list available tools or book an appointment
        headers = {
            "Authorization": f"Bearer {mcp_token}",
            "Content-Type": "application/json",
        }
        
        # Try to call the MCP endpoint to book a Calendly event
        # The exact structure depends on Zapier's MCP implementation
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "calendly_create_event",  # This may need to be adjusted based on actual tool name
                "arguments": {
                    "email": customer_email or "customer@example.com",
                    "date": preferred_date,
                    "time": preferred_time,
                }
            },
            "id": 1
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                mcp_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            # Handle MCP response
            if "result" in result:
                booking_info = result["result"]
                if isinstance(booking_info, dict) and "booking_link" in booking_info:
                    return f"Great! I've scheduled your call. Here's your booking link: {booking_info['booking_link']}"
                elif isinstance(booking_info, dict) and "content" in booking_info:
                    # MCP tools return content in a specific format
                    content = booking_info.get("content", [])
                    if content and isinstance(content[0], dict):
                        text = content[0].get("text", "")
                        return f"Booking confirmed! {text}"
                return f"Booking request submitted. {json.dumps(booking_info)}"
            elif "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                # Fallback to providing a generic booking message
                return (
                    f"I encountered an issue with the booking system ({error_msg}). "
                    "Let me provide you with our booking link instead. "
                    "You can schedule a call at your convenience using our Calendly page."
                )
            else:
                # If response format is unexpected, provide fallback
                return (
                    "I'm setting up your call booking. "
                    "You'll receive a booking link shortly where you can select a time that works for you."
                )
                
    except httpx.HTTPError as e:
        # If HTTP request fails, provide fallback message
        return (
            "I'm having trouble accessing the booking system right now. "
            "Let me provide you with our general booking information. "
            "You can schedule a call at your convenience, and we'll call you back during our business hours."
        )
    except Exception as e:
        # Generic fallback for any other errors
        return (
            "I'll help you schedule a call. "
            "Please let me know your preferred date and time, and I'll arrange for someone to call you back "
            "during our business hours (Monday-Saturday, 11:00 AM - 8:00 PM)."
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
        step_name: Name of the step to add to completed_steps (e.g., "trading_experience", "bot_recommendation", "budget_check", "profit_share_clarification", "instructions")
        trading_experience: User's trading experience level (e.g., "yes", "no", "beginner", "experienced")
        previous_broker: Name of the broker the user previously used (if any)
        trading_type: Type of trading the user did (e.g., "stocks", "forex", "crypto", "futures")
        budget_confirmed: Whether the user confirmed they have the minimum budget (True/False)
        budget_amount: The budget amount the user mentioned (if any)
        demo_offered: Whether a demo account was offered (True/False)
        instructions_provided: Whether instructions have been provided (True/False)
        onboarding_complete: Whether onboarding is fully complete - user has opened account AND set up copy trading (True/False)
    
    Returns:
        Confirmation message indicating the state was updated
    """
    print(f"   [TOOL EXEC] update_onboarding_state(step_name='{step_name}', trading_experience='{trading_experience}', previous_broker='{previous_broker}', trading_type='{trading_type}', budget_confirmed={budget_confirmed}, budget_amount={budget_amount}, demo_offered={demo_offered}, instructions_provided={instructions_provided}, onboarding_complete={onboarding_complete})")
    
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
