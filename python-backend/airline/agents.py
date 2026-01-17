from __future__ import annotations as _annotations

import random
import string

from agents import Agent, RunContextWrapper, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

# Try importing FileSearchTool - adjust import path if needed
try:
    from agents.tools import FileSearchTool
except ImportError:
    try:
        from agents import FileSearchTool
    except ImportError:
        # Fallback: will use string-based tool configuration if needed
        FileSearchTool = None

from .context import AirlineAgentChatContext
from .demo_data import apply_itinerary_defaults
from .guardrails import jailbreak_guardrail, relevance_guardrail
from .tools import (
    assign_special_service_seat,
    book_new_flight,
    cancel_flight,
    display_seat_map,
    faq_lookup_tool,
    flight_status_tool,
    get_matching_flights,
    get_trip_details,
    issue_compensation,
    update_seat,
)

MODEL = "gpt-5.2"


def seat_services_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    confirmation = ctx.confirmation_number or "[unknown]"
    flight = ctx.flight_number or "[unknown]"
    seat = ctx.seat_number or "[unassigned]"
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        "You are the Seat & Special Services Agent. Handle seat changes and medical/special service requests.\n"
        f"1. The customer's confirmation number is {confirmation} for flight {flight} and current seat {seat}. "
        "If any of these are missing, ask to confirm. If present, act without re-asking. Record any special needs.\n"
        "2. Offer to open the seat map or capture a specific seat. Use assign_special_service_seat for front row/medical requests, "
        "or update_seat for standard changes. If they want to choose visually, call display_seat_map.\n"
        "3. Confirm the new seat and remind the customer it is saved on their confirmation.\n"
        "Important: if the request is clear and data is present, perform multiple tool calls in a single turn without waiting for user replies. "
        "When done, emit at most one handoff: to Refunds & Compensation if disruption support is pending, to Baggage if baggage help is pending, otherwise back to Triage.\n"
        "If the request is unrelated to seats or special services, transfer back to the Triage Agent."
    )


seat_special_services_agent = Agent[AirlineAgentChatContext](
    name="Seat and Special Services Agent",
    model=MODEL,
    handoff_description="Updates seats and handles medical or special service seating.",
    instructions=seat_services_instructions,
    tools=[update_seat, assign_special_service_seat, display_seat_map],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def flight_information_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    confirmation = ctx.confirmation_number or "[unknown]"
    flight = ctx.flight_number or "[unknown]"
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        "You are the Flight Information Agent. Provide status, connection risk, and quick options to keep trips on track.\n"
        f"1. The confirmation number is {confirmation} and the flight number is {flight}. "
        "If either is missing, infer from context or ask once; do not block if you have hydrated data.\n"
        "2. Use flight_status_tool immediately to share current status and note if delays will cause a missed connection.\n"
        "3. If a delay or cancellation impacts the trip, call get_matching_flights to propose alternatives and then hand off to the Booking & Cancellation Agent to secure rebooking.\n"
        "Work autonomously: chain multiple tool calls, then emit a single handoff (one per message) without pausing for user input when data is present."
        "If the customer asks about other topics (baggage, refunds, etc.), transfer to the relevant agent with a single handoff."
    )


flight_information_agent = Agent[AirlineAgentChatContext](
    name="Flight Information Agent",
    model=MODEL,
    handoff_description="Provides flight status, connection impact, and alternate options.",
    instructions=flight_information_instructions,
    tools=[flight_status_tool, get_matching_flights],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def booking_cancellation_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    confirmation = ctx.confirmation_number or "[unknown]"
    flight = ctx.flight_number or "[unknown]"
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        "You are the Booking & Cancellation Agent. You can cancel, book, or rebook customers when plans change.\n"
        f"1. Work from confirmation {confirmation} and flight {flight}. If these are present, proceed without asking; only ask if critical info is missing.\n"
        "2. If the customer needs a new flight, call get_matching_flights if options were not already shared, then use book_new_flight to secure the best match and auto-assign a seat.\n"
        "3. For cancellations, confirm details and use cancel_flight. If they have seat preferences after booking, hand off to the Seat & Special Services Agent.\n"
        "4. Summarize what changed and share the updated confirmation and seat assignment.\n"
        "Execute autonomously: perform multiple tool calls in your turn without waiting for user responses when data is available. Only emit one handoff per message. "
        "Preferred next handoff after rebooking: Seat & Special Services if a seat preference exists; otherwise Refunds & Compensation if disrupted; otherwise Baggage if bags are missing. "
        "If none apply, return to the Triage Agent."
    )


booking_cancellation_agent = Agent[AirlineAgentChatContext](
    name="Booking and Cancellation Agent",
    model=MODEL,
    handoff_description="Handles new bookings, rebookings after delays, and cancellations.",
    instructions=booking_cancellation_instructions,
    tools=[cancel_flight, get_matching_flights, book_new_flight],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def refunds_compensation_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    confirmation = ctx.confirmation_number or "[unknown]"
    case_id = ctx.compensation_case_id or "[not opened]"
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        "You are the Refunds & Compensation Agent. You help customers understand and receive compensation after disruptions.\n"
        f"1. Work from confirmation {confirmation}. If missing, ask for it, then proceed.\n"
        "2. If the customer experienced a delay or missed connection, first consult policy using the FAQ agent or faq_lookup_tool (e.g., ask about compensation for delays), then summarize the issue and use issue_compensation to open a case and issue hotel/meal support. "
        f"Current case id: {case_id}.\n"
        "3. Confirm what was issued and what receipts to keep. If they need baggage help, hand off to the Baggage Agent; otherwise return to Triage when done.\n"
        "Operate autonomously: chain multiple tool calls in your turn without waiting for user input when sufficient data exists. Only emit one handoff per message (usually to FAQ for policy if not consulted yet, then Baggage if needed, else Triage)."
    )


