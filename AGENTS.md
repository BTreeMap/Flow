# AGENTS.md

This repository is an HCI research platform prototype with three core pillars:

1) A stateful LangGraph-based Conversation Flow engine (parity with a legacy Go system).
2) A React PWA frontend with real-time chat via SSE and vendor-neutral Web Push support.
3) A secure FastAPI scaffold and passkey-first authentication using h4ckath0n.

This file defines the project structure and how agents should behave when working in this repo.

---

## Source of truth

### Legacy Conversation Flow contract
Authoritative legacy behavior lives here:
- `docs/legacy-conversation-flow-contract.md`

The Python implementation must replicate its semantics exactly unless a deviation is explicitly documented.

### Parity matrix
We maintain a mapping from legacy behaviors to new code and tests:
- `docs/parity-matrix.md`

If behavior changes, the parity matrix and tests must be updated.

---

## Core invariants

### Identity
- Stable user identity is the h4ckath0n user id (`u...`).
- A user can join multiple research projects.
- Projects are identified by opaque ids (`p...`). No project slug is required.

### Email collection
- Email is collected as optional contact metadata only.
- Email is not unique, not validated, and must never be used for identity, login, authorization, or keys.
- Email may be used for future fallback notifications (out of scope unless explicitly implemented).

### ID policy (important)
We only use the custom id scheme for user-visible, URL-addressable objects.

- Custom scheme format: `<prefix> + base32(randombytes(20))[1:]` (32 chars).
- Existing h4ckath0n user ids are `u...`.
- Project ids must be `p...`.

All internal-only entities may use internal database primary keys (auto-increment int or UUID), including:
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
- iOS onboarding must include “Add to Home Screen” guidance before enabling notifications.

---

## Repository structure

Scaffolded from h4ckath0n:

- `api/` FastAPI backend (must use h4ckath0n `create_app()` factory)
- `web/` React frontend (from scaffold template)
- `docs/` documentation
  - `legacy-conversation-flow-contract.md` (pre-filled, authoritative)
  - `parity-matrix.md` (must be created and kept current)

Optional:
- `prompts/` for system prompts if needed
- `api/tests/` for backend tests

---

## Backend responsibilities

### Multi-tenancy model
All data is scoped by project and membership. A user can join multiple projects. Each project is displayed as a thread on the dashboard.

Key entities:
- Project (`projects.id` is `p...`, user-visible)
- Membership: links `(project_id, user_id)` with a status (internal DB id)
- Conversation: typically 1:1 with membership (internal DB id)
- Messages: persisted chat history (internal DB id)
- Conversation runtime state: persisted LangGraph checkpoint (internal)
- Push subscriptions: stored per membership/device (internal)
- Outbox events: scheduling and idempotent side effects (internal)

### Conversation Flow engine
- Implement as LangGraph (preferred).
- Must replicate semantics defined in `docs/legacy-conversation-flow-contract.md`:
  - INTAKE vs FEEDBACK routing and defaults
  - tool loop behavior and termination
  - history trimming rules
  - scheduling semantics (daily prompt, reminder cancellation, auto-feedback, delayed transitions, intensity adjustment)
  - tone adaptation whitelist and gating, plus prompt injection

### Scheduling
- Use outbox events with dedupe keys to ensure idempotency.
- Reply must cancel reminder semantics exactly as per the legacy contract.

### Observability
- Use h4ckath0n trace id middleware.
- Avoid logging secrets, push crypto keys, or raw invite tokens.

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
- Build LangGraph Conversation Flow engine.
- Implement persistence for runtime state, messages, and profile-like state.
- Implement scheduling using outbox events.
- Implement SSE endpoints and message fanout.
- Implement push subscription storage endpoints and VAPID key endpoint.

Rules:
- Read `docs/legacy-conversation-flow-contract.md` first.
- Create or update `docs/parity-matrix.md` before significant engine work.
- For every legacy behavior, add a corresponding test.
- Do not use email for identity.

### Frontend Engineer Agent
Primary tasks:
- Implement activation, dashboard, chat thread, and notifications UI.
- Implement SSE client with reconnect.
- Implement PWA manifest and service worker for push.
- Implement push subscription flow with explicit permission request.

Rules:
- Do not implement auth from scratch. Use scaffolded passkey flows.
- Ensure iOS “Add to Home Screen” guidance exists before notification enablement.
- Do not treat email as identity.

### Documentation and Parity Agent
Primary tasks:
- Maintain `docs/parity-matrix.md` and ensure mapping stays accurate.
- Write clear “how it works” docs for the new architecture.

Rules:
- If referencing legacy behavior, cite the contract section.
- No ambiguous language.

### QA and Test Agent
Primary tasks:
- Convert legacy behavioral scenarios into automated tests.
- Add integration tests for SSE and activation flow.
- Add tests for push subscription storage.

Rules:
- Tests must be deterministic and fast.
- Ensure coverage for cancellation and idempotency semantics.

---

## Workflow rules for all agents

### Read-first policy
Before changing engine behavior, read:
1) `docs/legacy-conversation-flow-contract.md`
2) `docs/parity-matrix.md`

### No silent behavior changes
If you change behavior intentionally:
- Document it in `docs/parity-matrix.md` as a deliberate deviation.
- Add tests demonstrating the new behavior.
- Update README or docs with implications.

### Security and privacy
- Never log secrets (invite codes, VAPID private key, push crypto keys).
- Do not store unnecessary personal data.
- Email is optional contact metadata only.
