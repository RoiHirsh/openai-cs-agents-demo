# Agent Architecture: Current vs Proposed

---

## Current Architecture (4 agents)

---

### 1. Triage Agent
**Role:** Entry point. Reads intent and routes to the right specialist. Never answers questions itself.

| | |
|---|---|
| **Entry point** | Yes — all conversations start here |
| **Model** | gpt-5.2 |

**Tools:**
- `update_lead_info` — persists lead corrections (e.g. country)
- `request_human_handoff` — can escalate to human

**Skills:**
- Handoff skill (dynamically enriched with handoff scenarios from KB)

**Handoff rules:**
- → Onboarding Agent: new lead + onboarding not complete, or user says "chat"
- → Scheduling Agent: user requests a call
- → Investments FAQ Agent: any information-seeking question
- Stays: message unclear and not a new lead
- After onboarding complete: routes to FAQ or Scheduling based on intent, no longer routes to Onboarding

**Human handoff:** Yes — has `request_human_handoff` tool

---

### 2. Investments FAQ Agent
**Role:** Answers investment and product questions using the knowledge base.

| | |
|---|---|
| **Entry point** | No |
| **Model** | gpt-5.2 |

**Tools:**
- `FileSearchTool` (vector store) — primary knowledge lookup
- `get_country_offers` — fallback for country/availability questions
- `request_human_handoff` — escalates to human if no tool returns a useful answer

**Skills:**
- Handoff skill

**Handoff rules:**
- → Triage Agent: after answering (step 3 of routine — unreliable in practice)
- → Scheduling Agent: if user requests a call mid-FAQ
- → Human: if neither file_search nor get_country_offers returns a useful answer

**Human handoff:** Yes — triggers if no tool can answer

---

### 3. Scheduling Agent
**Role:** Handles callback scheduling using Israel-time availability windows.

| | |
|---|---|
| **Entry point** | No |
| **Model** | gpt-5.2 |

**Tools:**
- `get_scheduling_context` — returns timezone-aware availability (offers, reasons, open/closed)
- `request_human_handoff` — can escalate to human

**Skills:**
- Scheduling skill
- Handoff skill

**Handoff rules:**
- → Triage Agent: after user accepts a callback
- → Triage Agent: if user declines call and wants to chat
- No explicit rule for product/FAQ questions (falls through to parametric knowledge)

**Human handoff:** Yes — has `request_human_handoff` tool

---

### 4. Onboarding Agent
**Role:** Guides new leads through the multi-step onboarding flow.

| | |
|---|---|
| **Entry point** | No — receives handoff from Triage |
| **Model** | gpt-5.2 |

**Tools:**
- `get_country_offers` — fetches available bots and brokers by country
- `get_broker_assets` — fetches registration links, copy-trade links, videos
- `update_lead_info` — persists lead corrections
- `update_onboarding_state` — persists onboarding step completion
- `request_human_handoff` — can escalate to human

**Skills:**
- Onboarding skill (phases 1–4, step-by-step flow)
- Product info skill (bot descriptions, comparison guideline)
- Handoff skill

**Handoff rules:**
- → Scheduling Agent: user requests a call
- → Investments FAQ Agent: user asks investment/product questions (overrides product_info skill in practice — known bug)
- → Triage Agent: when onboarding_complete=True
- → Human: via handoff skill scenarios

**Human handoff:** Yes — has `request_human_handoff` tool

---

### Current human handoff summary
All 4 agents have `request_human_handoff`. Any agent can escalate to human at any time. No single agent owns the escalation decision.

---

### Known knowledge boundary problems with current architecture
- Agents have no explicit rule preventing them from answering from parametric (model) knowledge
- When a tool or skill doesn't cover a question, agents fill the gap with their own general knowledge — giving answers that are unverified, sometimes wrong, and not approved by the business
- Examples seen in testing: Scheduling Agent invented "what's your main goal?" from parametric knowledge; FAQ Agent gave wrong MT5 credential flow from parametric knowledge; Onboarding Agent described Gold bot incorrectly before product_info skill was added
- There is no instruction telling any agent "if you don't have the answer from your tools or skills, say so or escalate — never invent"

---

### Known routing problems with current architecture
- Triage routes product questions to FAQ mid-onboarding, displacing Onboarding Agent
- FAQ doesn't reliably hand back to Triage after answering (step 3 is LLM-dependent)
- When FAQ gets control during onboarding, it runs its own generic flow with no onboarding state awareness
- Onboarding's product_info skill is overridden by the handoff priority rule ("hand to FAQ immediately for investment questions")
- Scheduling Agent has no rule for off-topic questions — falls through to parametric knowledge
- Human handoff can be triggered by any agent without checking what's already been tried

---
---

## Proposed Architecture (3 agents — Triage removed)

---

### 1. Onboarding Agent ← NEW: Master / Entry Point
**Role:** Permanent master of all conversations. Handles onboarding flow, answers product questions inline, owns all routing decisions, and is the only agent that can escalate to human.

| | |
|---|---|
| **Entry point** | Yes — replaces Triage as default starting agent in LucentiveServer |
| **Model** | gpt-5.2 |

