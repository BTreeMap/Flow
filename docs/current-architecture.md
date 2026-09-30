# Current Architecture: Multi-Bot Conversation Engine

> **Status:** Authoritative. This document describes the active conversation engine architecture.

---

## Overview

The conversation engine uses a **Router + specialist** architecture built on LangChain primitives (agents, tools, structured outputs) with Pydantic for type safety.

### Key Principles

1. **Single Writer**: The Router is the only component that commits to stores.
2. **Proposal-based**: Specialist bots propose patches; Router validates and commits.
3. **Two distinct stores**: Structured profile (Store A) and semi-structured memory (Store B).
4. **LangChain-native**: All bot logic uses LangChain agents, tools, and structured outputs.

---

## Store A: UserProfile (Structured)

Schema-validated fields used for generation, scheduling, and protocol logic.

| Field | Description | Set By |
|-------|-------------|--------|
| `prompt_anchor` | Habit anchor cue | Intake |
| `preferred_time` | Preferred prompt time | Intake |
| `habit_domain` | Habit category | Intake |
| `motivational_frame` | Motivational framing | Intake |
| `intensity` | Prompt intensity level | Feedback |
| `last_barrier` | Last barrier encountered | Feedback |
| `last_tweak` | Last adjustment made | Feedback |
| `last_successful_prompt` | Last working prompt | Feedback |
| `last_motivator` | Last motivator noted | Feedback |
| `tone_tags` / `tone_scores` | Tone preferences | Feedback |
| `total_prompts` / `success_count` | Counters | System |

**Properties:**
- Pydantic validated (`UserProfileData` schema)
- Persisted in `user_profiles` table as JSON
- Only updated through Router commit path

## Store B: Memory (Semi-Structured)

Session summaries and durable facts that don't fit in the profile schema.

**Examples:**
- "Prefers gentle accountability and short messages"
- "Recurring barrier is evening fatigue"
- "Travels on weekends, misses prompts"

**Properties:**
- Stored as individual items in `memory_items` table
- Each item has: content, timestamp, source message IDs, optional tags
- Conservative writes only (max 500 chars per item)
- Anchored to user statements and repeated patterns

---

## Router: Single Writer Authority

The Router owns the final commit to both stores. It:

1. **Routes** each turn to the appropriate specialist (INTAKE, FEEDBACK, or COACH)
2. **Validates** all patch proposals deterministically
3. **Commits** approved patches to the stores
4. **Logs** all proposals and decisions to the audit trail

### Routing Policy

| Condition | Route |
|-----------|-------|
| Required onboarding fields missing | INTAKE |
| Currently in feedback protocol | FEEDBACK |
| Profile complete, normal conversation | COACH |

### Deterministic Validation

Before committing any patch, the Router checks:

1. **Schema validation** — Pydantic validates the patch against `UserProfileData`
2. **Field-level permissions** — enforced by the permission matrix
3. **Confidence thresholds** — INTAKE/FEEDBACK ≥ 0.5, COACH ≥ 0.8
4. **Evidence spans** — must reference recent message IDs, not retrieved materials
5. **Conservative memory rules** — items ≤ 500 chars with source pointers

---

## Permission Matrix

| Bot | Profile Fields Allowed | Memory Write |
|-----|----------------------|--------------|
| **Intake** | `prompt_anchor`, `preferred_time`, `habit_domain`, `motivational_frame` | Yes (initial summary) |
| **Feedback** | `last_barrier`, `last_tweak`, `last_successful_prompt`, `last_motivator`, `intensity`, `tone_tags`, `tone_scores` | Yes (stable patterns) |
| **Coach** | None (candidate proposals only) | No |

---

## Proposal → Commit Flow

```
User Message
    │
    ▼
┌─────────┐
│  Router  │── route_turn_deterministic() or route_turn_llm()
└────┬────┘
     │
     ▼
┌──────────────┐
│  Specialist   │  (Intake / Feedback / Coach)
│  Agent        │  Uses LangChain agent with proposal tools only
│               │  Can call propose_profile_patch / propose_memory_patch
└──────┬───────┘
       │ proposals
       ▼
┌─────────────────┐
│  Router          │
│  Validator       │  validate_profile_patch() / validate_memory_patch()
│                  │  Check: permissions, confidence, evidence
└──────┬──────────┘
       │ approved
       ▼
┌─────────────────┐
│  Commit Path     │  save_user_profile() / add_memory_item()
│  + Audit Log     │  log_patch_audit() records decision
└─────────────────┘
```

