# Flow: HCI Research Platform

A production-shaped prototype for HCI research combining a LangGraph-based conversation engine, React PWA frontend, passkey-first authentication (via [h4ckath0n](https://github.com/user/h4ckath0n)), SSE-based real-time chat, and vendor-neutral Web Push notifications.

## Architecture Overview

| Pillar | Stack | Description |
|--------|-------|-------------|
| **Backend** | FastAPI + h4ckath0n + SQLAlchemy 2.x | Async API with passkey auth, multi-tenant project model, and SSE fan-out |
| **Conversation Engine** | LangGraph-compatible Python modules | Replicates legacy Go conversation flow with INTAKE/FEEDBACK routing, tool loop, scheduling, and tone adaptation |
| **Frontend** | React 19 + Vite + Tailwind CSS | PWA with service worker, SSE streaming chat, and Web Push notification support |

## Quick Start

### Backend

```bash
cd api
uv sync
# Copy .env.example to .env and configure
cp ../.env.example ../.env
uv run uvicorn app.main:app --reload
```

### Frontend (in another terminal)

```bash
cd web
npm install
npm run dev
```

The frontend dev server runs at `http://localhost:5173` and proxies API requests to the backend.

## Project Structure

```
Flow/
├── api/                          # FastAPI backend
│   ├── app/
│   │   ├── main.py               # App entry point (h4ckath0n create_app)
│   │   ├── routes.py             # API route handlers
│   │   ├── models.py             # SQLAlchemy 2.x models
│   │   ├── db.py                 # Database session management
│   │   ├── middleware.py         # CSP and other middleware
│   │   ├── id_utils.py           # Custom ID generation (p... / u...)
│   │   └── engine/               # Conversation Flow engine
│   │       ├── flow.py           # Orchestrator (INTAKE/FEEDBACK routing)
│   │       ├── modules.py        # IntakeModule, FeedbackModule, tool loop
│   │       ├── state.py          # State enums, Pydantic models, DataKeys
│   │       ├── tools.py          # Tool implementations
│   │       ├── scheduler.py      # Daily prompts, reminders, auto-feedback
│   │       └── tone.py           # Tone adaptation (EMA, hysteresis, whitelist)
│   ├── prompts/                  # System prompt templates
│   ├── tests/                    # Backend test suite
│   └── pyproject.toml
├── web/                          # React PWA frontend
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
├── docs/
│   ├── legacy-conversation-flow-contract.md   # Authoritative legacy behavior
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
| `messages` | auto-increment int | Chat history with `server_msg_id` (UUID) |
| `conversation_runtime_state` | FK to conversation | JSON blob for engine state (LangGraph checkpoint) |
| `push_subscriptions` | auto-increment int | Web Push endpoints + crypto keys per device |
| `outbox_events` | auto-increment int | Durable scheduled events with dedupe keys |

## Conversation Engine

The engine replicates the semantics defined in [`docs/legacy-conversation-flow-contract.md`](docs/legacy-conversation-flow-contract.md).

### Routing (§4.1)

Every message is routed by conversation sub-state:

- **INTAKE** (default) → `IntakeModule` — onboarding, profile building, schedule setup
- **FEEDBACK** → `FeedbackModule` — habit tracking, barrier analysis, prompt refinement

### Tool Loop (§8.1)

Both modules run a tool loop (max 10 rounds):

1. Build message context: system prompt → profile status → tone guide → chat history → user message
2. Call LLM (or stub) with available tools
3. If LLM returns **content** → return as assistant response (terminate)
4. If LLM returns **tool calls** → execute tools, append results, loop
5. If neither → return fallback message

Available tools: `save_user_profile`, `scheduler`, `generate_habit_prompt`, `transition_state`

### Scheduling (§5)

- **Daily prompts** — generated via `PromptGeneratorTool`, scheduled through outbox events
- **Reminders** — 5-hour follow-up if no reply; cancelled on user response
- **Auto-feedback** — 5-minute timer transitions to FEEDBACK if no reply after prompt
- **Intensity adjustment** — daily poll ("more"/"less"/"same") adjusts prompt intensity

### Tone Adaptation (§6)

- Tag whitelist with 15 validated tags (style, stance, interaction)
- EMA smoothing (α=0.15) with hysteresis (activation ≥ 0.7, deactivation ≤ 0.4)
- Mutual exclusion enforcement (e.g., `concise` vs `detailed`)
- Rate-limited implicit updates (min 3-minute interval)
- Injected as `<TONE POLICY>` block in LLM context

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
- `test_api.py` — API endpoint integration tests
- `test_flow.py` — Conversation engine routing and history
- `test_scheduler.py` — Daily prompts, reminders, auto-feedback, intensity
- `test_tone.py` — Tone adaptation, EMA, whitelist validation
- `test_tools.py` — Tool execution and state management

### Frontend

```bash
cd web && npm test         # Unit tests (Vitest)
cd web && npm run test:e2e # E2E tests (Playwright)
```

## What Is Stubbed

This is a prototype. The following are mocked or incomplete:

- **LLM calls** — The engine uses `StubLLMClient` which returns fixed responses. Replace with a real LLM client (OpenAI, Anthropic, etc.) by implementing the `LLMClient` protocol.
- **Web Push delivery** — Push subscriptions are stored in the database but no actual push messages are sent. Wire up `pywebpush` with VAPID keys to enable delivery.
- **Outbox event processing** — Outbox events (reminders, auto-feedback timers) are created with dedupe keys but no background worker processes them. Add a polling worker or task queue to fire events at `available_at`.
- **Message endpoint** — `POST /p/{project_id}/messages` returns a stub echo response instead of running the full engine pipeline.

## Environment Variables

Configure in `.env` at the repository root (see `.env.example`):

| Variable | Description |
|----------|-------------|
| `H4CKATH0N_ENV` | Environment mode (`development` / `production`) |
| `H4CKATH0N_DATABASE_URL` | SQLAlchemy async database URL |
| `H4CKATH0N_AUTH_SIGNING_KEY` | Hex secret for JWT signing |
| `H4CKATH0N_RP_ID` | WebAuthn relying party ID (e.g., `localhost`) |
| `H4CKATH0N_ORIGIN` | Allowed origin for CORS and WebAuthn |
| `VITE_API_BASE_URL` | API base URL for the frontend (e.g., `/api`) |
| `VAPID_PUBLIC_KEY` | VAPID public key for Web Push |
| `VAPID_PRIVATE_KEY` | VAPID private key for Web Push (never log this) |

## License

See [LICENSE](LICENSE).
