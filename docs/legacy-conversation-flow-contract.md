# PromptPipe Conversation Flow Engine — Behavioral Contract

> ⚠️ **DEPRECATED** — This document is deprecated and retained for historical reference only. It must NOT be treated as the authoritative behavioral contract. The current architecture is defined in [`docs/current-architecture.md`](current-architecture.md) and the "State, authority, and write-path rules" section of `AGENTS.md`. Any legacy behaviors preserved for continuity are documented explicitly in the current design docs and tests.

> **Purpose.** This document captures the complete behavioral contract of the PromptPipe conversation flow engine as implemented at time of writing. A replacement implementation that satisfies every requirement below is a valid drop-in substitute. Sections are ordered so that each one depends only on material already introduced.

---

## Repository Mapping

These are the source files that define the conversation flow engine. Every claim in this document is traceable to one or more of them.

| Area | File | Role |
|---|---|---|
| Orchestrator | `internal/flow/conversation_flow.go` | `ConversationFlow` struct, routing, history management |
| Generator registry | `internal/flow/flow.go` | Generator registry (unused in conversation path) |
| State interfaces | `internal/flow/state.go` | `StateManager` interface, `Dependencies` struct |
| State persistence | `internal/flow/state_manager.go` | `StoreBasedStateManager` implementation |
| Intake module | `internal/flow/intake_module.go` | `IntakeModule` — intake conversation behavior |
| Feedback module | `internal/flow/feedback_module.go` | `FeedbackModule` — feedback tracking behavior |
| Scheduler tool | `internal/flow/scheduler_tool.go` | `SchedulerTool` — schedule CRUD, prompt delivery, reminders |
| Prompt generator | `internal/flow/prompt_generator_tool.go` | `PromptGeneratorTool` — LLM-based prompt generation |
| State transition | `internal/flow/state_transition_tool.go` | `StateTransitionTool` — immediate and delayed transitions |
| Profile save | `internal/flow/profile_save_tool.go` | `ProfileSaveTool`, `UserProfile` struct |
| Profile helpers | `internal/flow/profile_helpers.go` | Shared profile helper functions |
| Coordinator (legacy) | `internal/flow/coordinator_module.go` | `CoordinatorModule` — LLM-based router, **not wired** |
| Static coordinator | `internal/flow/coordinator_module_static.go` | `StaticCoordinatorModule` — **not wired** |
| Coordinator iface | `internal/flow/coordinator_interface.go` | `Coordinator` interface |
| Coordinator selector | `internal/flow/coordinator_selector.go` | Coordinator selection logic |
| Durable jobs | `internal/flow/durable_jobs.go` | Job kind constants and handlers |
| Recovery | `internal/flow/conversation_flow_recovery.go` | Recovery after restart |
| State constants | `internal/models/flow_types.go` | `StateType`, `DataKey` constants |
| FlowState struct | `internal/models/state.go` | `FlowState` persistence record |
| Tool types | `internal/models/tools.go` | `SchedulerToolParams`, `ToolCall`, `ToolResult` |
| Core models | `internal/models/models.go` | `ConversationParticipant`, `Schedule`, `Timer` interface |
| Tone adaptation | `internal/tone/tone.go` | Whitelist, EMA, `BuildToneGuide` |
| Enrollment API | `internal/api/conversation_handlers.go` | `POST /conversation/participants` handler |
| API wiring | `internal/api/api.go` | Production wiring of all components |
| Messaging | `internal/messaging/response_handler.go` | `ProcessResponse` routing to registered hooks |
| System prompts | `prompts/intake_bot_system.txt` | Intake module system prompt |
| System prompts | `prompts/feedback_tracker_system.txt` | Feedback module system prompt |
| System prompts | `prompts/prompt_generator_system.txt` | Prompt generator system prompt |
| System prompts | `prompts/conversation_system_3bot.txt` | Fallback system prompt |

---

## 1. System Boundary and Glossary

### 1.1 System Boundary

The **Conversation Flow engine** comprises everything in `internal/flow/`, `internal/models/`, `internal/tone/`, and the prompt text files in `prompts/`. The boundary explicitly excludes:

- `internal/whatsapp/` — WhatsApp client transport
- `internal/messaging/` — message routing (except where it calls `ConversationFlow.ProcessResponse`)
- `internal/api/` — HTTP endpoints (except enrollment, which initializes flow state)
- `internal/store/` — storage backends (consumed via interfaces)

### 1.2 Glossary

| Term | Definition | Canonical location |
|---|---|---|
| **Participant** | A person enrolled in the system, stored as `ConversationParticipant`. Has ID, PhoneNumber, Name, Gender, Ethnicity, Background, Timezone, Status, EnrolledAt, CreatedAt, UpdatedAt. | `internal/models/models.go:L375-L387` |
| **Enrollment** | The process of creating a participant via `POST /conversation/participants`. Initializes state to `CONVERSATION_ACTIVE`, stores background, registers a response hook, and sends the first AI message. | `internal/api/conversation_handlers.go:L19-L132` |
| **Conversation State (sub-state)** | Stored in `DataKeyConversationState`. Either `"INTAKE"` or `"FEEDBACK"`. Defaults to `"INTAKE"` if empty. See §3.1 for the distinction between top-level state and sub-state. | `internal/models/flow_types.go:L43` |
| **Module** | A struct implementing a specific conversation behavior. Each has its own system prompt, tool set, and tool-calling loop. | `IntakeModule`, `FeedbackModule` |
| **Tool** | An LLM function-calling tool exposed via OpenAI tool definitions: `scheduler`, `save_user_profile`, `generate_habit_prompt`, `transition_state`. | Various `GetToolDefinition()` methods |
| **Schedule** | A recurring daily timer for sending habit prompts. Stored in `DataKeyScheduleRegistry` as JSON array of `ScheduleInfo`. | `internal/flow/scheduler_tool.go` |
| **Reminder** | A one-shot follow-up message sent if the user does not reply to a daily prompt within `dailyPromptReminderDelay` (default 5 hours). | `internal/flow/scheduler_tool.go:L21` |
| **Daily Prompt Pending** | State tracking whether a daily prompt was sent and is awaiting a reply. Stored in `DataKeyDailyPromptPending` as JSON. | `internal/flow/scheduler_tool.go:L25` |
| **FlowState** | The persistence record for a participant. Contains ParticipantID, FlowType, CurrentState (top-level), StateData (`map[DataKey]string`). | `internal/models/state.go:L9-L16` |
| **UserProfile** | Structured profile data stored as JSON in `DataKeyUserProfile`. | `internal/flow/profile_save_tool.go:L19-L39` |

