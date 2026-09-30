# Conversation engine — state, authority & write-path rules

**Authoritative** for the multi-bot conversation engine. Must stay consistent with
[`AGENTS.md`](../../AGENTS.md) and [`current-architecture.md`](../current-architecture.md).
Read this before changing routing, patch permissions, thresholds, evidence rules, or
commit behavior.

## Two memory stores

### Store A — UserProfile (authoritative, structured)
Pydantic-validated fields used for generation, scheduling, and protocol logic:
`PromptAnchor`, `PreferredTime`, `HabitDomain`, `MotivationalFrame`, `Intensity`, tone
tags/scores, and rolling coaching fields (`LastBarrier`, `LastTweak`, `LastMotivator`,
`LastSuccessfulPrompt`). Hard to corrupt; updated only through the Router's single
writer path.

### Store B — Memory (long-term narrative, semi-structured)
Session summaries and durable facts that do not fit the profile schema (e.g. "prefers
gentle accountability", "recurring barrier is evening fatigue"). More vulnerable to
drift/injection. Stored as a list of items with timestamps and pointers to source
message ids. Conservative updates only, anchored to user statements and repeated
patterns — prefer "what the user said" over inferred traits.

## Authority model (single writer)
The **Router is the only component allowed to commit writes** to either store.
Specialist bots never write directly — they only propose patches.

### Patch proposal mechanism
Specialists propose candidates through internal, non-user-visible channels:
`propose_profile_patch`, `propose_memory_patch` (see
[`api/app/tools/proposal_tools.py`](../../api/app/tools/proposal_tools.py)).

The Router validates deterministically before committing:
- Pydantic schema validation
- Field-level permissions by module (matrix below)
- Confidence thresholds
- Evidence spans must reference the current/recent user message — never retrieved materials
- If a patch changes a stable preference, optionally require explicit user confirmation next turn

After validation the Router commits via the only writer path: `apply_profile_patch`,
`apply_memory_patch`.

### Practical safety rules
1. **Only Intake** sets/changes required onboarding fields (`PromptAnchor`,
   `PreferredTime`) — or an explicit user request routed into an Intake-like flow.
2. **Only Feedback** writes behavior outcomes (adherence/measured feedback), and only
   inside the feedback protocol — never from free chat.
3. **Memory writes are conservative**: short, quote-like items with timestamps and
   source message-id pointers; avoid inferred traits.

### Disagreement resolution & audit
When proposals conflict, Feedback-derived updates outrank Coach-derived proposals.
Maintain an audit trail (`PatchAuditLog`) of proposed patches and commit decisions.

## Module responsibilities

| Module | May propose | Never does |
|--------|-------------|------------|
| **Router** | n/a — owns the only commit path; enforces permissions, validation, thresholds, evidence | Produce coaching content unless explicitly a visible system response; delegate user-facing replies to specialists |
| **Intake** | Onboarding fields (`PromptAnchor`, `PreferredTime`, `HabitDomain`, `MotivationalFrame`, scheduling prefs); optional initial Memory summary | Write to either store directly |
| **Feedback** | `LastBarrier`, `LastTweak`, `LastSuccessfulPrompt`, `LastMotivator`; intensity/tone adjustments; Memory updates from stable repeated patterns | Write to either store directly |
| **Coach** | Candidate items only (memory/profile candidates) — Router decides commit/ignore/confirm | Write to either store; set onboarding or outcome fields |

The permission matrix is enforced by the Router validator. Code:
`INTAKE_ALLOWED_FIELDS`, `FEEDBACK_ALLOWED_FIELDS`, `COACH_ALLOWED_FIELDS` in
[`api/app/schemas/patches.py`](../../api/app/schemas/patches.py).

## When you change engine behavior
Any change to patch permissions, thresholds, evidence rules, routing logic, or commit
behavior **must** update this doc, add/update tests, and document migration implications.
All bot logic uses LangChain primitives (agents, tools, structured outputs) — do not
hand-roll tool-call parsing or agent loops.
