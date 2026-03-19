# March 18 — Knowledge Base Overhaul Plan

## What We Are Building

A Supabase-backed knowledge base and handoff rules system to replace the current OpenAI
vector store (PDF-based). Includes a password-protected internal dashboard for the team
to manage Q&A pairs and handoff rules in real time without code changes or deployments.

Both the AI agent and the dashboard will live in this repo and be deployed as separate
services on Railway.

---

## Branch & Safety

- [x] Backup branch created: `backup/pre-knowledge-base-feature-api-chat`
- All changes go on `feature/api-chat`

---

## Step 1 — Supabase Migration File ✅

Create `supabase/migrations/001_knowledge_base.sql`:

- [x] Enable pgvector extension
- [x] Create `qa_pairs` table (id, question, answer, embedding vector(1536), active, created_at, updated_at)
- [x] Create `handoff_triggers` table (id, scenario, default_response, embedding vector(1536), active, created_at, updated_at)
- [x] Add hnsw indexes on both embedding columns
- [x] Create RPC function `match_qa_pairs` — cosine similarity search, active rows only, returns rows above threshold
- [x] Create RPC function `match_handoff_triggers` — same pattern
- [x] RLS policies: service role = full access, anon = read-only
- [x] Instructions for running: paste into Supabase SQL Editor → Run

> No code changes yet. This step produces one SQL file only.

---

## Step 2 — Repo Restructure ✅

Move existing backend into `/agent` subfolder, create `/dashboard` placeholder:

- [x] Move all contents of `python-backend/` into a new `/agent` folder (git mv, history preserved)
- [x] All internal imports verified unchanged (imports are relative, structure is identical)
- [x] All route definitions intact (`/chatkit`, `/api/chat`, `/api/context`, `/health`, `/twilio/whatsapp/webhook`)
- [x] All env var references intact
- [x] `/dashboard` folder created with README
- [x] Import test passed using venv python

> No logic changes. Pure file reorganisation.

---

## Step 3 — Agent API Endpoints (Knowledge CRUD) ✅

Add `/knowledge` routes to the agent FastAPI app, protected by `x-dashboard-key` header:

- [x] `x-dashboard-key` header dependency checking `DASHBOARD_API_KEY` env var
- [x] `GET /knowledge/qa`
- [x] `POST /knowledge/qa` — embeds question via OpenAI text-embedding-3-small
- [x] `PUT /knowledge/qa/:id` — regenerates embedding if question changed
- [x] `DELETE /knowledge/qa/:id`
- [x] `GET /knowledge/handoff`
- [x] `POST /knowledge/handoff` — embeds scenario
- [x] `PUT /knowledge/handoff/:id` — regenerates embedding if scenario changed
- [x] `DELETE /knowledge/handoff/:id`
- [x] Router registered in main.py, all 8 routes verified

---

## Step 4 — Dashboard React App ✅

Built Vite + React dashboard in `/dashboard`:

- [x] Vite + React project initialised (manual file setup — `create-vite` is interactive)
- [x] Auth gate with sessionStorage, reads `VITE_DASHBOARD_PASSWORD`
- [x] Two-tab layout: Knowledge Base | Handoff Rules
- [x] Knowledge Base tab: list, add, edit, toggle active, delete — full CRUD
- [x] Handoff Rules tab: same, default_response pre-filled with `אחד רגע בבקשה 🙏`
- [x] Validation: min 10 chars on required fields, inline error messages
- [x] `VITE_API_BASE_URL` + `VITE_DASHBOARD_API_KEY` env vars wired
- [x] Production build verified (`npm run build` — clean, 0 errors)

---

## Step 5 — Agent Runtime Logic ✅