---

## 2. High-Level Architecture

### 2.1 Request Flow

```
                        ┌──────────────────────┐
  POST /participants ──▶│   Enrollment Handler  │──┐
                        └──────────────────────┘  │
                                                   ▼
  Incoming user msg ──▶ ResponseHandler.ProcessResponse
                            │
                            ▼ (registered hook lookup)
                     ConversationFlow.ProcessResponse
                            │
                            ▼
                    processConversationMessage
                       │                │
            ┌──────────┘                └──────────┐
            ▼                                      ▼
     processIntakeState                   processFeedbackState
            │                                      │
            ▼                                      ▼
     IntakeModule                           FeedbackModule
     (tool loop)                            (tool loop)
```

### 2.2 Detailed Processing Pipeline

1. **API entry:** `POST /conversation/participants` → enrollment → first AI message via `ConversationFlow.ProcessResponse` (`internal/api/conversation_handlers.go:L19-L132`).

2. **Incoming user messages:** `ResponseHandler.ProcessResponse` → looks up registered hook by phone number → finds `ConversationFlow` → calls `ConversationFlow.ProcessResponse` (`internal/messaging/response_handler.go`).

3. **`ConversationFlow.ProcessResponse`** (`internal/flow/conversation_flow.go:L226-L288`):
   - Gets current top-level state (`CONVERSATION_ACTIVE` or initializes it).
   - Calls `processConversationMessage`.

4. **`processConversationMessage`** (`internal/flow/conversation_flow.go:L292-L400`):
   - Retrieves conversation history from `DataKeyConversationHistory`.
   - Appends the incoming user message.
   - Checks for "Done" poll response → increments `SuccessCount` on profile.
   - Checks for intensity-adjustment poll response → updates profile `Intensity`.
   - Calls `schedulerTool.handleDailyPromptReply` to cancel pending reminders.
   - Gets conversation sub-state from `DataKeyConversationState`.
   - Routes to `processIntakeState` (`"INTAKE"`) or `processFeedbackState` (`"FEEDBACK"`).
   - Appends assistant response to history.
   - Saves history (trimmed to max 50 messages).

5. **`processIntakeState`** (`internal/flow/conversation_flow.go:L811-L843`): Gets chat history (50 messages), calls `intakeModule.ExecuteIntakeBotWithHistoryAndConversation`.

6. **`processFeedbackState`** (`internal/flow/conversation_flow.go:L847-L886`): Gets chat history (50 messages), calls `feedbackModule.ExecuteFeedbackTrackerWithHistoryAndConversation`, then `CancelPendingFeedback`.

### 2.3 Scheduled Prompt Delivery

1. LLM calls `scheduler` tool with `action=create` → `executeCreateSchedule` (`internal/flow/scheduler_tool.go:L817`).
2. Determines target time, builds `Schedule` (with prep time before target), creates recurring timer.
3. If `shouldScheduleToday` is true, also schedules a one-shot delayed timer for today.
4. Timer fires → `executeScheduledPrompt` (`internal/flow/scheduler_tool.go:L356`): generates prompt via `PromptGeneratorTool` → sends message → schedules reminder → checks intensity poll → optionally schedules auto-feedback enforcement.

### 2.4 History Persistence

All state is persisted in the `flow_states` table via `StoreBasedStateManager`. `StateData` is a `map[DataKey]string` stored as JSON. Each value is either a plain string or JSON-serialized structured data.

---

## 3. State Model

### 3.1 Top-Level State

Top-level state constants (`internal/models/flow_types.go:L25-L30`):

| Constant | Value | Usage |
|---|---|---|
| `StateConversationActive` | `"CONVERSATION_ACTIVE"` | The **only** top-level state used in production. Stored in `FlowState.CurrentState`. |
| `StateIntake` | `"INTAKE"` | Used as a sub-state value, **not** as `CurrentState`. |
| `StateFeedback` | `"FEEDBACK"` | Used as a sub-state value, **not** as `CurrentState`. |

**Critical invariant:** The top-level `CurrentState` field is always `"CONVERSATION_ACTIVE"`. The actual behavioral sub-state (`INTAKE` or `FEEDBACK`) is stored in the `StateData` map under `DataKeyConversationState`, not in `CurrentState`.

### 3.2 DataKey Reference

All keys defined in `internal/models/flow_types.go:L33-L52`:

