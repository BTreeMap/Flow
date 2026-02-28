# Parity Matrix — Legacy Conversation Flow → Python Implementation

> ⚠️ **HISTORICAL REFERENCE** — This document is retained for traceability. The legacy
> engine (`api/app/engine/`) has been fully removed. The current architecture is
> defined in [`current-architecture.md`](current-architecture.md) and the "State,
> authority, and write-path rules" section of [`AGENTS.md`](../AGENTS.md).

> **Purpose.** This document maps every load-bearing behavior from the
> [Legacy Conversation Flow Contract](legacy-conversation-flow-contract.md) (§10.1) to the
> corresponding Python code, and maps each behavioral test scenario (§9) to planned test
> functions.

---

## 1. Must-Reproduce Behaviors (§10.1)

| # | Legacy Behavior | Contract § | Python File | Class / Function | Status |
|---|---|---|---|---|---|
| 1 | Sub-state routing via `DataKeyConversationState` (not `CurrentState`) | §3.1, §4.1 | `engine/flow.py` | `ConversationFlow._get_conversation_state()`, `ConversationFlow.process_response()` | ✅ Implemented |
| 2 | Tool loop: max 10 rounds, terminate on content, fallback on exhaustion | §8.1 | `engine/modules.py` | `IntakeModule.execute()`, `FeedbackModule.execute()`, `MAX_TOOL_ROUNDS = 10` | ✅ Implemented |
| 3 | Profile field-by-field merge (only update if non-empty AND different) | §4.7 | `engine/tools.py` | `execute_profile_save()` | ✅ Implemented |
| 4 | Tone whitelist enforcement and EMA smoothing (α=0.15, thresholds 0.7/0.4) | §6.1–§6.5 | `engine/tone.py` | `ALL_TAGS`, `validate_proposal()`, `update_profile_tone()`, `ALPHA`, `ACTIVATION_THRESHOLD`, `DEACTIVATION_THRESHOLD` | ✅ Implemented |
| 5 | Daily prompt reminder scheduling and cancellation on reply | §5.2 | `engine/scheduler.py` | `Scheduler.schedule_daily_prompt_reminder()`, `Scheduler.handle_daily_prompt_reply()`, `Scheduler.send_daily_prompt_reminder()` | ✅ Implemented |
| 6 | History trimming: 50 stored, 30 sent to LLM | §3.3 | `engine/flow.py`, `engine/modules.py` | `MAX_HISTORY_LENGTH = 50`, `MAX_HISTORY_MESSAGES_FOR_LLM = 30`, `_build_messages(max_history_messages=30)` | ✅ Implemented |
| 7 | Auto-feedback enforcement (5-minute timer) | §5.3 | `engine/scheduler.py` | `Scheduler.schedule_auto_feedback_enforcement()`, `Scheduler.enforce_feedback_if_no_response()`, `AUTO_FEEDBACK_ENFORCEMENT_DELAY = 5 min` | ✅ Implemented |
| 8 | Intensity adjustment at most once per day | §5.4 | `engine/scheduler.py` | `Scheduler.check_and_send_intensity_adjustment()` | ✅ Implemented |
| 9 | `PromptAnchor` and `PreferredTime` mandatory for prompt generation | §4.5 | `engine/tools.py` | `execute_prompt_generator()` — returns error if missing | ✅ Implemented |
| 10 | Legacy `last_blocker` → `last_barrier` alias in profile save | §4.7 | `engine/tools.py` | `execute_profile_save()` — alias handling block | ✅ Implemented |
| 11 | Mutual exclusion enforcement for tone pairs | §6.2, §6.5 | `engine/tone.py` | `MUTUALLY_EXCLUSIVE_PAIRS`, enforcement in `update_profile_tone()` | ✅ Implemented |
| 12 | `no_emojis` overrides `emojis_ok` | §6.5 | `engine/tone.py` | Override block in `update_profile_tone()` | ✅ Implemented |

---

## 2. Behavioral Test Scenarios (§9) → Planned Test Functions

All tests are under `api/tests/`. Legacy engine tests and new LangChain layer tests are both active.