- [x] `knowledge_search.py` created with sync + async embedding helpers
- [x] `check_handoff_triggers()` — sync, runs in `process_plaintext_message` before agent, wraps in try/except so failures never block messages
- [x] `search_knowledge_tool` — async `@function_tool` replacing `FileSearchTool`, called by FAQ agent
- [x] `FileSearchTool` removed from `agents.py` with comment explaining why
- [x] FAQ agent now uses `search_knowledge_tool` + instructions updated accordingly
- [x] Handoff check wired into `process_plaintext_message` in `server.py`
- [x] Thresholds `HANDOFF_THRESHOLD = 0.82`, `QA_THRESHOLD = 0.78` as named constants
- [x] All imports verified at runtime — FAQ agent tools: `['search_knowledge', 'request_human_handoff']`

---

## Step 6 — Railway Config ✅

- [x] `agent/railway.toml` — nixpacks, start command `uvicorn main:app --host 0.0.0.0 --port $PORT`, healthcheck `/health`
- [x] `dashboard/railway.toml` — nixpacks, buildCommand `npm run build`, startCommand `npx serve dist -p $PORT`
- [x] Root-level railway.toml removed (was wrong format)

---

## Step 8 — Manual Steps (Human Does These)

Before retiring the old vector store, the human must:

- [ ] Run `001_knowledge_base.sql` migration against the live Supabase project
- [ ] Set new env vars in Railway agent service: `DASHBOARD_API_KEY`
- [ ] Set new env vars in Railway dashboard service: `VITE_API_BASE_URL`, `DASHBOARD_PASSWORD`, `DASHBOARD_API_KEY`
- [ ] Push code — confirm both Railway services deploy successfully
- [ ] Open dashboard, log in, confirm both tabs load
- [ ] Re-enter the existing ~20 Q&A pairs via the Knowledge Base tab
- [ ] Send test messages via WhatsApp/chat — confirm answers come from Supabase
- [ ] Confirm handoff triggers work as expected

> Do not proceed to Step 9 until all of the above are confirmed working.

---

## Step 9 — Retire OpenAI Vector Store

Only after Step 8 is fully confirmed:

- [ ] Remove the PDF knowledge file from the repo
- [ ] Remove all vector store upload and query code from the agent
- [ ] Leave a comment at each removal point noting what was removed and why
- [ ] Final test: confirm agent still answers correctly with old code fully removed

---

## Step 10 — Dashboard: Search Field

Add a search/filter field at the top of both the Knowledge Base tab and the Handoff Rules tab so the team can quickly find and edit existing entries.

- [ ] Knowledge Base tab: text input that filters the displayed Q&A list in real time by question or answer text (client-side, no API call needed)
- [ ] Handoff Rules tab: same — filters by scenario text
- [ ] Clear button (×) to reset the filter
- [ ] No results state: show "No matches" message when filter returns nothing
- [ ] Search is case-insensitive

---

## Step 11 — Dashboard: Bulk Import

Add a "Bulk Import" button on each tab that lets the team paste or upload a list of entries instead of adding them one by one.

- [ ] Knowledge Base tab: button opens a modal — user pastes JSON array of `[{ "question": "...", "answer": "..." }]` or CSV with two columns (question, answer)
- [ ] Handoff Rules tab: same — accepts JSON array of `[{ "scenario": "..." }]` or single-column CSV
- [ ] Validate each row before submitting (min 10 chars on required fields, skip blanks)
- [ ] Submit all rows sequentially to the existing POST endpoints; show progress count ("Importing 3 of 20...")
- [ ] On completion: show success summary ("18 imported, 2 skipped") and refresh the list
- [ ] On partial failure: continue importing remaining rows, report which failed at the end

---

## Environment Variables Reference

| Variable | Service | Notes |
|---|---|---|
| `SUPABASE_URL` | agent | already exists |
| `SUPABASE_SERVICE_KEY` | agent | already exists |
| `OPENAI_API_KEY` | agent | already exists |
| `DASHBOARD_API_KEY` | agent + dashboard | new — shared secret |
| `VITE_API_BASE_URL` | dashboard | new — public URL of agent service |
| `DASHBOARD_PASSWORD` | dashboard | new — team login password |
