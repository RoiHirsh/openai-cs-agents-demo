# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI-powered customer service agent system for **Lucentive Club** (a trading bot financing service), built on the **OpenAI Agents SDK** with a **Next.js frontend** and **Python FastAPI backend**. The system uses a triage-and-handoff pattern where a central Triage Agent routes customers to specialist agents.

## Development Commands

### Setup

```bash
# Backend (from python-backend/)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend (from ui/)
npm install
```

### Running

```bash
# Run both backend + frontend simultaneously (from ui/)
npm run dev
# Backend: http://localhost:8000   Frontend: http://localhost:3000

# Run separately
cd python-backend && python -m uvicorn main:app --reload --port 8000
cd ui && npm run dev:next
```

### Build & Lint

```bash
cd ui && npm run build   # Production build
cd ui && npm run lint    # ESLint
```

### Testing

```bash
# From python-backend/
python -m pytest airline/test_scheduling_timezones.py
```

### Environment

Set `OPENAI_API_KEY` in `python-backend/.env`. Optionally set `BACKEND_URL` (defaults to `http://127.0.0.1:8000`) for frontend-to-backend proxying.

## Architecture

### Two Main Components

**Python Backend** (`python-backend/`) — FastAPI + OpenAI Agents SDK
**Next.js UI** (`ui/`) — React 19 + ChatKit widget

### Agent System (`python-backend/airline/agents.py`)

Four agents with a triage-and-handoff pattern:

| Agent | Role |
|-------|------|
| `triage_agent` | Entry point; routes to specialist agents based on intent |
| `onboarding_agent` | Guides new leads through a 5-step trading bot onboarding flow |
| `scheduling_agent` | Schedules callbacks with timezone-aware availability |
| `investments_faq_agent` | Answers trading/investment questions via `FileSearchTool` |

Handoffs are bidirectional — specialists return to Triage when done. Context is preserved across handoffs via `context_cache.py` (module-level dicts keyed by `thread_id`).

### State Management

`AirlineAgentContext` (`airline/context.py`) holds lead info (`first_name`, `email`, `phone`, `country`, `new_lead`) and `onboarding_state` (completed steps, trading experience, budget, etc.).

When agents hand off, state is saved to `context_cache.py` and restored from it — this is the mechanism for keeping state coherent across agent transitions.

### Tool System (`airline/tools.py`, `lucentive/tools.py`)

Agents call function tools that return JSON; agents must translate results to natural language — never paste raw tool output to users.

Key tools:
- `get_scheduling_context` — returns timezone-aware availability windows
- `update_onboarding_state` — persists onboarding step completion
- `update_lead_info` — updates lead contact details
- `get_country_offers` — returns available bots/brokers by country
- `get_broker_assets` — returns broker links and videos

### Scheduling (`airline/scheduling.py`)

Anchors service availability to **Israel time (11:00–22:00)**. Handles DST transitions and midnight-crossing edge cases. Offers: 20-min callback (if within window), 2–4 hour callback (fallback), or Calendly link (always available).

### Guardrails (`airline/guardrails.py`)

Two input-level guardrails run before agent processing:
- **Relevance**: Blocks messages unrelated to trading bots/Lucentive services
- **Jailbreak**: Detects prompt injection and credential-harvesting attempts

### Conversation Flow for New Leads

1. `LeadInfoModal` (UI) captures name/email/phone/country
2. UI calls `/chatkit/bootstrap` with lead data
3. Backend initializes `AirlineAgentContext` with `new_lead=True`
4. Triage Agent detects `new_lead=True`, routes to Onboarding Agent
5. Onboarding runs 5-step flow; each step calls `update_onboarding_state`
6. After onboarding completes, follow-up questions route to FAQ or Scheduling

### Frontend UI Panels (`ui/components/`)

Three-panel layout: ChatKit widget | Agent activity visualization (events, guardrails, tool calls, handoffs) | Lead info + onboarding state display. Useful for debugging agent behavior.

### FAQ Knowledge Base

`investments_faq_agent` uses `FileSearchTool` with vector store ID `vs_6943a96a15188191926339603da7e399`. Citation markers (`【…†source】`) are stripped before displaying responses to users.

### Skill Files

Agent prompts load Markdown skill guides from `airline/skills/` at runtime (e.g., `airline/skills/scheduling/SKILL.md`). These are embedded in agent instructions to provide behavioral guidance.

### Backend API Endpoints (`main.py`)

- `POST /chatkit` — main ChatKit message handler
- `GET /chatkit/state` — fetch thread state
- `GET /chatkit/state/stream` — SSE stream for real-time state updates
- `POST /chatkit/bootstrap` — initialize a new thread with lead data
- `GET /health` — health check
