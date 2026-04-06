from __future__ import annotations as _annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from agents import Agent, FileSearchTool, RunContextWrapper, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

load_dotenv()

logger = logging.getLogger(__name__)

from .context import LucentiveAgentChatContext
from .context_cache import restore_lead_info_to_context, restore_onboarding_state_to_context
from .guardrails import jailbreak_guardrail
from .tools import (
    get_broker_assets,
    get_country_offers,
    get_scheduling_context,
    request_human_handoff,
    update_lead_info,
    update_onboarding_state,
)

_VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID", "")

MODEL = "gpt-5.2"

PLAIN_TEXT_RULE = (
    "FORMATTING: Always respond in plain text only. "
    "Never use markdown (no asterisks for bold, no underscores for italic, no dashes for bullets, no # headers). "
    "Never use emojis. Keep responses natural and conversational.\n"
    "CONVERSATION HISTORY: Some messages in the conversation history marked as 'assistant' may be prefixed with [Human Agent]: — "
    "these were written by a human team member, not by you. Do not treat them as your own prior responses and do not reference them as things you said.\n"
    "IDENTITY: You are Perry, a human team member at Lucentive Club. You are not an AI, a bot, or an assistant — you are a person. "
    "Never say 'as an AI', 'as an assistant', 'I'm a chatbot', or anything that frames you as artificial. "
    "If a customer asks whether you are a bot or AI, deflect naturally without confirming or denying. "
    "Never use the same phrasing twice in the same conversation — vary your response each time as a human would. "
    "Always speak in a casual, human WhatsApp tone.\n"
    "NATURAL CONVERSATION: When a customer asks a side or clarifying question mid-conversation, answer it and then resume the topic naturally — "
    "do not repeat your previous question word for word. Re-introduce it the way a human would, for example: "
    "'Anyway, back to what I was asking...' or just flow into it. Never copy-paste your own previous message.\n"
)

_SCHEDULING_SKILL: str | None = None
_ONBOARDING_SKILL: str | None = None
_PRODUCT_INFO_SKILL: str | None = None
_HANDOFF_SKILL_STATIC: str | None = None


def _load_handoff_skill() -> str:
    global _HANDOFF_SKILL_STATIC
    if _HANDOFF_SKILL_STATIC is None:
        skill_path = Path(__file__).parent / "skills" / "handoff" / "SKILL.md"
        try:
            _HANDOFF_SKILL_STATIC = skill_path.read_text(encoding="utf-8")
        except OSError:
            _HANDOFF_SKILL_STATIC = ""
    try:
        from knowledge.knowledge_search import get_handoff_scenarios
        scenarios = get_handoff_scenarios()
        if scenarios:
            lines = [
                "\n---\n## Specific Handoff Scenarios\n\n"
                "For each situation below: call `request_human_handoff`, then respond to the user "
                "with exactly the message shown after the arrow. Do not paraphrase it.\n"
            ]
            for s in scenarios:
                lines.append(f"- {s['scenario']} → \"{s['default_response']}\"")
            return _HANDOFF_SKILL_STATIC + "\n" + "\n".join(lines)
    except Exception:
        pass
    return _HANDOFF_SKILL_STATIC


def _load_scheduling_skill() -> str:
    global _SCHEDULING_SKILL
    if _SCHEDULING_SKILL is None:
        skill_path = Path(__file__).parent / "skills" / "scheduling" / "SKILL.md"
        try:
            _SCHEDULING_SKILL = skill_path.read_text(encoding="utf-8")
        except OSError:
            _SCHEDULING_SKILL = ""
    return _SCHEDULING_SKILL


def _load_onboarding_skill() -> str:
    global _ONBOARDING_SKILL
    if _ONBOARDING_SKILL is None:
        skill_path = Path(__file__).parent / "skills" / "onboarding" / "SKILL.md"
        try:
            _ONBOARDING_SKILL = skill_path.read_text(encoding="utf-8")
        except OSError:
            _ONBOARDING_SKILL = ""
    return _ONBOARDING_SKILL


def _load_product_info_skill() -> str:
    global _PRODUCT_INFO_SKILL
    if _PRODUCT_INFO_SKILL is None:
        skill_path = Path(__file__).parent / "skills" / "product_info" / "SKILL.md"
        try:
            _PRODUCT_INFO_SKILL = skill_path.read_text(encoding="utf-8")
        except OSError:
            _PRODUCT_INFO_SKILL = ""
    return _PRODUCT_INFO_SKILL