| # | DataKey | Type / Format | Default | Written by | Read by |
|---|---|---|---|---|---|
| 1 | `conversationHistory` | JSON `ConversationHistory{Messages []ConversationMessage}`. Each message: `{Role, Content, Timestamp}`. | `{"messages":[]}` | `ConversationFlow` | `ConversationFlow`, modules |
| 2 | `systemPrompt` | String | Empty | Unused in current code (prompts loaded from files) | — |
| 3 | `participantBackground` | Plain text. Format: `"Name: X\nGender: Y\nEthnicity: Z\nBackground: W"` | Empty string | Enrollment handler (`conversation_handlers.go:L91-L102`) | `buildOpenAIMessages`, module message builders |
| 4 | `userProfile` | JSON `UserProfile` struct | Empty profile with `Intensity="normal"` | `ProfileSaveTool`, `PromptGeneratorTool`, `FeedbackModule`, `SchedulerTool`, `ConversationFlow` | Same |
| 5 | `lastHabitPrompt` | Plain text string of the last generated habit prompt | Empty | `PromptGeneratorTool` (`prompt_generator_tool.go:L105`) | `PromptGeneratorTool`, modules |
| 6 | `feedbackState` | String enum: `"waiting_initial"`, `"followup_sent"`, `"completed"` | Empty | `FeedbackModule`, durable job handlers | `FeedbackModule` (idempotency checks) |
| 7 | `feedbackTimerID` | String (timer/job ID) | Empty | `FeedbackModule.ScheduleFeedbackCollection` | `CancelPendingFeedback` |
| 8 | `feedbackFollowupTimerID` | String (timer/job ID) | Empty | `FeedbackModule.scheduleFollowupFeedback` | `CancelPendingFeedback` |
| 9 | `scheduleRegistry` | JSON `[]ScheduleInfo`. Each: `{ID, Type, FixedTime, RandomStartTime, RandomEndTime, Timezone, CreatedAt, TimerID}` | `[]` | `SchedulerTool` | `SchedulerTool` |
| 10 | `conversationState` | String: `"INTAKE"` or `"FEEDBACK"` | `"INTAKE"` | `getCurrentConversationState` (default), `StateTransitionTool` | `processConversationMessage` |
| 11 | `stateTransitionTimerID` | String (timer/job ID) | Empty | `StateTransitionTool.scheduleDelayedTransition` | `StateTransitionTool` |
| 12 | `lastPromptSentAt` | RFC3339 timestamp string | Empty | `SchedulerTool.executeScheduledPrompt` (`scheduler_tool.go:L409`) | `enforceFeedbackIfNoResponse` |
| 13 | `autoFeedbackTimerID` | String (timer/job ID) | Empty | `SchedulerTool.scheduleAutoFeedbackEnforcement` | `StateTransitionTool` (cancellation on transition) |
| 14 | `dailyPromptPending` | JSON `dailyPromptPendingState{SentAt, To, ReminderDueAt}` | Empty | `scheduleDailyPromptReminder` (`scheduler_tool.go:L601`) | `handleDailyPromptReply`, `sendDailyPromptReminder` |
| 15 | `dailyPromptReminderTimerID` | String (timer/job ID) | Empty | `scheduleDailyPromptReminder` | `handleDailyPromptReply` (cancellation) |
| 16 | `dailyPromptReminderSentAt` | RFC3339 timestamp | Empty | `sendDailyPromptReminder` (`scheduler_tool.go:L744`) | Analytics |
| 17 | `dailyPromptRespondedAt` | RFC3339 timestamp | Empty | `handleDailyPromptReply` (`scheduler_tool.go:L705`) | Analytics |
| 18 | `lastIntensityPromptDate` | Date string `"YYYY-MM-DD"` | Empty | `checkAndSendIntensityAdjustment` (`scheduler_tool.go:L556`) | Same (prevents >1 poll/day) |

### 3.3 History Trimming Rules

| Context | Limit | Location |
|---|---|---|
| **Storage** | Most recent 50 messages | `saveConversationHistory` (`conversation_flow.go:L437-L457`), `maxHistoryLength = 50` at L439 |
| **LLM context** | Most recent 30 messages | `buildOpenAIMessages` (`conversation_flow.go:L463`), `maxHistoryMessages = 30` at L492 |
| **Chat history retrieval** | `min(chatHistoryLimit, maxMessages)` where `maxMessages=50` | `getPreviousChatHistory` (`conversation_flow.go:L574-L625`) |
| **chatHistoryLimit config** | `-1` = no limit (use maxMessages), `0` = no history, positive = last N | `ConversationFlow.chatHistoryLimit` (default `-1`) |

---

## 4. Module Responsibilities

### 4.1 ConversationFlow Orchestrator

- **File:** `internal/flow/conversation_flow.go`
- **Struct:** `ConversationFlow` (`L86-L100`)
- **Constructors:**
  - `NewConversationFlow` (`L101`) — simple construction, no tools.
  - `NewConversationFlowWithAllTools` (`L112`) — production wiring with all modules and tools.
- **Entry methods:**
  - `ProcessResponse(ctx, participantID, response string) (string, error)` (`L226`) — called by `ResponseHandler`.
  - `Generate(ctx, prompt) (string, error)` (`L209`) — not used in conversation flow path.
- **System prompt:** `prompts/conversation_system_3bot.txt` loaded via `LoadSystemPrompt()` (`L150`). Used as fallback; primary routing uses module-specific prompts.
- **Tools:** None directly exposed to LLM. Acts as router only.
- **Behavior:** Gets history → appends user message → checks polls → handles reminder reply → routes to module by sub-state → appends assistant response → saves history.
- **Critical invariant:** The top-level `CurrentState` is always `"CONVERSATION_ACTIVE"`. Sub-state routing (`INTAKE`/`FEEDBACK`) uses `DataKeyConversationState` from `StateData`, not `CurrentState` (see §3.1).

### 4.2 IntakeModule

- **File:** `internal/flow/intake_module.go`
- **Struct:** `IntakeModule` (`L22-L32`)
- **Constructor:** `NewIntakeModule` (`L34`)
- **Entry method:** `ExecuteIntakeBotWithHistoryAndConversation(ctx, participantID, args, chatHistory, conversationHistory)` (`L55`)
- **System prompt:** `prompts/intake_bot_system.txt` loaded via `LoadSystemPrompt()` (`L151`)
- **Tools exposed to LLM:** `save_user_profile`, `scheduler`, `generate_habit_prompt`, `transition_state`
- **Tool loop:** Max 10 rounds (`L269`). Calls `genaiClient.GenerateThinkingWithTools`. If tool calls returned, executes them via `executeIntakeToolCallsAndUpdateContext`, adds assistant message with tool calls + tool result messages to context. If content is non-empty, returns it. If no tool calls and no content, returns fallback. Continues loop until content produced or max rounds hit.
- **Message building:** system prompt + intake context (profile info, profile status) + tone guide + chat history (up to 30 messages) + user message.

### 4.3 FeedbackModule

- **File:** `internal/flow/feedback_module.go`
- **Struct:** `FeedbackModule` (`L24-L37`)
- **Constructor:** `NewFeedbackModule` (`L40`)
- **Entry method:** `ExecuteFeedbackTrackerWithHistoryAndConversation(ctx, participantID, args, chatHistory, conversationHistory)` (`L103`)
- **System prompt:** `prompts/feedback_tracker_system.txt`
- **Tools exposed to LLM:** `transition_state`, `save_user_profile`, `scheduler`
- **Tool loop:** Max 10 rounds (`L553`). Same loop pattern as IntakeModule.
- **Additional methods:**
  - `CancelPendingFeedback(ctx, participantID)` (`L521`) — cancels `feedbackTimerID` and `feedbackFollowupTimerID`.
  - `ScheduleFeedbackCollection(ctx, participantID)` (`L314`) — schedules initial feedback timeout.

