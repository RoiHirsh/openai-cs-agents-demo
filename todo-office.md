# Todo

## [ ] Agent orchestration audit & cleanup

**Location**: `agent/airline/agents.py`

**Overview**: Review and fix the agent handoff graph — instructions, routing rules, and handoff permissions across all four agents.

**Known bug — FAQ agent transfers before replying:**
The FAQ agent is instructed to: run file_search → reply to user → then hand back to Triage. But in practice the model sometimes calls `transfer_to_triage_agent` immediately after file_search without sending a response first. Triage then wakes up and answers from conversation history instead of the knowledge base. This is a prompt compliance issue — investigate whether the instruction needs to be made harder to violate (e.g. stricter ordering language, or splitting into two turns).

**Questions to decide and implement:**

1. **Should all specialists always return to Triage after finishing?**
   Currently: FAQ → Triage or Onboarding. Scheduling → Triage or Onboarding. Onboarding → Triage, Scheduling, or FAQ. Decide whether Triage should always be the hub that all agents return to, or whether direct specialist-to-specialist handoffs are acceptable (and if so, which ones make sense).

2. **Why can Scheduling not transfer to FAQ?**
   If a user asks a question mid-scheduling flow, Scheduling has no way to route to FAQ — it can only go to Triage or Onboarding. Decide if this is intentional or a gap.

3. **Triage answering directly without file_search:**
   Because all agents see the full conversation history, Triage can construct plausible-sounding answers to FAQ-type questions from context + model training data — with no knowledge base grounding. Decide whether Triage should be explicitly forbidden from answering FAQ-type questions directly (force it to always route to FAQ agent instead).

4. **Audit all agent instructions for handoff ordering rules:**
   Ensure every agent that is supposed to reply before handing off has clear, unambiguous language that the model consistently follows.

---

## [ ] Agent flow resilience — keep agents on track when users deviate

**Location**: `agent/airline/agents.py` + individual agent instruction prompts

**Problem**: The agent flow works correctly only when users respond in the exact format the agent expects (e.g. simple answers like "yes", "no", "gold", "forex"). As soon as a user deviates — sending one word at a time across multiple messages, asking an off-topic question mid-flow, or going off-script during onboarding or scheduling — the active agent loses its place and doesn't return to its original purpose.

**Examples of deviation patterns to handle**:
- User sends fragmented input across multiple messages ("gold" → then "actually" → then "forex") instead of one complete answer
- User asks a question mid-onboarding ("wait, what is forex?") — agent gets derailed into FAQ territory without ever completing onboarding
- User asks a question mid-scheduling — agent either answers directly (without file_search grounding) or hands off but never resumes scheduling
- Any unexpected input causes the agent to treat the conversation as resolved and fall back to generic responses

**Questions to decide and implement**:

1. **State persistence within a flow** — should onboarding and scheduling agents track which step they were on so they can resume after an interruption (e.g. a mid-flow FAQ question)?

2. **Interruption handling** — if a user asks an off-topic question mid-flow, should the agent: (a) answer briefly and immediately return to the flow, (b) hand off to the right specialist and instruct it to return, or (c) refuse to deviate and ask the user to complete the current step first?

3. **Input tolerance** — should agents be more tolerant of fragmented or ambiguous input, e.g. accumulating partial answers before deciding the user has completed a step?

4. **Explicit "resume" instructions** — every agent that runs a multi-step flow should have explicit prompt language instructing it to re-ask the current step if the user's response is off-topic or incomplete, rather than accepting anything as a valid answer.

---

## [ ] Extend human handoff tool to all agents

**Location**: `agent/airline/agents.py`

**Problem**: Currently only Triage and FAQ agents have access to the `request_human_handoff` tool and the handoff skill injected into their instructions. Scheduling and Onboarding agents have neither — so if a user asks to speak to a human mid-flow, those agents can't trigger the handoff directly and must first return to Triage.

**Decision needed**: Should all four agents have access to `request_human_handoff` and the handoff skill? The assumption is yes — a user can ask to speak to a human at any point in any flow and the active agent should be able to handle it immediately without an unnecessary Triage detour.

**If yes, implement**:
- Add `request_human_handoff` to the tools list of Scheduling and Onboarding agents
- Inject `_load_handoff_skill()` into their instruction prompts the same way it's done for Triage and FAQ

---

## [ ] Remove `/manager` slash command

**Location**: Find all references to the `/manager` command in the codebase (frontend + backend)

**Context**: `/manager` was added as a manual testing shortcut to simulate a human handoff scenario. Now that dynamic handoff triggers are being configured via the dashboard and working correctly, this hardcoded command should be evaluated for removal.

**Decision needed**: Confirm that dynamic handoff scenarios fully cover the `/manager` use case before removing, then delete the command handling from both the frontend (dashboard/UI) and backend (agent server).

---

## [ ] Improve error handling & logging for vector store sync (`knowledge.py`)

**Location**: `agent/knowledge.py` — `_sync_qa_vector_store()` (lines 51-99)

**Problem**: The sync that runs after every QA pair create/update/delete has three gaps:

1. **Upload/attach has no error handling** — lines 94-98 are unwrapped. Any failure (network, OpenAI outage, quota) bubbles up as an uncontextualized 500 with no log entry.

2. **No polling for `completed` status** — `vector_stores.files.create()` returns while the file is still `in_progress`. The code logs "synced" prematurely. If the agent queries the vector store before indexing finishes, the new question is not yet searchable (confirmed timing issue).

3. **Sync failures are invisible to the dashboard** — if sync fails, the dashboard still receives `201 Created` because Supabase insert succeeded. The user has no indication the vector store is out of sync.

**Proposed changes**:
- Wrap the upload + attach (lines 92-99) in a `try/except`, log `ERROR` on failure with full exception detail
- After `vector_stores.files.create()`, poll the file status until `completed` or `failed` (with a timeout), then log accordingly
- Return `207 Multi-Status` with `{"saved": true, "synced": false, "sync_error": "..."}` when sync fails so the dashboard can surface it to the user

---

## [ ] Re-evaluate whether guardrails are needed

**Location**: `agent/airline/guardrails.py` + all agent definitions in `agents.py`

**Context**: All four agents currently have `relevance_guardrail` and `jailbreak_guardrail` applied as `input_guardrails`. These guardrails respond to off-topic or adversarial input with a bot-like rejection message (e.g. "I can only help with X" or "I can't help with that").

**The conflict**: The entire product premise is that the AI agent appears human. The design principle is: either answer confidently as a human would, or silently hand off to a real human in the background. A guardrail response breaks this illusion — it reads unmistakably as a bot and undermines trust.

**The argument for removing/replacing guardrails**:
- Jailbreak attempts and off-topic messages are exactly the cases where a human handoff is the right answer anyway
- A handoff response ("Please wait one sec") is indistinguishable from a human saying "let me get someone for you" — a guardrail response is not
- With dynamic handoff scenarios in place, any edge case can be caught and routed to a human gracefully

**Questions to decide**:
1. Can the jailbreak and relevance guardrails be fully replaced by handoff triggers (either dynamic Supabase scenarios or a catch-all rule in the agent instructions)?
2. If guardrails are kept, can their responses be rewritten to sound human rather than bot-like?
3. Are there cases where a guardrail is genuinely needed over a handoff (e.g. rate limiting, abuse prevention at infrastructure level)?
4. of course we do need guardrails against prompt injection and those saftey cases!
