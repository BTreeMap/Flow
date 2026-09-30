# Core invariants — identity, IDs, deployment

These are hard constraints. Violating them is a defect, not a style choice.

## Identity
- Stable identity is the h4ckath0n user id (`u...`).
- A user can join multiple research projects; each is shown as a dashboard thread.
- Projects use opaque ids (`p...`). No slug required.

## Email
- Optional contact metadata only. Not unique, not validated.
- **Never** used for identity, login, authorization, or keys.

## ID policy
- Custom scheme only for user-visible, URL-addressable objects:
  `<prefix> + base32(randombytes(20))[1:]` (32 chars). Users `u...`, projects `p...`.
- Internal-only entities use DB primary keys (int/UUID): memberships, conversations,
  messages, push subscriptions, outbox events, contact records, audit logs.
- Rule of thumb: addressable in a URL or seen as an object → custom id; otherwise DB id.
- Invite codes appear in URLs but are tokens, not ids — store only **hashed** invite
  codes; never log raw invite tokens.

## Multi-tenancy
All data is scoped by `(project_id, user_id)` → `membership_id`. Foreign keys enforce
scoping (Conversation, UserProfileStore, MemoryItem, PatchAuditLog, Notification, …) so
no cross-project leakage is possible at the DB level. Every route resolves membership
first (404 if the user is not in the project).

## Scheduling
Use outbox/scheduled-task events with dedupe keys for idempotency and explicit
cancellation semantics. Specialists must not mutate scheduling state without a Router
commit.

## Deployment architecture
- Single-origin: `flow-web` (Caddy) serves the React app at `/` and reverse-proxies
  `/api/*` to backend `flow` (FastAPI) with prefix stripping (`handle_path`).
- Cloudflare Tunnel terminates TLS and forwards to `flow-web` over plain HTTP on 8080.
- `flow-web` stays HTTP-only (`auto_https off`), binds 8080, runs as non-root.
- Backend routes have **no** `/api` prefix — Caddy strips it.
- Root [`docker-compose.yml`](../../docker-compose.yml) runs a production-like stack.
- Images publish to GHCR multi-arch: backend `ghcr.io/<owner>/<repo>` (pkg `flow`),
  frontend `ghcr.io/<owner>/<repo>-web` (pkg `flow-web`).

## Observability & secrets
Use the h4ckath0n trace-id middleware. Log Router decisions and patch-commit outcomes
with trace ids. **Never** log secrets: invite codes, VAPID private key, or push crypto
keys.