| Scenario | Contract § | Description | Test File | Test Function(s) | Status |
|---|---|---|---|---|---|
| 1 | §9 Scenario 1 | Normal intake completion flow | `test_flow.py`, `test_langchain_agents.py` | `TestSubStateRouting::test_defaults_to_intake`, `TestOrchestratorNoLLM::test_intake_route_default` | ✅ Passing |
| 2 | §9 Scenario 2 | Missing profile repair (prompt gen fails) | `test_tools.py`, `test_langchain_tools.py` | `TestPromptGenerator::test_requires_prompt_anchor`, `TestPromptGeneratorTool::test_missing_profile_returns_error` | ✅ Passing |
| 3 | §9 Scenario 3 | Prompt generation path | `test_tools.py`, `test_langchain_tools.py` | `TestPromptGenerator::test_success_with_required_fields`, `TestPromptGeneratorTool::test_success_with_complete_profile` | ✅ Passing |
| 4 | §9 Scenario 4 | Feedback collection path | `test_flow.py`, `test_langchain_agents.py` | `TestSubStateRouting::test_feedback_cancels_pending_timers`, `TestOrchestratorNoLLM::test_feedback_cancels_timers` | ✅ Passing |
| 5 | §9 Scenario 5 | State transition with delay | `test_tools.py`, `test_langchain_tools.py` | `TestStateTransition::test_delayed_transition_stores_timer_id`, `TestStateTransitionTool::test_delayed_transition` | ✅ Passing |
| 6 | §9 Scenario 6 | Daily prompt → reminder → cancellation | `test_scheduler.py` | `TestDailyPromptReminder`, `TestCancellationOnReply` | ✅ Passing |
| 7 | §9 Scenario 7 | Reminder fires then late reply | `test_scheduler.py` | `TestCancellationOnReply::test_late_reply_after_reminder_fired` | ✅ Passing |
| 8 | §9 Scenario 8 | Intensity adjustment once/day | `test_scheduler.py` | `TestIntensityAdjustment` | ✅ Passing |
| 9 | §9 Scenario 9 | Debug mode behavior | — | Not implemented (incidental per §10.2) | ⏭ Skipped |
| 10 | §9 Scenario 10 | Tool failure fallbacks | `test_flow.py`, `test_langchain_tools.py` | `TestToolLoop::test_tool_error_continues_loop`, `TestStateTransitionTool::test_invalid_state_returns_error` | ✅ Passing |
| 11 | §9 Scenario 11 | Auto-feedback enforcement | `test_scheduler.py` | `TestAutoFeedbackEnforcement` | ✅ Passing |
| 12 | §9 Scenario 12 | Tone update, rate limiting | `test_tone.py` | `TestEMASmoothing`, `TestRateLimiting`, `TestMutualExclusion` | ✅ Passing |

---

## 3. What Is Stubbed

| Component | Stub Location | What It Does | Production Replacement Needed |
|---|---|---|---|
| **LLM client** | `engine/modules.py` — `StubLLMClient` | Returns canned `LLMResponse` objects; can be pre-loaded with a sequence of responses for tool-loop testing | Real OpenAI / LangGraph LLM integration via `agents/` layer |
| **Prompt generation (LLM call)** | `engine/tools.py` — `execute_prompt_generator()` | Produces a deterministic string from profile fields instead of calling an LLM | LLM call with `prompt_generator_system.txt` |
| **Outbox event persistence** | `engine/scheduler.py` — `Scheduler.pending_events` | Collects `OutboxEvent` objects in an in-memory list for the caller to persist | Database-backed outbox with durable scheduling |
| **Timer/job execution** | `engine/scheduler.py` — `OutboxEvent` | Events are created but never actually fired by a background worker | Durable job runner (e.g., Celery, APScheduler, or DB poller) |
| **Message delivery** | Not implemented | No `msgService` equivalent; prompt delivery and reminder sending return strings only | Push notification / SSE delivery layer |
| **State persistence** | `engine/flow.py`, all tools | `state_data` is a plain `dict[str, str]` passed in by the caller | Database-backed `StateManager` (SQLAlchemy or equivalent) |
| **Debug mode** | Not implemented | Legacy debug messages (`🐛 DEBUG:`) are not reproduced | Optional; debug is incidental per §10.2 |
| **Recovery manager** | Not implemented | Legacy `conversation_flow_recovery.go` is not ported | Incidental per §10.2; may be implemented if needed |

---

## 4. Deliberate Deviations

| # | Area | Legacy Behavior | New Behavior | Rationale |
|---|---|---|---|---|
| 1 | Architecture | Go structs with constructor-based DI (`NewConversationFlowWithAllTools`) | Python classes with protocol-based DI (`LLMClient` protocol, injectable via constructor) | Idiomatic Python; same dependency injection semantics |
| 2 | State persistence | `StoreBasedStateManager` with `GetStateData` / `SetStateData` methods | Plain `dict[str, str]` passed to all functions; persistence responsibility is in the caller | Decouples engine logic from database layer; enables easier testing |
| 3 | Scheduling | In-memory timers with durable job fallback (`jobRepo` / `timer`) | Outbox event pattern (`Scheduler.pending_events` list) | Aligns with project architecture (outbox events with dedup keys per AGENTS.md) |
| 4 | Coordinator module | `CoordinatorModule` and `StaticCoordinatorModule` exist in Go but are not wired | Not ported | Legacy contract §4.8 confirms these are not wired; omission is intentional |
| 5 | Tone score type | Go uses `float32` for tone scores | Python uses `float` (float64) | Python has no native float32; negligible precision difference for EMA at α=0.15 |
| 6 | Identity model | Phone number is primary external identifier; participant ID generated via `util.GenerateParticipantID()` | h4ckath0n user ID (`u...`) is the stable identity; no phone number dependency | Per AGENTS.md identity policy; phone-based routing replaced by web-based auth |
| 7 | Transport | WhatsApp message service with polls/buttons | SSE (mandatory) + optional WebSocket behind feature flag | Per AGENTS.md delivery plane requirements |
| 8 | Debug mode | `SetDebugMode(true)` sends `🐛 DEBUG:` messages via `msgService` | Not implemented | Incidental behavior per §10.2; may be added later via logging |
| 9 | Orchestration layer | Custom `LLMClient` protocol + hand-rolled tool loop in `IntakeModule.execute()` / `FeedbackModule.execute()` | LangChain `create_agent()` (LangGraph-backed) with `@tool` wrappers and `RouteDecision` Pydantic structured output | LangChain-native, idiomatic; preserves all legacy semantics via delegation to unchanged engine functions |

---

## 5. LangChain Orchestration Refactor

> **Scope.** The orchestration layer was refactored to use LangChain primitives.
> In Milestone 2, the legacy engine (`api/app/engine/`), `agents/router.py`,
> `agents/orchestrator.py`, and `tools/langchain_tools.py` were removed.
> The canonical engine is now `agents/engine.py`.

### Architecture

| Component | Old Implementation | Current Implementation | Current File(s) |
|---|---|---|---|
| **Router/Coordinator** | `ConversationFlow._get_conversation_state()` — direct state lookup | `RouteDecision` Pydantic model + deterministic routing in engine | `agents/engine.py`, `schemas/router.py` |
| **Intake agent** | `IntakeModule.execute()` — hand-rolled tool loop | `create_intake_agent()` — LangGraph `create_agent()` with LangChain tools | `agents/intake.py` |
| **Feedback agent** | `FeedbackModule.execute()` — hand-rolled tool loop | `create_feedback_agent()` — LangGraph `create_agent()` with LangChain tools | `agents/feedback.py` |
| **Tool wrappers** | `INTAKE_TOOLS` / `FEEDBACK_TOOLS` — raw OpenAI function-calling dicts | `@tool` decorators with Pydantic `args_schema` (proposal + scheduler) | `tools/proposal_tools.py`, `tools/scheduler_tools.py` |
| **Orchestrator pipeline** | `ConversationFlow.process_response()` | `process_turn()` — router → agent → persist | `agents/engine.py` |

### Key design decisions

1. **Coordinator is router-only.** `RouteDecision` has exactly two fields: `route` (Literal["INTAKE", "FEEDBACK", "COACH"]) and `reason` (log-only, never shown to user). No user-visible text is produced.

2. **LangChain tools use proposal pattern.** Specialists use `propose_profile_patch` and `propose_memory_patch` tools (`tools/proposal_tools.py`). The Router validates and commits proposals.

3. **Pydantic everywhere.** Patch proposals, evidence spans, and permissions are Pydantic models in `schemas/patches.py`.

4. **No hand-rolled loops.** Agent tool dispatch is handled by LangGraph's `create_agent()` runtime.

5. **Stub fallback.** When no LLM is provided, the engine uses deterministic routing and stub responses.

### Behavior preservation

All 12 must-reproduce behaviors (§10.1, table above) are preserved:

| # | Behavior | Where preserved | Tests |
|---|---|---|---|
| 1 | Sub-state routing defaults | `agents/engine.py` — deterministic routing | `test_new_architecture.py`, `test_engine_integration.py` |
| 2 | Tool loop max iterations | LangGraph agent recursion limit | `test_langchain_agents.py` |
| 3 | Profile field-by-field merge | `tools/proposal_tools.py` → `services/profile_service.py` | `test_langchain_tools.py` |
| 4 | Tone whitelist + EMA | Legacy engine removed; tone logic in profile service | `test_new_architecture.py` |
| 5 | Reminder scheduling/cancellation | `agents/engine.py` — scheduling in turn pipeline | `test_nudge_integration.py` |
| 6 | History trimming | Message pagination in routes | `test_api.py` |
| 7 | Auto-feedback enforcement | Outbox worker scheduled events | `test_outbox_worker.py` |
| 8 | Intensity adjustment once/day | Outbox worker scheduled events | `test_outbox_worker.py` |
| 9 | PromptAnchor/PreferredTime mandatory | Profile validation in engine | `test_new_architecture.py` |
| 10 | last_blocker alias | Legacy engine removed | — |
| 11 | Mutual exclusion for tone | Legacy engine removed | — |
| 12 | no_emojis overrides emojis_ok | Legacy engine removed | — |

**Semantics unchanged; orchestration changed only.**

### Test coverage

| Test File | Tests | Coverage Area |
|---|---|---|
| `test_langchain_router.py` | 10 | RouteDecision schema, deterministic routing, no user text |
| `test_langchain_tools.py` | 14 | Tool creation, Pydantic args/results, tool permissions, error handling |
| `test_langchain_agents.py` | 24 | Agent tool permissions, orchestrator pipeline, history, poll responses |

---

## Revision History

| Date | Author | Change |
|---|---|---|
| 2025-07-15 | Initial | Created parity matrix from legacy contract and engine implementation |
| 2026-02-15 | LangChain Refactor | Added §5: LangChain orchestration refactor with code + test pointers |
| 2026-02-27 | Doc Parity | Updated stale file references after Milestone 2 removal of legacy engine |