### 4.4 SchedulerTool

- **File:** `internal/flow/scheduler_tool.go`
- **Struct:** `SchedulerTool` (`L33-L44`)
- **Constructor:** `NewSchedulerTool` (`L65`)
- **Tool name:** `"scheduler"` (`L205`)
- **Parameters:** `action` (create/list/delete), `type` (fixed/random), `fixed_time`, `timezone`, `random_start_time`, `random_end_time`, `schedule_id`
- **Key methods:**

| Method | Line | Responsibility |
|---|---|---|
| `ExecuteScheduler` | L251 | Tool dispatch by action |
| `executeScheduledPrompt` | L356 | Generate and deliver daily prompt |
| `scheduleDailyPromptReminder` | L563 | Set up follow-up reminder timer |
| `handleDailyPromptReply` | L653 | Cancel reminder when user replies |
| `sendDailyPromptReminder` | L710 | Fire reminder message |
| `scheduleAutoFeedbackEnforcement` | L444 | Set up 5-minute auto-feedback timer |
| `enforceFeedbackIfNoResponse` | L769 | Transition to FEEDBACK if no reply |
| `checkAndSendIntensityAdjustment` | L500 | Send intensity poll (max once/day) |
| `executeCreateSchedule` | L817 | Create schedule + recurring timer |

- **Default timezone:** `"America/Toronto"` for fixed schedules, `"UTC"` for random schedules (`L843-L849`).
- **Prep time:** Configurable via `prepTimeMinutes` (passed to constructor, default set in `api.go`).

### 4.5 PromptGeneratorTool

- **File:** `internal/flow/prompt_generator_tool.go`
- **Struct:** `PromptGeneratorTool` (`L19-L25`)
- **Constructor:** `NewPromptGeneratorTool` (`L28`)
- **Tool name:** `"generate_habit_prompt"` (`L43`)
- **Parameters:** `delivery_mode` (immediate/scheduled), `personalization_notes` (optional)
- **System prompt:** `prompts/prompt_generator_system.txt`
- **Key method:** `ExecutePromptGenerator` (`L65`) — validates profile (`PromptAnchor` and `PreferredTime` required, `L302-L309`), generates via LLM, stores result in `DataKeyLastHabitPrompt`.
- **Profile validation:** `PromptAnchor` and `PreferredTime` are **mandatory** (returns error if missing). `HabitDomain` and `MotivationalFrame` generate warnings only.

### 4.6 StateTransitionTool

- **File:** `internal/flow/state_transition_tool.go`
- **Struct:** `StateTransitionTool` (`L18-L22`)
- **Constructor:** `NewStateTransitionTool` (`L24`)
- **Tool name:** `"transition_state"` (`L44`)
- **Parameters:** `target_state` (enum: `"INTAKE"`, `"FEEDBACK"`), `delay_minutes` (optional float), `reason` (optional string)
- **Immediate transition:** Writes `DataKeyConversationState`, cancels any pending auto-feedback timer (`DataKeyAutoFeedbackTimerID`).
- **Delayed transition:** Schedules via `jobRepo` (durable) or `timer` (in-memory). Stores timer ID in `DataKeyStateTransitionTimerID`.

### 4.7 ProfileSaveTool

- **File:** `internal/flow/profile_save_tool.go`
- **Struct:** `ProfileSaveTool` (`L41-L45`)
- **Constructor:** `NewProfileSaveTool` (`L47`)
- **Tool name:** `"save_user_profile"` (`L60`)
- **Parameters:** `prompt_anchor` (required), `preferred_time` (required), `habit_domain`, `motivational_frame`, `additional_info`, `last_successful_prompt`, `last_barrier`, `last_motivator`, `last_tweak`, `tone_tags`, `tone_update_source`, `tone_confidence`
- **Merge logic:** Field-by-field merge — only updates a field if the new value is non-empty AND differs from the existing value. Handles legacy `last_blocker` → `last_barrier` alias. Tone proposals validated server-side via `tone.ValidateProposal`. Returns `"success"` or `"noop"`.
- **`GetOrCreateUserProfile`** (`L275`) — retrieves or creates default profile with `Intensity="normal"`.

### 4.8 CoordinatorModule (Legacy — Not Wired)

- **File:** `internal/flow/coordinator_module.go`
- **Struct:** `CoordinatorModule` (`L23-L33`)
- **Status:** `NewConversationFlowWithAllTools` (`conversation_flow.go:L112`) does **NOT** create a `CoordinatorModule`. It creates `IntakeModule` and `FeedbackModule` directly. The comment at `L124` says `"coordinator removed in new design"`.
- `StaticCoordinatorModule` (`coordinator_module_static.go`) also exists but is not wired.

---

## 5. Scheduling Semantics and Timers

### 5.1 Daily Prompt Generation and Delivery

1. LLM calls `scheduler` tool with `action=create` → `executeCreateSchedule` (`scheduler_tool.go:L817`).
2. Determines target time, builds `Schedule` (with prep time offset before target), creates a recurring timer.
3. If `shouldScheduleToday` is true, also schedules a one-shot delayed timer for today.
4. Timer fires → `executeScheduledPrompt` (`scheduler_tool.go:L356`):
   - Uses `PromptGeneratorTool` to generate content.
   - Sends via `msgService` (uses polls/buttons if supported).
   - Records `DataKeyLastPromptSentAt` (RFC3339).
   - Increments `TotalPrompts` on profile.
   - Calls `scheduleDailyPromptReminder`.
   - Calls `checkAndSendIntensityAdjustment`.
   - Optionally calls `scheduleAutoFeedbackEnforcement` (if `autoFeedbackEnabled`).

### 5.2 Daily Prompt Reminder

| Property | Value | Location |
|---|---|---|
| Default delay | `5 * time.Hour` | `defaultDailyPromptReminderDelay` (`scheduler_tool.go:L21`) |
| Override | `SetDailyPromptReminderDelay(delay)` (`L87`). Non-positive value disables. | |
| Dedup key | `"daily_prompt_reminder:{participantID}"` | `scheduleDailyPromptReminder` |
| Timer ID stored in | `DataKeyDailyPromptReminderTimerID` | |
| Pending state stored in | `DataKeyDailyPromptPending` (JSON `dailyPromptPendingState`) | |

**Scheduling** (`scheduleDailyPromptReminder`, `scheduler_tool.go:L563`):
1. Cancels any existing reminder (dedup).
2. Stores pending state in `DataKeyDailyPromptPending`.
3. Prefers durable job. Falls back to in-memory timer.

**Cancellation on user reply** (`handleDailyPromptReply`, `scheduler_tool.go:L653`):
1. Checks `DataKeyDailyPromptPending`.
2. Validates reply timestamp > sent timestamp (prevents stale cancellations).
3. Cancels timer/job.
4. Clears pending state.
5. Records `DataKeyDailyPromptRespondedAt`.

**Reminder fires** (`sendDailyPromptReminder`, `scheduler_tool.go:L710`):
1. Checks pending state still matches `expectedSentAt` (prevents stale reminders from firing).
2. Sends default message: `"Friendly check-in: we haven't heard back after today's habit prompt. Reply with a quick update when you're ready!"` (`scheduler_tool.go:L22`).
3. Records `DataKeyDailyPromptReminderSentAt`.
4. Clears `DataKeyDailyPromptPending`.

### 5.3 Auto-Feedback Enforcement

| Property | Value | Location |
|---|---|---|
| Delay | `5 * time.Minute` | `enforcementDelay` (`scheduler_tool.go:L445`) |
| Trigger | After `executeScheduledPrompt` if `autoFeedbackEnabled` | `scheduler_tool.go:L437` |
| Dedup key | `"auto_feedback:{participantID}"` | |
| Timer ID stored in | `DataKeyAutoFeedbackTimerID` | |

**Scheduling** (`scheduleAutoFeedbackEnforcement`, `scheduler_tool.go:L444`):
- Cancels any existing auto-feedback timer.
- Prefers durable job. Falls back to in-memory timer.

**Fires** (`enforceFeedbackIfNoResponse`, `scheduler_tool.go:L769`):
1. Checks if already in `FEEDBACK` state → skips.
2. Checks if a newer prompt was sent within ~4.5 minutes → skips (prompt was re-sent, new enforcement will handle it).
3. Transitions to `FEEDBACK` state by writing `DataKeyConversationState`.

### 5.4 State Transition Timer

- **Trigger:** LLM calls `transition_state` with `delay_minutes > 0`.
- **Scheduling:** `scheduleDelayedTransition` (`state_transition_tool.go`). Prefers durable job (dedup key `"state_transition:{participantID}"`). Falls back to in-memory timer. Timer ID in `DataKeyStateTransitionTimerID`.
- **Fires:** Executes immediate transition to target state.

### 5.5 Feedback Timers

| Timer | Timeout source | DataKey | Dedup key |
|---|---|---|---|
| Initial timeout | `feedbackInitialTimeout` (configurable, e.g. `"15m"`) | `DataKeyFeedbackTimerID` | `"feedback_timeout:{participantID}"` |
| Follow-up | `feedbackFollowupDelay` (configurable, e.g. `"3h"`) | `DataKeyFeedbackFollowupTimerID` | `"feedback_followup:{participantID}"` |

Both cancelled by `CancelPendingFeedback` (`feedback_module.go:L521-L548`).

---

## 6. Tone Adaptation

### 6.1 Tag Whitelist

Defined in `internal/tone/tone.go:L14-L34` (`AllTags`):

| Category | Tags |
|---|---|
| **Style** | `concise`, `detailed`, `formal`, `casual`, `no_emojis`, `emojis_ok`, `bullet_points`, `one_question_at_a_time` |
| **Stance** | `warm_supportive`, `neutral_professional`, `direct_coach`, `gentle_coach` |
| **Interaction** | `confirm_before_acting`, `default_actionable`, `high_autonomy` |

### 6.2 Mutually Exclusive Pairs

Defined in `tone.go:L37-L41`:

- `concise` ↔ `detailed`
- `formal` ↔ `casual`
- `direct_coach` ↔ `gentle_coach`

If both tags in a pair have score ≥ 0.7, the higher score is kept and the lower is set to 0.39 (i.e., `deactivateThresh - 0.01`), ensuring it falls below the 0.4 deactivation threshold and will be deactivated.

### 6.3 Tag Storage

Tone data lives inside `UserProfile.Tone` of type `tone.ProfileTone` (`tone.go:L62-L69`):

```go
type ProfileTone struct {
    Tags          []string           `json:"tone_tags,omitempty"`
    Scores        map[string]float32 `json:"tone_scores,omitempty"`
    Version       int                `json:"tone_version"`
    LastUpdatedAt time.Time          `json:"tone_last_updated_at,omitempty"`
    UpdateSource  UpdateSource       `json:"tone_update_source,omitempty"`
    OverrideUntil *time.Time         `json:"tone_override_until,omitempty"`
}
```

### 6.4 Validation (`ValidateProposal`, `tone.go:L84-L116`)

Applied to every LLM-originated tone proposal before persistence:

1. Lowercase and trim all tag names.
2. Strip unknown tags (not in `AllTags`).
3. Deduplicate tags.
4. Clamp scores to `[0, 1]`.
5. Only keep scores for whitelisted tags.

### 6.5 EMA Smoothing (`UpdateProfileTone`, `tone.go:L121-L239`)

| Constant | Value | Line |
|---|---|---|
| Alpha (α) | `0.15` | `tone.go:L74` |
| Activation threshold | `0.7` | `tone.go:L75` |
| Deactivation threshold | `0.4` | `tone.go:L76` |
| Min implicit interval | `3 minutes` | `tone.go:L78` |

**Explicit updates** (`source = "explicit"`): Apply immediately with full weight (`score = proposed value`).

**Implicit updates** (`source = "implicit"`):
- Observed tags: `new_score = (1 - 0.15) * old + 0.15 * observed`
- Non-observed tags decay: `new_score = (1 - 0.15) * old`
- Rate limited: minimum 3 minutes between implicit updates.

**Override rules:**
- `no_emojis` overrides `emojis_ok` (`tone.go:L191-L193`, `L224-L226`).
- Mutual exclusion enforcement: if both tags in a pair have score ≥ 0.7, keep the higher, set the lower to 0.39 (`tone.go:L196-L206`).

**Tag activation hysteresis:**
- Score ≥ 0.7 → activate (add to `Tags` list).
- Score ≤ 0.4 → deactivate (remove from `Tags` list).
- Score between 0.4 and 0.7 → keep current state (hysteresis).

### 6.6 Tone Guide Injection (`BuildToneGuide`, `tone.go:L243-L319`)

- Called by `IntakeModule`, `FeedbackModule`, `CoordinatorModule`, `PromptGeneratorTool` in their message builders.
- Returns empty string if no active tags.
- Produces a `<TONE POLICY>` block with rules per category.
- Always appends: `"NEVER mirror hostility, sarcasm, insults, or unsafe language."`
- Default stance if no stance tags are active: `"Keep a neutral, professional stance."`

### 6.7 LLM-to-Server Tone Flow

The LLM writes tone proposals via `save_user_profile` with fields:
- `tone_tags` (array of strings)
- `tone_update_source` (`"explicit"` or `"implicit"`)
- `tone_confidence` (float)

Parsed by `parseToneProposal` (`profile_save_tool.go:L368-L405`). Validated server-side by `tone.ValidateProposal`. Applied by `tone.UpdateProfileTone`.

---

## 7. Enrollment and Identity

### 7.1 Participant Struct

`ConversationParticipant` (`internal/models/models.go:L375-L387`):

| Field | Type | Notes |
|---|---|---|
| `ID` | `string` | Generated via `util.GenerateParticipantID()`. Primary internal identifier. |
| `PhoneNumber` | `string` | Canonicalized E.164 format. Primary external identifier for message routing. |
| `Name` | `string` | Optional metadata. |
| `Gender` | `string` | Optional demographic info. |
| `Ethnicity` | `string` | Optional demographic info. |
| `Background` | `string` | Optional cultural/mental health background. |
| `Timezone` | `string` | Optional, used if provided (e.g. `"America/New_York"`). |
| `Status` | `ConversationParticipantStatus` | `active`, `paused`, `completed`, `withdrawn` |
| `EnrolledAt` | `time.Time` | Timestamp of enrollment. |
| `CreatedAt` | `time.Time` | Record creation. |
| `UpdatedAt` | `time.Time` | Last update. |

### 7.2 Enrollment Flow

`POST /conversation/participants` (`internal/api/conversation_handlers.go:L19-L132`):

1. Validate request + canonicalize phone number.
2. Check for existing participant by phone → `409 Conflict` if exists.
3. Generate participant ID via `util.GenerateParticipantID()`.
4. Create `ConversationParticipant` with `status=Active`.
5. Save to store.
6. Set flow state `CurrentState = CONVERSATION_ACTIVE`.
7. Store participant background in `DataKeyParticipantBackground`.
8. Register persistent response hook (phone → participantID mapping).
9. Generate first AI message via:
   ```go
   ConversationFlow.ProcessResponse(ctx, participantID,
       "<Hint: The user has joined the conversation and is expecting a greeting>")
   ```
   (`conversation_handlers.go:L152`)
10. Send first message via `MessagingService`.
11. Return `201 Created`.

### 7.3 Identity in Flow Decisions

- `participantID` is the key for **all** `StateManager` operations.
- Phone number is passed via Go context key `phoneNumberContextKey` for messaging operations.
- Phone number from context is used by: `SchedulerTool` (recipient for schedules), debug messages, state transition messaging.
- Recovery uses phone-to-participantID mapping restored from hooks.

---

## 8. Tool Loop Contract

Both `IntakeModule` and `FeedbackModule` follow the same tool-calling loop pattern.

### 8.1 Loop Invariants

1. **Max rounds:** 10. If no user-facing content is produced in 10 rounds, return a fallback message.
2. **Termination on content:** If the LLM response contains non-empty `Content` (text), return it immediately as the assistant reply. The presence of content ends the loop.
3. **Tool execution:** If the LLM response contains tool calls but no content, execute all tool calls server-side, append tool results to the message context, and loop.
4. **Fallback:** If the LLM response has neither content nor tool calls, return a hardcoded fallback message.
5. **Error in tool execution:** Tool execution errors are returned as tool result messages to the LLM (not thrown). The LLM is expected to recover or inform the user.

### 8.2 Message Context Construction

For each round of the loop, the full message array sent to the LLM is:

```
[system prompt] + [context block] + [tone guide] + [chat history] + [user message] + [tool call/result pairs from this loop]
```

Tool call/result pairs accumulate within a single loop invocation (across rounds) but are **not** persisted to conversation history. Only the final assistant text response is persisted.

---

## 9. Behavioral Test Scenarios

### Scenario 1: Normal Intake Completion Flow

**Given** a newly enrolled participant with sub-state `"INTAKE"` and an empty `UserProfile`.
**When** the user sends a message describing their habit domain, motivation, preferred time, and prompt anchor across one or more exchanges.
**Then** the `IntakeModule` tool loop (`intake_module.go:L269`) calls `save_user_profile` to persist each field. Once the profile is complete (at minimum `PromptAnchor` and `PreferredTime`), the LLM calls `generate_habit_prompt` to produce an initial prompt, then calls `scheduler` to create a recurring schedule, and finally calls `transition_state` with `target_state="FEEDBACK"` to move the sub-state.
**Code path:** `processConversationMessage` (`conversation_flow.go:L292`) → sub-state is `"INTAKE"` → `processIntakeState` (`L811`) → `IntakeModule.ExecuteIntakeBotWithHistoryAndConversation` (`intake_module.go:L55`) → tool loop.

### Scenario 2: Missing Profile Repair