---

## Specialist Bots

### Intake Bot
- Handles onboarding and profile setup
- Proposes updates to onboarding fields (PromptAnchor, PreferredTime, etc.)
- May propose initial memory summary after intake completion

### Feedback Bot
- Handles habit tracking and barrier analysis
- Proposes updates to rolling coaching fields
- May propose memory updates for stable patterns

### Coach Bot
- Handles normal conversation and encouragement
- Can only propose candidates with low authority
- Router applies higher confidence threshold (0.8)

---

## Prompt System

All prompts are loaded from `api/prompts/*.txt` files via `app.prompt_loader`:

| File | Used By |
|------|---------|
| `router_system.txt` | Router (structured output routing) |
| `intake_system.txt` | Intake specialist agent |
| `feedback_system.txt` | Feedback specialist agent |
| `coach_system.txt` | Coach specialist agent |
| `prompt_generator_system.txt` | Scheduled habit prompt generation |

### Prompt Versioning

Each assistant message SSE event includes a `prompt_versions` field with:
- `prompt_file`: name of the prompt file used by the specialist
- `prompt_sha256`: SHA-256 hash of the prompt content at time of generation

This enables tracking which prompt version produced each response, supporting A/B testing and prompt quality analysis.

---

## Audit Trail

All proposals are logged in the `patch_audit_log` table:

| Column | Description |
|--------|-------------|
| `proposal_type` | "profile" or "memory" |
| `source_bot` | "INTAKE", "FEEDBACK", or "COACH" |
| `patch_json` | The proposed patch payload |
| `confidence` | Proposal confidence (0-1) |
| `evidence_json` | Evidence spans with message IDs |
| `decision` | "committed" or "ignored: {reason}" |
| `committed_at` | Timestamp if committed |

---

## Data Model

| Table | Purpose |
|-------|---------|
| `user_profiles` | Store A — structured profile JSON (1:1 with membership) |
| `memory_items` | Store B — individual memory items per membership |
| `patch_audit_log` | Audit trail for all proposals and decisions |
| `conversations` / `messages` | Chat history (1:1 conversation per membership) |
| `conversation_runtime_state` | Runtime state for conversation protocol (JSON) |
| `conversation_events` | Persisted SSE events for durable replay |
| `conversation_turns` | Idempotent messaging dedupe (`client_msg_id`) |
| `participations` | One row per participant in a study (carries `study_start_date`) |
| `daily_intervention_logs` | Per-day telemetry per participation |
| `daily_summaries` | EOD sterilized cross-day memory (see below) |
| `scheduled_tasks` | Durable scheduled work with lease + dedupe keys |
| `notifications` / `notification_rules` / `notification_rule_state` / `notification_deliveries` | Notification engine state + delivery audit |

---

## Alembic Migrations

Flow uses its own Alembic environment separate from h4ckath0n:

- **Migration directory:** `api/app/db_migrations/`
- **Version table:** `flow_alembic_version`
- **Runner:** `api/app/db_migrations/migrate.py` (`upgrade_to_head()`, `stamp_head()`)
- **Startup:** The lifespan runs `upgrade_to_head()` with `init_db()` fallback for test environments.
- **URL normalization:** Async driver prefixes (`sqlite+aiosqlite`, `postgresql+asyncpg`) are converted to sync equivalents for Alembic.

---

## Durable SSE with Replay

The `/p/{project_id}/events` SSE endpoint supports durable replay:

1. Events are persisted to `conversation_events` before being published to in-memory queues.
2. If a client reconnects with `Last-Event-ID` header, missed events are replayed from the database before switching to live streaming.
3. Cross-process delivery uses DB polling (no Redis dependency).

---

## Idempotent Messaging

`POST /p/{project_id}/messages` supports idempotent retries:

1. If `client_msg_id` is provided, the endpoint checks `conversation_turns` for an existing turn.
2. If found, the existing assistant message is returned without re-processing.
3. If not found, a new turn entry is created with `Unique(conversation_id, client_msg_id)`.

---

## Notification Worker

