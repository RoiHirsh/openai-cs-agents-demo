from __future__ import annotations as _annotations

import json
import os
import random
import string
from copy import deepcopy
from datetime import datetime, timedelta, time, timezone

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
from .demo_data import active_itinerary, apply_itinerary_defaults, get_itinerary_for_flight


@function_tool(
    name_override="faq_lookup_tool", description_override="Lookup frequently asked questions."
)
async def faq_lookup_tool(question: str) -> str:
    """Lookup answers to frequently asked questions."""
    print(f"   [TOOL EXEC] faq_lookup_tool(question='{question[:50]}{'...' if len(question) > 50 else ''}')")
    q = question.lower()
    if "bag" in q or "baggage" in q:
        return (
            "You are allowed to bring one bag on the plane. "
            "It must be under 50 pounds and 22 inches x 14 inches x 9 inches. "
            "If a bag is delayed or missing, file a baggage claim and we will track it for delivery."
        )
    if "compensation" in q or "delay" in q or "voucher" in q:
        return (
            "For lengthy delays we provide duty-of-care: hotel and meal vouchers plus ground transport where needed. "
            "If the delay is over 3 hours or causes a missed connection, we also open a compensation case and can offer miles or travel credit. "
            "A Refunds & Compensation agent can submit the case and share the voucher details with you."
        )
    elif "seats" in q or "plane" in q:
        return (
            "There are 120 seats on the plane. "
            "There are 22 business class seats and 98 economy seats. "
            "Exit rows are rows 4 and 16. "
            "Rows 5-8 are Economy Plus, with extra legroom."
        )
    elif "wifi" in q:
        return "We have free wifi on the plane, join Airline-Wifi"
    return "I'm sorry, I don't know the answer to that question."


@function_tool(
    name_override="get_trip_details",
    description_override="Infer the disrupted Paris->New York->Austin trip from user text and hydrate context.",
)
async def get_trip_details(
    context: RunContextWrapper[AirlineAgentChatContext], message: str
) -> str:
    """
    If the user mentions Paris, New York, or Austin, hydrate the context with the disrupted mock itinerary.
    Otherwise, hydrate the on-time mock itinerary. Returns the detected flight and confirmation.
    """
    print(f"   [TOOL EXEC] get_trip_details(message='{message[:50]}{'...' if len(message) > 50 else ''}')")
    text = message.lower()
    keywords = ["paris", "new york", "austin"]
    scenario_key = "disrupted" if any(k in text for k in keywords) else "on_time"
    apply_itinerary_defaults(context.context.state, scenario_key=scenario_key)
    ctx = context.context.state
    if scenario_key == "disrupted":
        ctx.origin = ctx.origin or "Paris (CDG)"
        ctx.destination = ctx.destination or "Austin (AUS)"
    segments = ctx.itinerary or []
    segment_summaries = []
    for seg in segments:
        segment_summaries.append(
            f"{seg.get('flight_number')} {seg.get('origin')} -> {seg.get('destination')} "
            f"status: {seg.get('status')}"
        )
    summary = "; ".join(segment_summaries) if segment_summaries else "No segment details available"
    return (
        f"Hydrated {scenario_key} itinerary: flight {ctx.flight_number}, confirmation "
        f"{ctx.confirmation_number}, origin {ctx.origin}, destination {ctx.destination}. {summary}"
    )


@function_tool
async def update_seat(
    context: RunContextWrapper[AirlineAgentChatContext], confirmation_number: str, new_seat: str
) -> str:
    """Update the seat for a given confirmation number."""
    print(f"   [TOOL EXEC] update_seat(confirmation_number='{confirmation_number}', new_seat='{new_seat}')")
    apply_itinerary_defaults(context.context.state)
    context.context.state.confirmation_number = confirmation_number
    context.context.state.seat_number = new_seat
    assert context.context.state.flight_number is not None, "Flight number is required"
    return f"Updated seat to {new_seat} for confirmation number {confirmation_number}"


