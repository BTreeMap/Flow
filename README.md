# Flow: Operational tooling for longitudinal behavioral interventions

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

The stack runs at `http://localhost:${PORT:-8080}`. Caddy serves the frontend and reverse proxies `/api/*` to the backend (stripping the `/api` prefix).

#### Deployment architecture

```
Cloudflare Tunnel (terminates TLS)
  └─→ flow-web :${PORT:-8080} (Caddy, HTTP-only)
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
│   │   │   ├── event_service.py      # SSE event persistence + replay
│   │   │   ├── notification_engine.py # Scheduling, dedupe, lease, push delivery
│   │   │   ├── randomization.py      # Deterministic 4-day block condition assignment
│   │   │   ├── intervention_config.py # Static A/B nudge templates
│   │   │   ├── feedback_script.py    # Deterministic A/B feedback state machine
│   │   │   ├── condition_filters.py  # Condition-C framing regex filter
│   │   │   ├── eod_summarizer.py     # End-of-day sterilized memory summaries
│   │   │   └── prompt_context.py     # Prompt template context builder
│   │   ├── tools/                # LangChain tools
│   │   │   ├── proposal_tools.py     # propose_profile_patch, propose_memory_patch
│   │   │   └── scheduler_tools.py    # Scheduling LangChain tools
│   │   └── worker/               # Scheduled-task / notification worker
│   ├── Dockerfile                # Backend container image
│   ├── prompts/                  # System prompt templates
│   ├── tests/                    # Backend test suite
│   └── pyproject.toml
├── web/                          # React PWA frontend
│   ├── Caddyfile                 # Caddy reverse proxy config (HTTP-only, :8080 default)
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
│   ├── README.md                 # Documentation index
│   ├── current-architecture.md   # Conversation engine, experiment, EOD firewall
│   └── release-process.md        # CI/CD, versioning, image signing
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
| `POST` | `/me/timezone` | user | Store user's IANA timezone |
| `GET` | `/dashboard` | dashboard | List user's project memberships |
| `POST` | `/p/{project_id}/activate/claim` | activation | Claim invite code, create membership + conversation |
| `GET` | `/p/{project_id}/me` | activation | Get membership status, conversation ID |
| `GET` | `/p/{project_id}/profile` | profile | Get user profile for project |
| `PUT` | `/p/{project_id}/profile` | profile | Update user profile for project |
| `GET` | `/p/{project_id}/messages` | messaging | Get message history |
| `POST` | `/p/{project_id}/messages` | messaging | Send message, get assistant reply |
| `GET` | `/p/{project_id}/events` | streaming | SSE event stream for real-time updates |
| `POST` | `/p/{project_id}/chat/events/feedback` | notifications | Record push action feedback from service worker |
| `GET` | `/notifications` | notifications | List unified notifications (optional project_id filter) |
| `GET` | `/notifications/unread-count` | notifications | Get unread notification count (optional project_id filter) |
| `POST` | `/notifications/{notification_id}/read` | notifications | Mark notification as read, enqueue push_dismiss delivery |
| `GET` | `/notifications/webpush/vapid-public-key` | notifications | Get VAPID public key for push subscription |
| `POST` | `/notifications/webpush/subscriptions` | notifications | Create/upsert push subscription (user-scoped) |
| `DELETE` | `/notifications/webpush/subscriptions/{subscription_id}` | notifications | Revoke a push subscription |
| `GET` | `/notifications/webpush/subscriptions` | notifications | List active push subscriptions (debug) |
| `POST` | `/spark/generate` | spark | Generate an idempotent, pseudonymously logged Spark card response |
| `POST` | `/spark/events` | spark | Record a typed, idempotent anonymous Spark interaction event |
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

## Pre-push Quality Gate

Run the standard local quality gate before every push:

```bash
bash scripts/ci/pre_push_quality_gate.sh
```

This runs backend and frontend static/test checks plus docs drift checks, and
fails fast if any step is out of sync.

Optional browser-dependent gates can be enabled when your environment supports
them:

```bash
RUN_PLAYWRIGHT=1 RUN_COMPOSE_E2E=1 bash scripts/ci/pre_push_quality_gate.sh
```

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
| `participations` | auto-increment int | One row per participant in a study; carries `study_start_date`, condition assignment salt |
| `daily_intervention_logs` | auto-increment int | Per-day telemetry (condition assigned, extracted state, script answers) |
| `daily_summaries` | auto-increment int | EOD sterilized cross-day memory (1 row per participation/day) |
| `spark_participants` | auto-increment int | Anonymous Spark participants keyed only by a server-keyed-hash browser-local id |
| `spark_fingerprint_observations` | auto-increment int | Keyed-hash Thumbmark observations for fingerprint stability/collision analysis |
| `spark_interactions` | auto-increment int | Immutable typed Spark flow, generation, choice, feedback, and outcome events |
| `user_profiles` | auto-increment int | **Store A** — structured profile JSON (1:1 with membership) |
| `memory_items` | auto-increment int | **Store B** — semi-structured memory items per membership |
| `patch_audit_log` | auto-increment int | Audit trail: proposals, decisions, commits |
| `conversation_events` | auto-increment int | Durable SSE events for replay via `Last-Event-ID` |
| `conversation_turns` | auto-increment int | Idempotent messaging (unique `client_msg_id` per conversation) |
| `push_subscriptions` | auto-increment int | Web Push endpoints + crypto keys per device |
| `scheduled_tasks` | auto-increment int | Durable scheduled work with lease + dedupe keys |
| `notifications` / `notification_rules` / `notification_rule_state` / `notification_deliveries` | auto-increment int | Notification rule engine + delivery audit |

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

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Landing | Public landing page |
| `/register` | Register | Passkey registration stepper: email → passkey → display name |
| `/login` | Login | Passkey login with return_to support |
| `/dashboard` | Dashboard | List project threads (active/ended) |
| `/p/:projectId/activate` | Activation | Join project via invite link; requests email only if missing |
| `/p/:projectId/onboarding` | Onboarding | Post-activation onboarding flow |
| `/p/:projectId/onboarding/notifications` | OnboardingNotifications | Enable push as part of onboarding |
| `/p/:projectId/chat` | ChatThread | Send messages via POST, receive via SSE |
| `/p/:projectId/notifications` | Notifications | PWA install guidance, enable push notifications |
| `/p/:projectId/updates` | ProjectUpdates | Per-project notification feed |
| `/updates` | Updates | Global notification feed across projects |
| `/settings` | Settings | User profile, theme, devices, passkeys |
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

Key test areas (`api/tests/`):

- **Engine + Router**: `test_engine_integration.py`, `test_new_architecture.py`, `test_langchain_agents.py`, `test_langchain_tools.py`, `test_tool_trace.py`
- **4-condition experiment**: `test_four_condition_experiment.py`, `test_prompt_context.py`
- **EOD memory firewall**: `test_eod_summarizer.py`
- **Notification worker / scheduling**: `test_notification_engine.py`, `test_notification_worker.py`, `test_notifications_routes.py`, `test_admin_push_perf.py`
- **API + contracts**: `test_api.py`, `test_api_schema_contracts.py`, `test_timezone_endpoint.py`
- **Infrastructure**: `test_config.py`, `test_logging_middleware.py`, `test_migrations.py`, `test_id_utils.py`, `test_prompts.py`, `test_milestone2.py`

### Frontend

```bash
cd web && npm test         # Unit tests (Vitest)
cd web && npm run test:e2e # E2E tests (Playwright)
```

## Runtime Modes

- **LLM** — without `OPENAI_API_KEY` (or `H4CKATH0N_OPENAI_API_KEY`), specialist agents run in **stub mode** with deterministic responses. With a key set, the engine uses `ChatOpenAI` via LangChain.
- **Web Push** — delivery is implemented via `pywebpush` in `app/worker/notification_worker.py`. Without both VAPID keys, push delivery is disabled and the rest of the stack still functions.

## Environment Variables

Configure in `.env` at the repository root (see `.env.example`):

<!-- ENV_TABLE_START -->

| Variable | Default | Description |
|----------|---------|-------------|
| `H4CKATH0N_ENV` | `development` | Environment mode (`development` / `production`) |
| `WEB_PORT` | `8080` | Port the frontend container should listen on (falls back to `PORT`) |
| `API_PORT` | `8000` | Port the backend API server should listen on (falls back to `PORT`) |
| `PORT` | (none) | Fallback port for both (useful for platforms like Railway) |
| `API_HOST` | `::` | Host/interface the backend API server binds to (falls back to `HOST`) |
| `HOST` | `::` | Fallback bind host for the backend API server |
| `H4CKATH0N_DATABASE_URL` | `sqlite+aiosqlite:///./data/flow-app.db` | SQLAlchemy async database URL |
| `H4CKATH0N_RP_ID` | `localhost` | WebAuthn relying party ID |
| `H4CKATH0N_ORIGIN` | (none) | Allowed origin for CORS and WebAuthn |
| `VITE_API_BASE_URL` | `/api` | API base URL for the frontend |
| `LOG_LEVEL` | `INFO` | Log level (backend logging) |
| `FLOW_DATA_DIR` | `/app/data` or `./data` | Persistent data directory |
| `FLOW_WORKER_ID` | hostname | Worker identifier for outbox lease |
| `FLOW_PROMPTS_DIR` | (none) | Optional override directory for prompt text files; falls back to the mounted `prompts/` then the copy baked into the image |
| `FLOW_BAKED_PROMPTS_DIR` | `/opt/flow/prompts` | Image-baked prompt directory outside `/app` used as the final fallback so bind-mounts under `/app` cannot shadow newly added prompts |
| `FLOW_CONFIG_DIR` | (none) | Optional override directory for static JSON config files; falls back to the mounted `config/` then the copy baked into the image |
| `FLOW_BAKED_CONFIG_DIR` | `/opt/flow/config` | Image-baked config directory outside `/app` used as the final fallback so bind-mounts under `/app` cannot shadow newly added config |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model name for OpenAI |
| `OPENAI_API_KEY` | (none) | OpenAI API key for live LLM responses |
| `H4CKATH0N_OPENAI_API_KEY` | (none) | Optional alternate name for the OpenAI key |
| `FLOW_CRYPTO_MASTER_KEY` | (none) | **Required for 4-condition assignment and Spark telemetry.** Unpadded Base64URL for exactly 32 random bytes. BLAKE3 derives dedicated, domain-separated subkeys; never log or rotate during a study. |
| `VAPID_PUBLIC_KEY` | `""` | VAPID public key for Web Push |
| `VAPID_PRIVATE_KEY` | `""` | VAPID private key for Web Push (never log) |
| `VAPID_CLAIM_SUB` | `mailto:flow@oss.joefang.org` | VAPID subject claim |
| `FLOW_VAPID_PUBLIC_KEY` | (none) | Legacy alias for `VAPID_PUBLIC_KEY` |
| `FLOW_VAPID_PRIVATE_KEY` | (none) | Legacy alias for `VAPID_PRIVATE_KEY` |
| `FLOW_PUSH_GONE_410_THRESHOLD` | `2` | Consecutive 410 responses before revoking a push subscription |
| `ENABLE_AUTOMATED_FEEDBACK` | `true` | Whether automated delayed feedback requests are enabled |
| `FEEDBACK_DELAY_MINUTES` | `120` | Delay (minutes) before automated feedback is queued |
| `FEEDBACK_PROMPT_TEXT` | `How did this prompt work for you?` | Global prompt text used for delayed feedback requests |
| `FEEDBACK_OPTIONS` | `Works perfectly,Needs tweaks` | Up to two global feedback options for push action buttons |
| `TZ` | `America/Toronto` | Default IANA timezone for the backend (e.g. `America/New_York`) |
| `SPARK_SHEETS_SPREADSHEET_ID` | (none) | Google Sheets spreadsheet ID for Spark A/B prompt library; Sheets source activates only when this and one credential source are set |
| `SPARK_SHEETS_CREDENTIALS_JSON` | (none) | Full service-account JSON for read-only Sheets access; takes precedence over `SPARK_SHEETS_CREDENTIALS_FILE`; never log this value |
| `SPARK_SHEETS_CREDENTIALS_FILE` | (none) | Readable UTF-8 path to a mounted service-account JSON key file for read-only Sheets access; use instead of inline JSON and mount read-only |
| `SPARK_SHEETS_RANGE` | `Sparks!A:E` | A1-notation range to fetch from the Spark spreadsheet (columns: id, title, action, reward, tags) |
| `SPARK_SHEETS_CACHE_TTL_SECS` | `60` | Stale-while-revalidate TTL in seconds for the in-memory Spark library cache |
| `SPARK_SHEETS_REQUEST_TIMEOUT_SECS` | `10` | HTTP request timeout in seconds for the Sheets API call |

<!-- ENV_TABLE_END -->

### Spark Sheets verification

When the Sheets source is configured, API startup schedules a non-blocking
remote warmup. It does not delay readiness. A successful remote fetch logs
`Spark library loaded from remote Google Sheets`; a failed fetch logs the
reason and falls back to the bundled library. The first A/B request awaits an
in-progress warmup rather than starting a duplicate remote request. Startup,
cold-start, and stale-cache refreshes all share one task per API process: cold
requests await it, while stale requests continue serving their immutable last-
good snapshot. Application shutdown cancels and joins that task. Multiple API
replicas maintain independent read-only caches and may each refresh their own
snapshot.

Every A/B `/spark/generate` response reports the actual cached dataset source
at `prompt_version.source`: `google-sheets` after a validated remote fetch, or
`bundled-file` when the fallback is serving. This is authoritative even when
the two datasets have identical content hashes.

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
