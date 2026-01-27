from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel

from agents import (
    Handoff,
    HandoffOutputItem,
    InputGuardrailTripwireTriggered,
    ItemHelpers,
    MessageOutputItem,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
)
from agents.exceptions import MaxTurnsExceeded
from chatkit.agents import stream_agent_response
from chatkit.server import ChatKitServer
from chatkit.types import (
    Action,
    AssistantMessageContent,
    AssistantMessageItem,
    ClientEffectEvent,
    ThreadItemDoneEvent,
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
    WidgetItem,
    ProgressUpdateEvent,
)
from chatkit.store import NotFoundError

from airline.context import AirlineAgentChatContext, AirlineAgentContext, create_initial_context, public_context
from airline.context_cache import (
    get_lead_info_cache,
    set_lead_info,
    restore_lead_info_to_context,
    get_onboarding_state_cache,
    set_onboarding_state,
    restore_onboarding_state_to_context,
)
from airline.agents import (
    investments_faq_agent,
    onboarding_agent,
    scheduling_agent,
    triage_agent,
)
from memory_store import MemoryStore


class AgentEvent(BaseModel):
    id: str
    type: str
    agent: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None


class GuardrailCheck(BaseModel):
    id: str
    name: str
    input: str
    reasoning: str
    passed: bool
    timestamp: float


def _get_agent_by_name(name: str):
    """Return the agent object by name."""
    agents = {
        triage_agent.name: triage_agent,
        investments_faq_agent.name: investments_faq_agent,
        scheduling_agent.name: scheduling_agent,
        onboarding_agent.name: onboarding_agent,
    }
    return agents.get(name, triage_agent)


def _get_guardrail_name(g) -> str:
    """Extract a friendly guardrail name."""
    name_attr = getattr(g, "name", None)
    if isinstance(name_attr, str) and name_attr:
        return name_attr
    guard_fn = getattr(g, "guardrail_function", None)
    if guard_fn is not None and hasattr(guard_fn, "__name__"):
        return guard_fn.__name__.replace("_", " ").title()
    fn_name = getattr(g, "__name__", None)
    if isinstance(fn_name, str) and fn_name:
        return fn_name.replace("_", " ").title()
    return str(g)


def _build_agents_list() -> List[Dict[str, Any]]:
    """Build a list of all available agents and their metadata."""

    def make_agent_dict(agent):
        return {
            "name": agent.name,
            "description": getattr(agent, "handoff_description", ""),
            "handoffs": [getattr(h, "agent_name", getattr(h, "name", "")) for h in getattr(agent, "handoffs", [])],
            "tools": [getattr(t, "name", getattr(t, "__name__", "")) for t in getattr(agent, "tools", [])],
            "input_guardrails": [_get_guardrail_name(g) for g in getattr(agent, "input_guardrails", [])],
        }

    return [
        make_agent_dict(triage_agent),
        make_agent_dict(investments_faq_agent),
        make_agent_dict(scheduling_agent),
        make_agent_dict(onboarding_agent),
    ]


def _user_message_to_text(message: UserMessageItem) -> str:
    parts: List[str] = []
    for part in message.content:
        text = getattr(part, "text", "")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _parse_tool_args(raw_args: Any) -> Any:
    if isinstance(raw_args, str):
        try:
            import json

            return json.loads(raw_args)
        except Exception:
            return raw_args
    return raw_args


@dataclass
class ConversationState:
    input_items: List[Any] = field(default_factory=list)
    context: AirlineAgentContext = field(default_factory=create_initial_context)
    current_agent_name: str = triage_agent.name
    events: List[AgentEvent] = field(default_factory=list)
    guardrails: List[GuardrailCheck] = field(default_factory=list)