**Given** a participant in `"FEEDBACK"` sub-state whose `UserProfile` is missing `PromptAnchor` or `PreferredTime`.
**When** the `PromptGeneratorTool.ExecutePromptGenerator` is called (e.g., by a scheduled prompt).
**Then** it returns an error indicating missing required fields (`prompt_generator_tool.go:L302-L309`). The LLM in `FeedbackModule` may call `transition_state` with `target_state="INTAKE"` to return to intake and repair the profile.
**Code path:** `executeScheduledPrompt` (`scheduler_tool.go:L356`) → `PromptGeneratorTool.ExecutePromptGenerator` (`prompt_generator_tool.go:L65`) → validation fails.

### Scenario 3: Prompt Generation Path

**Given** a participant with a complete `UserProfile` (at least `PromptAnchor` and `PreferredTime` set).
**When** the LLM calls `generate_habit_prompt` with `delivery_mode="immediate"`.
**Then** `PromptGeneratorTool.ExecutePromptGenerator` (`prompt_generator_tool.go:L65`) validates the profile, constructs a prompt context from profile fields and `participantBackground`, calls the LLM with `prompts/prompt_generator_system.txt`, and stores the result in `DataKeyLastHabitPrompt`. Returns the generated prompt text.
**Code path:** `IntakeModule` tool loop → `executeIntakeToolCallsAndUpdateContext` → `PromptGeneratorTool.ExecutePromptGenerator`.

### Scenario 4: Feedback Collection Path

**Given** a participant in `"FEEDBACK"` sub-state.
**When** the user sends a message about how their habit went.
**Then** `processConversationMessage` (`conversation_flow.go:L292`) routes to `processFeedbackState` (`L847`). `FeedbackModule.ExecuteFeedbackTrackerWithHistoryAndConversation` (`feedback_module.go:L103`) runs its tool loop. The LLM may call `save_user_profile` to update `LastBarrier`, `LastTweak`, `LastSuccessfulPrompt`, or `LastMotivator`. After the response is generated, `CancelPendingFeedback` (`L521`) cancels any outstanding feedback timers.
**Code path:** `processConversationMessage` → `processFeedbackState` (`L847`) → `FeedbackModule` tool loop → `CancelPendingFeedback` (`L521`).

### Scenario 5: State Transition with Delay

**Given** a participant in `"INTAKE"` sub-state.
**When** the LLM calls `transition_state` with `target_state="FEEDBACK"` and `delay_minutes=30`.
**Then** `StateTransitionTool` (`state_transition_tool.go`) does NOT immediately update `DataKeyConversationState`. Instead it calls `scheduleDelayedTransition`, which creates a durable job (dedup key `"state_transition:{participantID}"`) or in-memory timer. The timer ID is stored in `DataKeyStateTransitionTimerID`. After 30 minutes, the job fires and executes an immediate transition to `"FEEDBACK"`.
**Code path:** Module tool loop → `StateTransitionTool` → `scheduleDelayedTransition`.

### Scenario 6: Daily Prompt → Reminder → User Reply Cancels Reminder

**Given** a participant with an active schedule. A daily prompt has just been delivered.
**When** `executeScheduledPrompt` (`scheduler_tool.go:L356`) completes.
**Then** `scheduleDailyPromptReminder` (`L563`) stores pending state in `DataKeyDailyPromptPending` and sets a timer for 5 hours.
**When** the user replies before 5 hours elapse.
**Then** `processConversationMessage` calls `handleDailyPromptReply` (`L653`). It validates the reply timestamp > sent timestamp, cancels the reminder timer/job, clears `DataKeyDailyPromptPending`, and records `DataKeyDailyPromptRespondedAt`.
**Code path:** `executeScheduledPrompt` → `scheduleDailyPromptReminder` → (user replies) → `processConversationMessage` (`L292`) → `handleDailyPromptReply` (`L653`).

### Scenario 7: Reminder Fires, Then User Replies (Late Reply)

**Given** a daily prompt was sent and the 5-hour reminder delay has elapsed without user reply.
**When** the reminder timer fires.
**Then** `sendDailyPromptReminder` (`scheduler_tool.go:L710`) verifies the pending state still matches the expected `SentAt` timestamp. Sends the default reminder message. Records `DataKeyDailyPromptReminderSentAt`. Clears `DataKeyDailyPromptPending`.
**When** the user later replies.
**Then** `handleDailyPromptReply` (`L653`) finds `DataKeyDailyPromptPending` is empty (already cleared by the reminder). No cancellation is needed. The reply is processed normally by the conversation flow.
**Code path:** Timer fires → `sendDailyPromptReminder` (`L710`) → (user replies later) → `handleDailyPromptReply` finds no pending state.

### Scenario 8: Intensity Adjustment — Once Per Day

**Given** a daily prompt has just been sent and `DataKeyLastIntensityPromptDate` is empty or set to a previous date.
**When** `checkAndSendIntensityAdjustment` (`scheduler_tool.go:L500`) runs after `executeScheduledPrompt`.
**Then** it computes today's date in the participant's timezone, compares with `DataKeyLastIntensityPromptDate`. If different (or empty), it sends the intensity adjustment poll and writes today's date to `DataKeyLastIntensityPromptDate` (`L556`).
**When** a second prompt is sent on the same day.
**Then** `checkAndSendIntensityAdjustment` finds `DataKeyLastIntensityPromptDate` equals today's date and skips the poll.
**Code path:** `executeScheduledPrompt` → `checkAndSendIntensityAdjustment` (`L500`) → date comparison → skip or send.

### Scenario 9: Debug Mode Behavior

**Given** `SetDebugMode(true)` has been called on `ConversationFlow` (`conversation_flow.go:L635`).
**When** a user message is processed.
**Then** debug messages prefixed with `"🐛 DEBUG:"` are sent via `msgService` as separate messages. Debug info includes current sub-state and profile summary (`conversation_flow.go:L750-L781`). Individual modules also send debug messages about tool execution. Debug mode is propagated to modules via `SetDebugModeInContext` (`conversation_flow.go:L38`).
**Code path:** `processConversationMessage` → debug checks → `msgService.SendMessage` for debug output.

### Scenario 10: Tool Failure and State Save Failure Fallbacks

