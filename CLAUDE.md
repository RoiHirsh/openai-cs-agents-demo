# CLAUDE.md — Lucentive Club Agent System

This file provides AI assistants with a comprehensive overview of the codebase, architecture, conventions, and development workflows.

---

## Project Overview

This is the **Lucentive Club Agent System** — an AI-powered customer service platform built for Lucentive Club's AI trading bot financing services. It uses the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) for multi-agent orchestration and [ChatKit](https://openai.github.io/chatkit-js/) for the chat UI.

The system guides prospective leads through an onboarding journey: gauging trading experience, recommending bots/brokers by country, confirming budget, and providing account setup instructions. It also handles call scheduling and investment-related FAQ questions.

---

## Repository Structure

```
openai-cs-agents-demo/
├── python-backend/           # FastAPI backend + agent logic
│   ├── main.py               # FastAPI app, all HTTP routes
│   ├── server.py             # AirlineServer: core ChatKit integration, streaming, state management
│   ├── memory_store.py       # In-memory thread/item store
│   ├── requirements.txt      # Python dependencies
│   ├── runtime.txt           # Python 3.12.7 (for Railway deployment)
│   ├── twilio_whatsapp.py    # Twilio WhatsApp helpers (signature validation, send_whatsapp_message)
│   ├── test_twilio_whatsapp.py  # Tests for Twilio integration
│   ├── airline/              # Core agent module (named "airline" for historical reasons)
│   │   ├── agents.py         # All agent definitions (Triage, Scheduling, Onboarding, FAQ)
│   │   ├── context.py        # AirlineAgentContext Pydantic model + public_context()
│   │   ├── context_cache.py  # Thread-scoped caches for lead_info and onboarding_state
│   │   ├── guardrails.py     # Relevance + Jailbreak input guardrails
│   │   ├── scheduling.py     # Scheduling window logic (Israel/Guatemala timezone math)
│   │   ├── tools.py          # get_scheduling_context, update_onboarding_state, update_lead_info
│   │   ├── test_scheduling_timezones.py  # Timezone/DST unit tests
│   │   └── skills/
│   │       ├── scheduling/SKILL.md   # Scheduling agent behavior spec (loaded at runtime)
│   │       └── onboarding/SKILL.md   # Onboarding agent behavior spec (loaded at runtime)
│   └── lucentive/            # Lucentive-specific tools and data
│       ├── tools.py          # get_broker_assets, get_country_offers
│       └── knowledge/
│           └── country_offers.json   # Country → bots/brokers availability data
├── ui/                       # Next.js 15 frontend
│   ├── app/
│   │   ├── page.tsx          # Main page: bootstrap, lead modal, panels
│   │   └── chatkit/          # ChatKit Next.js integration routes
│   ├── components/
│   │   ├── agent-panel.tsx        # Left panel: agents, events, guardrails, context
│   │   ├── chatkit-panel.tsx      # Right panel: ChatKit chat UI
│   │   ├── lead-info-modal.tsx    # Lead info popup (randomizes test data on page load)
│   │   ├── conversation-context.tsx  # Displays context variables (first_name, country, etc.)
│   │   ├── agents-list.tsx        # Agent list with handoffs/tools display
│   │   ├── guardrails.tsx         # Guardrail check results display
│   │   └── runner-output.tsx      # Agent events timeline
│   ├── lib/
│   │   ├── api.ts            # fetchBootstrapState, fetchThreadState
│   │   └── types.ts          # TypeScript types (Agent, AgentEvent, GuardrailCheck)
│   ├── package.json
│   └── next.config.mjs
├── README.md
├── tasks.md                  # Task backlog (numbered; checkboxes; Tasks 1–26)
└── LUCENTIVE_ADAPTATION_PLAN.md  # Historical architecture planning doc
```

---

## Tech Stack

