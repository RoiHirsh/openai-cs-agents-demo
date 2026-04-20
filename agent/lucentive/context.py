from __future__ import annotations as _annotations

from chatkit.agents import AgentContext
from pydantic import BaseModel


class LucentiveAgentContext(BaseModel):
    """Context for Lucentive Club customer service agents."""

    # Lead information fields
    first_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    new_lead: bool = False
    # Onboarding state tracking
    onboarding_state: dict | None = None
    # Chatwoot conversation ID — populated per request, used by handoff tool
    conversation_id: str | None = None
    # Structure: {
    #   "completed_steps": list[str],
    #   "trading_experience": str | None,
    #   "previous_broker": str | None, # Optional prior broker mentioned by the user
    #   "trading_type": str | None,     # Optional prior trading type mentioned by the user
    #   "bot_preference": str | None,   # User's chosen bot type (e.g. Gold, Forex, Crypto) from step 2a
    #   "broker_preference": str | None, # User's chosen broker (e.g. Vantage, PU Prime) from step 2b
    #   "budget_confirmed": bool | None,
    #   "budget_amount": float | None,
    #   "demo_offered": bool | None,
    #   "instructions_provided": bool | None,
    #   "onboarding_complete": bool | None  # Set to True when user has opened broker account and set up copy trading
    # }


class LucentiveAgentChatContext(AgentContext[dict]):
    """
    AgentContext wrapper used during ChatKit runs.
    Holds the persisted LucentiveAgentContext in `state`.
    """

    state: LucentiveAgentContext


def create_initial_context() -> LucentiveAgentContext:
    """
    Factory for a new LucentiveAgentContext.
    Starts empty; values are populated during the conversation.
    """
    return LucentiveAgentContext()


def public_context(ctx: LucentiveAgentContext) -> dict:
    """
    Return a filtered view of the context for UI display.
    """
    return ctx.model_dump()
