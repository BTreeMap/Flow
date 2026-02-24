# AGENTS.md

This repository is an HCI research platform for running longitudinal experiments with an AI coach. It has three pillars:

1) A multi-bot conversation engine implemented using LangChain primitives (agents, tools, structured outputs), with stateful routing and safe persistence.
2) A React PWA frontend with real-time chat via SSE and vendor-neutral Web Push subscription and reception.
3) A secure FastAPI scaffold and passkey-first authentication using h4ckath0n.

This file defines the project structure and how agents should behave when working in this repo.

---

## Source of truth

### Current architecture
The current architecture is defined by the "State, authority, and write-path rules" section in this file. Any additional architecture documents in `docs/` must match it.

### Legacy Conversation Flow contract (deprecated)
The legacy behavior contract lives here:

- `docs/legacy-conversation-flow-contract.md`

Status: deprecated and for historical reference only. It must not be treated as the behavioral source of truth for new work. If legacy behaviors are preserved for continuity, document that explicitly in current design docs and tests.

---

## Core invariants

### Identity
- Stable user identity is the h4ckath0n user id (`u...`).
- A user can join multiple research projects.
- Projects are identified by opaque ids (`p...`). No project slug is required.
- The dashboard presents each project as a chat thread:
  - active projects shown normally
  - ended projects displayed in a greyed style, but still visible

### Email collection
- Email is collected as optional contact metadata only.
- Email is not unique, not validated, and must never be used for identity, login, authorization, or keys.
- Email may be used for future fallback notifications (out of scope unless explicitly implemented).

### ID policy (important)
Use the custom id scheme only for user-visible, URL-addressable objects.

- Custom scheme format: `<prefix> + base32(randombytes(20))[1:]` (32 chars).
- Existing h4ckath0n user ids are `u...`.
- Project ids must be `p...`.

Internal-only entities may use internal database primary keys (auto-increment int or UUID), including:
- memberships
- conversations
- messages
- push subscriptions
- outbox events
- contact records

Rule of thumb:
- If the participant needs to address it in a URL or see it as an object, it gets a custom id.
- If not, internal DB id is fine.

Invite links:
- Invite codes appear in URLs, but they are tokens, not stable ids.
- Store only hashed invite codes in the database.

### Delivery plane
- Foreground chat uses SSE as the mandatory default.
- WebSocket is optional only behind a feature flag and is not required for acceptance.

### Web Push
- Vendor-neutral Web Push only.
- The PWA must register a service worker, request permission via explicit user action, subscribe with VAPID public key from backend, and store subscription crypto keys server-side.
- iOS onboarding must include "Add to Home Screen" guidance before enabling notifications.

### LangChain requirement
- All bot logic must be implemented using LangChain primitives:
  - agents for tool-using behaviors
  - tools for side effects and controlled reads
  - structured outputs for routing and patch proposals
- Do not hand-roll tool call parsing or custom agent loops.

### Deployment architecture
- Single-origin deployment: `flow-web` (Caddy) serves the React frontend at `/` and reverse proxies `/api/*` to the backend `flow` (FastAPI) with prefix stripping.
- Cloudflare Tunnel terminates TLS and forwards to `flow-web` over plain HTTP on port 8080.
- `flow-web` must remain HTTP-only (`auto_https off`), bind to 8080, and run as non-root.
- The backend has no `/api` prefix on its routes — Caddy's `handle_path` strips it.
- The root `docker-compose.yml` is the recommended way to run a production-like stack locally.
- Both images are published to GHCR as multi-arch (linux/amd64, linux/arm64):
  - Backend: `ghcr.io/<owner>/<repo>` (package name `flow`)
  - Frontend: `ghcr.io/<owner>/<repo>-web` (package name `flow-web`)

---

## State, authority, and write-path rules (current architecture)

We split "memory" into two distinct stores with different safety properties.