### Backend
- **Python 3.12** (required; `runtime.txt` pins to `3.12.7`)
- **FastAPI** + **Uvicorn** — HTTP server
- **OpenAI Agents SDK** (`openai-agents`) — multi-agent orchestration, `Agent`, `Runner`, `handoff`, `function_tool`, guardrails
- **OpenAI ChatKit** (`openai-chatkit`) — server-side ChatKit integration (`ChatKitServer`)
- **Pydantic** — context models
- **pytz** — timezone handling for scheduling window (Israel/Guatemala)
- **Twilio** — WhatsApp inbound/outbound messaging (Tasks 22–26, partially complete)
- **python-dotenv** — `.env` loading

### Frontend
- **Next.js 15** (React 19, TypeScript)
- **@openai/chatkit** + **@openai/chatkit-react** — chat UI components
- **Tailwind CSS** — styling
- **Radix UI** — accessible scroll area / slot primitives
- **Motion** (Framer Motion) — animations
- **concurrently** — runs Next.js dev server and Python backend simultaneously

### AI Model
- Main agents: `gpt-5.2` (defined as `MODEL` constant in `agents.py`)
- Guardrail agents: `gpt-4.1-mini` (defined as `GUARDRAIL_MODEL` in `guardrails.py`)

---

## Architecture

### Agent Orchestration

The system uses a **hub-and-spoke** pattern with the **Triage Agent** as the central router:

```
User Message
    ↓
Triage Agent  ←──────────────────────────────────┐
    │                                             │
    ├──→ Onboarding Agent ────────────────────────┤
    ├──→ Scheduling Agent ────────────────────────┤
    ├──→ Investments FAQ Agent ───────────────────┤
    └──→ (Onboarding) ←── FAQ / Scheduling can return here
```

**Handoff rules:**
- **Triage Agent** is the only agent that initiates handoffs to specialists
- Specialist agents hand back to **Triage Agent** (or to Onboarding Agent for cross-specialty cases)
- New leads (`new_lead=True`, `onboarding_complete=False`) are proactively routed to **Onboarding Agent** by default
- Saying "call" routes to **Scheduling Agent**; investment questions route to **FAQ Agent**
- When `onboarding_complete=True`, Triage routes normally (no default onboarding)

### Agent Definitions (`python-backend/airline/agents.py`)

| Agent | Role | Tools | Guardrails |
|-------|------|-------|-----------|
| `triage_agent` | Central router; handles corrections via `update_lead_info` | `update_lead_info` | Relevance, Jailbreak |
| `scheduling_agent` | Call scheduling: 20 min → 2–4 hours → Calendly fallback | `get_scheduling_context` | Relevance, Jailbreak |
| `onboarding_agent` | Multi-step onboarding: trading exp → bot/broker → budget → instructions | `get_country_offers`, `get_broker_assets`, `update_lead_info`, `update_onboarding_state` | Relevance, Jailbreak |
| `investments_faq_agent` | Investment Q&A using OpenAI file search (vector store) | `FileSearchTool` (vector store `vs_6943a96a15188191926339603da7e399`) | Relevance, Jailbreak |

### Agent Instructions Pattern

Triage, Scheduling, and Onboarding agents use **dynamic instruction functions** that accept `RunContextWrapper[AirlineAgentChatContext]` — they read the current context state and inject it into the prompt. FAQ agent uses a static string.

Scheduling and Onboarding agents additionally load their instructions from **SKILL.md files** at runtime (e.g. `airline/skills/scheduling/SKILL.md`). Editing these files changes agent behavior without touching Python code.

### Context Model (`python-backend/airline/context.py`)

```python
class AirlineAgentContext(BaseModel):
    first_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    new_lead: bool = False
    onboarding_state: dict | None = None
    # onboarding_state structure:
    # {
    #   "completed_steps": list[str],  # e.g. ["trading_experience", "bot_recommendation", ...]
    #   "trading_experience": str | None,
    #   "previous_broker": str | None,
    #   "trading_type": str | None,
    #   "bot_preference": str | None,
    #   "broker_preference": str | None,
    #   "budget_confirmed": bool | None,
    #   "budget_amount": float | None,
    #   "demo_offered": bool | None,
    #   "instructions_provided": bool | None,
    #   "onboarding_complete": bool | None,
    #   "has_broker_account": bool | None
    # }
```

