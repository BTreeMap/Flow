# Parity Matrix — Legacy Conversation Flow → Python Implementation

> **Purpose.** This document maps every load-bearing behavior from the
> [Legacy Conversation Flow Contract](legacy-conversation-flow-contract.md) (§10.1) to the
> corresponding Python code, and maps each behavioral test scenario (§9) to planned test
> functions. It must be kept current whenever engine behavior changes.

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

All tests are planned under `api/tests/test_engine/`. No tests have been written yet.

| Scenario | Contract § | Description | Planned Test File | Planned Test Function(s) |
|---|---|---|---|---|
| 1 | §9 Scenario 1 | Normal intake completion flow | `test_flow.py` | `test_intake_completion_saves_profile_and_transitions` |
| 2 | §9 Scenario 2 | Missing profile repair (prompt gen fails → LLM transitions back to INTAKE) | `test_tools.py` | `test_prompt_generator_rejects_missing_anchor`, `test_prompt_generator_rejects_missing_time` |
| 3 | §9 Scenario 3 | Prompt generation path (profile complete → prompt stored) | `test_tools.py` | `test_prompt_generator_success`, `test_prompt_generator_increments_total_prompts` |
| 4 | §9 Scenario 4 | Feedback collection path (route to FeedbackModule, cancel pending feedback) | `test_flow.py` | `test_feedback_state_routes_to_feedback_module`, `test_feedback_cancels_pending_timers` |
| 5 | §9 Scenario 5 | State transition with delay (stores timer ID, does not change state immediately) | `test_tools.py` | `test_delayed_state_transition`, `test_immediate_state_transition` |
| 6 | §9 Scenario 6 | Daily prompt → reminder → user reply cancels reminder | `test_scheduler.py` | `test_daily_prompt_reminder_scheduled`, `test_user_reply_cancels_reminder` |
| 7 | §9 Scenario 7 | Reminder fires then user replies (late reply, no pending state) | `test_scheduler.py` | `test_reminder_fires_and_clears_pending`, `test_late_reply_after_reminder_fires` |
| 8 | §9 Scenario 8 | Intensity adjustment — once per day | `test_scheduler.py` | `test_intensity_adjustment_sent_once_per_day`, `test_intensity_adjustment_skipped_same_day` |
| 9 | §9 Scenario 9 | Debug mode behavior | `test_flow.py` | `test_debug_mode` (low priority — debug is incidental per §10.2) |
| 10 | §9 Scenario 10 | Tool failure and state-save failure fallbacks | `test_modules.py` | `test_tool_error_returned_to_llm`, `test_history_save_failure_still_returns_response` |
| 11 | §9 Scenario 11 | Auto-feedback enforcement after prompt | `test_scheduler.py` | `test_auto_feedback_scheduled_after_prompt`, `test_auto_feedback_skips_if_already_feedback`, `test_auto_feedback_skips_if_recent_prompt` |
| 12 | §9 Scenario 12 | Tone update — explicit vs implicit, rate limiting | `test_tone.py` | `test_implicit_rate_limit_rejects_within_3min`, `test_implicit_rate_limit_accepts_after_3min`, `test_explicit_ignores_rate_limit`, `test_ema_smoothing_values`, `test_mutual_exclusion_enforcement` |

---

## 3. What Is Stubbed

| Component | Stub Location | What It Does | Production Replacement Needed |
|---|---|---|---|
| **LLM client** | `engine/modules.py` — `StubLLMClient` | Returns canned `LLMResponse` objects; can be pre-loaded with a sequence of responses for tool-loop testing | Real OpenAI / LangGraph LLM integration |
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

---

## Revision History

| Date | Author | Change |
|---|---|---|
| 2025-07-15 | Initial | Created parity matrix from legacy contract and engine implementation |