**Given** a participant in `"INTAKE"` sub-state. The `ProfileSaveTool` or `SchedulerTool` encounters a transient error during execution.
**When** a tool call fails.
**Then** the error is returned as a tool result message (error string) to the LLM within the tool loop. The LLM receives the error context and is expected to either retry, inform the user, or adjust its approach. The loop continues to the next round.
**When** `saveConversationHistory` (`conversation_flow.go:L437`) fails to persist state.
**Then** the error is logged but does NOT prevent the assistant response from being returned to the user. The response is still delivered; the history loss is a degraded-but-functional state.
**Code path:** Tool loop → tool execution error → error string returned as `ToolResult` → LLM continues. History save → error logged → response returned.

### Scenario 11: Auto-Feedback Enforcement After Prompt

**Given** a participant with `autoFeedbackEnabled=true`. A daily prompt has just been sent.
**When** `executeScheduledPrompt` completes.
**Then** `scheduleAutoFeedbackEnforcement` (`scheduler_tool.go:L444`) creates a 5-minute timer (dedup key `"auto_feedback:{participantID}"`). Timer ID stored in `DataKeyAutoFeedbackTimerID`.
**When** 5 minutes elapse without user reply.
**Then** `enforceFeedbackIfNoResponse` (`L769`) checks: (a) if already in `FEEDBACK` state → skips; (b) if a newer prompt was sent within ~4.5 minutes → skips. Otherwise, writes `"FEEDBACK"` to `DataKeyConversationState`.
**When** the user replies before 5 minutes.
**Then** `StateTransitionTool` immediate transition (or any sub-state write) cancels the pending auto-feedback timer by clearing `DataKeyAutoFeedbackTimerID`.
**Code path:** `executeScheduledPrompt` (`L356`) → `scheduleAutoFeedbackEnforcement` (`L444`) → timer → `enforceFeedbackIfNoResponse` (`L769`).

### Scenario 12: Tone Update — Explicit vs Implicit, Rate Limiting

**Given** a participant with an existing `UserProfile.Tone` having `Scores = {"concise": 0.8}` and `LastUpdatedAt = 2 minutes ago`.
**When** the LLM calls `save_user_profile` with `tone_tags=["concise","warm_supportive"]`, `tone_update_source="implicit"`, `tone_confidence=0.9`.
**Then** `parseToneProposal` (`profile_save_tool.go:L368-L405`) extracts the proposal. `tone.ValidateProposal` (`tone.go:L84`) strips invalid tags. `tone.UpdateProfileTone` (`tone.go:L121`) checks the rate limit: `LastUpdatedAt` was 2 minutes ago, which is < 3 minutes minimum → the implicit update is **rejected** (skipped).
**When** the same proposal arrives 4 minutes after `LastUpdatedAt`.
**Then** the rate limit passes. EMA is applied: `concise` score = `(1-0.15)*0.8 + 0.15*1.0 = 0.83`. `warm_supportive` (not previously scored) gets `0.15*1.0 = 0.15`. Non-observed tags decay: `score = (1-0.15)*old`. Tags with score ≥ 0.7 are activated; ≤ 0.4 deactivated; between = unchanged (hysteresis).
**When** the LLM calls with `tone_update_source="explicit"`.
**Then** the update is applied immediately regardless of rate limit. Scores are set directly to proposed values (no EMA).
**Code path:** `ProfileSaveTool` → `parseToneProposal` (`L368`) → `tone.ValidateProposal` (`L84`) → `tone.UpdateProfileTone` (`L121`).

---

## 10. Handoff Notes

### 10.1 Must Reproduce Exactly

These behaviors are load-bearing contracts. A replacement implementation must match them:

| Behavior | Key locations |
|---|---|
| Sub-state routing via `DataKeyConversationState` (not `CurrentState`) | `conversation_flow.go:L292-L400` |
| Tool loop: max 10 rounds, terminate on content, fallback on exhaustion | `intake_module.go:L269`, `feedback_module.go:L553` |
| Profile field-by-field merge (only update if non-empty AND different) | `profile_save_tool.go` |
| Tone whitelist enforcement and EMA smoothing (α=0.15, thresholds 0.7/0.4) | `tone.go:L74-L76`, `L84-L239` |
| Daily prompt reminder scheduling and cancellation on reply | `scheduler_tool.go:L563-L710` |
| History trimming: 50 stored, 30–50 sent to LLM | `conversation_flow.go:L437-L492` |
| Auto-feedback enforcement (5-minute timer) | `scheduler_tool.go:L444-L769` |
| Intensity adjustment at most once per day | `scheduler_tool.go:L500-L556` |
| `PromptAnchor` and `PreferredTime` mandatory for prompt generation | `prompt_generator_tool.go:L302-L309` |
| Legacy `last_blocker` → `last_barrier` alias in profile save | `profile_save_tool.go` |
| Mutual exclusion enforcement for tone pairs | `tone.go:L37-L41`, `L196-L206` |
| `no_emojis` overrides `emojis_ok` | `tone.go:L191-L193`, `L224-L226` |

### 10.2 Incidental Behaviors (May Be Changed)

These are implementation details that a replacement may freely alter:

- Exact fallback message text (e.g., "I'm here to help…")
- Debug message formatting and `"🐛 DEBUG:"` prefix
- Timer ID format and generation method
- Exact log levels and `slog` messages
- Recovery manager implementation (`conversation_flow_recovery.go`)
- Coordinator module code (exists but is not wired)
- Exact wording of the daily prompt reminder message

### 10.3 Implicit Assumptions

These assumptions are not enforced by code contracts but are relied upon throughout the implementation:

1. **Single-threaded per participant.** No concurrent message handling for the same participant. There is no locking or optimistic-concurrency mechanism.
2. **Phone number always in context.** Messaging operations assume `phoneNumberContextKey` is set in the Go context.
3. **StateData values are always strings.** Structured data is JSON-serialized. Empty string from `GetStateData` means "not set" (not an error).
4. **Timezone defaults.** `"America/Toronto"` for fixed schedules, `"UTC"` for random schedules.
5. **UserProfile intensity defaults to `"normal"`.** `GetOrCreateUserProfile` (`profile_save_tool.go:L275`) creates profiles with `Intensity="normal"`.
6. **Timestamps use Go's default JSON marshaling.** `time.Time` fields serialize as RFC3339 via `json.Marshal`.
7. **Tool result errors are informational.** They are passed back to the LLM as string messages, not thrown as Go errors that abort the flow.