Context is **persisted in two ways**:
1. `state.context` on the in-memory `ConversationState` per thread
2. `context_cache.py` module-level caches (`_lead_info_cache`, `_onboarding_state_cache`) keyed by `thread_id` — used to survive handoffs and context resets

### Server (`python-backend/server.py`)

`AirlineServer` extends `ChatKitServer`. Key responsibilities:
- **Thread management**: `_ensure_thread()` creates/loads threads; always restores lead info from cache
- **`respond()`**: Main streaming loop — runs `Runner.run_streamed()`, sanitizes citations from assistant text, handles scheduling acceptance phrases, broadcasts state updates to SSE listeners
- **`process_plaintext_message()`**: Used by WhatsApp webhook — runs the same `respond()` loop, returns the final assistant text as a string
- **`snapshot()`**: Returns full state (thread_id, current_agent, context, agents list, events, guardrails) for the UI

**Citation stripping**: `_strip_user_visible_citations()` removes OpenAI file_search citation markers (e.g. `【...†source】`) from user-visible text.

**Scheduling acceptance guard**: When a user accepts a callback (`yes`, `sure`, `ok`, etc.) and Scheduling Agent tries to ask for phone/timezone (a known LLM failure mode), `server.py` replaces the response with a canned confirmation.

---

## API Endpoints (`python-backend/main.py`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chatkit` | Main ChatKit message processing (streaming SSE) |
| `GET` | `/chatkit/state` | Get snapshot of a thread's state |
| `GET` | `/chatkit/bootstrap` | Create/load thread with lead info; returns initial snapshot |
| `GET` | `/chatkit/state/stream` | SSE stream of state updates for a thread |
| `GET` | `/health` | Health check |
| `POST` | `/twilio/whatsapp/webhook` | Twilio WhatsApp inbound webhook (signature validation → agent → outbound reply) |

**Bootstrap endpoint** is called by the frontend on page load after the lead info modal is submitted. It accepts `first_name`, `email`, `phone`, `country`, and `new_lead` query parameters.

---

## Key Data Files

### `lucentive/knowledge/country_offers.json`

Defines bot and broker availability by country group:

```json
{
  "AUSTRALIA": { "bots": ["Futures in Crypto"], "brokers": [{"name": "ByBit", "notes": []}] },
  "CANADA":    { "bots": ["Gold", "Silver", "Forex", "Cryptocurrencies"], "brokers": [{"name": "PU Prime", "notes": [...]}] },
  "OTHER":     { "bots": ["Gold", "Silver", "Forex", "Cryptocurrencies", "Futures"], "brokers": [...] }
}
```

Countries are normalized to `AUSTRALIA`, `CANADA`, or `OTHER`. Edit this file to add/change country availability.

### `lucentive/tools.py` — Broker assets

`BROKER_LINKS` and `BROKER_VIDEOS` dicts hardcode referral/registration URLs and tutorial video links per broker (`bybit`, `vantage`, `pu_prime`) and purpose (`registration`, `copy_trade_open_account`, `copy_trade_connect`, `copy_trade_start`).

Supported brokers: **Vantage**, **PU Prime**, **ByBit**. To add a broker: add entries to both dicts, update `normalize_broker()`, update `country_offers.json`.

---

## Onboarding Flow

The Onboarding Agent follows this exact sequence. Each step must be completed and recorded via `update_onboarding_state()` before proceeding:

1. **`trading_experience`** — Ask "Do you have prior trading experience?" If YES, ask follow-up (type + broker) in a separate message
2. **`bot_recommendation`** — Call `get_country_offers(country)` → present available bots → user selects
3. **`broker_selection`** — Call `get_country_offers(country)` again → present available brokers → user selects
4. **`budget_check`** — Ask if $500 minimum is workable. If NO, offer 10-day demo
5. **`profit_share_clarification`** — Fixed text: "We take zero upfront. We only take 35% of the profit…"
6. **`has_broker_account`** — Ask if they already have an account with the selected broker
7. **`instructions`** — Send registration link + video (if no account) then copy-trade steps via `get_broker_assets()`
8. **Complete** — When user confirms both account created and copy trading connected, call `update_onboarding_state(onboarding_complete=True)` and hand off to Triage