class AirlineServer(ChatKitServer[dict[str, Any]]):
    def __init__(self) -> None:
        self.store = MemoryStore()
        super().__init__(self.store)
        self._state: Dict[str, ConversationState] = {}
        self._listeners: Dict[str, list[asyncio.Queue]] = {}
        self._last_event_index: Dict[str, int] = {}
        self._last_snapshot: Dict[str, str] = {}
        # Store lead info persistently per thread to restore if context is reset
        # Also sync with module-level cache for handoff callbacks
        self._lead_info_cache: Dict[str, dict] = get_lead_info_cache()
        # Store onboarding state persistently per thread to restore if context is reset
        self._onboarding_state_cache: Dict[str, dict] = get_onboarding_state_cache()

    def _state_for_thread(self, thread_id: str) -> ConversationState:
        if thread_id not in self._state:
            self._state[thread_id] = ConversationState()
        state = self._state[thread_id]
        
        # CRITICAL: Restore lead info from cache if context was reset
        # This ensures lead info persists even if the context is recreated
        if thread_id in self._lead_info_cache:
            cached_lead_info = self._lead_info_cache[thread_id]
            if cached_lead_info.get("first_name") and not state.context.first_name:
                state.context.first_name = cached_lead_info["first_name"]
            if cached_lead_info.get("email") and not state.context.email:
                state.context.email = cached_lead_info["email"]
            if cached_lead_info.get("phone") and not state.context.phone:
                state.context.phone = cached_lead_info["phone"]
            if cached_lead_info.get("country") and not state.context.country:
                state.context.country = cached_lead_info["country"]
            if cached_lead_info.get("new_lead") is not None and state.context.new_lead is False:
                state.context.new_lead = cached_lead_info["new_lead"]
        
        # CRITICAL: Restore onboarding state from cache if context was reset
        restore_onboarding_state_to_context(thread_id, state.context)
        
        return state

    async def _ensure_thread(
        self, thread_id: Optional[str], context: dict[str, Any]
    ) -> ThreadMetadata:
        if thread_id:
            try:
                thread = await self.store.load_thread(thread_id, context)
                state = self._state_for_thread(thread.id)  # This will restore from cache
                
                # Update lead info if provided in context (takes precedence)
                lead_info = context.get("lead_info")
                if lead_info:
                    if lead_info.get("first_name"):
                        state.context.first_name = lead_info.get("first_name")
                    if lead_info.get("email"):
                        state.context.email = lead_info.get("email")
                    if lead_info.get("phone"):
                        state.context.phone = lead_info.get("phone")
                    if lead_info.get("country"):
                        state.context.country = lead_info.get("country")
                    if lead_info.get("new_lead") is not None:
                        state.context.new_lead = lead_info.get("new_lead", False)
                    # Cache lead info for this thread to restore if context is reset
                    lead_info_dict = {
                        "first_name": state.context.first_name,
                        "email": state.context.email,
                        "phone": state.context.phone,
                        "country": state.context.country,
                        "new_lead": state.context.new_lead,
                    }
                    self._lead_info_cache[thread.id] = lead_info_dict
                    set_lead_info(thread.id, lead_info_dict)  # Also update module-level cache
                    print(f"[DEBUG] Updated lead info for thread {thread.id}: first_name={state.context.first_name}, country={state.context.country}, new_lead={state.context.new_lead}")
                else:
                    # Even if no lead_info in context, restore from cache if available
                    restore_lead_info_to_context(thread.id, state.context)
                    print(f"[DEBUG] Loaded existing thread {thread.id} - restored from cache: first_name={state.context.first_name}, country={state.context.country}, new_lead={state.context.new_lead}")
                return thread
            except NotFoundError:
                pass
        new_thread = ThreadMetadata(id=self.store.generate_thread_id(context), created_at=datetime.now())
        await self.store.save_thread(new_thread, context)
        state = self._state_for_thread(new_thread.id)
        # Set lead info if provided
        lead_info = context.get("lead_info")
        if lead_info:
            if lead_info.get("first_name"):
                state.context.first_name = lead_info.get("first_name")
            if lead_info.get("email"):
                state.context.email = lead_info.get("email")
            if lead_info.get("phone"):
                state.context.phone = lead_info.get("phone")
            if lead_info.get("country"):
                state.context.country = lead_info.get("country")
            if lead_info.get("new_lead") is not None:
                state.context.new_lead = lead_info.get("new_lead", False)
            # Cache lead info for this thread to restore if context is reset
            lead_info_dict = {
                "first_name": state.context.first_name,
                "email": state.context.email,
                "phone": state.context.phone,
                "country": state.context.country,
                "new_lead": state.context.new_lead,
            }
            self._lead_info_cache[new_thread.id] = lead_info_dict
            set_lead_info(new_thread.id, lead_info_dict)  # Also update module-level cache
            print(f"[DEBUG] Set lead info for new thread {new_thread.id}: first_name={state.context.first_name}, country={state.context.country}, new_lead={state.context.new_lead}")
        return new_thread

    async def ensure_thread(self, thread_id: Optional[str], context: dict[str, Any]) -> ThreadMetadata:
        """Public wrapper to ensure a thread exists."""
        return await self._ensure_thread(thread_id, context)

    def _record_guardrails(
        self,
        agent_name: str,
        input_text: str,
        guardrail_results: List[Any],
    ) -> List[GuardrailCheck]:
        checks: List[GuardrailCheck] = []
        timestamp = time.time() * 1000
        agent = _get_agent_by_name(agent_name)
        for guardrail in getattr(agent, "input_guardrails", []):
            result = next((r for r in guardrail_results if r.guardrail == guardrail), None)
            reasoning = ""
            passed = True
            if result:
                info = getattr(result.output, "output_info", None)
                reasoning = getattr(info, "reasoning", "") or reasoning
                passed = not result.output.tripwire_triggered
            checks.append(
                GuardrailCheck(
                    id=uuid4().hex,
                    name=_get_guardrail_name(guardrail),
                    input=input_text,
                    reasoning=reasoning,
                    passed=passed,
                    timestamp=timestamp,
                )
            )
        return checks

    @staticmethod
    def _truncate(val: Any, limit: int = 200) -> Any:
        if isinstance(val, str) and len(val) > limit:
            return val[:limit] + "…"
        return val

    async def _broadcast_delta(self, thread: ThreadMetadata, delta_events: list[AgentEvent]) -> None:
        """Send a delta-only payload (used for transient progress updates)."""
        listeners = self._listeners.get(thread.id, [])
        if not listeners:
            return
        payload = json.dumps({"events_delta": [e.model_dump() for e in delta_events]}, default=str)
        for q in list(listeners):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def _record_events(
        self,
        run_items: List[Any],
        current_agent_name: str,
        thread_id: str,
    ) -> (List[AgentEvent], str):
        events: List[AgentEvent] = []
        active_agent = current_agent_name
        for item in run_items:
            now_ms = time.time() * 1000
            if isinstance(item, MessageOutputItem):
                text = self._truncate(ItemHelpers.text_message_output(item))
                
                # Print agent message to terminal
                print(f"\n[AGENT MESSAGE]")
                print(f"   Agent: {item.agent.name}")
                # Safely encode text for Windows console compatibility
                # Get console encoding or default to utf-8
                console_encoding = sys.stdout.encoding or 'utf-8'
                try:
                    # Truncate text first
                    truncated = text[:200] + ('...' if len(text) > 200 else '')
                    # Encode to console encoding with error handling
                    safe_text = truncated.encode(console_encoding, errors='replace').decode(console_encoding, errors='replace')
                    try:
                        print(f"   Message: {safe_text}")
                    except UnicodeEncodeError:
                        # If print still fails, use ASCII fallback
                        safe_text = truncated.encode('ascii', errors='replace').decode('ascii', errors='replace')
                        print(f"   Message: {safe_text}")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    # Ultimate fallback: replace all problematic characters with ASCII
                    truncated = text[:200] + ('...' if len(text) > 200 else '')
                    safe_text = truncated.encode('ascii', errors='replace').decode('ascii', errors='replace')
                    try:
                        print(f"   Message: {safe_text}")
                    except UnicodeEncodeError:
                        # Last resort: just print a message that encoding failed
                        print(f"   Message: [Text contains unsupported characters - message truncated]")
                print()
                
                events.append(
                    AgentEvent(
                        id=uuid4().hex,
                        type="message",
                        agent=item.agent.name,
                        content=text,
                        timestamp=now_ms,
                    )
                )
            elif isinstance(item, HandoffOutputItem):
                from_agent = item.source_agent
                to_agent = item.target_agent
                
                # Print handoff information to terminal
                print(f"\n{'='*60}")
                print(f"[AGENT HANDOFF]")
                print(f"   From: {from_agent.name}")
                print(f"   To:   {to_agent.name}")
                print(f"{'='*60}\n")
                
                events.append(
                    AgentEvent(
                        id=uuid4().hex,
                        type="handoff",
                        agent=item.source_agent.name,
                        content=f"{item.source_agent.name} -> {item.target_agent.name}",
                        metadata={"source_agent": item.source_agent.name, "target_agent": item.target_agent.name},
                        timestamp=now_ms,
                    )
                )
                ho = next(
                    (
                        h
                        for h in getattr(from_agent, "handoffs", [])
                        if isinstance(h, Handoff) and getattr(h, "agent_name", None) == to_agent.name
                    ),
                    None,
                )
                if ho:
                    fn = ho.on_invoke_handoff
                    fv = fn.__code__.co_freevars
                    cl = fn.__closure__ or []
                    if "on_handoff" in fv:
                        idx = fv.index("on_handoff")
                        if idx < len(cl) and cl[idx].cell_contents:
                            cb = cl[idx].cell_contents
                            cb_name = getattr(cb, "__name__", repr(cb))
                            events.append(
                                AgentEvent(
                                    id=uuid4().hex,
                                    type="tool_call",
                                    agent=to_agent.name,
                                    content=cb_name,
                                    timestamp=now_ms,
                                )
                            )

                active_agent = to_agent.name
            elif isinstance(item, ToolCallItem):
                tool_name = getattr(item.raw_item, "name", None)
                raw_args = getattr(item.raw_item, "arguments", None)
                parsed_args = _parse_tool_args(raw_args)
                
                # Print tool call information to terminal
                print(f"\n{'-'*60}")
                print(f"[TOOL CALL]")
                print(f"   Agent: {item.agent.name}")
                print(f"   Tool:  {tool_name}")
                if parsed_args:
                    try:
                        args_str = self._truncate(str(parsed_args), limit=500)
                        print(f"   Args:  {args_str}")
                    except UnicodeEncodeError:
                        # Fallback: encode with errors='replace' to handle Unicode characters
                        args_str = str(parsed_args)[:500].encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                        print(f"   Args:  {args_str}")
                print(f"{'-'*60}\n")
                
                ev = AgentEvent(
                    id=uuid4().hex,
                    type="tool_call",
                    agent=item.agent.name,
                    content=self._truncate(tool_name or ""),
                    metadata={"tool_args": self._truncate(parsed_args)},
                    timestamp=now_ms,
                )
                events.append(ev)
            elif isinstance(item, ToolCallOutputItem):
                # Print tool output information to terminal
                output_str = str(item.output)
                try:
                    safe_output = self._truncate(output_str, limit=300)
                    print(f"   [TOOL RESULT] {safe_output}")
                except UnicodeEncodeError:
                    # Fallback: encode with errors='replace' to handle Unicode characters
                    safe_output = output_str[:300].encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                    print(f"   [TOOL RESULT] {safe_output}")
                print()
                
                ev = AgentEvent(
                    id=uuid4().hex,
                    type="tool_output",
                    agent=item.agent.name,
                    content=self._truncate(output_str),
                    metadata={"tool_result": self._truncate(item.output)},
                    timestamp=now_ms,
                )
                events.append(ev)

        return events, active_agent

    async def respond(
        self,
        thread: ThreadMetadata,
        input_user_message: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        state = self._state_for_thread(thread.id)
        
        # Preserve existing lead info before updating (in case it gets overwritten)
        preserved_first_name = state.context.first_name
        preserved_email = state.context.email
        preserved_phone = state.context.phone
        preserved_country = state.context.country
        preserved_new_lead = state.context.new_lead
        
        # Update lead info from context if provided (in case it wasn't set during bootstrap)
        lead_info = context.get("lead_info")
        if lead_info:
            if lead_info.get("first_name"):
                state.context.first_name = lead_info.get("first_name")
            if lead_info.get("email"):
                state.context.email = lead_info.get("email")
            if lead_info.get("phone"):
                state.context.phone = lead_info.get("phone")
            if lead_info.get("country"):
                state.context.country = lead_info.get("country")
            if lead_info.get("new_lead") is not None:
                state.context.new_lead = lead_info.get("new_lead", False)
            # Update cache when lead info is provided
            lead_info_dict = {
                "first_name": state.context.first_name,
                "email": state.context.email,
                "phone": state.context.phone,
                "country": state.context.country,
                "new_lead": state.context.new_lead,
            }
            self._lead_info_cache[thread.id] = lead_info_dict
            set_lead_info(thread.id, lead_info_dict)  # Also update module-level cache
        else:
            # If no lead_info in context, restore from cache (set during bootstrap)
            if thread.id in self._lead_info_cache:
                cached_lead_info = self._lead_info_cache[thread.id]
                # Only restore if cached values are actually valid (not None/empty)
                if cached_lead_info.get("first_name") and not state.context.first_name:
                    state.context.first_name = cached_lead_info["first_name"]
                if cached_lead_info.get("email") and not state.context.email:
                    state.context.email = cached_lead_info["email"]
                if cached_lead_info.get("phone") and not state.context.phone:
                    state.context.phone = cached_lead_info["phone"]
                if cached_lead_info.get("country") and not state.context.country:
                    state.context.country = cached_lead_info["country"]
                if cached_lead_info.get("new_lead") is not None and state.context.new_lead is False:
                    state.context.new_lead = cached_lead_info["new_lead"]
                print(f"[DEBUG] Restored lead info from cache for thread {thread.id}: first_name={state.context.first_name}, country={state.context.country}, new_lead={state.context.new_lead}")
            
            # FALLBACK: If this thread still has no valid lead info, try to copy from most recent cache entry with valid data
            # This handles the case where ChatKit creates a new thread or cached thread has null values
            if (not state.context.first_name and not state.context.country and 
                len(self._lead_info_cache) > 0):
                # Find the most recent cache entry that has valid lead info
                for cached_thread_id, cached_lead_info in reversed(list(self._lead_info_cache.items())):
                    if cached_lead_info.get("first_name") or cached_lead_info.get("country"):
                        # Found a cache entry with valid data - copy it
                        state.context.first_name = cached_lead_info.get("first_name")
                        state.context.email = cached_lead_info.get("email")
                        state.context.phone = cached_lead_info.get("phone")
                        state.context.country = cached_lead_info.get("country")
                        state.context.new_lead = cached_lead_info.get("new_lead", False)
                        # Cache for this thread too so it persists
                        self._lead_info_cache[thread.id] = cached_lead_info.copy()
                        set_lead_info(thread.id, cached_lead_info.copy())
                        print(f"[DEBUG] Copied valid lead info from thread {cached_thread_id} to thread {thread.id}: first_name={state.context.first_name}, country={state.context.country}")
                        break
                # Fallback to preserved values if cache doesn't exist
                if preserved_first_name and not state.context.first_name:
                    state.context.first_name = preserved_first_name
                if preserved_email and not state.context.email:
                    state.context.email = preserved_email
                if preserved_phone and not state.context.phone:
                    state.context.phone = preserved_phone
                if preserved_country and not state.context.country:
                    state.context.country = preserved_country
                if preserved_new_lead is True and state.context.new_lead is False:
                    state.context.new_lead = True
        
        print(f"[DEBUG] Before Runner - Context state: first_name={state.context.first_name}, country={state.context.country}, new_lead={state.context.new_lead}")
        
        user_text = ""
        if input_user_message is not None:
            user_text = _user_message_to_text(input_user_message)
            
            # Add Perry's initial greeting if this is the first user message
            if not state.input_items:
                first_name = state.context.first_name
                if first_name:
                    initial_greeting = (
                        f"Hi {first_name}!\n"
                        "My name is Perry, Senior Portfolio Manager at Lucentive Club.\n\n"
                        "I'm confident that very soon you'll realize you've come to the right place.\n"
                        "Let's start with a short conversation.\n\n"
                        "Do you prefer a call or would you rather we chat here?"
                    )
                else:
                    initial_greeting = (
                        "Hi!\n"
                        "My name is Perry, Senior Portfolio Manager at Lucentive Club.\n\n"
                        "I'm confident that very soon you'll realize you've come to the right place.\n"
                        "Let's start with a short conversation.\n\n"
                        "Do you prefer a call or would you rather we chat here?"
                    )
                state.input_items.append({"role": "assistant", "content": initial_greeting})
            
            state.input_items.append({"content": user_text, "role": "user"})

        # CRITICAL: Restore context from cache BEFORE creating chat_context
        # This ensures context is populated even if it was reset
        restore_lead_info_to_context(thread.id, state.context)
        restore_onboarding_state_to_context(thread.id, state.context)
        
        # FALLBACK: If this thread still has no valid lead info, try to copy from most recent cache entry with valid data
        if (not state.context.first_name and not state.context.country and 
            len(self._lead_info_cache) > 0):
            # Find the most recent cache entry that has valid lead info
            for cached_thread_id, cached_lead_info in reversed(list(self._lead_info_cache.items())):
                if cached_lead_info.get("first_name") or cached_lead_info.get("country"):
                    # Found a cache entry with valid data - copy it
                    state.context.first_name = cached_lead_info.get("first_name")
                    state.context.email = cached_lead_info.get("email")
                    state.context.phone = cached_lead_info.get("phone")
                    state.context.country = cached_lead_info.get("country")
                    state.context.new_lead = cached_lead_info.get("new_lead", False)
                    # Cache for this thread too so it persists
                    self._lead_info_cache[thread.id] = cached_lead_info.copy()
                    set_lead_info(thread.id, cached_lead_info.copy())
                    print(f"[DEBUG] Before Runner - Copied valid lead info from thread {cached_thread_id} to thread {thread.id}: first_name={state.context.first_name}, country={state.context.country}")
                    break
        
        previous_context = public_context(state.context)
        
        chat_context = AirlineAgentChatContext(
            thread=thread,
            store=self.store,
            request_context=context,
            state=state.context,  # Same object reference - all fields persist automatically
        )
        
        # No need to set values on chat_context.state - it's the same object as state.context
        # The lead info should already be in state.context from lines 424-480 above
        streamed_items_seen = 0

        # Tell the client which thread to bind runner updates to before streaming starts.
        yield ClientEffectEvent(name="runner_bind_thread", data={"thread_id": thread.id, "ts": time.time()})

        try:
            current_agent = _get_agent_by_name(state.current_agent_name)
            print(f"\n{'#'*60}")
            print(f"[AGENT ACTIVE] {current_agent.name}")
            if user_text:
                try:
                    safe_user_text = user_text[:100] + ('...' if len(user_text) > 100 else '')
                    print(f"   User Message: {safe_user_text}")
                except UnicodeEncodeError:
                    # Fallback: encode with errors='replace' to handle Unicode characters
                    safe_user_text = user_text[:100].encode('utf-8', errors='replace').decode('utf-8', errors='replace') + ('...' if len(user_text) > 100 else '')
                    print(f"   User Message: {safe_user_text}")
            print(f"{'#'*60}\n")
            
            result = Runner.run_streamed(
                current_agent,
                state.input_items,
                context=chat_context,
            )
            async for event in stream_agent_response(chat_context, result):
                if isinstance(event, ProgressUpdateEvent) or getattr(event, "type", "") == "progress_update_event":
                    # Ignore progress updates for the Runner panel; ChatKit will handle them separately.
                    continue
                # If this is a run-item event, convert and broadcast immediately.
                if hasattr(event, "item"):
                    try:
                        run_item = getattr(event, "item")
                        new_events, active_agent = self._record_events(
                            [run_item], state.current_agent_name, thread.id
                        )
                        if new_events:
                            state.events.extend(new_events)
                            state.current_agent_name = active_agent
                            await self._broadcast_state(thread, context)
                            yield ClientEffectEvent(
                                name="runner_state_update",
                                data={"thread_id": thread.id, "ts": time.time()},
                            )
                            yield ClientEffectEvent(
                                name="runner_event_delta",
                                data={
                                    "thread_id": thread.id,
                                    "ts": time.time(),
                                    "events": [e.model_dump() for e in new_events],
                                },
                            )
                    except Exception as err:
                        pass
                yield event
                new_items = result.new_items[streamed_items_seen:]
                if new_items:
                    new_events, active_agent = self._record_events(
                        new_items, state.current_agent_name, thread.id
                    )
                    state.events.extend(new_events)
                    state.current_agent_name = active_agent
                    streamed_items_seen += len(new_items)
                    await self._broadcast_state(thread, context)
                    yield ClientEffectEvent(
                        name="runner_state_update",
                        data={"thread_id": thread.id, "ts": time.time()},
                    )
                    yield ClientEffectEvent(
                        name="runner_event_delta",
                        data={
                            "thread_id": thread.id,
                            "ts": time.time(),
                            "events": [e.model_dump() for e in new_events],
                        },
                    )
        except MaxTurnsExceeded:
            await self._broadcast_state(thread, context)
        except InputGuardrailTripwireTriggered as exc:
            failed_guardrail = exc.guardrail_result.guardrail
            gr_output = exc.guardrail_result.output.output_info
            reasoning = getattr(gr_output, "reasoning", "")
            timestamp = time.time() * 1000
            checks: List[GuardrailCheck] = []
            for guardrail in _get_agent_by_name(state.current_agent_name).input_guardrails:
                checks.append(
                    GuardrailCheck(
                        id=uuid4().hex,
                        name=_get_guardrail_name(guardrail),
                        input=user_text,
                        reasoning=reasoning if guardrail == failed_guardrail else "",
                        passed=guardrail != failed_guardrail,
                        timestamp=timestamp,
                    )
                )
            state.guardrails = checks
            refusal = "Sorry, I can only answer questions related to financing trading bot services and related topics."
            state.input_items.append({"role": "assistant", "content": refusal})
            yield ThreadItemDoneEvent(
                item=AssistantMessageItem(
                    id=self.store.generate_item_id("message", thread, context),
                    thread_id=thread.id,
                    created_at=datetime.now(),
                    content=[AssistantMessageContent(text=refusal)],
                )
            )
            return
        state.input_items = result.to_input_list()
        remaining_items = result.new_items[streamed_items_seen:]
        new_events, active_agent = self._record_events(remaining_items, state.current_agent_name, thread.id)
        state.events.extend(new_events)
        final_agent_name = active_agent
        try:
            final_agent_name = result.last_agent.name
        except Exception:
            pass
        state.current_agent_name = final_agent_name
        state.guardrails = self._record_guardrails(
            agent_name=state.current_agent_name,
            input_text=user_text,
            guardrail_results=result.input_guardrail_results,
        )

        # Ensure context state is preserved - chat_context.state should be the same object as state.context
        # Explicitly sync to ensure any modifications during handoffs are preserved
        # The Runner might create a new context during handoffs, so we need to ensure our state.context
        # is updated with any changes from chat_context.state
        if chat_context.state is not state.context:
            # If they're different objects (shouldn't happen, but be safe), sync the state
            print(f"[WARNING] chat_context.state is not the same object as state.context - syncing...")
            # Copy all fields from chat_context.state to state.context
            for field_name in state.context.model_fields.keys():
                if hasattr(chat_context.state, field_name):
                    new_value = getattr(chat_context.state, field_name)
                    # Only update if the new value is not None/empty, or if it's explicitly set
                    current_value = getattr(state.context, field_name)
                    if new_value is not None or current_value is None:
                        setattr(state.context, field_name, new_value)
        else:
            # They're the same object, so modifications should already be reflected
            # But explicitly ensure state.context is set to be safe
            state.context = chat_context.state
        
        # CRITICAL: After handoffs, ensure lead info is never lost
        # Restore from cache if any critical fields are missing
        if thread.id in self._lead_info_cache:
            cached_lead_info = self._lead_info_cache[thread.id]
            # Restore if missing (use cache as source of truth for lead info)
            if cached_lead_info.get("country") and (not state.context.country or state.context.country == "Unknown"):
                state.context.country = cached_lead_info["country"]
            if cached_lead_info.get("first_name") and not state.context.first_name:
                state.context.first_name = cached_lead_info["first_name"]
            if cached_lead_info.get("email") and not state.context.email:
                state.context.email = cached_lead_info["email"]
            if cached_lead_info.get("phone") and not state.context.phone:
                state.context.phone = cached_lead_info["phone"]
            if cached_lead_info.get("new_lead") is not None and state.context.new_lead is False:
                state.context.new_lead = cached_lead_info["new_lead"]
        
        # CRITICAL: After handoffs, ensure onboarding state is never lost
        # Restore from cache if missing
        restore_onboarding_state_to_context(thread.id, state.context)
        
        # Update cache with current context values to keep it in sync
        # This ensures cache always has the latest values
        if state.context.first_name or state.context.country or state.context.email or state.context.phone:
            lead_info_dict = {
                "first_name": state.context.first_name,
                "email": state.context.email,
                "phone": state.context.phone,
                "country": state.context.country,
                "new_lead": state.context.new_lead,
            }
            self._lead_info_cache[thread.id] = lead_info_dict
            set_lead_info(thread.id, lead_info_dict)  # Also update module-level cache
        
        # Update onboarding state cache with current context values to keep it in sync
        if state.context.onboarding_state:
            self._onboarding_state_cache[thread.id] = state.context.onboarding_state.copy()
            set_onboarding_state(thread.id, state.context.onboarding_state.copy())
        
        # Debug: Print context state to verify it's preserved
        print(f"[DEBUG] After Runner - Context state: first_name={state.context.first_name}, country={state.context.country}, new_lead={state.context.new_lead}, email={state.context.email}, onboarding_state={state.context.onboarding_state}")

        new_context = public_context(state.context)
        changes = {k: new_context[k] for k in new_context if previous_context.get(k) != new_context[k]}
        if changes:
            state.events.append(
                AgentEvent(
                    id=uuid4().hex,
                    type="context_update",
                    agent=state.current_agent_name,
                    content="",
                    metadata={"changes": changes},
                    timestamp=time.time() * 1000,
                )
            )
        await self._broadcast_state(thread, context)
        yield ClientEffectEvent(
            name="runner_state_update",
            data={"thread_id": thread.id, "ts": time.time()},
        )
        if new_events:
            yield ClientEffectEvent(
                name="runner_event_delta",
                data={
                    "thread_id": thread.id,
                    "ts": time.time(),
                    "events": [e.model_dump() for e in new_events],
                },
            )

    async def action(
        self,
        thread: ThreadMetadata,
        action: Action[str, Any],
        sender: WidgetItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        # No client-handled actions in this demo.
        if False:
            yield

    async def snapshot(self, thread_id: Optional[str], context: dict[str, Any]) -> Dict[str, Any]:
        thread = await self._ensure_thread(thread_id, context)
        state = self._state_for_thread(thread.id)
        return {
            "thread_id": thread.id,
            "current_agent": state.current_agent_name,
            "context": public_context(state.context),
            "agents": _build_agents_list(),
            "events": [e.model_dump() for e in state.events],
            "guardrails": [g.model_dump() for g in state.guardrails],
        }

    # -- Streaming state updates to UI listeners ---------------------------------
    def _register_listener(self, thread_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._listeners.setdefault(thread_id, []).append(q)
        # Push last snapshot if available so late listeners get current state immediately.
        last = self._last_snapshot.get(thread_id)
        if last:
            try:
                q.put_nowait(last)
            except asyncio.QueueFull:
                pass
        return q

    def register_listener(self, thread_id: str) -> asyncio.Queue:
        """Public wrapper for listener registration."""
        return self._register_listener(thread_id)

    def _unregister_listener(self, thread_id: str, queue: asyncio.Queue) -> None:
        listeners = self._listeners.get(thread_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners and thread_id in self._listeners:
            self._listeners.pop(thread_id, None)

    def unregister_listener(self, thread_id: str, queue: asyncio.Queue) -> None:
        """Public wrapper for listener cleanup."""
        self._unregister_listener(thread_id, queue)

    async def _broadcast_state(self, thread: ThreadMetadata, context: dict[str, Any]) -> None:
        listeners = self._listeners.get(thread.id, [])
        if not listeners:
            return
        snap = await self.snapshot(thread.id, context)
        # Compute delta of new events since last broadcast to reduce payloads
        last_idx = self._last_event_index.get(thread.id, 0)
        total_events = len(snap.get("events", []))
        delta = snap.get("events", [])[last_idx:] if total_events >= last_idx else snap.get("events", [])
        self._last_event_index[thread.id] = total_events
        payload_obj = {
            **snap,
            "events_delta": delta,
        }
        payload = json.dumps(payload_obj, default=str)
        self._last_snapshot[thread.id] = payload
        for q in list(listeners):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass
