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
│   │   ├── config.py             # Configuration (env vars, settings)
│   │   ├── db.py                 # Database session management
│   │   ├── middleware.py         # CSP and other middleware
│   │   ├── id_utils.py           # Custom ID generation (p... / u...)
│   │   ├── agents/               # Multi-bot LangChain agents
│   │   │   ├── engine.py         # Turn engine: Router + specialist pipeline
│   │   │   ├── intake.py         # Intake specialist agent
│   │   │   ├── feedback.py       # Feedback specialist agent
│   │   │   ├── coach.py          # Coach specialist agent
│   │   │   ├── runner.py         # Agent runner (LangChain invoke wrapper + tool trace)
│   │   │   └── tool_trace.py     # Tool call tracing callback
│   │   ├── schemas/              # Pydantic models
│   │   │   ├── router.py         # RouteDecision (INTAKE/FEEDBACK/COACH)
│   │   │   ├── patches.py        # Proposals, evidence, permissions, profile/memory schemas
│   │   │   └── tool_schemas.py   # Tool argument schemas
│   │   ├── services/             # Business logic layer
│   │   │   ├── profile_service.py    # Profile/memory persistence, validation, audit
│   │   │   ├── event_service.py      # Event handling
│   │   │   ├── outbox_service.py     # Outbox event persistence
│   │   │   └── scheduler_service.py  # Scheduling logic
│   │   ├── tools/                # LangChain tools
│   │   │   ├── proposal_tools.py     # propose_profile_patch, propose_memory_patch
│   │   │   └── scheduler_tools.py    # Scheduling LangChain tools
│   │   └── worker/               # Outbox event worker
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
│   │   ├── api/                  # API client, types, and generated OpenAPI (openapi.ts)
│   │   └── components/           # Shared UI components
│   └── package.json
├── docker-compose.yml            # Production-like local stack (flow-web + flow + postgres)
├── docs/
│   ├── current-architecture.md           # Current architecture (authoritative)
│   ├── legacy-conversation-flow-contract.md   # Legacy behavior reference (deprecated)
│   └── parity-matrix.md                       # Legacy → new code mapping
├── .env.example
└── AGENTS.md                     # Agent behavior rules
```

## API Endpoints

All project-scoped endpoints require passkey authentication.

<!-- ROUTE_TABLE_START -->

| Method | Path | Tag | Description |
|--------|------|-----|-------------|
| `GET` | `/` | h4ckath0n | Welcome (framework root) |
| `GET` | `/health` | h4ckath0n | Health check (framework) |
| `GET` | `/healthz` | infra | Readiness probe (includes llm_mode) |
| `GET` | `/demo/ping` | demo | Liveness ping |
| `POST` | `/demo/echo` | demo | Echo with reverse |
| `WS` | `/demo/ws` | demo | Authenticated WebSocket demo |
| `GET` | `/demo/sse` | demo | Authenticated SSE demo stream |
| `POST` | `/auth/passkey/register/start` | passkey | Start passkey registration |
| `POST` | `/auth/passkey/register/finish` | passkey | Finish passkey registration |
| `POST` | `/auth/passkey/login/start` | passkey | Start passkey login |
| `POST` | `/auth/passkey/login/finish` | passkey | Finish passkey login |
| `POST` | `/auth/passkey/add/start` | passkey | Start adding a passkey |
| `POST` | `/auth/passkey/add/finish` | passkey | Finish adding a passkey |
| `GET` | `/auth/passkeys` | passkey | List passkeys |
| `PATCH` | `/auth/passkeys/{key_id}` | passkey | Rename a passkey |
| `POST` | `/auth/passkeys/{key_id}/revoke` | passkey | Revoke a passkey |
| `GET` | `/auth/me` | auth | Current user from auth context |
| `GET` | `/auth/sessions` | auth | List registered passkey devices |
| `POST` | `/auth/sessions/{device_id}/revoke` | auth | Revoke a passkey device |
| `GET` | `/me` | user | Current user profile (email, display_name, is_admin) |
| `PATCH` | `/me` | user | Update email and/or display name |
| `GET` | `/dashboard` | dashboard | List user's project memberships |
| `POST` | `/p/{project_id}/activate/claim` | activation | Claim invite code, create membership + conversation |
| `GET` | `/p/{project_id}/me` | activation | Get membership status, conversation ID |
| `GET` | `/p/{project_id}/profile` | profile | Get user profile for project |
| `PUT` | `/p/{project_id}/profile` | profile | Update user profile for project |
| `GET` | `/p/{project_id}/messages` | messaging | Get message history |
| `POST` | `/p/{project_id}/messages` | messaging | Send message, get assistant reply |
| `GET` | `/p/{project_id}/events` | streaming | SSE event stream for real-time updates |
| `GET` | `/p/{project_id}/push/vapid-public-key` | push | Get VAPID public key for push subscription |
| `POST` | `/p/{project_id}/push/subscribe` | push | Store a push subscription |
| `POST` | `/p/{project_id}/push/unsubscribe` | push | Revoke a push subscription |
| `GET` | `/p/{project_id}/notifications` | notifications | List notifications |
| `GET` | `/p/{project_id}/notifications/unread-count` | notifications | Get unread notification count |
| `POST` | `/p/{project_id}/notifications/{notification_id}/read` | notifications | Mark notification as read |
| `GET` | `/admin/debug/status` | admin | System debug status |
| `POST` | `/admin/debug/llm-connectivity` | admin | Test LLM connectivity |
| `POST` | `/admin/projects` | admin | Create a new project |
| `GET` | `/admin/projects` | admin | List all projects |
| `PATCH` | `/admin/projects/{project_id}` | admin | Update project name or status |
| `POST` | `/admin/projects/{project_id}/invites` | admin | Create invite for project |
| `GET` | `/admin/projects/{project_id}/participants` | admin | List project participants |
| `GET` | `/admin/projects/{project_id}/export` | admin | Export project data |
| `GET` | `/admin/projects/{project_id}/push/channels` | admin | List push subscriptions for a project |
| `POST` | `/admin/push/test` | admin | Send test push notification |

<!-- ROUTE_TABLE_END -->

> This table is auto-verified by CI. See [Drift prevention](#drift-prevention).

## Data Model

| Table | ID Type | Description |
|-------|---------|-------------|
| `projects` | `p...` (custom, 32 chars) | User-visible research projects |
| `project_invites` | auto-increment int | Hashed invite codes with expiry |
| `project_memberships` | auto-increment int | Links (project, user) with status; unique constraint |
| `participant_contacts` | auto-increment int | Legacy email contact metadata (per-membership) |
| `flow_user_profiles` | user_id (string PK) | User-level display_name (not per-project) |
| `conversations` | auto-increment int | 1:1 with membership |
| `messages` | auto-increment int | Chat history with `server_msg_id` (36-char string: `m` + 35 lowercase base32 chars; UUID-length for DB schema compatibility) |
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

The legacy conversation flow engine was fully removed. The legacy behavioral contract (`docs/legacy-conversation-flow-contract.md`) is deprecated and retained for historical reference only.

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Landing | Public landing page |
| `/register` | Register | Passkey registration stepper: email → passkey → display name |
| `/login` | Login | Passkey login with return_to support |
| `/dashboard` | Dashboard | List project threads (active/ended) |
| `/p/:projectId/activate` | Activation | Join project via invite link; requests email only if missing |
| `/p/:projectId/chat` | ChatThread | Send messages via POST, receive via SSE |
| `/p/:projectId/notifications` | Notifications | PWA install guidance, enable push notifications |
| `/settings` | Settings | User profile (email, display name), theme, devices, passkeys |
| `/admin` | Admin | Project management, invite generation, push testing, debug tools |

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
cd api && uv run pytest tests/ -v --tb=short
```