@function_tool(
    name_override="flight_status_tool",
    description_override="Lookup status for a flight."
)
async def flight_status_tool(
    context: RunContextWrapper[AirlineAgentChatContext], flight_number: str
) -> str:
    """Lookup the status for a flight using mock itineraries."""
    print(f"   [TOOL EXEC] flight_status_tool(flight_number='{flight_number}')")
    await context.context.stream(ProgressUpdateEvent(text=f"Checking status for {flight_number}..."))
    ctx_state = context.context.state
    ctx_state.flight_number = flight_number
    match = get_itinerary_for_flight(flight_number)
    if match:
        scenario_key, itinerary = match
        apply_itinerary_defaults(ctx_state, scenario_key=scenario_key)
        segments = itinerary.get("segments", [])
        rebook_options = itinerary.get("rebook_options", [])
        segment = next(
            (seg for seg in segments if seg.get("flight_number", "").lower() == flight_number.lower()),
            None,
        )
        if segment:
            route = f"{segment.get('origin', 'Unknown')} to {segment.get('destination', 'Unknown')}"
            details = [
                f"Flight {flight_number} ({route})",
                f"Status: {segment.get('status', 'On time')}",
            ]
            if segment.get("gate"):
                details.append(f"Gate: {segment['gate']}")
            if segment.get("departure") and segment.get("arrival"):
                details.append(f"Scheduled {segment['departure']} -> {segment['arrival']}")
            if scenario_key == "disrupted" and segment.get("flight_number") == "PA441":
                details.append("This delay will cause a missed connection to NY802. Reaccommodation is recommended.")
            await context.context.stream(
                ProgressUpdateEvent(text=f"Found status for flight {flight_number}")
            )
            return " | ".join(details)
        replacement = next(
            (
                seg
                for seg in rebook_options
                if seg.get("flight_number", "").lower() == flight_number.lower()
            ),
            None,
        )
        if replacement:
            route = f"{replacement.get('origin', 'Unknown')} to {replacement.get('destination', 'Unknown')}"
            seat = replacement.get("seat", "auto-assign")
            await context.context.stream(
                ProgressUpdateEvent(text=f"Found alternate flight {flight_number}")
            )
            return (
                f"Replacement flight {flight_number} ({route}) is available. "
                f"Departure {replacement.get('departure')} arriving {replacement.get('arrival')}. Seat {seat} held."
            )
    await context.context.stream(ProgressUpdateEvent(text=f"No disruptions found for {flight_number}"))
    return f"Flight {flight_number} is on time and scheduled to depart at gate A10."


@function_tool(
    name_override="baggage_tool",
    description_override="Lookup baggage allowance and fees."
)
async def baggage_tool(query: str) -> str:
    """Lookup baggage allowance and fees."""
    q = query.lower()
    if "fee" in q:
        return "Overweight bag fee is $75."
    if "allowance" in q:
        return "One carry-on and one checked bag (up to 50 lbs) are included."
    if "missing" in q or "lost" in q:
        return "If a bag is missing, file a baggage claim at the airport or with the Baggage Agent so we can track and deliver it."
    return "Please provide details about your baggage inquiry."


@function_tool(
    name_override="get_matching_flights",
    description_override="Find replacement flights when a segment is delayed or cancelled."
)
async def get_matching_flights(
    context: RunContextWrapper[AirlineAgentChatContext],
    origin: str | None = None,
    destination: str | None = None,
) -> str:
    """Return mock matching flights for a disrupted itinerary."""
    print(f"   [TOOL EXEC] get_matching_flights(origin='{origin}', destination='{destination}')")
    await context.context.stream(ProgressUpdateEvent(text="Scanning for matching flights..."))
    ctx_state = context.context.state
    scenario_key, itinerary = active_itinerary(ctx_state)
    apply_itinerary_defaults(ctx_state, scenario_key=scenario_key)
    options = itinerary.get("rebook_options", [])
    if not options:
        await context.context.stream(ProgressUpdateEvent(text="No alternates needed — trip on time"))
        return "All flights are operating on time. No alternate flights are needed."
    filtered = [
        opt
        for opt in options
        if (origin is None or origin.lower() in opt.get("origin", "").lower())
        and (destination is None or destination.lower() in opt.get("destination", "").lower())
    ]
    final_options = filtered or options
    await context.context.stream(
        ProgressUpdateEvent(text=f"Found {len(final_options)} matching flight option(s)")
    )
    lines = []
    for opt in final_options:
        lines.append(
            f"{opt.get('flight_number')} {opt.get('origin')} -> {opt.get('destination')} "
            f"dep {opt.get('departure')} arr {opt.get('arrival')} | seat {opt.get('seat', 'auto-assign')} | {opt.get('note', '')}"
        )
    if scenario_key == "disrupted":
        lines.append("These options arrive in Austin the next day. Overnight hotel and meals are covered.")
    ctx_state.itinerary = ctx_state.itinerary or deepcopy(itinerary.get("segments", []))
    return "Matching flights:\n" + "\n".join(lines)