The full specification is in `airline/skills/onboarding/SKILL.md`.

---

## Scheduling Logic

The Scheduling Agent uses `get_scheduling_context()` (calls `compute_scheduling_context()` in `scheduling.py`).

**Service window**: 11:00 Israel time → 20:00 Guatemala time (~09:00–02:00 UTC, DST-adjusted)

**Priority of offers**:
1. 20-minute callback (when open and within window)
2. 2–4 hours callback (when closed but opening within ~4 hours)
3. Calendly link (Sunday or closed for many hours)

Sundays are always closed. The agent calls `get_scheduling_context(exclude_actions=["20_min"])` etc. to step down to the next offer when the user declines.

The full specification is in `airline/skills/scheduling/SKILL.md`. The Calendly booking URL is set as `CALENDLY_BOOKING_URL` constant in `scheduling.py`.

---

## Guardrails (`python-backend/airline/guardrails.py`)

Two input guardrails are applied to all agents:

- **Relevance Guardrail** (`gpt-4.1-mini`): Blocks questions unrelated to trading bots, financing, onboarding, broker setup, scheduling, etc. Allows short conversational responses in context (e.g. "yes", "chat", "call").
- **Jailbreak Guardrail** (`gpt-4.1-mini`): Blocks prompt injection attempts and system prompt extraction.

When tripped, the server returns: `"Sorry, I can only answer questions related to financing trading bot services and related topics."`

---

## Environment Variables

Create a `.env` file in `python-backend/`:

```env
OPENAI_API_KEY=sk-...

# Optional: Twilio WhatsApp (Tasks 22–26)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
PUBLIC_BASE_URL=https://your-deployed-domain.com

# Optional
TWILIO_MESSAGING_SERVICE_SID=...
```

`OPENAI_TRACING_DISABLED=1` is set in `main.py` automatically.

---

## Development Setup

### Backend

```bash
cd python-backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

Backend available at: `http://localhost:8000`

### Frontend + Backend Together

```bash
cd ui
npm install
npm run dev       # Starts Next.js on :3000 AND uvicorn on :8000 simultaneously
```

The `dev` script uses `concurrently` to start both processes. See `ui/package.json` scripts.

Frontend available at: `http://localhost:3000`

### Running Tests

```bash
# Backend timezone/scheduling tests
cd python-backend
python -m pytest airline/test_scheduling_timezones.py -v

# Backend Twilio webhook tests
python -m pytest test_twilio_whatsapp.py -v
```

No frontend test suite is currently configured.

---

## Deployment (Railway)

The app is designed for Railway (Railpack) deployment:

- Set `RAILPACK_PYTHON_VERSION=3.12` (or `3.12.7`) to avoid `mise ERROR no precompiled python found`
- `runtime.txt` and `python-backend/runtime.txt` both specify `python-3.12.7`
- Set all `OPENAI_API_KEY` and Twilio environment variables in Railway service Variables tab

---

## UI Architecture

The UI is a single-page Next.js app with two panels:

**Left panel (`AgentPanel`):**
- `agents-list.tsx`: Shows all agents with their handoff targets and tools
- `runner-output.tsx`: Timeline of agent events (messages, handoffs, tool calls, tool outputs, context updates)
- `guardrails.tsx`: Pass/fail status of each guardrail check
- `conversation-context.tsx`: Live context variables (first_name, country, new_lead, onboarding_state, etc.)

**Right panel (`ChatKitPanel`):**
- Renders the ChatKit chat interface
- Initial buttons: "Chat" (sends `"chat"`) and "Call" (sends `"call"`)
- Personalized greeting uses `first_name` from lead info

**Lead Info Modal (`LeadInfoModal`):**
- Appears on page load; pre-fills randomized test data (name, email, phone, country)
- On submit: calls `/chatkit/bootstrap` to initialize thread with lead data
- Sets `new_lead=true` for all sessions loaded via the modal