refunds_compensation_agent = Agent[AirlineAgentChatContext](
    name="Refunds and Compensation Agent",
    model=MODEL,
    handoff_description="Opens compensation cases and issues hotel/meal support after delays.",
    instructions=refunds_compensation_instructions,
    tools=[issue_compensation, faq_lookup_tool],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


faq_agent = Agent[AirlineAgentChatContext](
    name="FAQ Agent",
    model=MODEL,
    handoff_description="Answers common questions about policies, baggage, seats, and compensation.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    You are an FAQ agent. If you are speaking to a customer, you probably were transferred from the triage agent.
    Use the following routine to support the customer.
    1. Identify the last question asked by the customer.
    2. Use the faq_lookup_tool to get the answer. Do not rely on your own knowledge.
    3. Respond to the customer with the answer and, if compensation or baggage is needed, offer to transfer to the right agent.""",
    tools=[faq_lookup_tool],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


investments_faq_agent = Agent[AirlineAgentChatContext](
    name="Investments FAQ Agent",
    model=MODEL,
    handoff_description="Answers investment-related questions about trading bots, stocks, investments, and related topics.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    You are the Investments FAQ Agent. You specialize in answering questions about investments, trading bots, stocks, and related financial topics.
    If you are speaking to a customer, you were likely transferred from the triage agent.
    Use the following routine to support the customer:
    1. Identify the last question asked by the customer about investments, trading bots, or related topics.
    2. Use the file_search tool to search the knowledge base for the answer. Do not rely on your own knowledge - only use information from the knowledge base.
    3. If you find relevant information, respond to the customer with the answer from the knowledge base.
    4. If no relevant information is found in the knowledge base, politely inform the customer that you don't have that information available.
    5. When done, return to the Triage Agent.""",
    tools=[FileSearchTool(vector_store_ids=["vs_6943a96a15188191926339603da7e399"])] if FileSearchTool else ["file_search"],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


triage_agent = Agent[AirlineAgentChatContext](
    name="Triage Agent",
    model=MODEL,
    handoff_description="Delegates requests to the right specialist agent (flight info, booking, seats, FAQ, baggage, compensation).",
    instructions=(
        f"{RECOMMENDED_PROMPT_PREFIX} "
        "You are a helpful triaging agent. Route the customer to the best agent: "
        "Flight Information for status/alternates, Booking and Cancellation for booking changes, Seat and Special Services for seating needs, "
        "FAQ for policy questions, Investments FAQ Agent for investment-related questions (trading bots, stocks, investments, etc.), "
        "and Refunds and Compensation for disruption support."
        "First, if the message mentions Paris/New York/Austin and context is missing, call get_trip_details to populate flight/confirmation."
        "If the request is clear, hand off immediately and let the specialist complete multi-step work without asking the user to confirm after each tool call."
        "Never emit more than one handoff per message: do your prep (at most one tool call) and then hand off once."
    ),
    tools=[get_trip_details],
    handoffs=[],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


async def on_seat_booking_handoff(context: RunContextWrapper[AirlineAgentChatContext]) -> None:
    """Ensure context is hydrated when handing off to the seat and special services agent."""
    apply_itinerary_defaults(context.context.state)
    if context.context.state.flight_number is None:
        context.context.state.flight_number = f"FLT-{random.randint(100, 999)}"
    if context.context.state.confirmation_number is None:
        context.context.state.confirmation_number = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )


async def on_booking_handoff(
    context: RunContextWrapper[AirlineAgentChatContext]
) -> None:
    """Prepare context when handing off to booking and cancellation."""
    apply_itinerary_defaults(context.context.state)
    if context.context.state.confirmation_number is None:
        context.context.state.confirmation_number = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
    if context.context.state.flight_number is None:
        context.context.state.flight_number = f"FLT-{random.randint(100, 999)}"


# Set up handoff relationships
triage_agent.handoffs = [
    flight_information_agent,
    handoff(agent=booking_cancellation_agent, on_handoff=on_booking_handoff),
    handoff(agent=seat_special_services_agent, on_handoff=on_seat_booking_handoff),
    faq_agent,
    investments_faq_agent,
    refunds_compensation_agent,
]
faq_agent.handoffs.append(triage_agent)
investments_faq_agent.handoffs.append(triage_agent)
seat_special_services_agent.handoffs.extend([refunds_compensation_agent, triage_agent])
flight_information_agent.handoffs.extend(
    [
        handoff(agent=booking_cancellation_agent, on_handoff=on_booking_handoff),
        triage_agent,
    ]
)
booking_cancellation_agent.handoffs.extend(
    [
        handoff(agent=seat_special_services_agent, on_handoff=on_seat_booking_handoff),
        refunds_compensation_agent,
        triage_agent,
    ]
)
refunds_compensation_agent.handoffs.extend([faq_agent, triage_agent])