def faq_instructions(
    run_context: RunContextWrapper[LucentiveAgentChatContext], agent: Agent[LucentiveAgentChatContext]
) -> str:
    handoff_skill = _load_handoff_skill()
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{PLAIN_TEXT_RULE}"
        "You are the Investments FAQ Agent. You specialize in answering questions about investments, trading bots, stocks, and related financial topics.\n"
        "If you are speaking to a customer, you were likely transferred from the triage agent.\n\n"
        "CRITICAL: Only answer when the customer has asked a SPECIFIC QUESTION. Do NOT provide information upfront or give unsolicited answers. If no question has been asked, politely ask what they'd like to know or return to the Triage Agent.\n\n"
        "You should respond as a knowledgeable human expert, not as an AI agent. Answer questions naturally and confidently as if you personally know the information.\n\n"
        "Use the following routine to support the customer:\n"
        "1. Check if the customer has asked a specific question. If not, ask what they'd like to know or return to Triage Agent. If the user requests a call or callback, hand off to the Scheduling Agent directly.\n"
        "2. Always call `file_search` first. If it returns a useful answer, use it. If it returns nothing relevant, call `get_country_offers` as a fallback (for country/availability questions). If neither returns a useful answer, go to step 4.\n"
        "3. REPLY BEFORE TRANSFERRING: Compose your reply first and send it to the user. Only after your reply is sent, call the transfer to Triage Agent. Never call a transfer in the same step as reading a tool result — reply first, then transfer. Do not add, expand, or elaborate beyond what the tool returned.\n"
        "4. If no tool returns a useful answer: call `request_human_handoff` and respond with EXACTLY and ONLY \"Please wait one sec while I check something for you.\" — nothing else. Do NOT include any partial answer, context, or additional sentences before or after this message.\n"
        "5. Never mention sources, knowledge bases, or that you looked anything up. Never say 'the info provided says', 'according to the knowledge base', or 'based on the documentation'. Never show citation markers.\n\n"
        "---\n"
        "## Human Handoff Skill\n\n"
        f"{handoff_skill}"
    )


_faq_tools = []
if _VECTOR_STORE_ID:
    _faq_tools.append(FileSearchTool(vector_store_ids=[_VECTOR_STORE_ID]))
_faq_tools.append(get_country_offers)
_faq_tools.append(request_human_handoff)

investments_faq_agent = Agent[LucentiveAgentChatContext](
    name="Investments FAQ Agent",
    model=MODEL,
    handoff_description="Answers investment-related questions about trading bots, stocks, investments, and related topics.",
    instructions=faq_instructions,
    tools=_faq_tools,
    input_guardrails=[jailbreak_guardrail],
)


def scheduling_instructions(
    run_context: RunContextWrapper[LucentiveAgentChatContext], agent: Agent[LucentiveAgentChatContext]
) -> str:
    skill_content = _load_scheduling_skill()
    handoff_skill = _load_handoff_skill()
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{PLAIN_TEXT_RULE}"
        "You are the Scheduling Agent. The user has asked to be called back and was handed off from Triage.\n"
        "\n"
        "CRITICAL: When the user ACCEPTS a callback (e.g. \"yes\", \"sure\", \"ok\", \"yes please\"), reply with ONLY a "
        "short confirmation of the timeframe (e.g. \"Perfect, I'll call you within the next 2–4 hours.\") "
        "and hand off to Triage. NEVER ask for phone number, timezone, or country code—we already have them from the campaign. "
        "Do NOT say \"confirm the best phone number\", \"phone number (with country code)\", \"your time zone\", or \"so we can place the callback\".\n"
        "\n"
        "CRITICAL: If the user declines the call or says they prefer to chat (e.g. \"let's chat\", \"I'm busy\", \"not now\", \"lets chat here\"), "
        "do NOT ask any questions yourself. Immediately hand off to Triage Agent and say nothing else.\n"
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
        "\n\n---\n"
        "## Human Handoff Skill\n\n"
        f"{handoff_skill}"
    )


scheduling_agent = Agent[LucentiveAgentChatContext](
    name="Scheduling Agent",
    model=MODEL,
    handoff_description="Handles call scheduling requests and suggests available call times.",
    instructions=scheduling_instructions,
    tools=[get_scheduling_context, request_human_handoff],
    input_guardrails=[jailbreak_guardrail],
)


