from __future__ import annotations as _annotations

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
from .context_cache import restore_lead_info_to_context
from .guardrails import jailbreak_guardrail, relevance_guardrail
from .tools import (
    check_call_availability,
    get_calendly_booking_link,
)

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
    5. If you cannot find relevant information, politely inform the customer that you don't have that information available right now.
    6. When done, return to the Triage Agent.""",
    tools=[FileSearchTool(vector_store_ids=["vs_6943a96a15188191926339603da7e399"])] if FileSearchTool else ["file_search"],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def scheduling_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        "You are the Scheduling Agent. You handle call scheduling requests when a customer wants to speak on the phone with a representative.\n"
        "\n"
        "When a customer requests a call or asks to speak with someone, you must follow this priority order:\n"
        "\n"
        "1. FIRST PRIORITY - Next 20 minutes:\n"
        "   - Call check_call_availability() to get current service status\n"
        "   - If service is open and we're within the availability window, offer a call in the next 20 minutes\n"
        "   - Present this option naturally: 'I can have someone call you in about 20 minutes. Does that work?'\n"
        "\n"
        "2. SECOND PRIORITY - 2-4 hours callback:\n"
        "   - If 20 minutes is not possible (service closed, outside window, or customer declines), suggest a callback in 2-4 hours\n"
        "   - Use the availability information from check_call_availability() to determine if this is feasible\n"
        "   - Present this option: 'How about we schedule a call in 2-4 hours? I can have someone reach out then.'\n"
        "\n"
        "3. FALLBACK - Calendly booking link:\n"
        "   - If neither 20 minutes nor 2-4 hours is possible (outside availability window, customer declines, or service closed), use the get_calendly_booking_link() tool to get the booking link\n"
        "   - Call get_calendly_booking_link() to retrieve the Calendly booking URL\n"
        "   - Present the booking link to the customer: 'Let me help you schedule a call for later. Here's our booking page where you can select a time that works for you.'\n"
        "   - Share the link naturally and let the customer know they can choose their preferred time\n"
        "\n"
        "IMPORTANT RULES:\n"
        "- Always call check_call_availability() FIRST to understand current service status\n"
        "- Only suggest ONE option per message - wait for customer response before offering the next priority\n"
        "- Keep messages short and natural (WhatsApp style)\n"
        "- Do not mention timezones, UTC, or technical scheduling details to the customer\n"
        "- Do not book calls on Sundays (the tool will indicate if it's Sunday)\n"
        "- When scheduling is complete or the customer declines, return to the Triage Agent\n"
        "- If the customer says 'no call' or 'stop calling', acknowledge and return to Triage Agent\n"
        "- If the customer asks specific questions about investments, trading bots, stocks, or other topics unrelated to scheduling, hand off to the Triage Agent so they can be routed to the appropriate specialist. Do NOT attempt to answer these questions yourself."
    )


scheduling_agent = Agent[AirlineAgentChatContext](
    name="Scheduling Agent",
    model=MODEL,
    handoff_description="Handles call scheduling requests and suggests available call times.",
    instructions=scheduling_instructions,
    tools=[check_call_availability, get_calendly_booking_link],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def onboarding_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    country = ctx.country or "Unknown"
    first_name = ctx.first_name or "there"
    
    # Get current onboarding state
    onboarding_state = ctx.onboarding_state or {}
    completed_steps = onboarding_state.get("completed_steps", [])
    trading_experience = onboarding_state.get("trading_experience")
    previous_broker = onboarding_state.get("previous_broker")
    trading_type = onboarding_state.get("trading_type")
    budget_confirmed = onboarding_state.get("budget_confirmed")
    budget_amount = onboarding_state.get("budget_amount")
    demo_offered = onboarding_state.get("demo_offered")
    instructions_provided = onboarding_state.get("instructions_provided")
    
    # Country-to-bot mapping (embedded in prompt)
    country_bot_mapping = """
    COUNTRY-TO-BOT MAPPING:
    - Australia: Crypto bot only. Available broker: ByBit
    - Canada: Gold, Silver, Forex, Cryptocurrencies, Futures bots. Available broker: PU Prime*
    - Any Other Country: Gold, Silver, Forex, Cryptocurrencies, Futures bots. Available brokers: Vantage, PU Prime*, Ox Securities, ByBit
    
    Note: *PU Prime investment in Gold and/or Silver is available only in cents (not dollars) and within 500-10,000 USD investment only
    """
    
    # Broker setup links (embedded in prompt)
    broker_links = """
    BROKER SETUP LINKS:
    
    Vantage:
    - Account creation: [Link 1: Account creation]
    - Copy trading setup: [Link 2: Copy trading setup]
    - Additional instructions: [Link 3: Additional instructions]
    
    PU Prime:
    - Account creation: [Link 1: Account creation]
    - Copy trading setup: [Link 2: Copy trading setup]
    - Additional instructions: [Link 3: Additional instructions]
    
    Ox Securities:
    - Account creation: [Link 1: Account creation]
    - Copy trading setup: [Link 2: Copy trading setup]
    - Additional instructions: [Link 3: Additional instructions]
    
    ByBit:
    - Account creation: [Link 1: Account creation]
    - Copy trading setup: [Link 2: Copy trading setup]
    - Additional instructions: [Link 3: Additional instructions]
    """
    
    # Determine current step based on completed steps
    current_step = None
    if "trading_experience" not in completed_steps:
        current_step = "trading_experience"
    elif "bot_recommendation" not in completed_steps:
        current_step = "bot_recommendation"
    elif "budget_check" not in completed_steps:
        current_step = "budget_check"
    elif "instructions" not in completed_steps:
        current_step = "instructions"
    else:
        current_step = "complete"
    
    instructions = f"""{RECOMMENDED_PROMPT_PREFIX}
    You are the Onboarding Agent. Your role is to guide new leads through the onboarding process step by step.
    
    Lead Information (ALREADY PROVIDED - DO NOT ASK FOR THIS):
    - Name: {first_name}
    - Country: {country}
    
    CRITICAL: The lead's country is already known ({country}). DO NOT ask the user for their country. 
    Use the provided country information directly to recommend appropriate bots and brokers.
    If the country shows "Unknown", you may ask for it. Otherwise, use the provided country value.
    
    {country_bot_mapping}
    
    {broker_links}
    
    CURRENT ONBOARDING STATE:
    - Completed steps: {completed_steps}
    - Trading experience: {trading_experience}
    - Previous broker: {previous_broker}
    - Trading type: {trading_type}
    - Budget confirmed: {budget_confirmed}
    - Budget amount: {budget_amount}
    - Demo offered: {demo_offered}
    - Instructions provided: {instructions_provided}
    - Current step to work on: {current_step}
    
    ONBOARDING FLOW - Ask ONE question at a time:
    
    STEP 1: Trading Experience
    - If "trading_experience" is NOT in completed_steps, ask: "Do you have prior trading experience?"
    - If YES: Ask which broker they used and what type of trading (stocks, forex, crypto, etc.)
    - After getting the answer, you must track this in your memory and note that trading_experience step is complete
    - Remember: previous_broker and trading_type if they provided it
    
    STEP 2: Country-Based Bot Recommendation
    - If "bot_recommendation" is NOT in completed_steps, recommend appropriate AI trading bot(s) based on their country ({country})
    - Use the country-to-bot mapping above to determine which bots are available
    - Explain which bots are available for their country in a friendly, conversational way
    - After explaining, note that bot_recommendation step is complete
    
    STEP 3: Budget Check
    - If "budget_check" is NOT in completed_steps, ask about their investment budget
    - If budget < $500: Offer demo account for 10 days, note that demo_offered=True
    - If budget >= $500: Confirm the amount and move to step 4
    - Remember: budget_confirmed=True, budget_amount, and demo_offered (if applicable)
    - After getting the answer, note that budget_check step is complete
    
    STEP 4: Instructions Phase
    - If "instructions" is NOT in completed_steps:
      - If they have an existing broker (previous_broker is set): Explain copy trading setup with existing broker, share relevant links from broker_links above
      - If they need a new broker: Recommend broker based on country ({country}), explain account creation, share setup links from broker_links above
      - Provide step-by-step instructions for trading copy setup
    - After providing instructions, note that instructions step is complete and onboarding is finished
    
    IMPORTANT RULES:
    - Ask ONLY ONE question per message - wait for the user's response before proceeding to the next step
    - Check the current onboarding state above to resume from where you left off
    - Be conversational and friendly, but stay focused on the onboarding flow
    - Track progress mentally - you know which steps are completed based on the state above
    - NEVER ask for information that is already provided in the "Lead Information" section above
    - Use the provided country ({country}) directly - do not ask the user to confirm or provide it unless it shows "Unknown"
    
    HANDOFF PRIORITY (CRITICAL - These take precedence over onboarding flow):
    - If user requests a call or wants to schedule a phone conversation: IMMEDIATELY hand off to Scheduling Agent
    - If user asks ANY questions about trading bots, investments, fees, profit splits, minimum investment, account ownership, trading strategies, returns, risks, or ANY investment-related topics: IMMEDIATELY hand off to Investments FAQ Agent
    - Examples of questions that require handoff to Investments FAQ Agent:
      * "What is the minimum to invest?"
      * "Who owns the account?"
      * "What are the fees?"
      * "How much can I make?"
      * "What are the risks?"
      * "How do the bots work?"
      * Any question about trading, investments, or financial topics
    - Do NOT try to answer investment/FAQ questions yourself - always hand off to the Investments FAQ Agent
    - When onboarding is complete (all 4 steps done): Hand off back to Triage Agent
    
    ONBOARDING FLOW RULES:
    - Never skip steps - complete them in order: trading_experience → bot_recommendation → budget_check → instructions
    - If the user asks simple clarification questions about the onboarding process itself (e.g., "what do you mean by trading experience?"), you can answer briefly and continue with the current step
    - However, if the question is about investments, trading bots, fees, or any topic that the Investments FAQ Agent handles, you MUST hand off instead of answering
    """
    
    return instructions


onboarding_agent = Agent[AirlineAgentChatContext](
    name="Onboarding Agent",
    model=MODEL,
    handoff_description="Guides new leads through onboarding: trading experience, budget, broker setup.",
    instructions=onboarding_instructions,
    tools=[],  # No tools needed - all data embedded in prompt
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


def triage_instructions(
    run_context: RunContextWrapper[AirlineAgentChatContext], agent: Agent[AirlineAgentChatContext]
) -> str:
    ctx = run_context.context.state
    new_lead = ctx.new_lead or False
    onboarding_state = ctx.onboarding_state or {}
    completed_steps = onboarding_state.get("completed_steps", [])
    onboarding_complete = "instructions" in completed_steps
    
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
            "PRIORITY ROUTING - NEW LEAD ONBOARDING:\n"
            "- This is a new lead (new_lead=True) who hasn't completed onboarding yet.\n"
            "- If the user hasn't made a specific request (call or FAQ question), route them to the Onboarding Agent.\n"
            "- The Onboarding Agent will guide them through the onboarding process step by step.\n"
            "- Specific requests (call, FAQ) take priority over onboarding - handle those first.\n"
        )
    
    return (
        f"{RECOMMENDED_PROMPT_PREFIX} "
        "You are a helpful triaging agent. Your role is to understand what the customer needs and route them to the appropriate specialist agent.\n\n"
        "IMPORTANT: Only hand off to a specialist agent when the customer has asked a SPECIFIC QUESTION or made a SPECIFIC REQUEST.\n\n"
        "ROUTING PRIORITY (in order):\n"
        "1. Specific requests take priority:\n"
        "   - Scheduling Agent: When customer says 'call' or explicitly requests a call or wants to schedule a phone conversation. This includes when they respond 'call' to the initial greeting question asking about their preference.\n"
        "   - Investments FAQ Agent: When customer asks specific questions about trading bots, stocks, investments, fees, profit splits, setup process, etc.\n"
        "2. New lead onboarding (if no specific request):\n"
        "   - Onboarding Agent: If this is a new lead (new_lead=True) who hasn't completed onboarding and hasn't made a specific request, route them to the Onboarding Agent.\n"
        "   - CRITICAL: When a new lead (new_lead=True) responds with 'chat' to the initial greeting, this is NOT a specific request - it's their preference choice. Route them to the Onboarding Agent immediately.\n\n"
        f"{onboarding_instruction}"
        "When NOT to hand off:\n"
        "- If customer hasn't asked a question yet and they're not a new lead - engage them in conversation first\n"
        "- If the message is unclear - ask for clarification before routing\n\n"
        "SPECIAL CASE - 'chat' response from new leads:\n"
        "- When a new lead (new_lead=True) says 'chat', this means they prefer to chat rather than have a call.\n"
        "- This is NOT a specific request that requires a specialist - it's just their preference.\n"
        "- You MUST route them to the Onboarding Agent immediately so they can begin the onboarding process.\n"
        "- Do NOT just acknowledge and continue - you MUST hand off to Onboarding Agent.\n"
        "- Only if they're NOT a new lead or have completed onboarding should you acknowledge and continue naturally.\n\n"
        "If the request is clear and specific, hand off immediately and let the specialist complete multi-step work without asking the user to confirm after each tool call.\n"
        "Never emit more than one handoff per message: do your prep (at most one tool call) and then hand off once."
    )


triage_agent = Agent[AirlineAgentChatContext](
    name="Triage Agent",
    model=MODEL,
    handoff_description="Delegates requests to the right specialist agent (scheduling, investments FAQ, onboarding).",
    instructions=triage_instructions,
    tools=[],
    handoffs=[],
    input_guardrails=[relevance_guardrail, jailbreak_guardrail],
)


async def on_onboarding_handoff(context: RunContextWrapper[AirlineAgentChatContext]) -> None:
    """Ensure lead info is preserved when handing off to the onboarding agent."""
    ctx_state = context.context.state
    # Get thread ID from the context
    thread_id = None
    if hasattr(context.context, 'thread') and context.context.thread:
        thread_id = context.context.thread.id
    
    # CRITICAL: Restore lead info from cache if context was reset during handoff
    if thread_id:
        restore_lead_info_to_context(thread_id, ctx_state)
        print(f"[DEBUG] Onboarding handoff - Restored context for thread {thread_id}")
    
    print(f"[DEBUG] Onboarding handoff - Context state: first_name={ctx_state.first_name}, country={ctx_state.country}, new_lead={ctx_state.new_lead}, email={ctx_state.email}")
    
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