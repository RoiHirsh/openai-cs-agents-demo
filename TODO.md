# Todo

---

## Agent Behavior

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

## Infrastructure

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