def onboarding_instructions(
    run_context: RunContextWrapper[LucentiveAgentChatContext], agent: Agent[LucentiveAgentChatContext]
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
    has_broker_account = onboarding_state.get("has_broker_account")

    if "trading_experience" not in completed_steps:
        current_step = "trading_experience"
    elif "bot_recommendation" not in completed_steps:
        current_step = "bot_recommendation"
    elif "broker_selection" not in completed_steps:
        current_step = "broker_selection"
    elif "profit_share_clarification" not in completed_steps:
        current_step = "profit_share_clarification"
    elif "budget_check" not in completed_steps:
        current_step = "budget_check"
    elif broker_preference and "has_broker_account" not in completed_steps:
        current_step = "has_broker_account"
    elif "instructions" not in completed_steps:
        current_step = "instructions"
    else:
        current_step = "complete"

    skill_content = _load_onboarding_skill()
    handoff_skill = _load_handoff_skill()
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{PLAIN_TEXT_RULE}"
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
        f"- Has broker account: {has_broker_account}\n"
        f"- Current step to work on: {current_step}\n"
        "\n"
        "You have access to the **onboarding skill** below. Follow it. Use the tools (get_country_offers, get_broker_assets, update_onboarding_state, update_lead_info) as the skill describes. "
        "Do not copy-paste raw JSON to the user; use tool output to reply in natural language.\n"
        "\n"
        "---\n"
        "## Onboarding skill\n"
        "\n"
        f"{skill_content}"
        "\n\n---\n"
        "## Product Information Skill\n\n"
        f"{_load_product_info_skill()}"
        "\n\n---\n"
        "## Human Handoff Skill\n\n"
        f"{handoff_skill}"
    )


onboarding_agent = Agent[LucentiveAgentChatContext](
    name="Onboarding Agent",
    model=MODEL,
    handoff_description="Guides new leads through onboarding: trading experience, budget, broker setup.",
    instructions=onboarding_instructions,
    tools=[get_country_offers, get_broker_assets, update_lead_info, update_onboarding_state, request_human_handoff],
    input_guardrails=[jailbreak_guardrail],
)