Scheduled nudges and notifications are driven by two cooperating components:

- `app/services/notification_engine.py` — inserts `scheduled_tasks` rows with idempotent dedupe keys and 5-minute leases (`locked_until`, `locked_by`, `claimed_at`); handles retry with exponential backoff and dead-letter after max attempts.
- `app/worker/notification_worker.py` — claims due tasks, generates the nudge (static template for A/B, LLM with regex-gated regen for C, framed LLM for D), persists the assistant `Message` with `condition_source` tagging, then attempts Web Push delivery.

**Push delivery is best-effort.** Push failures or timeouts after the message is persisted are logged per-subscription but do **not** retry the scheduled task. This prevents duplicate messages when push transport fails after the message has already been written.

---

## Key Code Entrypoints

| File | Purpose |
|------|---------|
| `api/app/agents/engine.py` | Main turn engine: `process_turn()` |
| `api/app/agents/intake.py` | Intake specialist agent |
| `api/app/agents/feedback.py` | Feedback specialist agent |
| `api/app/agents/coach.py` | Coach specialist agent (incl. Condition-C regex rewrite) |
| `api/app/agents/runner.py` | Agent runner (LangChain invoke wrapper + tool trace) |
| `api/app/agents/tool_trace.py` | Tool call tracing callback |
| `api/app/tools/proposal_tools.py` | Proposal tools + ProposalCollector |
| `api/app/tools/scheduler_tools.py` | Scheduling LangChain tools |
| `api/app/prompt_loader.py` | Prompt file loader with caching and versioning |
| `api/app/services/profile_service.py` | Profile/memory persistence + validation |
| `api/app/services/event_service.py` | SSE event persistence and replay |
| `api/app/services/notification_engine.py` | Scheduled-task scheduling, lease, retry, push delivery |
| `api/app/worker/notification_worker.py` | Worker loop: claims tasks, generates nudges, persists, pushes |
| `api/app/schemas/patches.py` | Pydantic schemas for proposals |
| `api/app/schemas/router.py` | RouteDecision schema |
| `api/app/db_migrations/migrate.py` | Alembic migration runner |

---

## 4-Condition Randomized Block Experiment

The platform supports a four-condition microcoaching study (codenamed
`microcoach_v1`). Conditions vary the prompt-generation source and the
psychological framing applied to nudges:

| Code | Prompt source | Framing | Feedback path |
|------|---------------|---------|---------------|
| **A** | Static template (`api/config/interventions.json` → `condition_A`) | None | Deterministic script, no LLM, no profile/memory writes |
| **B** | Static template (`condition_B`) | Implementation Intention + Commitment Contract | Deterministic script, no LLM, no profile/memory writes |
| **C** | LLM (`prompts/prompt_generator_condition_c.txt`) | **Strictly forbidden** (regex-gated post-filter + regen) | LLM (`feedback_system.txt`) with profile/memory adaptation |
| **D** | LLM (`prompts/prompt_generator_condition_d.txt`) | Required (If/Then + Commitment in every nudge) | LLM (`feedback_system.txt`) with profile/memory adaptation |

### Assignment

Every participant is enrolled in a `Participation` row when they pass the
INTAKE phase. The daily condition is computed deterministically by
`app/services/randomization.py::get_daily_condition()` using BLAKE3 keyed mode
over `(participation_id, block_index)` with a BLAKE3-derived randomization
subkey to pick a Latin square from the 24 possible 4-day permutations. This
guarantees:

- balanced exposure (every block uses each condition exactly once),
- reproducible audit (the same inputs always produce the same assignment),
- independence between participants.

`FLOW_CRYPTO_MASTER_KEY` must be an unpadded Base64URL encoding of exactly 32
random bytes. `app.services.crypto` derives the dedicated randomization subkey
in BLAKE3's dedicated derive-key mode; the master secret is never used directly.

Static A/B template selection is separate from condition assignment. It uses an
unkeyed BLAKE3 content hash over `(participation_id, day_index, static_nudge)`
to choose a reproducible template and is not a security boundary.

### Master-key rotation

The current master key is applied to every existing and new `Participation`
when its condition is resolved. Changing the master key therefore changes the
deterministic assignment for future days; existing `DailyInterventionLog` rows
retain the previously delivered conditions for analysis. Keep a stable key for
the duration of a study unless a deliberate reassignment is intended.

