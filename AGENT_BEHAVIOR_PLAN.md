# Agent Behavior Control — Research & Plan

## What the community calls what we're experiencing

The academic term is **agent drift** — specifically two subtypes visible in production:

- **Semantic drift**: agent falls back on its own parametric knowledge instead of the knowledge base/tools
- **Behavioral drift**: tone shifts, unsolicited long responses, breaking out of step-following flows

The root cause is well understood: **context window recency bias** — as conversation history grows, the system prompt loses statistical weight. The model starts treating rules as suggestions, not constraints.

---

## The solution architecture — four layers

### Layer 1 — What we already have
Input guardrails (jailbreak detection). Keep it.

### Layer 2 — What we're missing: Tool-level enforcement
Instead of telling the agent "call `update_onboarding_state` after each step," intercept tool calls in the framework and reject out-of-sequence calls. The AWS community calls this "rules LLMs cannot bypass." The OpenAI Agents SDK supports `BeforeToolCall` hooks for this. Enforces step-following behavior architecturally, not via prompt suggestion.

### Layer 3 — Output guardrails (LLM-as-a-Judge)
A second LLM call (or rule-based check) that reviews the response before it reaches the user. Checks:
- Response length within bounds
- Did it use parametric knowledge instead of tools?
- Is it in plain text (no markdown)?
- Is the tone correct?

This is called **LLM-as-a-Judge** or the **Evaluator-Optimizer** pattern (Anthropic's term for the two-LLM loop where one generates, one evaluates).

### Layer 4 — Behavioral anchoring
Re-inject a compressed version of the behavioral rules at every reconstructed turn — not just at session start. This counteracts recency bias. The `PLAIN_TEXT_RULE` constant already injected into every agent prompt is a version of this. The community calls this **archetypal anchoring**.

---

## The Prompt Registry pattern — directly applicable to our dashboard

The community has converged on this pattern:

> Prompts are fetched from a database at runtime, not hardcoded. Changing behavior is a data operation, not a code deployment.

**We already have this partially built.** The Markdown skill files (`skills/scheduling/SKILL.md`, etc.) are loaded at runtime from disk — that is the right architecture. The next step is moving them into Supabase so they can be edited from the dashboard, the same way FAQ pairs, handoff scenarios, broker assets, and country offers are already managed.

That makes the dashboard the **single control panel** for all agent behavior:

| Data | Currently in Supabase? |
|---|---|
| FAQ knowledge (qa_pairs) | ✓ Yes |
| Handoff scenarios | ✓ Yes |
| Country/broker data | ✓ Yes |
| Agent skills (scheduling, onboarding, handoff SKILL.md files) | ✗ Hardcoded on disk |
| Agent personas / tone rules | ✗ Hardcoded in agents.py |

---

## The production feedback loop

When bad behavior is observed in production:

1. **Trace it** — every tool call, decision, and response is logged (events system partially covers this)
2. **Flag it** — the corrections table is already this; someone marks a bad response
3. **Fix it** — update the relevant skill or rule in the dashboard (no redeploy needed)
4. **Test it** — run a scripted replay of the failing conversation against the new version
5. **Promote it** — if it passes, it goes live; the failure case becomes a permanent regression test

---

## Recommended implementation order

### Phase 1 — Move skill files to Supabase (highest impact, enables dashboard control)

**What:** Replace `skills/scheduling/SKILL.md`, `skills/onboarding/SKILL.md`, `skills/handoff/SKILL.md` on disk with rows in a `agent_skills` Supabase table. `_load_scheduling_skill()`, `_load_onboarding_skill()`, and `_load_handoff_skill()` fetch from the database instead of the filesystem. Add a "Skills" section to the dashboard for editing.

**Why:** This closes the most important gap — you see drift, identify which skill caused it, update it in the dashboard, and it is live on the next request. No code change, no redeploy.

**Schema:**
```
agent_skills (
  id uuid,
  skill_name text unique,   -- e.g. "scheduling", "onboarding", "handoff"
  content text,             -- full markdown content
  version int,
  updated_at timestamptz,
  updated_by text
)
```

### Phase 2 — Add output guardrail (LLM-as-a-Judge)

**What:** After each agent response, run a lightweight evaluator that checks:
- Response is plain text (no markdown symbols)
- Response length is within acceptable bounds
- Response does not contain phrases that suggest parametric knowledge usage ("based on my knowledge", "generally speaking", "I believe", etc.)

If the evaluator flags the response, either block it and retry or log it for review.

**Why:** Catches behavioral drift before it reaches the user.

### Phase 3 — Tool-level sequence enforcement

**What:** Add `BeforeToolCall` hooks to the onboarding flow that enforce correct step ordering. For example: `update_onboarding_state(step_name="broker_selection")` cannot be called unless `bot_recommendation` is already in `completed_steps`.

**Why:** Makes step-following a hard architectural constraint rather than a prompt suggestion. The model cannot skip steps even if the user sends unexpected input.

### Phase 4 — Scripted eval harness

**What:** A test runner that replays scripted conversation sequences against the live agent and asserts on the output state. For example: "given these 6 messages, the agent must reach onboarding step `budget_check` and `bot_preference` must be set."

**Why:** Every production failure that gets corrected becomes a regression test. Prompt changes can be validated before going live.

---

## Key terms and references

| Term | Meaning |
|---|---|
| Agent drift | Progressive behavioral degradation over extended interactions |
| Semantic drift | Agent deviates from intended knowledge source |
| Behavioral drift | Tone shifts, unsolicited responses, broken step-following |
| Archetypal anchoring | Re-injecting behavioral identity at session start/resumption to reduce drift |
| Prompt registry | External store for prompts, decoupled from code, enabling runtime updates |
| Prompt as Code | Treating prompts as versioned, tested, deployed artifacts |
| LLM-as-a-Judge | Using a second LLM call to evaluate the first LLM's output |
| Evaluator-Optimizer | Anthropic's name for the two-LLM generate/evaluate loop |
| Colang / NeMo Guardrails | NVIDIA's DSL + runtime for behavioral constraint programming (model-agnostic) |
| Defense-in-depth | No single guardrail layer is sufficient; overlapping layers are required |
| Poka-yoke | Anthropic's term for designing tool interfaces to make agent errors structurally impossible |

**Sources:**
- [Agent Drift: Quantifying Behavioral Degradation in Multi-Agent LLM Systems](https://arxiv.org/abs/2601.04170)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Equipping Agents for the Real World with Agent Skills — Anthropic](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [AI Agent Guardrails: Rules That LLMs Cannot Bypass — AWS](https://dev.to/aws/ai-agent-guardrails-rules-that-llms-cannot-bypass-596d)
- [NeMo Guardrails — NVIDIA](https://github.com/NVIDIA-NeMo/Guardrails)
- [A Practical Guide to Building AI Agents — OpenAI](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)
- [Preventing AI Agent Drift — Maxim AI](https://www.getmaxim.ai/articles/a-comprehensive-guide-to-preventing-ai-agent-drift-over-time/)
- [How Prompt Updates Drive Most Incidents — Deepchecks](https://deepchecks.com/llm-production-challenges-prompt-update-incidents/)
