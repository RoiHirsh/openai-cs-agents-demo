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
    
    # Get timezone-aware times for Israel and Guatemala
    israel_tz = None
    guatemala_tz = None
    
    if PYTZ_AVAILABLE:
        print(f"      [USING PYTZ] Attempting to load timezones with pytz...")
        try:
            israel_tz = pytz.timezone("Asia/Jerusalem")
            guatemala_tz = pytz.timezone("America/Guatemala")
            print(f"      Timezones loaded: Israel={israel_tz}, Guatemala={guatemala_tz}")
        except Exception as e:
            israel_tz = None
            guatemala_tz = None
            print(f"      Timezone loading failed, using fallback: {e}")
    elif ZoneInfo is not None:
        print(f"      [USING ZONEINFO] Attempting to load timezones with zoneinfo...")
        try:
            israel_tz = ZoneInfo("Asia/Jerusalem")
            guatemala_tz = ZoneInfo("America/Guatemala")
            print(f"      Timezones loaded: Israel={israel_tz}, Guatemala={guatemala_tz}")
        except Exception as e:
            israel_tz = None
            guatemala_tz = None
            print(f"      Timezone loading failed, using fallback: {e}")
    else:
        print(f"      No timezone library available, using fallback calculations")
    
    # Get current day of week (0 = Monday, 6 = Sunday)
    day_of_week = now_utc.weekday()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day_of_week]
    print(f"      Current day: {day_name} (day_of_week={day_of_week})")
    
    # Check if it's Sunday - no service
    if day_of_week == 6:  # Sunday
        print(f"      [SUNDAY DETECTED] Service closed on Sundays")
        # Calculate next Monday 11:00 Israel time
        days_until_monday = 1
        if israel_tz:
            # Get next Monday's date in Israel timezone
            now_israel = now_utc.astimezone(israel_tz)
            print(f"      Current Israel time: {now_israel.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            next_monday_date = now_israel.date() + timedelta(days=days_until_monday)
            if PYTZ_AVAILABLE:
                next_monday_israel = israel_tz.localize(datetime.combine(next_monday_date, time(11, 0)))
            else:
                next_monday_israel = datetime.combine(next_monday_date, time(11, 0), tzinfo=israel_tz)
            next_monday_utc = next_monday_israel.astimezone(timezone.utc)
            print(f"      Next Monday 11:00 Israel = {next_monday_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            # Fallback: assume 11:00 Israel = 09:00 UTC
            next_monday_date = (now_utc + timedelta(days=days_until_monday)).date()
            next_monday_utc = datetime.combine(next_monday_date, time(9, 0), tzinfo=timezone.utc)
            print(f"      [FALLBACK] Next Monday 09:00 UTC = {next_monday_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        hours_until_open = (next_monday_utc - now_utc).total_seconds() / 3600
        result = json.dumps({
            "day": day_name.lower(),
            "customer_service": "currently_closed",
            "service_opens": f"service will resume on {next_monday_utc.strftime('%A, %B %d')} at 09:00 UTC, {int(hours_until_open)} hours from now"
        })
        print(f"      Result: {result}")
        return result
    
    # Calculate window boundaries
    # Window: 11:00 Israel time to 20:00 Guatemala time
    print(f"      Calculating service window: 11:00 Israel -> 20:00 Guatemala")
    if israel_tz and guatemala_tz:
        # Get today's date in Israel timezone
        now_israel = now_utc.astimezone(israel_tz)
        today_israel = now_israel.date()
        print(f"      Today in Israel timezone: {today_israel}")
        
        # Window start: 11:00 Israel time today
        if PYTZ_AVAILABLE:
            window_start_israel = israel_tz.localize(datetime.combine(today_israel, time(11, 0)))
        else:
            window_start_israel = datetime.combine(today_israel, time(11, 0), tzinfo=israel_tz)
        window_start_utc = window_start_israel.astimezone(timezone.utc)
        print(f"      Window start: 11:00 Israel = {window_start_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        # Window end: 20:00 Guatemala time today (or next day if it wraps)
        now_guatemala = now_utc.astimezone(guatemala_tz)
        today_guatemala = now_guatemala.date()
        print(f"      Today in Guatemala timezone: {today_guatemala}")
        if PYTZ_AVAILABLE:
            window_end_guatemala = guatemala_tz.localize(datetime.combine(today_guatemala, time(20, 0)))
        else:
            window_end_guatemala = datetime.combine(today_guatemala, time(20, 0), tzinfo=guatemala_tz)
        window_end_utc = window_end_guatemala.astimezone(timezone.utc)
        print(f"      Window end: 20:00 Guatemala = {window_end_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        # If window end is before window start, it means it wraps to next day
        if window_end_utc < window_start_utc:
            window_end_utc += timedelta(days=1)
            print(f"      [WINDOW WRAPS] Adjusted end to next day: {window_end_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    else:
        # Fallback calculation
        # Approximate: 11:00 Israel (UTC+2) = 09:00 UTC, 20:00 Guatemala (UTC-6) = 02:00 UTC next day
        print(f"      [FALLBACK MODE] Using approximate timezone offsets")
        today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start_utc = today_utc + timedelta(hours=9)  # 09:00 UTC
        window_end_utc = today_utc + timedelta(days=1, hours=2)  # 02:00 UTC next day
        print(f"      Window start (fallback): {window_start_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"      Window end (fallback): {window_end_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        # If we're past window_end, move to next day
        if now_utc > window_end_utc:
            window_start_utc += timedelta(days=1)
            window_end_utc += timedelta(days=1)
            print(f"      [PAST WINDOW] Moved to next day")
    
    # Check if we're within the window
    print(f"      Checking if current time is within window...")
    print(f"         Window: {window_start_utc.strftime('%H:%M UTC')} to {window_end_utc.strftime('%H:%M UTC')}")
    print(f"         Current: {now_utc.strftime('%H:%M UTC')}")
    
    if window_start_utc <= now_utc <= window_end_utc:
        # Service is open
        print(f"      [SERVICE OPEN] Current time is within service window")
        hours_until_close = (window_end_utc - now_utc).total_seconds() / 3600
        result = json.dumps({
            "day": day_name.lower(),
            "customer_service": "open",
            "service_closes": f"service will close in the next {int(hours_until_close)} hours"
        })
        print(f"      Result: {result}")
        return result
    else:
        # Service is closed
        if now_utc < window_start_utc:
            # Before opening today
            print(f"      [SERVICE CLOSED] Before opening today")
            hours_until_open = (window_start_utc - now_utc).total_seconds() / 3600
            open_time_str = window_start_utc.strftime("%A, %B %d") if hours_until_open > 24 else window_start_utc.strftime("%H:%M UTC")
            result = json.dumps({
                "day": day_name.lower(),
                "customer_service": "currently_closed",
                "service_opens": f"service will resume at {open_time_str}, {int(hours_until_open)} hours from now"
            })
            print(f"      Hours until open: {int(hours_until_open)}")
            print(f"      Result: {result}")
            return result
        else:
            # After closing - next window is tomorrow
            print(f"      [SERVICE CLOSED] After closing today, next window is tomorrow")
            next_window_start = window_start_utc + timedelta(days=1)
            hours_until_open = (next_window_start - now_utc).total_seconds() / 3600
            result = json.dumps({
                "day": day_name.lower(),
                "customer_service": "currently_closed",
                "service_opens": f"service will resume on {next_window_start.strftime('%A, %B %d')} at 09:00 UTC, {int(hours_until_open)} hours from now"
            })
            print(f"      Hours until next window: {int(hours_until_open)}")
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