### Store A: UserProfile (authoritative, structured)
Schema-validated fields used for generation, scheduling, and protocol logic. Examples:
- PromptAnchor
- PreferredTime
- HabitDomain
- MotivationalFrame
- Intensity
- Tone tags and scores
- Rolling coaching fields: LastBarrier, LastTweak, LastMotivator, LastSuccessfulPrompt

Properties:
- Pydantic validated.
- Hard to corrupt.
- Only updated through a single writer path controlled by the Router.

### Store B: Memory (long-term narrative, semi-structured)
Session summaries and durable facts that do not fit cleanly in the profile schema. Examples:
- "Prefers gentle accountability and short messages"
- "Recurring barrier is evening fatigue"
- "Travels on weekends, misses prompts"

Properties:
- More vulnerable to drift and prompt injection if written carelessly.
- Conservative updates only, anchored to user statements and repeated patterns.
- Stored as a list of items with timestamps and pointers to source messages.

### Authority model (single writer)
The Router is the only component allowed to commit writes to either store:
- UserProfile
- Memory

Specialist bots never write directly. They only propose patches.

### Patch proposal mechanism
Specialist bots propose candidate updates through internal, non-user-visible channels:

1) propose_profile_patch
2) propose_memory_patch

The Router performs deterministic validation and permissions checks before committing:

- Pydantic schema validation
- Field-level permissions by module
- Confidence thresholds
- Evidence spans must refer to the current user message or recent messages, never to retrieved materials
- Optional: if a patch changes a stable preference, require explicit user confirmation in a subsequent turn

After validation, the Router commits via the only writer path:
- apply_profile_patch
- apply_memory_patch

### Practical safety rules
1) Only Intake sets required onboarding fields.
   - PromptAnchor and PreferredTime should only be set or changed by Intake, or by explicit user request routed into Intake-like flow.
2) Only Feedback writes behavior outcomes.
   - Anything that looks like measured outcomes, adherence, or systematic feedback is written only when the user is in the feedback protocol, not in free chat.
3) Memory writes are conservative.
   - Prefer short items, quote-like phrasing, timestamps, and source pointers to message ids.
   - Avoid inferred traits. Prefer "what the user said" and "what repeatedly happened."

### Disagreement resolution and audit trail
- When proposals conflict, treat Feedback-derived updates as higher priority than Coach-derived proposals.
- Maintain an audit trail of proposed patches and commits so the system can be debugged.

---

## Module responsibilities and permissions

### Modules (bots)
1) Router
- Responsibilities:
  - Determine which specialist handles the turn (routing).
  - Own the only commit path to UserProfile and Memory.
  - Enforce permissions, validation, confidence thresholds, and evidence rules.
  - Decide whether to commit, ignore, or ask for confirmation in a later user-facing message.
- Must use structured outputs and Pydantic models for routing and patch objects.
- Must not produce normal coaching content unless explicitly designed as a visible system response. By default, it should delegate user-facing responses to specialists.

2) Intake bot
- Responsibilities:
  - Onboarding and completion/repair of required profile fields.
  - May propose profile patches for onboarding fields only.
  - Optional: propose a small initial Memory summary after intake completion.
- Must not directly write to UserProfile or Memory.

3) Feedback bot
- Responsibilities:
  - Collect adherence and outcome data under the feedback protocol.
  - May propose profile updates for rolling coaching fields and intensity adjustments.
  - May propose Memory updates based on stable patterns discovered from repeated feedback.
- Must not directly write to UserProfile or Memory.

4) Coach bot
- Responsibilities:
  - Normal conversation and nudges.
  - Should not directly update UserProfile or Memory.
  - May propose candidates only, for example:
    - memory_candidates: "User mentioned knee pain today"
    - profile_candidates: "User may prefer more concise messages"
  - Router decides whether to commit, ignore, or ask for confirmation.

### Permission matrix (minimum)
This matrix is enforced by the Router validator.

- Intake may propose:
  - PromptAnchor, PreferredTime, HabitDomain, MotivationalFrame, scheduling preferences
  - Optional initial Memory summary