Test modules:

- `test_api.py` — API endpoint integration tests (messaging wired to new engine)
- `test_api_schema_contracts.py` — OpenAPI schema contract tests
- `test_admin_push_perf.py` — Admin push notification performance tests
- `test_config.py` — Configuration loading and validation
- `test_engine_integration.py` — Full turn pipeline with async DB, profile persistence, memory persistence, audit log
- `test_id_utils.py` — Custom ID generation utilities
- `test_langchain_agents.py` — Agent tool permissions and orchestrator pipeline
- `test_langchain_tools.py` — LangChain tool schemas and invocation
- `test_logging_middleware.py` — Logging middleware behavior
- `test_migrations.py` — Database migration tests
- `test_milestone2.py` — Milestone 2 feature integration tests
- `test_new_architecture.py` — Router permissions, confidence thresholds, evidence spans, profile/memory validation, proposal tools, deterministic routing
- `test_notifications_routes.py` — Notification endpoint tests
- `test_nudge_integration.py` — Nudge scheduling integration tests
- `test_outbox_worker.py` — Outbox worker processing tests
- `test_prompts.py` — System prompt template tests
- `test_read_receipt_logic.py` — Read receipt logic tests
- `test_tool_trace.py` — Tool call tracing tests
- `test_worker_logic.py` — Worker logic unit tests

