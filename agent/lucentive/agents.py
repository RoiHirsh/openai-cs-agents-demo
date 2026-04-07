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
    "KNOWLEDGE BOUNDARY: You may only answer from your assigned tools, skills, and knowledge base. "
    "Never answer from general model knowledge. If a question is not covered by your assigned sources, "
    "either hand off to the appropriate agent or (Onboarding Agent only, as a last resort) escalate to human handoff.\n"
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
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{PLAIN_TEXT_RULE}"
        "You are the Investments FAQ Agent. You specialize in answering questions about investments, trading bots, stocks, and related financial topics.\n"
        "You were handed off from the Onboarding Agent. Your only job is to answer the question and return control to the Onboarding Agent.\n\n"
        "CRITICAL: Only answer when the customer has asked a SPECIFIC QUESTION. Do NOT provide information upfront or give unsolicited answers.\n\n"
        "You should respond as a knowledgeable human expert, not as an AI agent. Answer questions naturally and confidently as if you personally know the information.\n\n"
        "Use the following routine:\n"
        "1. Always call `file_search` first. If it returns a useful answer, use it. If it returns nothing relevant, call `get_country_offers` as a fallback (for country/availability questions). If neither returns a useful answer, go to step 3.\n"
        "2. REPLY BEFORE TRANSFERRING: Compose your reply first and send it to the user. Only after your reply is sent, hand off to Onboarding Agent. Never call a transfer in the same step as reading a tool result — reply first, then transfer. Do not add, expand, or elaborate beyond what the tool returned.\n"
        "3. If no tool returns a useful answer: respond with EXACTLY and ONLY \"I wasn't able to find a clear answer on that one — let me hand you back.\" and hand off to Onboarding Agent. Do NOT attempt to answer from general knowledge.\n"
        "4. Never mention sources, knowledge bases, or that you looked anything up. Never say 'the info provided says', 'according to the knowledge base', or 'based on the documentation'. Never show citation markers.\n\n"
        "ALWAYS hand off to Onboarding Agent after every interaction — whether you found an answer or not. Never hand off to human directly. Never hand off to Scheduling Agent directly.\n"
    )


_faq_tools = []
if _VECTOR_STORE_ID:
    _faq_tools.append(FileSearchTool(vector_store_ids=[_VECTOR_STORE_ID]))
_faq_tools.append(get_country_offers)

investments_faq_agent = Agent[LucentiveAgentChatContext](
    name="Investments FAQ Agent",
    model=MODEL,
    handoff_description="Answers investment-related questions about trading bots, stocks, investments, and related topics. Always returns control to Onboarding Agent.",
    instructions=faq_instructions,
    tools=_faq_tools,
    input_guardrails=[jailbreak_guardrail],
)


def scheduling_instructions(
    run_context: RunContextWrapper[LucentiveAgentChatContext], agent: Agent[LucentiveAgentChatContext]
) -> str:
    skill_content = _load_scheduling_skill()
    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{PLAIN_TEXT_RULE}"
        "You are the Scheduling Agent. The user has asked to be called back and was handed off from the Onboarding Agent.\n"
        "\n"
        "CRITICAL: When the user ACCEPTS a callback (e.g. \"yes\", \"sure\", \"ok\", \"yes please\"), reply with ONLY a "
        "short confirmation of the timeframe (e.g. \"Perfect, I'll call you within the next 2–4 hours.\") "
        "and hand off to Onboarding Agent. NEVER ask for phone number, timezone, or country code—we already have them from the campaign. "
        "Do NOT say \"confirm the best phone number\", \"phone number (with country code)\", \"your time zone\", or \"so we can place the callback\".\n"
        "\n"
        "CRITICAL: If the user declines the call or says they prefer to chat (e.g. \"let's chat\", \"I'm busy\", \"not now\", \"lets chat here\"), "
        "do NOT ask any questions yourself. Immediately hand off to Onboarding Agent and say nothing else.\n"
        "\n"
        "You have access to the **scheduling skill** below. Follow it. Your only tool is **get_scheduling_context**. "
        "Call it first. It returns **context only** (day, open/closed, why, available offers, reasons). "
        "**Do not** copy-paste any message from the tool. Use the context to reply in **natural language** and explain "
        "why you're offering what you're offering.\n"
        "\n"
        "Offer one option at a time; if the user declines, call the tool again with exclude_actions and offer the next "
        "option. When the user accepts: one confirmation sentence only, then hand off. Do not ask for phone or timezone.\n"
        "\n"
        "ALWAYS hand off to Onboarding Agent after every interaction — whether call was accepted, declined, or any other outcome. "
        "Never hand off to human directly. Never hand off to FAQ Agent directly.\n"
        "\n"
        "---\n"
        "## Scheduling skill\n"
        "\n"
        f"{skill_content}"
    )


