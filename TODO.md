# Todo

---

## Agent Behavior

### [X] Agent orchestration audit & cleanup
**Location**: `agent/lucentive/agents.py`

Full mesh handoffs implemented (every agent can reach every other). Triage explicitly forbidden from answering FAQ questions directly. FAQ "reply before transfer" ordering rule added with unambiguous language. All sub-items resolved:

1. ~~**Handoff graph topology**~~ ✓ Full mesh — all specialists can reach each other directly.
2. ~~**Scheduling → FAQ gap**~~ ✓ Scheduling now has a direct path to FAQ Agent.
3. ~~**Triage answering FAQ questions directly**~~ ✓ Triage instructions say "CRITICAL: Never answer investment-related questions yourself."
4. ~~**Triage instructions missing company context**~~ ✓ Done
5. ~~**Remove stale UI comment**~~ ✓ Done
6. ~~**Triage routing — Scheduling trigger wording**~~ ✓ Done
7. ~~**Triage routing — broaden FAQ trigger**~~ ✓ Done
8. ~~**Audit and rewrite all agent instruction prompts**~~ ✓ Done
9. ~~**Audit handoff ordering rules**~~ ✓ Done — "REPLY BEFORE TRANSFERRING" rule in FAQ; confirmed in all agents.
10. ~~**Tool ownership per agent**~~ ✓ Done — `request_human_handoff` on all agents; tool assignments follow chosen orchestration.

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

**Missing infrastructure — testing & correction pipeline:**
Beyond fixing individual deviation bugs, the team needs a repeatable way to catch and correct regressions. Without this, every prompt fix is a guess with no feedback loop.

Questions to decide and build:
- How do we run a scripted conversation against the agent and assert on the output? (e.g. "given this message sequence, the agent must end up in onboarding step 2 and not deviate")
- Where do we log real conversations that went wrong so they become test cases?
- Who reviews flagged conversations and decides whether the fix is a prompt change, a tool change, or a knowledge base addition?
- Should we build a lightweight eval harness (scripted chat replay + expected behavior assertions) or use an existing framework?

---

### [X] Extend human handoff to all agents
**Location**: `agent/lucentive/agents.py`

`request_human_handoff` added to all four agents. `_load_handoff_skill()` injected into all agent instruction prompts.

---

### [X] Re-evaluate guardrails
**Location**: `agent/lucentive/guardrails.py` + `agents.py`

Relevance guardrail removed. Only Jailbreak guardrail remains — handles prompt injection and system override attempts. Off-topic and edge-case messages now route via dynamic handoff scenarios in the dashboard.

---

## Infrastructure

### [X] Improve error handling & logging for vector store sync
**Location**: `agent/knowledge/knowledge.py`

Polling, error handling, and logging all implemented: `_poll_vector_store_file` polls until `completed` or `failed` (with timeout); upload/attach wrapped in `try/except`; failures logged at ERROR level with full traceback.

---

### [X] FAQ agent — always run file_search before get_country_offers
**Location**: `agent/lucentive/agents.py` — `faq_instructions()`

Fixed. FAQ instructions now say: "Always call `file_search` first. If it returns a useful answer, use it. If it returns nothing relevant, call `get_country_offers` as a fallback."

---

### [X] Thread tracking — view past conversations & agent behavior

Full state (input_items, context, events, guardrails) is persisted to Supabase `threads` table on every message. Admin endpoints expose thread history, events, and corrections. Dashboard has a threads view.

---

### [ ] Update human handoff — assign to team, not a specific agent
**Location**: `agent/integrations/chatwoot.py` — `trigger_human_handoff()`

Currently the handoff assigns the conversation to agent ID 1 (a hardcoded specific agent). This should be changed to assign to a **Chatwoot team** instead, so any available human agent on the team can pick it up.

**Changes needed:**
- Replace the `assign_agent` API call (agent ID 1) with an `assign_team` API call using the appropriate team ID.
- Confirm which Chatwoot team ID to use (check Chatwoot settings → Teams).
- Optionally remove the hardcoded agent assignment entirely if team assignment is sufficient.

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