### Anti-contamination guardrails

The dominant validity threat is the LLM in Condition C implicitly mimicking
the framing it produced under Conditions B / D. Three independent
guardrails protect against this:

1. **Condition-source tagging.** Every assistant `Message` and every
   nudge created by the worker is tagged with `condition_source`
   (`COND_A` / `COND_B` / `COND_C` / `COND_D` / `SYSTEM`).
2. **History filtering.** When the engine assembles chat history for a
   Condition C turn it (a) drops any message whose `condition_source` is
   `COND_B` or `COND_D`, and (b) restricts the window to the trailing 24
   hours. See `CONDITION_C_EXCLUDED_SOURCES` and the `timedelta(hours=24)`
   filter in `app/agents/engine.py::process_turn`.
3. **Regex framing filter.** Both the Coach turn path
   (`app/agents/coach.py`) and the worker nudge path
   (`app/worker/notification_worker.py::_generate_condition_nudge`) run
   Condition C output through
   `app/services/condition_filters.py::contains_condition_c_framing`. On
   match the prompt is regenerated up to three times with an explicit
   "remove the framing" instruction; if the model still drifts, the worker
   falls back to a safe neutral string (`CONDITION_C_SAFE_FALLBACK`) and
   the Coach returns its last attempt while logging the failure.

### Static-feedback bypass for A / B

The research design forbids any LLM intervention on the feedback path for
the two control conditions (otherwise the dynamic user model would
silently adapt and confound the comparison). The engine therefore short-
circuits the FEEDBACK route under conditions A and B and calls
`app/services/feedback_script.py::run_static_feedback` instead of the
`run_feedback` LangChain agent. The script:

- asks one fixed question at a time (attempt → yes/no follow-up → close),
- stores raw answers in `DailyInterventionLog.extracted_state["script"]`
  for observational analysis,
- **never** emits a `propose_profile_patch` or `propose_memory_patch`.

The turn is tagged `RouteDecision(route="STATIC_FEEDBACK", ...)`. The
`STATIC_TEMPLATE` and `STATIC_FEEDBACK` route literals are engine-internal
markers — the Router LLM is post-validated and is **never** allowed to
emit them (see `route_turn_llm` coercion).

### Telemetry

`DailyInterventionLog` rows are heartbeated once per day per participant
with `(intervention_date, study_day_index, assigned_condition,
extracted_state)`. The FEEDBACK bot in conditions C and D may push
factual state into `extracted_state` via the `record_daily_telemetry`
tool; the static A / B script writes its raw answers there directly.

### Configuration knobs

| Setting | Where | Purpose |
|---------|-------|---------|
| `FLOW_CRYPTO_MASTER_KEY` | env | One Base64URL-encoded 32-byte master secret. BLAKE3 derives domain-separated subkeys; missing or invalid makes the engine fail and makes the worker use the generic prompt. Do not rotate during a study. |
| `api/config/interventions.json` | repo | Lists of static nudge templates for A and B. Underscore-prefixed keys (e.g. `_comment`) are ignored. |
| `MAX_CONDITION_C_REGEN_ATTEMPTS` | `notification_worker.py` | Worker-side regen budget before the safe fallback fires. |
| `MAX_CONDITION_C_REWRITE_ATTEMPTS` | `coach.py` | Coach-side regen budget for chat turns. |

### Key code entry points (experiment-specific)

| File | Purpose |
|------|---------|
| `api/app/services/randomization.py` | Deterministic 4-day block assignment |
| `api/app/services/intervention_config.py` | Loads + samples static templates for A/B |
| `api/app/services/condition_filters.py` | Shared Condition-C framing regex |
| `api/app/services/feedback_script.py` | Deterministic A/B feedback script |
| `api/prompts/prompt_generator_condition_c.txt` | Condition C nudge prompt (no framing) |
| `api/prompts/prompt_generator_condition_d.txt` | Condition D nudge prompt (If/Then + commitment) |
| `api/app/worker/notification_worker.py::_generate_condition_nudge` | Worker-side condition dispatcher |
| `api/tests/test_four_condition_experiment.py` | Coverage for all of the above |

## Daily Memory Condensation (EOD Semantic Firewall)

