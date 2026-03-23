# Todo

---

## Agent Behavior

### [ ] Agent orchestration audit & cleanup
**Location**: `agent/lucentive/agents.py`

Review and fix the agent handoff graph — instructions, routing rules, and handoff permissions across all four agents.

**Known bug — FAQ agent transfers before replying:**
The FAQ agent is instructed to: run file_search → reply to user → hand back to Triage. In practice the model sometimes calls `transfer_to_triage_agent` immediately after file_search without sending a reply first. Triage then answers from conversation history instead of the knowledge base. Investigate whether stricter ordering language or a two-turn split fixes this.

**Items to decide and implement:**

1. **Handoff graph topology** — should all specialists always return to Triage (hub-and-spoke), or are direct specialist-to-specialist handoffs acceptable? Decide which connections are intentional.

2. **Scheduling → FAQ gap** — Scheduling can only route to Triage or Onboarding. If a user asks a question mid-scheduling, there's no path to FAQ. Intentional or a gap?

3. **Triage answering FAQ questions directly** — Triage sees full conversation history and can construct plausible answers without hitting the knowledge base. Decide whether Triage should be explicitly forbidden from answering FAQ-type questions and always route to FAQ instead.

4. ~~**Triage instructions missing company context**~~ ✓ Done
5. ~~**Remove stale UI comment**~~ ✓ Done
6. ~~**Triage routing — Scheduling trigger wording**~~ ✓ Done
7. ~~**Triage routing — broaden FAQ trigger**~~ ✓ Done

8. **Audit and rewrite all agent instruction prompts** — Instructions have grown organically through trial and error and now contain redundant rules, contradictory emphasis, and ad-hoc patches. Do a clean read-through of every agent's instructions and rewrite with intention: remove duplicates, sort by priority (must-dos first, edge cases last), ensure consistent tone and structure.

9. **Audit handoff ordering rules** — Ensure every agent that must reply before handing off has unambiguous language the model consistently follows.

10. **Tool ownership per agent** — `update_lead_info` is held by both Triage and Onboarding. Revisit once the handoff graph is decided. Same logic applies to `request_human_handoff`, `get_country_offers`, `get_broker_assets`, and future tools — tool ownership should follow directly from the chosen orchestration structure, not be assigned ad hoc.

---

### [ ] Agent flow resilience — keep agents on track when users deviate
**Location**: `agent/lucentive/agents.py` + individual agent instruction prompts

Agents lose their place the moment a user deviates from the expected response format: sending fragmented input, asking an off-topic question mid-flow, or going off-script during onboarding or scheduling.

**Deviation patterns to handle:**
- Fragmented input across multiple messages ("gold" → "actually" → "forex") instead of one complete answer
- Mid-onboarding questions ("wait, what is forex?") that derail the flow without completing the current step
- Mid-scheduling questions that cause the agent to answer directly (without knowledge base grounding) or hand off but never resume

**Questions to decide and implement:**
1. Should onboarding and scheduling agents track which step they were on so they can resume after an interruption?
2. If a user asks an off-topic question mid-flow, should the agent: (a) answer briefly and return, (b) hand off and instruct the specialist to return, or (c) decline to deviate and ask the user to complete the current step first?
3. Should agents be more tolerant of fragmented input — accumulate partial answers before treating a step as complete?
4. Every multi-step flow agent should have explicit prompt language instructing it to re-ask the current step if the user's response is off-topic or incomplete, rather than accepting anything as a valid answer.

---

### [X] Extend human handoff to all agents
**Location**: `agent/airline/agents.py`

Only Triage and FAQ have `request_human_handoff`. If a user asks to speak to a human mid-scheduling or mid-onboarding, those agents must first return to Triage — an unnecessary detour.

**If decided yes (assumed):**
- Add `request_human_handoff` to the tools list of Scheduling and Onboarding agents
- Inject `_load_handoff_skill()` into their instruction prompts the same way it's done for Triage and FAQ

---

### [X] Re-evaluate guardrails
**Location**: `agent/airline/guardrails.py` + `agents.py`

All four agents have `relevance_guardrail` and `jailbreak_guardrail`. These return bot-like rejection messages that break the human-agent illusion the product is built on.

**The argument for replacing with handoff triggers:**
- Jailbreak and off-topic messages are exactly the cases where a human handoff is the right response anyway
- A handoff response is indistinguishable from a human; a guardrail rejection is not
- Dynamic handoff scenarios in the dashboard can catch and route edge cases gracefully

