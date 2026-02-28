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
| `conversations` | Chat conversations (1:1 with membership) |
| `messages` | Chat message history |
| `conversation_runtime_state` | Runtime state for conversation protocol (JSON blob) |
| `conversation_events` | Persisted SSE events for durable replay |
| `conversation_turns` | Idempotent messaging deduplication (client_msg_id) |
| `outbox_events` | Scheduled/async event queue with dedup and leasing |

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

## Worker Semantics

The outbox worker (`app.worker.outbox_worker`) processes scheduled events:

- After persisting a scheduled prompt message and committing, **push delivery is best-effort**.
- Push failures or timeouts are logged per-subscription but do **not** cause the outbox event to retry.
- This prevents duplicate messages from push delivery failures.
- Events are claimed with lease fields (`locked_until`, `locked_by`, `claimed_at`) and use 5-minute lock TTL.
- Failed events retry with exponential backoff; dead-letter after max attempts.

---

## Key Code Entrypoints

| File | Purpose |
|------|---------|
| `api/app/agents/engine.py` | Main turn engine: `process_turn()` |
| `api/app/agents/intake.py` | Intake specialist agent |
| `api/app/agents/feedback.py` | Feedback specialist agent |
| `api/app/agents/coach.py` | Coach specialist agent |
| `api/app/agents/runner.py` | Agent runner (LangChain invoke wrapper + tool trace) |
| `api/app/agents/tool_trace.py` | Tool call tracing callback |
| `api/app/tools/proposal_tools.py` | Proposal tools + ProposalCollector |
| `api/app/tools/scheduler_tools.py` | Scheduling LangChain tools |
| `api/app/prompt_loader.py` | Prompt file loader with caching and versioning |
| `api/app/services/profile_service.py` | Profile/memory persistence + validation |
| `api/app/services/event_service.py` | SSE event persistence and replay |
| `api/app/services/outbox_service.py` | Outbox event persistence |
| `api/app/services/scheduler_service.py` | Scheduling logic |
| `api/app/schemas/patches.py` | All Pydantic schemas for proposals |
| `api/app/schemas/router.py` | RouteDecision (INTAKE/FEEDBACK/COACH) |
| `api/app/worker/outbox_worker.py` | Outbox event processing worker |
| `api/app/db_migrations/migrate.py` | Alembic migration runner |

---

## Deprecation Notes

- The legacy conversation flow engine (`api/app/engine/`) has been fully removed. 
- The legacy behavioral contract (`docs/legacy-conversation-flow-contract.md`) is deprecated and for historical reference only.
- New work should use the Router + specialist architecture defined here.
