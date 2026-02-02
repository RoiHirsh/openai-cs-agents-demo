from __future__ import annotations as _annotations

from pathlib import Path

from dotenv import load_dotenv
from agents import Agent, RunContextWrapper, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

# Load environment variables
load_dotenv()

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
from .context_cache import restore_lead_info_to_context, restore_onboarding_state_to_context
from .guardrails import jailbreak_guardrail, relevance_guardrail
from .tools import (
    get_scheduling_context,
    update_lead_info,
    update_onboarding_state,
)

# Import the new broker assets tool from lucentive module
try:
    from lucentive.tools import get_broker_assets, get_country_offers
except ImportError:
    # Fallback if lucentive module not available
    get_broker_assets = None
    get_country_offers = None

MODEL = "gpt-5.2"


investments_faq_agent = Agent[AirlineAgentChatContext](
    name="Investments FAQ Agent",
    model=MODEL,
    handoff_description="Answers investment-related questions about trading bots, stocks, investments, and related topics.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    You are the Investments FAQ Agent. You specialize in answering questions about investments, trading bots, stocks, and related financial topics.
    If you are speaking to a customer, you were likely transferred from the triage agent.
    
    CRITICAL: Only answer when the customer has asked a SPECIFIC QUESTION. Do NOT provide information upfront or give unsolicited answers. If no question has been asked, politely ask what they'd like to know or return to the Triage Agent.
    
    Important: You should respond as a knowledgeable human expert, not as an AI agent. Answer questions naturally and confidently as if you personally know the information.
    
    Use the following routine to support the customer:
    1. First, check if the customer has asked a specific question. If not, ask what they'd like to know or return to Triage Agent.
    2. If a question was asked, identify the specific question about investments, trading bots, or related topics.
    3. Use the file_search tool to find the relevant information (use it silently in the background - do not mention it to the customer).
    4. Respond to the customer naturally and conversationally with the answer. Answer as if you know this information personally - do not mention sources, knowledge bases, or that you "looked up" anything. Never say phrases like "the info provided says", "according to the knowledge base", or "based on the documentation".
    5. If you cannot find relevant information, politely inform the customer that you don't have that information available right now, then hand off to the Triage Agent. This ensures that the next time around, the conversation will go back and start with the Triage Agent for proper follow-up handling.
    6. When done, return to the Triage Agent.""",
    tools=[FileSearchTool(vector_store_ids=["vs_6943a96a15188191926339603da7e399"])] if FileSearchTool else ["file_search"],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def _load_scheduling_skill() -> str:
    skill_path = Path(__file__).parent / "skills" / "scheduling" / "SKILL.md"
    try:
        return skill_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _load_onboarding_skill() -> str:
    skill_path = Path(__file__).parent / "skills" / "onboarding" / "SKILL.md"
    try:
        return skill_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def scheduling_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    skill_content = _load_scheduling_skill()
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        "FIRST RULE: When the user says yes/sure/ok/yes please to a callback, reply with ONLY: \"That's great, someone will give you a call in the next [timeframe].\" Do not ask for phone, timezone, or country code. Never.\n"
        "\n"
        "You are the Scheduling Agent. The user has asked to be called back and was handed off from Triage.\n"
        "\n"
        "CRITICAL: When the user ACCEPTS a callback (e.g. \"yes\", \"sure\", \"ok\", \"yes please\"), reply with ONLY a "
        "short confirmation of the timeframe (e.g. \"That's great, someone will give you a call in the next 2–4 hours.\") "
        "and hand off to Triage. NEVER ask for phone number, timezone, or country code—we already have them from the campaign. "
        "Do NOT say \"confirm the best phone number\", \"phone number (with country code)\", \"your time zone\", or \"so we can place the callback\".\n"
        "\n"
        "You have access to the **scheduling skill** below. Follow it. Your only tool is **get_scheduling_context**. "
        "Call it first. It returns **context only** (day, open/closed, why, available offers, reasons). "
        "**Do not** copy-paste any message from the tool. Use the context to reply in **natural language** and explain "
        "why you're offering what you're offering.\n"
        "\n"
        "Offer one option at a time; if the user declines, call the tool again with exclude_actions and offer the next "
        "option. When the user accepts: one confirmation sentence only, then hand off. Do not ask for phone or timezone.\n"
        "\n"
        "---\n"
        "## Scheduling skill\n"
        "\n"
        f"{skill_content}"
    )


scheduling_agent = Agent[AirlineAgentChatContext](
    name="Scheduling Agent",
    model=MODEL,
    handoff_description="Handles call scheduling requests and suggests available call times.",
    instructions=scheduling_instructions,
    tools=[get_scheduling_context],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def onboarding_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    country = ctx.country or "Unknown"
    first_name = ctx.first_name or "there"

    onboarding_state = ctx.onboarding_state or {}
    completed_steps = onboarding_state.get("completed_steps", [])
    trading_experience = onboarding_state.get("trading_experience")
    previous_broker = onboarding_state.get("previous_broker")
    trading_type = onboarding_state.get("trading_type")
    bot_preference = onboarding_state.get("bot_preference")
    broker_preference = onboarding_state.get("broker_preference")
    budget_confirmed = onboarding_state.get("budget_confirmed")
    budget_amount = onboarding_state.get("budget_amount")
    demo_offered = onboarding_state.get("demo_offered")
    instructions_provided = onboarding_state.get("instructions_provided")
    onboarding_complete = onboarding_state.get("onboarding_complete", False)

    if "trading_experience" not in completed_steps:
        current_step = "trading_experience"
    elif "bot_recommendation" not in completed_steps:
        current_step = "bot_recommendation"
    elif "broker_selection" not in completed_steps:
        current_step = "broker_selection"
    elif "budget_check" not in completed_steps:
        current_step = "budget_check"
    elif "profit_share_clarification" not in completed_steps:
        current_step = "profit_share_clarification"
    elif "instructions" not in completed_steps:
        current_step = "instructions"
    else:
        current_step = "complete"

    skill_content = _load_onboarding_skill()
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        "You are the Onboarding Agent. Your role is to guide new leads through the onboarding process step by step.\n"
        "\n"
        "Lead information (ALREADY PROVIDED - DO NOT ASK FOR THIS):\n"
        f"- Name: {first_name}\n"
        f"- Country: {country}\n"
        "\n"
        f"CRITICAL: The lead's country is already known ({country}). DO NOT ask the user for their country. "
        "Use the provided country when calling get_country_offers(country). If country shows \"Unknown\", you may ask for it; otherwise use the provided value.\n"
        "\n"
        "Current onboarding state:\n"
        f"- Completed steps: {completed_steps}\n"
        f"- Trading experience: {trading_experience}\n"
        f"- Previous broker: {previous_broker}\n"
        f"- Trading type: {trading_type}\n"
        f"- Bot preference: {bot_preference}\n"
        f"- Broker preference: {broker_preference}\n"
        f"- Budget confirmed: {budget_confirmed}\n"
        f"- Budget amount: {budget_amount}\n"
        f"- Demo offered: {demo_offered}\n"
        f"- Instructions provided: {instructions_provided}\n"
        f"- Onboarding complete: {onboarding_complete}\n"
        f"- Current step to work on: {current_step}\n"
        "\n"
        "You have access to the **onboarding skill** below. Follow it. Use the tools (get_country_offers, get_broker_assets, update_onboarding_state, update_lead_info) as the skill describes. "
        "Do not copy-paste raw JSON to the user; use tool output to reply in natural language.\n"
        "\n"
        "---\n"
        "## Onboarding skill\n"
        "\n"
        f"{skill_content}"
    )


onboarding_agent = Agent[AirlineAgentChatContext](
    name="Onboarding Agent",
    model=MODEL,
    handoff_description="Guides new leads through onboarding: trading experience, budget, broker setup.",
    instructions=onboarding_instructions,
    tools=[
        tool
        for tool in [get_country_offers, get_broker_assets, update_lead_info, update_onboarding_state]
        if tool is not None
    ],  # Add tools if available
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def triage_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    new_lead = ctx.new_lead or False
    onboarding_state = ctx.onboarding_state or {}
    completed_steps = onboarding_state.get("completed_steps", [])
    onboarding_complete = onboarding_state.get("onboarding_complete", False)
    
    # Debug print to verify state values
    print(f"[DEBUG] Triage Agent - new_lead={new_lead}, first_name={ctx.first_name}, country={ctx.country}, onboarding_complete={onboarding_complete}")
    
    # Determine if we should route to onboarding
    # Note: Don't route if user has made a specific request (call/FAQ)
    # This will be handled by the agent's natural language understanding
    should_route_to_onboarding = (
        new_lead and 
        not onboarding_complete
    )
    
    onboarding_instruction = ""
    if should_route_to_onboarding:
        onboarding_instruction = (
            "\n\n"
            "DEFAULT ROUTING - NEW LEAD ONBOARDING (PROACTIVE):\n"
            "- This is a new lead (new_lead=True) who hasn't completed onboarding yet.\n"
            "- DEFAULT ACTION: Route them to the Onboarding Agent proactively - this is the default behavior.\n"
            "- The Onboarding Agent will guide them through the onboarding process step by step.\n"
            "- Only override this default if there's a specific request (call or FAQ question) - those take priority.\n"
            "- The goal is to be proactive and make things moving by routing to onboarding by default.\n"
        )
    
    return (
        f"{RECOMMENDED_PROMPT_PREFIX} "
        "You are a helpful triaging agent. Your role is to understand what the customer needs and route them to the appropriate specialist agent.\n\n"
        "IMPORTANT - USER CORRECTIONS:\n"
        "- If the user corrects a conversation variable (at minimum country), you must:\n"
        "  1) Acknowledge the correction briefly\n"
        "  2) Call update_lead_info(...) to persist the corrected value so the UI variables panel updates\n"
        "  3) Then continue routing normally\n"
        "- Example: if country is Austria but user says 'Actually I'm from Australia', call update_lead_info(country='Australia').\n\n"
        "ROUTING PRIORITY (in order):\n"
        "1. Specific requests take priority (override default onboarding):\n"
        "   - Scheduling Agent: When customer says 'call' or explicitly requests a call or wants to schedule a phone conversation. This includes when they respond 'call' to the initial greeting question asking about their preference.\n"
        "   - Investments FAQ Agent: When customer asks specific questions about trading bots, stocks, investments, fees, profit splits, setup process, etc.\n"
        "2. DEFAULT BEHAVIOR - New lead onboarding (proactive routing):\n"
        "   - Onboarding Agent: If this is a new lead (new_lead=True) who hasn't completed onboarding (onboarding_complete=False), route them to the Onboarding Agent proactively as the default action.\n"
        "   - This is the DEFAULT behavior for new leads - you should route to Onboarding Agent unless there's a specific request that requires Scheduling or FAQ Agent.\n"
        "   - CRITICAL: When a new lead (new_lead=True) responds with 'chat' to the initial greeting, route them to the Onboarding Agent immediately to begin onboarding.\n"
        "   - The goal is to be proactive - make things moving by routing new leads to onboarding by default.\n"
        "   - IMPORTANT: If onboarding_complete=True, do NOT route to Onboarding Agent by default - the user has already completed onboarding.\n\n"
        f"{onboarding_instruction}"
        "When NOT to hand off:\n"
        "- If customer hasn't asked a question yet and they're NOT a new lead - engage them in conversation first\n"
        "- If the message is unclear and they're NOT a new lead - ask for clarification before routing\n"
        "- If onboarding is already complete (onboarding_complete=True) - do NOT route to Onboarding Agent by default. Handle follow-up questions normally by routing to appropriate agents (Scheduling Agent, Investments FAQ Agent, etc.)\n\n"
        "SPECIAL CASE - 'chat' response from new leads:\n"
        "- When a new lead (new_lead=True) says 'chat', this is a direct trigger to begin onboarding - NOT just a preference.\n"
        "- This MUST trigger an immediate handoff to the Onboarding Agent to begin the onboarding process.\n"
        "- You MUST route them to the Onboarding Agent immediately - do NOT just acknowledge and continue.\n"
        "- This is a specific action that requires routing to the Onboarding Agent - treat it the same as a specific request.\n"
        "- Only if they're NOT a new lead or have completed onboarding should you acknowledge and continue naturally.\n\n"
        "CALLBACK ACCEPTANCE - When the user says only 'yes', 'sure', 'ok', 'yes please', or 'that works' and the last assistant message was from the Scheduling Agent offering a callback (e.g. 20 minutes or 2–4 hours):\n"
        "- Do NOT ask for phone number or timezone. We already have them from the campaign.\n"
        "- Hand off immediately to the Scheduling Agent so it can send the confirmation and close the flow. Do not ask any questions.\n\n"
        "If the request is clear and specific, hand off immediately and let the specialist complete multi-step work without asking the user to confirm after each tool call.\n"
        "Never emit more than one handoff per message: do your prep (at most one tool call) and then hand off once."
    )


triage_agent = Agent[AirlineAgentChatContext](
    name="Triage Agent",
    model=MODEL,
    handoff_description="Delegates requests to the right specialist agent (scheduling, investments FAQ, onboarding).",
    instructions=triage_instructions,
    tools=[update_lead_info],
    handoffs=[],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


async def on_onboarding_handoff(context: RunContextWrapper[AirlineAgentChatContext]) -> None:
    """Ensure lead info and onboarding state are preserved when handing off to the onboarding agent."""
    ctx_state = context.context.state
    # Get thread ID from the context
    thread_id = None
    if hasattr(context.context, 'thread') and context.context.thread:
        thread_id = context.context.thread.id
    
    # CRITICAL: Restore lead info from cache if context was reset during handoff
    if thread_id:
        restore_lead_info_to_context(thread_id, ctx_state)
        restore_onboarding_state_to_context(thread_id, ctx_state)
        print(f"[DEBUG] Onboarding handoff - Restored context for thread {thread_id}")
    
    print(f"[DEBUG] Onboarding handoff - Context state: first_name={ctx_state.first_name}, country={ctx_state.country}, new_lead={ctx_state.new_lead}, email={ctx_state.email}, onboarding_state={ctx_state.onboarding_state}")
    
    # Validate that critical context is present
    if not ctx_state.country or ctx_state.country == "Unknown":
        print(f"[WARNING] Country is missing or Unknown during onboarding handoff!")
    if not ctx_state.first_name:
        print(f"[WARNING] First name is missing during onboarding handoff!")


# Set up handoff relationships
triage_agent.handoffs = [
    investments_faq_agent,
    scheduling_agent,
    handoff(agent=onboarding_agent, on_handoff=on_onboarding_handoff),
]
investments_faq_agent.handoffs.append(triage_agent)
investments_faq_agent.handoffs.append(onboarding_agent)
scheduling_agent.handoffs.append(onboarding_agent)
scheduling_agent.handoffs.append(triage_agent)
onboarding_agent.handoffs.extend([scheduling_agent, investments_faq_agent, triage_agent])