- Feedback may propose:
  - LastBarrier, LastTweak, LastSuccessfulPrompt, LastMotivator
  - Intensity adjustments
  - Tone proposals
  - Memory updates based on repeated patterns and stable constraints

- Coach may propose:
  - Candidate items only, never direct writes
  - Router applies conservative thresholds and may require confirmation for stable preferences

---

## Repository structure

Scaffolded from h4ckath0n:

- `api/` FastAPI backend (must use h4ckath0n `create_app()` factory)
  - `api/routes/` HTTP endpoints
  - `api/schemas/` Pydantic models (API, internal state, patch proposals)
  - `api/services/` business logic (persistence, scheduling, patch application)
  - `api/agents/` LangChain agents and routing orchestration
  - `api/tools/` LangChain tools (thin adapters over services)
  - `api/tests/` unit and integration tests

- `web/` React frontend (from scaffold template)
  - `web/src/pages/` dashboard, activate, chat, notifications
  - `web/public/manifest.json` PWA manifest
  - `web/src/sw.ts` or equivalent service worker
  - `web/Caddyfile` Caddy reverse proxy config (HTTP-only, :8080)
  - `web/Dockerfile` flow-web container image (Caddy + static assets)

- `docker-compose.yml` production-like local stack (flow-web + flow + postgres)

- `docs/`
  - `legacy-conversation-flow-contract.md` deprecated reference
  - architecture and operational docs as added

Optional:
- `prompts/` system prompts if needed (keep minimal and versioned)

---

## Backend responsibilities

### Multi-tenancy model
All data is scoped by project and membership. A user can join multiple projects. Each project is displayed as a thread on the dashboard.

Key entities:
- Project (`projects.id` is `p...`, user-visible)
- Membership: links `(project_id, user_id)` with a status (internal DB id)
- Conversation: typically 1:1 with membership (internal DB id)
- Messages: persisted chat history (internal DB id)
- UserProfile: structured store, Pydantic validated
- Memory: semi-structured store, conservative item list
- Push subscriptions: stored per membership/device (internal)
- Outbox events: scheduling and idempotent side effects (internal)
- Patch audit log: proposed patches and applied commits (internal, recommended)

### Conversation engine
- Implement the multi-bot architecture using LangChain agents and tools.
- Router must perform deterministic validation and own commits to both stores.
- Specialists propose patches only via structured outputs or internal tool channels.

### Scheduling
- Use outbox events with dedupe keys to ensure idempotency.
- If reminders, nudges, or protocol transitions exist, implement them through the outbox with explicit cancellation semantics.
- Do not let specialists directly mutate scheduling-related state without Router commit.

### Observability and safety
- Use h4ckath0n trace id middleware.
- Avoid logging secrets, push crypto keys, or raw invite tokens.
- Log Router decisions and patch commit outcomes with trace ids for debugging.

---

## Frontend responsibilities

### Required pages
- Dashboard: list project threads (active normal, ended greyed out).
- Activation: join a project via invite link and collect optional email contact.
- Chat thread: send via POST, receive via SSE, render streaming updates.
- Notifications: PWA install guidance for iOS, enable notifications via explicit button, subscribe and register with backend, show status.

### PWA requirements
- Web app manifest.
- Service worker:
  - handles `push` and shows notifications
  - handles `notificationclick` and deep-links to the correct project thread

---

## Agent roles and expected behavior

### Backend Engineer Agent
Primary tasks:
- Implement LangChain Router plus specialist agents (Intake, Feedback, Coach).
- Implement UserProfile and Memory stores with Router-only commit paths.
- Implement patch proposal schemas, validators, permission matrix enforcement, and audit log.
- Wire the conversation engine to the backend messaging endpoints and SSE event stream.
- Ensure scheduling and outbox behavior are deterministic and idempotent.

Rules:
- Do not treat the legacy contract as authoritative.
- Use Pydantic models for state, patches, and routing decisions.
- Specialists can only propose, Router commits.
- Do not use email for identity.