scheduling_agent = Agent[LucentiveAgentChatContext](
    name="Scheduling Agent",
    model=MODEL,
    handoff_description="Handles call scheduling requests and suggests available call times. Always returns control to Onboarding Agent.",
    instructions=scheduling_instructions,
    tools=[get_scheduling_context],
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

    if onboarding_complete:
        mode_instructions = (
            "MODE: Post-onboarding. The lead has completed onboarding. Do NOT run the onboarding flow steps.\n"
            "Your role now is to route freely: answer product questions inline using the Product Information Skill, "
            "hand off to the Investments FAQ Agent for deep investment questions, hand off to the Scheduling Agent for call requests. "
            "Both FAQ and Scheduling will always return control here. Resume helping the user after they return.\n"
        )
    else:
        mode_instructions = (
            "MODE: Onboarding. Guide the lead through the onboarding flow step by step as described in the Onboarding Skill below.\n"
        )

    return (
        f"{RECOMMENDED_PROMPT_PREFIX}\n"
        f"{PLAIN_TEXT_RULE}"
        "You are the Onboarding Agent — the master agent and permanent entry point for all conversations. "
        "You own all routing decisions. You are the only agent that can escalate to human handoff.\n"
        "\n"
        f"{mode_instructions}"
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
        "HANDOFF PRIORITY (apply in this order):\n"
        "1. User requests a call → hand off to Scheduling Agent. It will return here after.\n"
        "2. User asks about bots, comparisons, or product details → answer inline from the Product Information Skill. Do NOT hand off to FAQ for these.\n"
        "3. User asks an investment/FAQ question not covered by the Product Information Skill → hand off to Investments FAQ Agent. It will return here after.\n"
        "4. ESCALATION CHAIN (last resort only): If you have already tried to answer a question and also sent the user to the Investments FAQ Agent "
        "(visible in the conversation history as a handoff to FAQ followed by FAQ returning with no answer), "
        "call request_human_handoff. Human handoff is the last resort — only after both you and FAQ have failed.\n"
        "5. For handoff scenarios defined in the Human Handoff Skill (e.g. proof of results, user is available now), "
        "call request_human_handoff directly without the FAQ loop.\n"
        "\n"
        "USER CORRECTIONS: If the user corrects any lead info (especially country), acknowledge briefly and call update_lead_info(...) to persist it. "
        "Then continue using the updated value.\n"
        "\n"
        "You have access to the onboarding skill, product info skill, and human handoff skill below. "
        "Use the tools (get_country_offers, get_broker_assets, update_onboarding_state, update_lead_info) as the skills describe. "
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
    handoff_description="Master agent and entry point. Guides new leads through onboarding and owns all routing and human escalation decisions.",
    instructions=onboarding_instructions,
    tools=[get_country_offers, get_broker_assets, update_lead_info, update_onboarding_state, request_human_handoff],
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


# Set up handoff relationships
# Onboarding is the master — routes to FAQ and Scheduling, receives them back
# FAQ and Scheduling are subordinates — they only return to Onboarding
onboarding_agent.handoffs.extend([
    investments_faq_agent,
    scheduling_agent,
])
investments_faq_agent.handoffs.extend([handoff(agent=onboarding_agent, on_handoff=on_onboarding_handoff)])
scheduling_agent.handoffs.extend([handoff(agent=onboarding_agent, on_handoff=on_onboarding_handoff)])