**State management** is done with React `useState`/`useCallback`; no Redux or Zustand. Thread state is fetched from backend via `/chatkit/state` and `/chatkit/state/stream` (SSE).

---

## Adding New Features

### Adding a new agent

1. Define the agent in `python-backend/airline/agents.py` (use `Agent[AirlineAgentChatContext]`)
2. Add it to `triage_agent.handoffs` (and any other agents that should be able to hand off to it)
3. Add a return handoff to Triage Agent from the new agent
4. Register in `_get_agent_by_name()` and `_build_agents_list()` in `server.py`
5. Import in `main.py` and add to `__all__`

### Adding a new tool

1. Define with `@function_tool(name_override=..., description_override=...)` in `tools.py` (or `lucentive/tools.py`)
2. Add to the relevant agent's `tools` list in `agents.py`

### Updating agent behavior

- For **Scheduling Agent**: Edit `airline/skills/scheduling/SKILL.md` — changes take effect on next request (loaded at runtime)
- For **Onboarding Agent**: Edit `airline/skills/onboarding/SKILL.md` — same
- For **other agents**: Edit the instructions string/function in `airline/agents.py`

### Updating country/broker availability

- Edit `lucentive/knowledge/country_offers.json` for country→bot/broker mapping
- Edit `BROKER_LINKS`/`BROKER_VIDEOS` in `lucentive/tools.py` for referral links and tutorial videos

---

## Key Conventions

### Python

- All agents use `from __future__ import annotations as _annotations` at the top
- Context type is always `AirlineAgentContext` (despite the "Airline" name — a historical artifact)
- Tools that need context access receive `run_context: RunContextWrapper[AirlineAgentChatContext]` as first parameter
- `@function_tool` decorator always sets explicit `name_override` and `description_override`
- Debug `print()` statements are intentionally verbose (prefixed `[DEBUG]`, `[TOOL EXEC]`, etc.) — they appear in backend logs
- Always update `context_cache` after modifying lead info or onboarding state to ensure persistence across handoffs
- The module is named `airline` for historical reasons (adapted from an airline customer service demo) — do not rename

### TypeScript / Next.js

- All components are in `ui/components/`; pages in `ui/app/`
- `"use client"` directive is used for any component with state or effects
- API calls go through `ui/lib/api.ts` (centralized fetch helpers)
- Types are in `ui/lib/types.ts`

### Commit style

- Imperative short message (no period): e.g. `fix scheduling timezone DST bug`
- No ticket numbers required

---

## Current Task Status (`tasks.md`)

Tasks 1–21 are complete. Outstanding tasks:

| Task | Description |
|------|-------------|
| **22** | WhatsApp (Twilio) — Install dependencies + env config |
| **23** | WhatsApp (Twilio) — Create inbound webhook endpoint (FastAPI) |
| **24** | WhatsApp (Twilio) — Connect webhook to agent + send outbound reply |
| **25** | WhatsApp (Twilio) — Add automated tests for webhook wiring |
| **26** | WhatsApp (Twilio) — Sandbox hookup checklist |

Note: Tasks 22–24 are partially implemented (`twilio_whatsapp.py` and the `/twilio/whatsapp/webhook` endpoint exist). Tasks 25–26 remain.

---

## Known Architecture Notes

- **Context persistence**: The OpenAI Agents SDK may reset context during handoffs; `context_cache.py` and the restore logic in `server.py:_state_for_thread()` / `respond()` defend against this
- **Thread ID instability**: ChatKit may create new threads mid-session; `server.py` fallback logic copies lead info from the most recent cache entry with valid data
- **FAQ vector store**: The `FileSearchTool` uses a hardcoded vector store ID (`vs_6943a96a15188191926339603da7e399`). Update this constant in `agents.py` if the OpenAI project changes
- **No database**: All state is in-memory; restarting the backend clears all conversations
- **WhatsApp thread mapping**: `WhatsAppThreadMapper` in `twilio_whatsapp.py` maps phone numbers to thread IDs using a plain dict — also in-memory only