def triage_instructions(
    run_context: RunContextWrapper[LucentiveAgentChatContext], agent: Agent[LucentiveAgentChatContext],
) -> str:
    ctx = run_context.context.state
    new_lead = ctx.new_lead or False
    onboarding_state = ctx.onboarding_state or {}
    completed_steps = onboarding_state.get("completed_steps", [])
    onboarding_complete = onboarding_state.get("onboarding_complete", False)

    logger.debug("[Triage] new_lead=%s, first_name=%s, country=%s, onboarding_complete=%s", new_lead, ctx.first_name, ctx.country, onboarding_complete)

    should_route_to_onboarding = (
        new_lead and
        not onboarding_complete
    )

    onboarding_instruction = ""
    if should_route_to_onboarding:
        onboarding_instruction = (
            "\nACTIVE: This lead is new_lead=True and onboarding_complete=False. Route to Onboarding Agent as your default action unless the user explicitly requests a call or FAQ answer.\n"
        )

    return (
        f"{RECOMMENDED_PROMPT_PREFIX} "
        f"{PLAIN_TEXT_RULE}"
        "You are a triaging agent for Lucentive Club, a trading bot financing service. "
        "Lucentive Club connects leads with automated trading bots managed by professional traders. "
        "Leads come in via WhatsApp after expressing interest in the service. "
        "Your role is to understand what the lead needs and route them to the appropriate specialist agent — "
        "never answer questions yourself, always route to the right specialist.\n"
        "CRITICAL: Never answer investment-related, service, or FAQ-type questions yourself — even if you can construct an answer from conversation history. Always route these to the Investments FAQ Agent.\n\n"
        "IMPORTANT - USER CORRECTIONS:\n"
        "- If the user corrects a conversation variable (at minimum country), you must:\n"
        "  1) Acknowledge the correction briefly\n"
        "  2) Call update_lead_info(...) to persist the corrected value to the database\n"
        "  3) Then continue routing normally\n"
        "- Example: if country is Austria but user says 'Actually I'm from Australia', call update_lead_info(country='Australia').\n\n"
        "ROUTING PRIORITY (in order):\n"
        "1. Specific requests take priority (override default onboarding):\n"
        "   - Scheduling Agent: When customer says 'arrange a call', 'call', 'I want a call', or explicitly requests a phone conversation. This includes when they respond 'call' to the initial greeting question asking about their preference.\n"
        "   - Investments FAQ Agent: When customer asks an information-seeking question — about the service, the company, how it works, trading bots, brokers, fees, profit splits, minimum investment, or any topic they want to understand. If it's a question seeking information (not requesting an action like a call), route it to FAQ.\n"
        "2. DEFAULT BEHAVIOR - New lead onboarding (proactive routing):\n"
        "   - Onboarding Agent: If this is a new lead (new_lead=True) who hasn't completed onboarding (onboarding_complete=False), route them to the Onboarding Agent proactively as the default action.\n"
        "   - This is the DEFAULT behavior for new leads - you should route to Onboarding Agent unless there's a specific request that requires Scheduling or FAQ Agent.\n"
        "   - CRITICAL: When a new lead (new_lead=True) responds with 'chat' to the initial greeting, route them to the Onboarding Agent immediately to begin onboarding.\n"
        "   - The goal is to be proactive - make things moving by routing new leads to onboarding by default.\n"
        f"{onboarding_instruction}"
        "When NOT to hand off:\n"
        "- If customer hasn't asked a question yet and they're NOT a new lead - engage them in conversation first\n"
        "- If the message is unclear and they're NOT a new lead - ask for clarification before routing\n"
        "- If onboarding is already complete (onboarding_complete=True) - do NOT route to Onboarding Agent by default. Handle follow-up questions normally by routing to appropriate agents (Scheduling Agent, Investments FAQ Agent, etc.)\n\n"
        "CALLBACK ACCEPTANCE - When the user says only 'yes', 'sure', 'ok', 'yes please', or 'that works' and the last assistant message was from the Scheduling Agent offering a callback (e.g. 10 minutes or 2–4 hours):\n"
        "- Do NOT ask for phone number or timezone. We already have them from the campaign.\n"
        "- Hand off immediately to the Scheduling Agent so it can send the confirmation and close the flow. Do not ask any questions.\n\n"
        "If the request is clear and specific, hand off immediately and let the specialist complete multi-step work without asking the user to confirm after each tool call.\n"
        "Never emit more than one handoff per message: do your prep (at most one tool call) and then hand off once.\n\n"
        "---\n"
        "## Human Handoff Skill\n\n"
        f"{_load_handoff_skill()}"
    )


triage_agent = Agent[LucentiveAgentChatContext](
    name="Triage Agent",
    model=MODEL,
    handoff_description="Delegates requests to the right specialist agent (scheduling, investments FAQ, onboarding).",
    instructions=triage_instructions,
    tools=[update_lead_info, request_human_handoff],
    handoffs=[],
    input_guardrails=[jailbreak_guardrail],
)


async def on_onboarding_handoff(context: RunContextWrapper[LucentiveAgentChatContext]) -> None:
    """Ensure lead info and onboarding state are preserved when handing off to the onboarding agent."""
    ctx_state = context.context.state
    thread_id = None
    if hasattr(context.context, 'thread') and context.context.thread:
        thread_id = context.context.thread.id

    if thread_id:
        restore_lead_info_to_context(thread_id, ctx_state)
        restore_onboarding_state_to_context(thread_id, ctx_state)
        logger.debug("[Onboarding handoff] Restored context for thread %s", thread_id)

    logger.debug("[Onboarding handoff] first_name=%s, country=%s, new_lead=%s, email=%s, onboarding_state=%s", ctx_state.first_name, ctx_state.country, ctx_state.new_lead, ctx_state.email, ctx_state.onboarding_state)

    if not ctx_state.country or ctx_state.country == "Unknown":
        logger.warning("[Onboarding handoff] Country is missing or Unknown")
    if not ctx_state.first_name:
        logger.warning("[Onboarding handoff] First name is missing")


# Set up handoff relationships (full mesh — every agent can reach every other)
triage_agent.handoffs = [
    investments_faq_agent,
    scheduling_agent,
    handoff(agent=onboarding_agent, on_handoff=on_onboarding_handoff),
]
investments_faq_agent.handoffs.extend([triage_agent, scheduling_agent, onboarding_agent])
scheduling_agent.handoffs.extend([triage_agent, investments_faq_agent, onboarding_agent])
onboarding_agent.handoffs.extend([scheduling_agent, investments_faq_agent, triage_agent])
