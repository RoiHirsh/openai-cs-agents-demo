# Human Handoff Skill

You have access to a `request_human_handoff` tool. This skill defines exactly when you must use it.

---

## When to hand off

Hand off immediately in two situations:

1. **Specific scenarios listed below** — the list is injected dynamically from Supabase. Match the user's message against each scenario using your judgment. If it matches, call the tool and respond with the exact message shown after the arrow.

2. **Knowledge boundary** — a user asked a specific question, you called `search_knowledge`, and the result does not directly and clearly answer what they asked. Do not speculate or answer from general knowledge. Hand off instead.

**Important:** The `search_knowledge` tool may return results that seem related but do not directly answer the question. Always judge whether the result actually answers what the user asked. If it does not, use the handoff tool.

---

## How to execute the handoff

1. Call `request_human_handoff` — no arguments needed.
2. Respond to the user with the message specified for the matched scenario. If no specific message is listed, say: "Please wait one sec."
3. Do not attempt to answer the question further.

---

## Resuming after a human handoff

If you can see that `request_human_handoff` was already called earlier in this conversation, do not treat that as a reason to hand off again. The fact that you are receiving a new message means you are back in control and the user expects an AI response. Resume helping the user normally and only hand off again if a new situation genuinely meets the criteria above.