@function_tool(
    name_override="book_new_flight",
    description_override="Book a new or replacement flight and auto-assign a seat."
)
async def book_new_flight(
    context: RunContextWrapper[AirlineAgentChatContext], flight_number: str | None = None
) -> str:
    """Book a replacement flight using mock inventory and update context."""
    print(f"   [TOOL EXEC] book_new_flight(flight_number='{flight_number}')")
    await context.context.stream(ProgressUpdateEvent(text="Booking replacement flight..."))
    ctx_state = context.context.state
    scenario_key, itinerary = active_itinerary(ctx_state)
    apply_itinerary_defaults(ctx_state, scenario_key=scenario_key)
    options = itinerary.get("rebook_options", [])
    selection = None
    if flight_number:
        selection = next(
            (opt for opt in options if opt.get("flight_number", "").lower() == flight_number.lower()),
            None,
        )
    if selection is None and options:
        selection = options[0]
    if selection is None:
        seat = ctx_state.seat_number or "auto-assign"
        confirmation = ctx_state.confirmation_number or "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
        ctx_state.confirmation_number = confirmation
        await context.context.stream(ProgressUpdateEvent(text="Booked placeholder flight"))
        return (
            f"Booked flight {flight_number or 'TBD'} with confirmation {confirmation}. "
            f"Seat assignment: {seat}."
        )
    ctx_state.flight_number = selection.get("flight_number")
    ctx_state.seat_number = selection.get("seat") or ctx_state.seat_number or "auto-assign"
    ctx_state.itinerary = ctx_state.itinerary or deepcopy(itinerary.get("segments", []))
    updated_itinerary = [
        seg
        for seg in ctx_state.itinerary
        if not (
            scenario_key == "disrupted"
            and seg.get("origin", "").startswith("New York")
            and seg.get("destination", "").startswith("Austin")
        )
    ]
    updated_itinerary.append(
        {
            "flight_number": selection["flight_number"],
            "origin": selection.get("origin", ""),
            "destination": selection.get("destination", ""),
            "departure": selection.get("departure", ""),
            "arrival": selection.get("arrival", ""),
            "status": "Confirmed replacement flight",
            "gate": "TBD",
        }
    )
    ctx_state.itinerary = updated_itinerary
    confirmation = ctx_state.confirmation_number or "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )
    ctx_state.confirmation_number = confirmation
    await context.context.stream(
        ProgressUpdateEvent(
            text=f"Rebooked to {selection['flight_number']} with seat {ctx_state.seat_number}",
        )
    )
    return (
        f"Rebooked to {selection['flight_number']} from {selection.get('origin')} to {selection.get('destination')}. "
        f"Departure {selection.get('departure')}, arrival {selection.get('arrival')} (next day arrival in Austin). "
        f"Seat assigned: {ctx_state.seat_number}. Confirmation {confirmation}."
    )


