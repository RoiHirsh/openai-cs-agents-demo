from __future__ import annotations as _annotations

from chatkit.agents import AgentContext
from pydantic import BaseModel


class AirlineAgentContext(BaseModel):
    """Context for Lucentive Club customer service agents."""

    # Lead information fields
    first_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    new_lead: bool = False
    # Onboarding state tracking
    onboarding_state: dict | None = None
    # Structure: {
    #   "completed_steps": list[str],
    #   "trading_experience": str | None,
    #   "previous_broker": str | None,
    #   "trading_type": str | None,
    #   "budget_confirmed": bool | None,
    #   "budget_amount": float | None,
    #   "demo_offered": bool | None,
    #   "instructions_provided": bool | None
    # }


class AirlineAgentChatContext(AgentContext[dict]):
    """
    AgentContext wrapper used during ChatKit runs.
    Holds the persisted AirlineAgentContext in `state`.
    """

    state: AirlineAgentContext


def create_initial_context() -> AirlineAgentContext:
    """
    Factory for a new AirlineAgentContext.
    Starts empty; values are populated during the conversation.
    """
    ctx = AirlineAgentContext()
    return ctx


def public_context(ctx: AirlineAgentContext) -> dict:
    """
    Return a filtered view of the context for UI display.
    """
    data = ctx.model_dump()
    return data