### Frontend Engineer Agent
Primary tasks:
- Implement activation, dashboard, chat thread, and notifications UI.
- Implement SSE client with reconnect.
- Implement PWA manifest and service worker for push.
- Implement push subscription flow with explicit permission request.

Rules:
- Do not implement auth from scratch. Use scaffolded passkey flows.
- Ensure iOS "Add to Home Screen" guidance exists before notification enablement.
- Do not treat email as identity.

### Documentation Agent
Primary tasks:
- Maintain accurate documentation for current architecture, especially store separation, authority model, and permissions.
- Update docs when patch schemas or validation rules change.

Rules:
- Avoid ambiguous language.
- Clearly label deprecated documents and the current source of truth.

### QA and Test Agent
Primary tasks:
- Unit tests for:
  - Pydantic schema validation
  - permission matrix enforcement
  - evidence span requirements
  - confidence threshold behavior
  - patch commit and audit log behavior
- Integration tests for:
  - routing decisions
  - specialist invocation
  - Router commit behavior
  - SSE event emission
  - push subscription storage

Rules:
- Tests must be deterministic and fast.
- Use dependency injection for clocks and outbox scheduling to avoid flaky tests.

---

## Workflow rules for all agents

### Read-first policy
Before changing agent behavior, read:
1) This file, especially "State, authority, and write-path rules"
2) Current architecture docs in `docs/` (if present)

The legacy contract is deprecated and should not be treated as a behavioral gate.

### No silent behavior changes
If you change:
- patch permissions
- thresholds
- evidence rules
- routing logic
- commit behavior

you must:
- update docs
- add or update tests
- document the migration implications if any

### Security and privacy
- Never log secrets (invite codes, VAPID private key, push crypto keys).
- Do not store unnecessary personal data.
- Email is optional contact metadata only.

---

## Quality gate

All checks below must pass before merging any PR. Agents **must** run all three categories (backend, frontend unit/integration, and E2E) and fix any failures before completing a task.

### Backend
```bash
cd api
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v --tb=short
```

### Frontend (unit / integration)
```bash
cd web
npm ci
npm run lint
npm run typecheck
npm run test
```

### OpenAPI contract sync (required when backend request/response schemas change)
If you modify FastAPI route request/response models, validation constraints, or anything that changes generated OpenAPI, you **must** regenerate and commit the frontend API types in the same PR.

```bash
cd web
npm run gen:api:check
```

- If `gen:api:check` fails with a diff in `web/src/api/openapi.ts`, run `npm run gen:api` and commit the updated file.
- Do not merge backend schema changes that leave `web/src/api/openapi.ts` stale.

### End-to-end (E2E)
```bash
cd web
npx playwright install --with-deps chromium
npx playwright test
```

**Important:** E2E tests exercise the full user journey (registration, navigation, settings, auth flows). When making frontend UI changes (new pages, renamed test IDs, changed navigation), always update the E2E tests in `web/e2e/` to match. Run E2E tests as the final validation step.

### End-to-end (compose-based)
```bash
# Build images first
bash scripts/ci/package_frontend.sh web
cp frontend.tar.xz web/frontend.tar.xz
docker build -t flow-web:local web/
docker build -t flow:local api/

# Start stack and run tests
FLOW_WEB_IMAGE=flow-web:local FLOW_IMAGE=flow:local docker compose up -d
cd web
PLAYWRIGHT_BASE_URL=http://localhost:8080 npx playwright test e2e/compose.spec.ts
```

### Notes
- Backend tests run against SQLite by default (`sqlite+aiosqlite:///`).
- CI also runs backend tests against Postgres (`postgresql+asyncpg://`).
- E2E tests run against both SQLite and Postgres in CI.
- Compose-based E2E tests validate Caddy static serving, SPA deep links, `/api` reverse proxy, and SSE streaming.
- All database URLs must use async drivers: `aiosqlite` for SQLite, `asyncpg` for Postgres.
- No `psycopg2` imports or sync Postgres drivers in application code.