@function_tool(
    name_override="assign_special_service_seat",
    description_override="Assign front row or special service seating for medical needs."
)
async def assign_special_service_seat(
    context: RunContextWrapper[AirlineAgentChatContext], seat_request: str = "front row for medical needs"
) -> str:
    """Assign a special service seat and record the request."""
    print(f"   [TOOL EXEC] assign_special_service_seat(seat_request='{seat_request}')")
    ctx_state = context.context.state
    apply_itinerary_defaults(ctx_state)
    preferred_seat = "1A" if "front" in seat_request.lower() else "2A"
    ctx_state.seat_number = preferred_seat
    ctx_state.special_service_note = seat_request
    confirmation = ctx_state.confirmation_number or "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )
    ctx_state.confirmation_number = confirmation
    return (
        f"Secured {seat_request} seat {preferred_seat} on flight {ctx_state.flight_number or 'upcoming segment'}. "
        f"Confirmation {confirmation} noted with special service flag."
    )


@function_tool(
    name_override="issue_compensation",
    description_override="Create a compensation case and issue hotel/meal vouchers."
)
async def issue_compensation(
    context: RunContextWrapper[AirlineAgentChatContext], reason: str = "Delay causing missed connection"
) -> str:
    """Open a compensation case and attach vouchers."""
    print(f"   [TOOL EXEC] issue_compensation(reason='{reason}')")
    await context.context.stream(ProgressUpdateEvent(text="Opening compensation case..."))
    ctx_state = context.context.state
    scenario_key, itinerary = active_itinerary(ctx_state)
    apply_itinerary_defaults(ctx_state, scenario_key=scenario_key)
    case_id = ctx_state.compensation_case_id or f"CMP-{random.randint(1000, 9999)}"
    ctx_state.compensation_case_id = case_id
    voucher_values = list(itinerary.get("vouchers", {}).values())
    if voucher_values:
        ctx_state.vouchers = voucher_values
    else:
        ctx_state.vouchers = ctx_state.vouchers or []
    vouchers_text = "; ".join(ctx_state.vouchers) if ctx_state.vouchers else "Documented compensation with no vouchers required."
    await context.context.stream(ProgressUpdateEvent(text=f"Issued vouchers for case {case_id}"))
    return (
        f"Opened compensation case {case_id} for: {reason}. "
        f"Issued: {vouchers_text}. Keep receipts for any hotel or meal costs and attach them to this case."
    )


@function_tool(
    name_override="display_seat_map",
    description_override="Display an interactive seat map to the customer so they can choose a new seat."
)
async def display_seat_map(
    context: RunContextWrapper[AirlineAgentChatContext]
) -> str:
    """Trigger the UI to show an interactive seat map to the customer."""
    print(f"   [TOOL EXEC] display_seat_map()")
    # The returned string will be interpreted by the UI to open the seat selector.
    return "DISPLAY_SEAT_MAP"


@function_tool(
    name_override="cancel_flight",
    description_override="Cancel a flight."
)
async def cancel_flight(
    context: RunContextWrapper[AirlineAgentChatContext]
) -> str:
    """Cancel the flight in the context."""
    print(f"   [TOOL EXEC] cancel_flight()")
    apply_itinerary_defaults(context.context.state)
    fn = context.context.state.flight_number
    assert fn is not None, "Flight number is required"
    confirmation = context.context.state.confirmation_number or "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )
    context.context.state.confirmation_number = confirmation
    return f"Flight {fn} successfully cancelled for confirmation {confirmation}"


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
    if ZoneInfo is not None:
        try:
            israel_tz = ZoneInfo("Asia/Jerusalem")
            guatemala_tz = ZoneInfo("America/Guatemala")
            print(f"      Timezones loaded: Israel={israel_tz}, Guatemala={guatemala_tz}")
        except Exception as e:
            # Fallback if timezones not available
            israel_tz = None
            guatemala_tz = None
            print(f"      Timezone loading failed, using fallback: {e}")
    else:
        print(f"      ZoneInfo not available, using fallback calculations")
    
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
        window_start_israel = datetime.combine(today_israel, time(11, 0), tzinfo=israel_tz)
        window_start_utc = window_start_israel.astimezone(timezone.utc)
        print(f"      Window start: 11:00 Israel = {window_start_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        # Window end: 20:00 Guatemala time today (or next day if it wraps)
        now_guatemala = now_utc.astimezone(guatemala_tz)
        today_guatemala = now_guatemala.date()
        print(f"      Today in Guatemala timezone: {today_guatemala}")
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