### Problem

Conditions C and D both need access to multi-day participant context (anchor,
barrier, last successful prompt, etc.) so the LLM can stay coherent across the
study. Feeding raw `chat_history` from prior days reintroduces exactly the
framing the experiment is trying to isolate: a Condition D message ("If it's
8am and I'm at my desk, then I will do one pushup. We agreed.") would leak into
Condition C's context window on the next day and contaminate the comparison.

The fix is a per-day **sterilized rolling summary** that both C and D read in
place of raw history. Both arms see identical condensed memory, so cross-day
recall is preserved while framing differences remain isolated to that day's
generation step.

### Storage

A dedicated table `daily_summaries` (migration `0012`) stores one row per
`(participation_id, summary_date)` with columns:

- `summary_text` (≤60 words, 1-2 sentences)
- `previous_summary_text` (what was fed in as prior context — for audit)
- `message_count` (raw turns synthesized that day)
- `sterilization_status` ∈ `{clean, regenerated, fallback}`
- `prompt_sha256` (anchors the row to a specific prompt version)

This store has its **own writer** (the summarizer service) and is **not**
subject to the Router single-writer rule that governs `UserProfile` and
`Memory`. The summarizer is treated as a deterministic transformation of
already-committed chat history, not as a behavior-changing patch.

### Lazy hot-path catch-up

There is no cron. Before the engine or worker invokes the C/D code path for a
participant, it calls:

```
await ensure_summaries_up_to(db, participation, yesterday)
summary = await load_latest_summary(db, participation.id)
```

`ensure_summaries_up_to` walks day-by-day from the last committed summary
(or `study_start_date`) up to `yesterday`, producing one row per day. It is
idempotent (existing rows are skipped) and bounded (30-day safety budget per
call). Days with no participant activity write a placeholder row so the chain
never has gaps.

A/B days are summarized too, even though A/B themselves never read summaries —
this keeps the **incremental synthesis** chain unbroken so that when a
participant rotates back to C or D the next block, the summary still reflects
the full study.

### Sterilization pipeline

`summarize_day` →

1. Format that day's chat log (`_format_chat_log`, assistant turns truncated).
2. Render `eod_summarizer_system.txt` with `$previous_memory`,
   `$daily_chat_log`, etc. The prompt explicitly forbids framing vocabulary
   (`promise`, `commit`, `if/then`, `reward`, `bet`, ...).
3. LLM call (15-20s timeout, `ChatOpenAI`).
4. **Regex-gated regen** via `contains_condition_c_framing` (the same filter
   the worker uses on Condition C nudges). On a hit, retry up to
   `MAX_REGEN_ATTEMPTS=2` with an "ADDITIONAL INSTRUCTION" reminder.
5. On persistent framing or LLM failure, fall back to a **deterministic
   skeleton** built from `DailyInterventionLog.extracted_state.script.attempted`
   ("User completed the habit." / "User did not complete the habit.").
6. `_truncate_to_word_cap` enforces the 60-word cap as a final safety net.

Every row records which path produced it via `sterilization_status`, so the
analysis pipeline can drop or downweight non-`clean` rows if needed.

### Consumption

- **Engine (chat turns):** for C/D, the latest summary is prepended as a
  `SystemMessage` ("Sterilized cross-day memory ...") in front of the day's
  filtered chat history. The existing 24h + `condition_source` filter for C is
  kept as defense-in-depth.
- **Worker (nudges):** `_llm_generate_nudge` accepts `daily_summary=` and
  appends it to the `HumanMessage` for the prompt-generator. A/B static
  templates ignore the summary entirely.

Both arms read the **same** sterilized text — that is the firewall.

### Key code entry points (summarizer)

| File | Purpose |
|------|---------|
| `api/prompts/eod_summarizer_system.txt` | Sterilization system prompt + forbidden-word list |
| `api/app/services/eod_summarizer.py` | `summarize_day` / `ensure_summaries_up_to` / `load_latest_summary` + fallback chain |
| `api/app/models.py::DailySummary` | ORM model |
| `api/app/db_migrations/versions/0012_add_daily_summaries_table.py` | Migration |
| `api/tests/test_eod_summarizer.py` | Coverage (clean, regen, fallback, idempotency, chaining, engine/worker injection) |

