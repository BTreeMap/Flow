# Flow: HCI Research Platform

A production-shaped prototype for HCI research combining a multi-bot conversation engine built on LangChain primitives, React PWA frontend, passkey-first authentication (via [h4ckath0n](https://github.com/BTreeMap/h4ckath0n)), SSE-based real-time chat, and vendor-neutral Web Push notifications.

## Architecture Overview

| Pillar | Stack | Description |
|--------|-------|-------------|
| **Backend** | FastAPI + h4ckath0n + SQLAlchemy 2.x | Async API with passkey auth, multi-tenant project model, and SSE fan-out |
| **Conversation Engine** | LangChain agents + Router | Multi-bot architecture: Router (single writer) + Intake/Feedback/Coach specialists with proposal/commit flow |
| **Frontend** | React 19 + Vite + Tailwind CSS | PWA with service worker, SSE streaming chat, and Web Push notification support |

### Conversation Engine Architecture

The engine uses a **Router + specialist** architecture:

- **Router** — Routes each turn to the correct specialist, validates all patch proposals, and owns the only commit path to UserProfile (Store A) and Memory (Store B).
- **Intake Bot** — Onboarding and profile setup. Can propose updates to onboarding fields.
- **Feedback Bot** — Habit tracking and barrier analysis. Can propose rolling coaching field updates and memory items.
- **Coach Bot** — Normal conversation and encouragement. Can propose candidates only (higher confidence threshold).

All bots use LangChain agents and tools. Proposals are validated against a permission matrix with confidence thresholds and evidence span requirements. See [`docs/current-architecture.md`](docs/current-architecture.md) for full details.

## Quick Start

### Docker Compose (recommended)

The recommended way to run a production-like stack locally:

```bash
# Build the frontend artifact
bash scripts/ci/package_frontend.sh web
cp frontend.tar.xz web/frontend.tar.xz

# Build local images
docker build -t flow-web:local web/
docker build -t flow:local api/

# Start the stack
FLOW_WEB_IMAGE=flow-web:local FLOW_IMAGE=flow:local docker compose up
```

The stack runs at `http://localhost:8080`. Caddy serves the frontend and reverse proxies `/api/*` to the backend (stripping the `/api` prefix).

#### Deployment architecture

```
Cloudflare Tunnel (terminates TLS)
  └─→ flow-web :8080 (Caddy, HTTP-only)
        ├─ /          → static frontend files
        └─ /api/*     → flow :8000 (prefix stripped)
```

- **flow-web** is HTTP-only — TLS is terminated by Cloudflare Tunnel (or any upstream TLS terminator).
- The backend has no `/api` prefix on its routes. Caddy's `handle_path` strips it before proxying.

#### With PostgreSQL

```bash
FLOW_WEB_IMAGE=flow-web:local FLOW_IMAGE=flow:local \
  H4CKATH0N_DATABASE_URL=postgresql+asyncpg://flow:flow@postgres:5432/flow \
  docker compose --profile postgres up
```

### Development (Vite dev server)

#### Backend

```bash
cd api
uv sync
# Copy .env.example to .env and configure
cp ../.env.example ../.env
uv run uvicorn app.main:app --reload
```

#### Frontend (in another terminal)

```bash
cd web
npm install
npm run dev
```

The frontend dev server runs at `http://localhost:5173` and proxies API requests to the backend.

To run real LLM responses instead of stub mode, set `OPENAI_API_KEY` (or `H4CKATH0N_OPENAI_API_KEY`) in your root `.env` before starting the backend. Keep this value secret and never commit it.

### Runtime configuration warnings

- Missing `OPENAI_API_KEY` / `H4CKATH0N_OPENAI_API_KEY` → chat runs in **stub mode**.
- Missing `VAPID_PUBLIC_KEY` or `VAPID_PRIVATE_KEY` → **push notifications are disabled**.

### VAPID Web Push configuration

Flow uses standard Web Push VAPID keys for push subscription and delivery.

Required environment variables:

- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`

Generate keys (example using Python `py_vapid`):

```bash
python -m pip install py-vapid
python -m py_vapid --gen
```

Copy the generated public/private keys into `.env`.

## Project Structure

```
Flow/
├── api/                          # FastAPI backend
│   ├── app/
│   │   ├── main.py               # App entry point (h4ckath0n create_app)
│   │   ├── routes.py             # API route handlers
│   │   ├── models.py             # SQLAlchemy 2.x models (incl. UserProfile, Memory, AuditLog)
│   │   ├── db.py                 # Database session management
│   │   ├── middleware.py         # CSP and other middleware
│   │   ├── id_utils.py           # Custom ID generation (p... / u...)
│   │   ├── agents/               # NEW: Multi-bot LangChain agents
│   │   │   ├── engine.py         # Turn engine: Router + specialist pipeline
│   │   │   ├── router.py         # Routing coordinator (structured output)
│   │   │   ├── intake.py         # Intake specialist agent
│   │   │   ├── feedback.py       # Feedback specialist agent
│   │   │   ├── coach.py          # Coach specialist agent
│   │   │   └── orchestrator.py   # Legacy orchestrator (backward compat)
│   │   ├── schemas/              # Pydantic models
│   │   │   ├── router.py         # RouteDecision (INTAKE/FEEDBACK/COACH)
│   │   │   ├── patches.py        # Proposals, evidence, permissions, profile/memory schemas
│   │   │   └── tool_schemas.py   # Legacy tool argument schemas
│   │   ├── services/             # NEW: Business logic layer
│   │   │   └── profile_service.py # Profile/memory persistence, validation, audit
│   │   ├── tools/                # LangChain tools
│   │   │   ├── proposal_tools.py # NEW: propose_profile_patch, propose_memory_patch
│   │   │   └── langchain_tools.py # Legacy tool wrappers
│   │   └── engine/               # Legacy conversation engine (deprecated for new work)
│   │       ├── flow.py           # Legacy orchestrator
│   │       ├── modules.py        # IntakeModule, FeedbackModule, tool loop
│   │       ├── state.py          # State enums, Pydantic models, DataKeys
│   │       ├── tools.py          # Tool implementations
│   │       ├── scheduler.py      # Daily prompts, reminders, auto-feedback
│   │       └── tone.py           # Tone adaptation (EMA, hysteresis, whitelist)
│   ├── Dockerfile                # Backend container image
│   ├── prompts/                  # System prompt templates
│   ├── tests/                    # Backend test suite
│   └── pyproject.toml
├── web/                          # React PWA frontend
│   ├── Caddyfile                 # Caddy reverse proxy config (HTTP-only, :8080)
│   ├── Dockerfile                # flow-web container image (Caddy + static assets)
│   ├── public/
│   │   ├── manifest.json         # PWA web app manifest
│   │   └── sw.js                 # Service worker (push + notificationclick)
│   ├── src/
│   │   ├── App.tsx               # Route definitions
│   │   ├── pages/                # Page components
│   │   │   ├── Dashboard.tsx     # Project thread list
│   │   │   ├── Activation.tsx    # Join project via invite link
│   │   │   ├── ChatThread.tsx    # Real-time chat with SSE
│   │   │   ├── Notifications.tsx # Push notification management
│   │   │   ├── Landing.tsx       # Public landing page
│   │   │   ├── Login.tsx         # Passkey login
│   │   │   ├── Register.tsx      # Passkey registration
│   │   │   └── Settings.tsx      # User settings
│   │   ├── auth/                 # Passkey auth (from h4ckath0n scaffold)
│   │   ├── api/                  # API client and types
│   │   ├── components/           # Shared UI components
│   │   └── gen/                  # Generated OpenAPI TypeScript client
│   └── package.json
├── docker-compose.yml            # Production-like local stack (flow-web + flow + postgres)
├── docs/
│   ├── current-architecture.md           # NEW: Current architecture (authoritative)
│   ├── legacy-conversation-flow-contract.md   # DEPRECATED: Legacy behavior reference
│   └── parity-matrix.md                       # Legacy → new code mapping
├── .env.example
└── AGENTS.md                     # Agent behavior rules
```

## API Endpoints

All project-scoped endpoints require passkey authentication.

| Method | Path | Tag | Description |
|--------|------|-----|-------------|
| `GET` | `/healthz` | infra | Readiness probe |
| `GET` | `/dashboard` | dashboard | List user's project memberships |
| `POST` | `/p/{project_id}/activate/claim` | activation | Claim invite code, create membership + conversation |
| `GET` | `/p/{project_id}/me` | activation | Get membership status, conversation ID, stored email |
| `POST` | `/p/{project_id}/messages` | messaging | Send message, get assistant reply |
| `GET` | `/p/{project_id}/events` | streaming | SSE event stream for real-time updates |
| `GET` | `/p/{project_id}/push/vapid-public-key` | push | Get VAPID public key for push subscription |
| `POST` | `/p/{project_id}/push/subscribe` | push | Store a push subscription |
| `POST` | `/p/{project_id}/push/unsubscribe` | push | Revoke a push subscription |
| `GET` | `/demo/ping` | demo | Liveness ping |
| `POST` | `/demo/echo` | demo | Echo with reverse |
| `GET` | `/demo/sse` | demo | Authenticated SSE demo stream |
| `WS` | `/demo/ws` | demo | Authenticated WebSocket demo |

## Data Model

| Table | ID Type | Description |
|-------|---------|-------------|
| `projects` | `p...` (custom, 32 chars) | User-visible research projects |
| `project_invites` | auto-increment int | Hashed invite codes with expiry |
| `project_memberships` | auto-increment int | Links (project, user) with status; unique constraint |
| `participant_contacts` | auto-increment int | Optional email contact metadata (not used for identity) |
| `conversations` | auto-increment int | 1:1 with membership |
| `messages` | auto-increment int | Chat history with `server_msg_id` (36-char string: `msg_` + 32 lowercase base32 chars; UUID-length for DB schema compatibility) |
| `conversation_runtime_state` | FK to conversation | JSON blob for engine state |
| `user_profiles` | auto-increment int | **Store A** — structured profile JSON (1:1 with membership) |
| `memory_items` | auto-increment int | **Store B** — semi-structured memory items per membership |
| `patch_audit_log` | auto-increment int | Audit trail: proposals, decisions, commits |
| `push_subscriptions` | auto-increment int | Web Push endpoints + crypto keys per device |
| `outbox_events` | auto-increment int | Durable scheduled events with dedupe keys |

## Conversation Engine

The engine implements the architecture defined in [`docs/current-architecture.md`](docs/current-architecture.md).

### Turn Pipeline

1. Persist user message
2. Load UserProfile (Store A) + Memory (Store B) + recent chat history
3. Router decides which specialist to run (INTAKE, FEEDBACK, or COACH)
4. Invoke specialist agent (LangChain tool-calling agent)
5. Collect patch proposals made during the agent run
6. Router validates proposals (permissions, confidence, evidence) and commits approved ones
7. Persist assistant message
8. Emit SSE events for UI update

### Routing

| Condition | Route |
|-----------|-------|
| Required onboarding fields missing | INTAKE |
| Currently in feedback protocol | FEEDBACK |
| Profile complete, normal conversation | COACH |

### Proposal + Commit Flow

Specialist bots propose changes via `propose_profile_patch` and `propose_memory_patch` tools. The Router validates each proposal against:

- **Permission matrix**: Intake → onboarding fields, Feedback → coaching fields, Coach → candidates only
- **Confidence thresholds**: INTAKE/FEEDBACK ≥ 0.5, COACH ≥ 0.8
- **Evidence spans**: Must reference recent message IDs
- **Memory rules**: Items ≤ 500 chars with source pointers

All proposals and decisions are logged in the `patch_audit_log` table.

### Legacy Engine

The legacy conversation flow engine (`api/app/engine/`) is retained for backward compatibility. The legacy behavioral contract (`docs/legacy-conversation-flow-contract.md`) is deprecated.

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Landing | Public landing page |
| `/register` | Register | Passkey registration |
| `/login` | Login | Passkey login |
| `/dashboard` | Dashboard | List project threads (active/ended) |
| `/p/:projectId/activate` | Activation | Join project via invite link, collect optional email |
| `/p/:projectId/chat` | ChatThread | Send messages via POST, receive via SSE |
| `/p/:projectId/notifications` | Notifications | PWA install guidance, enable push notifications |
| `/settings` | Settings | User settings |

## PWA & Push Notifications

- **Web App Manifest** — `web/public/manifest.json` enables "Add to Home Screen"
- **Service Worker** (`web/public/sw.js`):
  - Handles `push` events → shows system notifications
  - Handles `notificationclick` → deep-links to the relevant project chat (`/p/{project_id}/chat`)
- **Subscription flow**: explicit user action → request permission → subscribe with VAPID public key from backend → store subscription server-side
- **iOS**: "Add to Home Screen" guidance is shown before enabling notifications

## Tests

### Backend

```bash
cd api && uv run python -m pytest tests/ -v
```

Test modules:

- `test_api.py` — API endpoint integration tests (messaging wired to new engine)
- `test_new_architecture.py` — **NEW:** Router permissions, confidence thresholds, evidence spans, profile/memory validation, proposal tools, deterministic routing
- `test_engine_integration.py` — **NEW:** Full turn pipeline with async DB, profile persistence, memory persistence, audit log
- `test_langchain_router.py` — Router structured output and deterministic routing
- `test_langchain_agents.py` — Agent tool permissions and orchestrator pipeline
- `test_langchain_tools.py` — LangChain tool schemas and invocation
- `test_flow.py` — Legacy conversation engine routing and history
- `test_scheduler.py` — Daily prompts, reminders, auto-feedback, intensity
- `test_tone.py` — Tone adaptation, EMA, whitelist validation
- `test_tools.py` — Tool execution and state management

### Verify Patch Audit Behavior

The audit trail can be inspected by querying the `patch_audit_log` table after processing messages. The `test_engine_integration.py::TestAuditLog` tests verify that proposals and commit decisions are properly recorded.

### Frontend

```bash
cd web && npm test         # Unit tests (Vitest)
cd web && npm run test:e2e # E2E tests (Playwright)
```

## What Is Stubbed

This is a prototype. The following are mocked or incomplete:

- **LLM calls** — In stub mode, specialist agents return fixed responses. Connect a real LLM (OpenAI, Anthropic, etc.) by passing `llm` and `router_llm` parameters to the engine.
- **Web Push delivery** — Push subscriptions are stored in the database but no actual push messages are sent. Wire up `pywebpush` with VAPID keys to enable delivery.
- **Outbox event processing** — Outbox events (reminders, auto-feedback timers) are created with dedupe keys but no background worker processes them. Add a polling worker or task queue to fire events at `available_at`.
- **Message endpoint** — `POST /p/{project_id}/messages` runs the Router + specialist pipeline in stub mode (deterministic routing, fixed responses). With a real LLM, it produces contextual responses.

## Environment Variables

Configure in `.env` at the repository root (see `.env.example`):

| Variable | Description |
|----------|-------------|
| `H4CKATH0N_ENV` | Environment mode (`development` / `production`) |
| `H4CKATH0N_DATABASE_URL` | SQLAlchemy async database URL |
| `H4CKATH0N_RP_ID` | WebAuthn relying party ID (e.g., `localhost`) |
| `H4CKATH0N_ORIGIN` | Allowed origin for CORS and WebAuthn |
| `VITE_API_BASE_URL` | API base URL for the frontend (e.g., `/api`) |
| `OPENAI_API_KEY` | OpenAI API key for live LLM responses (backend only) |
| `H4CKATH0N_OPENAI_API_KEY` | Optional alternate env name for the OpenAI key |
| `VAPID_PUBLIC_KEY` | VAPID public key for Web Push |
| `VAPID_PRIVATE_KEY` | VAPID private key for Web Push (never log this) |

## License

See [LICENSE](LICENSE).