### Verify Patch Audit Behavior

The audit trail can be inspected by querying the `patch_audit_log` table after processing messages. The `test_engine_integration.py::TestAuditLog` tests verify that proposals and commit decisions are properly recorded.

### Frontend

```bash
cd web && npm test         # Unit tests (Vitest)
cd web && npm run test:e2e # E2E tests (Playwright)
```

## What Is Stubbed

This is a prototype. The following are mocked or incomplete:

- **LLM calls** — In stub mode (no `OPENAI_API_KEY`), specialist agents return fixed responses. Connect a real LLM (OpenAI, Anthropic, etc.) by passing `llm` and `router_llm` parameters to the engine.
- **Web Push delivery** — Push delivery is implemented via `pywebpush` in the outbox worker. Configure `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` to enable it.
- **Message endpoint** — `POST /p/{project_id}/messages` runs the full Router + specialist pipeline. Without an OpenAI API key it operates in stub mode (deterministic routing, fixed responses); with a real API key it produces contextual LLM responses.

## Environment Variables

Configure in `.env` at the repository root (see `.env.example`):

<!-- ENV_TABLE_START -->

| Variable | Default | Description |
|----------|---------|-------------|
| `H4CKATH0N_ENV` | `development` | Environment mode (`development` / `production`) |
| `H4CKATH0N_DATABASE_URL` | `sqlite+aiosqlite:///./data/flow-app.db` | SQLAlchemy async database URL |
| `H4CKATH0N_RP_ID` | `localhost` | WebAuthn relying party ID |
| `H4CKATH0N_ORIGIN` | (none) | Allowed origin for CORS and WebAuthn |
| `VITE_API_BASE_URL` | `/api` | API base URL for the frontend |
| `LOG_LEVEL` | `INFO` | Log level (backend logging) |
| `FLOW_DATA_DIR` | `/app/data` or `./data` | Persistent data directory |
| `FLOW_WORKER_ID` | hostname | Worker identifier for outbox lease |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model name for OpenAI |
| `OPENAI_API_KEY` | (none) | OpenAI API key for live LLM responses |
| `H4CKATH0N_OPENAI_API_KEY` | (none) | Optional alternate name for the OpenAI key |
| `VAPID_PUBLIC_KEY` | `""` | VAPID public key for Web Push |
| `VAPID_PRIVATE_KEY` | `""` | VAPID private key for Web Push (never log) |
| `VAPID_CLAIM_SUB` | `mailto:flow@oss.joefang.org` | VAPID subject claim |
| `FLOW_VAPID_PUBLIC_KEY` | (none) | Legacy alias for `VAPID_PUBLIC_KEY` |
| `FLOW_VAPID_PRIVATE_KEY` | (none) | Legacy alias for `VAPID_PRIVATE_KEY` |

<!-- ENV_TABLE_END -->

## Drift Prevention

Documentation parity is enforced by CI. The docs check script validates:

1. **API endpoint drift** — the route table in this README matches the current OpenAPI schema.
2. **Environment variable drift** — the env var table matches what `api/app/config.py` reads and what `.env.example` provides.
3. **Link hygiene** — all relative markdown links in README and `docs/` resolve to existing files.

Run locally:

```bash
python3 scripts/docs/check_docs.py
```

The CI job `docs-check` runs this on every PR and push to main.

## License

See [LICENSE](LICENSE).
