# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI-powered customer service agent system for **Lucentive Club** (a trading bot financing service), built on the **OpenAI Agents SDK** with a **Vite frontend** and **Python FastAPI backend**. The system uses a triage-and-handoff pattern where a central Triage Agent routes customers to specialist agents. Leads come in via WhatsApp (through Chatwoot) after expressing interest in the service.

## Development Commands

### Setup

```bash
# Backend (from agent/)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend (from dashboard/)
npm install
```

### Running

```bash
# Backend
cd agent && python -m uvicorn main:app --reload --port 8000

# Frontend (Vite — http://localhost:5173)
cd dashboard && npm run dev
```

### Build & Lint

```bash
cd dashboard && npm run build
```

### Testing

```bash
# From agent/
python -m pytest lucentive/test_scheduling_timezones.py
```

### Environment

Set the following in `agent/.env`:
- `OPENAI_API_KEY`
- `OPENAI_VECTOR_STORE_ID` — vector store for FAQ agent
- `CHATWOOT_API_TOKEN` — required for human handoff
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_TEAM_CHAT_ID`, `TELEGRAM_NOTIFICATIONS_ENABLED` — team alerts channel
- `CHATWOOT_APP_BASE_URL` — optional deep links in Telegram alerts
- `DASHBOARD_API_KEY` — protects `/admin/*` endpoints
- `DASHBOARD_ORIGIN` — CORS allowlist for production dashboard
- `RESET_ENABLED=true` — enables `/reset` dev command
- Supabase credentials (see `agent/integrations/supabase_client.py`)

## Architecture

### Two Main Components

**Python Backend** (`agent/`) — FastAPI + OpenAI Agents SDK
**Vite Dashboard** (`dashboard/`) — React frontend

### Agent System (`agent/lucentive/agents.py`)

Four agents with a full-mesh handoff pattern (every agent can reach every other):

| Agent | Role |
|-------|------|
| `triage_agent` | Entry point; routes to specialist agents based on intent |
| `onboarding_agent` | Guides new leads through a multi-step trading bot onboarding flow |
| `scheduling_agent` | Schedules callbacks with timezone-aware availability |
| `investments_faq_agent` | Answers trading/investment questions via `FileSearchTool` |

All agents run on model `gpt-5.2`. Handoffs are bidirectional. Context is preserved across handoffs via `context_cache.py` (module-level dicts keyed by `thread_id`).

### State Management

`LucentiveAgentContext` (`lucentive/context.py`) holds lead info (`first_name`, `email`, `phone`, `country`, `new_lead`, `conversation_id`) and `onboarding_state` (completed steps, trading experience, bot/broker preference, budget, etc.).

The wrapping `LucentiveAgentChatContext` is the `AgentContext` used during ChatKit runs, with `.state` holding the above.

### Tool System (`agent/lucentive/tools.py`)

Agents call function tools that return JSON; agents must translate results to natural language — never paste raw tool output to users.

Key tools:
- `get_scheduling_context` — returns timezone-aware availability windows
- `update_onboarding_state` — persists onboarding step completion
- `update_lead_info` — updates lead contact details in Supabase
- `get_country_offers` — returns available bots/brokers by country
- `get_broker_assets` — returns broker links and videos
- `request_human_handoff` — triggers the human escalation sequence in Chatwoot

### Scheduling (`agent/lucentive/scheduling.py`)

Anchors service availability to **Israel time (11:00–22:00)**. Handles DST transitions and midnight-crossing edge cases. Offers: 10-min callback (if within window), 2–4 hour callback (fallback), or Calendly link (always available).

### Guardrails (`agent/lucentive/guardrails.py`)

One input-level guardrail runs before agent processing:
- **Jailbreak**: Detects prompt injection and system override attempts

### Skill Files

Agent prompts load Markdown skill guides from `agent/lucentive/skills/` at runtime:
- `skills/scheduling/SKILL.md`
- `skills/onboarding/SKILL.md`
- `skills/handoff/SKILL.md` — also dynamically enriched with handoff scenarios from the knowledge base

### Integrations (`agent/integrations/`)

- `chatwoot.py` — human handoff logic (sets conversation open, assigns agent, applies label, posts private note)
- `telegram.py` / `team_notifications.py` — non-blocking Telegram alerts (`conversation_started`, `human_handoff`); deduped in `team_notification_events`
- `supabase_client.py` — shared Supabase client; persists leads, threads, corrections

### Knowledge Base (`agent/knowledge/`)

- `knowledge.py` — CRUD API (`/knowledge/*`) for `qa_pairs` and `handoff_triggers` in Supabase. After any write, regenerates and re-uploads the OpenAI vector store file so `FileSearchTool` stays in sync.
- `knowledge_search.py` — reads handoff scenarios from Supabase and injects them into agent instructions at runtime.
- Vector store ID is read from `OPENAI_VECTOR_STORE_ID` env var. Citation markers (`【…†source】`) are stripped before displaying responses to users.

### Backend API Endpoints (`agent/main.py`)

- `POST /chatkit` — ChatKit message handler (streaming)
- `GET /chatkit/state` — fetch thread state
- `GET /chatkit/state/stream` — SSE stream for real-time state updates
- `GET /chatkit/bootstrap` — initialize a new thread with lead data
- `POST /api/chat` — WhatsApp/Chatwoot message handler; looks up lead by phone number, restores full state from Supabase, runs agent, persists state back
- `POST /api/context` — inject a message into a thread's input_items directly (without running the agent)
- `GET /admin/threads` — list all threads with correction summary (requires `DASHBOARD_API_KEY`)
- `GET /admin/conversations` — list all sessions including archived ones
- `GET /admin/threads/{thread_id}` — events for a thread, with corrections attached
- `GET /admin/conversations/{thread_id}/messages` — clean chat view (user + assistant only)
- `POST /admin/corrections` — upsert a correction/praise on an AI message
- `GET /health` — health check

### Conversation Flow for WhatsApp Leads

1. Lead data arrives via `POST /api/chat` (phone number + message from Chatwoot/n8n)
2. Backend looks up lead in Supabase `leads` table by phone number
3. If `thread_id` exists, full state (input_items, context, events) is restored from `threads` table
4. `conversation_id` (Chatwoot) is injected into context so `request_human_handoff` can use it
5. `LucentiveServer.process_plaintext_message` runs the agent pipeline
6. Updated state is upserted back to `threads` table; if new thread, `thread_id` is saved to `leads`

### Conversation Flow for New Leads (ChatKit / Dashboard)

1. `LeadInfoModal` captures name/email/phone/country
2. UI calls `GET /chatkit/bootstrap` with lead data
3. Backend initializes `LucentiveAgentContext` with `new_lead=True`
4. Triage Agent detects `new_lead=True`, routes to Onboarding Agent
5. Onboarding runs multi-step flow; each step calls `update_onboarding_state`
6. After onboarding completes, follow-up questions route to FAQ or Scheduling

## Style Guidelines

- Always use proper punctuation in responses and written communication.