**Tools:**
- `get_country_offers`
- `get_broker_assets`
- `update_lead_info`
- `update_onboarding_state`
- `request_human_handoff` ← only agent that retains this

**Skills:**
- Onboarding skill (phases 1–4) — updated: Phase 1 is small talk, no forced closing
- Product info skill — updated: answers bot/comparison questions inline, NEVER hands to FAQ for these
- Handoff skill — updated: new escalation chain logic

**Handoff rules:**
- → FAQ Agent: only for questions not covered by product_info skill or its tools. Expects control back.
- → Scheduling Agent: user requests a call. Expects control back.
- → Human: ONLY when all of the following are true: (1) Onboarding tried to answer and couldn't, (2) sent to FAQ and FAQ returned with no answer, (3) visible in conversation history. This is the last resort.

**Modes:**
- **Onboarding mode** (onboarding_complete=False): runs the full onboarding flow step by step
- **Post-onboarding mode** (onboarding_complete=True): lighter mode — routes FAQ and scheduling questions freely, no longer runs onboarding steps

**Human handoff:** Yes — sole owner of `request_human_handoff`

---

### 2. Investments FAQ Agent ← UPDATED: Subordinate, always returns to Onboarding
**Role:** Answers investment and product questions. Returns to Onboarding after every interaction without exception.

| | |
|---|---|
| **Entry point** | No |
| **Model** | gpt-5.2 |

**Tools:**
- `FileSearchTool` (vector store)
- `get_country_offers`
- `request_human_handoff` ← REMOVED (Onboarding owns escalation)

**Skills:**
- Handoff skill — updated: only one handoff target (Onboarding Agent)

**Handoff rules:**
- → Onboarding Agent: always, after every response — whether it found an answer or not
- Never hands to human directly
- Never hands to Scheduling directly

**Human handoff:** No — removed. If FAQ can't answer, it returns to Onboarding which then decides whether to escalate.

---

### 3. Scheduling Agent ← UPDATED: Subordinate, always returns to Onboarding
**Role:** Handles callback scheduling. Returns to Onboarding after every interaction without exception.

| | |
|---|---|
| **Entry point** | No |
| **Model** | gpt-5.2 |

**Tools:**
- `get_scheduling_context`
- `request_human_handoff` ← REMOVED (Onboarding owns escalation)

**Skills:**
- Scheduling skill
- Handoff skill — updated: only one handoff target (Onboarding Agent)

**Handoff rules:**
- → Onboarding Agent: always — after call accepted, after call declined, after any scheduling outcome
- Never hands to human directly
- Never hands to FAQ directly

**Human handoff:** No — removed.

---

### Knowledge boundary rule (applies to all 3 agents)
Every agent must only answer from its assigned sources — skills, tools, and KB. Never from parametric (model) knowledge.

| Agent | Approved knowledge sources |
|---|---|
| Onboarding | Onboarding skill, product_info skill, `get_country_offers`, `get_broker_assets`, `update_onboarding_state`, `update_lead_info` |
| FAQ | Vector store via `FileSearchTool`, `get_country_offers` |
| Scheduling | `get_scheduling_context` output only |

If a question is not covered by the agent's approved sources → do not answer from general knowledge. Either hand off to the agent that can answer, or (Onboarding only, as last resort) escalate to human.

This rule must be added explicitly to `PLAIN_TEXT_RULE` so it applies to all agents automatically.

---

### Proposed human handoff summary
Only Onboarding Agent has `request_human_handoff`. Escalation to human follows a defined chain:

```
Onboarding tries (product_info skill + tools)
    ↓ can't answer
FAQ Agent tries (file_search + get_country_offers)
    ↓ can't answer → returns to Onboarding
Onboarding detects prior FAQ attempt in history
    ↓
Human handoff (request_human_handoff)
```

For handoff scenarios defined in the handoff skill (e.g. proof of results, available now), Onboarding triggers human handoff directly without the FAQ loop.

---

### Removed
- **Triage Agent** — fully removed. Entry point, routing logic, and `update_lead_info` absorbed by Onboarding Agent.

---

### Changes required to implement
| What | Where |
|---|---|
| Add knowledge boundary rule to `PLAIN_TEXT_RULE`: never answer from parametric knowledge — only from assigned skills/tools/KB | `agents.py` |
| Change default starting agent from `triage_agent` to `onboarding_agent` | `agent/main.py` or `LucentiveServer` |
| Remove `request_human_handoff` from FAQ Agent tools | `agents.py` |
| Remove `request_human_handoff` from Scheduling Agent tools | `agents.py` |
| Update FAQ Agent handoff instructions: always return to Onboarding | `agents.py` — faq_instructions |
| Update Scheduling Agent handoff instructions: always return to Onboarding | `agents.py` — scheduling_instructions |
| Update Onboarding handoff priority: answer product questions inline, only send to FAQ if product_info skill doesn't cover it | `skills/onboarding/SKILL.md` |
| Add escalation chain logic to Onboarding: if FAQ returned with no answer → human handoff | `skills/onboarding/SKILL.md` or `agents.py` |
| Add post-onboarding mode to Onboarding Agent instructions | `agents.py` — onboarding_instructions |
| Remove Triage Agent definition and all references | `agents.py`, `main.py` |