**Questions to decide:**
1. Can relevance and jailbreak guardrails be fully replaced by handoff triggers (either dynamic Supabase scenarios or a catch-all agent instruction)?
2. If guardrails are kept, rewrite their responses to sound human rather than bot-like.
3. Prompt injection and safety-critical cases must still be handled — guardrails for those are non-negotiable.

---

## Infrastructure

### [X] Improve error handling & logging for vector store sync
**Location**: `agent/knowledge.py` — `_sync_qa_vector_store()` (lines 51–99)

Three gaps in the sync that runs after every QA pair create/update/delete:

1. **No error handling on upload/attach** — lines 94–98 are unwrapped; any failure bubbles up as an uncontextualized 500 with no log entry.
2. **No polling for `completed` status** — `vector_stores.files.create()` returns while the file is still `in_progress`. Code logs "synced" prematurely; if the agent queries before indexing finishes, the new QA pair is not yet searchable.
3. **Sync failures are invisible to the dashboard** — if sync fails, the dashboard still receives `201 Created` because the Supabase insert succeeded. The user has no indication the vector store is out of sync.

**Proposed fixes:**
- Wrap upload + attach in `try/except`, log `ERROR` on failure with full exception detail
- After `vector_stores.files.create()`, poll until `completed` or `failed` (with timeout), then log accordingly
- Return `207 Multi-Status` with `{"saved": true, "synced": false, "sync_error": "..."}` when sync fails so the dashboard can surface it

---

### [ ] Thread tracking — view past conversations & agent behavior

A way to look back at past user conversations: which agents handled the thread, what tools were called, what handoffs happened, and what the agent said at each step. Currently threads are in-memory only and lost on restart.

**Questions to decide before designing:**
- Where should threads be stored?
- What level of detail is needed — full message history, tool calls only, or handoff trace?
- Should this be viewable from the dashboard or a separate interface?
- Do we need filtering/search (by phone number, date, country)?
- How long should threads be retained?

**Likely approach:** Persist thread events (messages, tool calls, handoffs, guardrail hits) to a Supabase table as they happen. Add a "Threads" view to the dashboard.

---

## Automation & Integrations

### [ ] Fix WhatsApp welcome message — prevent "Read More" collapse

WhatsApp collapses long messages with a "Read More" button above roughly 1024 characters. The welcome message sent on first contact is too long and getting truncated.

**Questions before fixing:**
- Is this a WhatsApp template message (pre-approved by Meta) or a freeform message via Twilio?
- What is the current message text?
- Is this sent from n8n or from the Python backend?

**Likely fix:** Shorten below the collapse threshold, or split into two shorter sequential messages.

---

### [ ] Calendly booking → WhatsApp notification to human agents (via n8n)

When a user books via Calendly, automate: Gmail receives Calendly confirmation email → parse booking details → send WhatsApp message to human agents with the lead info. No Calendly premium needed — n8n as the glue.

**Flow:** `Gmail trigger (new email from Calendly)` → `Parse email body` → `Send WhatsApp via Twilio to agents`

**Questions before building:**
- Does n8n already have a Gmail connection, or does that need to be created?
- What details from the Calendly email should be included (name, phone, time slot)?
- Which WhatsApp number should receive agent notifications?

---

### [ ] Notify human agents on WhatsApp when user confirms callback

When a user confirms a callback (10-min or 2–4 hour window), human agents need to be notified immediately via WhatsApp with the lead's details so they can place the call.

**Key constraint — WhatsApp 24-hour window:** Since we're sending to the human agent (not a user who just messaged us), a pre-approved WhatsApp message template must be submitted and approved via Meta/BSP before this can go live.

**Questions before building:**
- Which agent phone number(s) should receive the notification?
- Which lead fields to include (name, phone, country, bot preference, budget)?
- Should the trigger come from the Python backend (webhook to n8n) or from n8n detecting the confirmation directly?

**Likely approach:** Python backend triggers an n8n webhook when the user confirms a callback → n8n sends the pre-approved WhatsApp template to agent number(s).

---

## Misc

### [X] Remove `/manager` slash command
**Location**: All references in the dashboard/UI frontend and the backend agent server

`/manager` was added as a manual testing shortcut to simulate human handoff. Now that dynamic handoff triggers are configured via the dashboard, this hardcoded command should be removed.

**Before removing:** Confirm that dynamic handoff scenarios fully cover the `/manager` use case.
