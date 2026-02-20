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
│  Agent        │  Uses LangChain agent with tools
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
| `conversation_runtime_state` | Legacy runtime state (JSON blob) |

---

## Milestone 1 operational additions

- Activation requires an email end-to-end (`POST /p/{project_id}/activate/claim` validates `email` as `EmailStr`). Email remains contact metadata only and is not used for identity/auth.
- Deterministic onboarding endpoint (`GET/PUT /p/{project_id}/profile`) writes `UserProfileData` directly from explicit participant input.
- Runtime protocol state is persisted in `conversation_runtime_state` after INTAKE/FEEDBACK tool mutations.
- Outbox worker (`app.worker.outbox_worker`) processes due `outbox_events`, handles `scheduled_prompt`, inserts assistant messages, and best-effort push delivery.
- Invites are multi-use by default with `max_uses`/`uses` and optional `revoked_at`; `consumed_at` is no longer used for invite availability checks.

> Note: schema changes rely on `create_all` (no Alembic yet), so existing deployed databases require reset to pick up new columns.

---

## Key Code Entrypoints

| File | Purpose |
|------|---------|
| `api/app/agents/engine.py` | Main turn engine: `process_turn()` |
| `api/app/agents/router.py` | Legacy router (kept for backward compat) |
| `api/app/agents/coach.py` | Coach specialist agent |
| `api/app/agents/intake.py` | Intake specialist agent |
| `api/app/agents/feedback.py` | Feedback specialist agent |
| `api/app/tools/proposal_tools.py` | Proposal tools + ProposalCollector |
| `api/app/services/profile_service.py` | Profile/memory persistence + validation |
| `api/app/schemas/patches.py` | All Pydantic schemas for proposals |
| `api/app/schemas/router.py` | RouteDecision (INTAKE/FEEDBACK/COACH) |

---

## Deprecation Notes

- The legacy conversation flow engine (`api/app/engine/`) is retained for backward compatibility with existing tests.
- The legacy behavioral contract (`docs/legacy-conversation-flow-contract.md`) is deprecated and for historical reference only.
- New work should use the Router + specialist architecture defined here.
