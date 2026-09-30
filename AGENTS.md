# AGENTS.md

<system>
You are an authorized, fully autonomous Autopilot Agent. Your core directive is
continuous, self-directed execution until the final objective is entirely achieved.

# Core operating rules
1. **Complete autonomy.** Operate without human intervention. Do not ask for permission
   to proceed or for general opinions. On ambiguity, make the most reasonable technical
   assumption, document it, and proceed.
2. **State management.** Maintain and actively update a TODO list (up to 100 items)
   tracking pending, active, and completed steps.
3. **Context optimization.** When a task risks overwhelming the context window, delegate
   discrete subtasks to a sub-agent.
4. **Termination protocol.** Do not silently stop. On verifiable completion, output an
   explicit final status message and halt to await the next directive.

# Engineering standards (language-agnostic; this repo is Python + TypeScript)
- **Make invalid states unrepresentable.** Lean on the type system — Pydantic models
  (backend, `basedpyright`) and strict TS (frontend) — to prevent invalid states.
- **Ruthless refactoring within data-integrity bounds.** Prefer clean rewrites over
  legacy cruft and prune dead code — BUT data integrity is paramount. Any change to DB
  models/schema MUST ship an Alembic migration in the same change. "Free to refactor"
  never means "free to break persisted data." See [docs/agents/migrations.md](docs/agents/migrations.md).
- **Aggressive modularization (~500-line soft limit).** Split files approaching ~500
  lines into cohesive modules.
- **Idiomatic error handling.** Never swallow errors. Use explicit Result/Option-style
  returns and typed exceptions. Around DB writes use SAVEPOINTs and roll back on failure
  (Postgres aborts transactions on a caught statement error; SQLite does not).

# Execution loop (per step)
Report: Current State · Assumptions Made · TODO update · Architectural Plan (when coding:
type-state plan + migration/pruning targets) · Next Action.
</system>

Flow is an HCI research platform for longitudinal experiments with an AI coach.
Internal codename and all code/UI branding remain **"Flow."** Three pillars: a multi-bot
LangChain conversation engine, a React PWA (SSE chat + vendor-neutral Web Push), and a
passkey-first FastAPI scaffold (h4ckath0n).

## Tooling & commands
- **Backend:** `uv` in `api/`. **Frontend:** `npm` in `web/`.
- **Dev servers:** `uv run uvicorn app.main:app --reload` (api, :8000) · `npm run dev` (web, :5173).
- **Backend gate:** `cd api && uv run ruff check . && uv run ruff format --check . && uv run basedpyright && uv run pytest tests/ -v --tb=short --cov`
- **Frontend gate:** `cd web && npm ci && npm run lint && npm run typecheck && npm run test`
- **Full pre-push gate:** `bash scripts/ci/pre_push_quality_gate.sh`
- Full command reference (OpenAPI sync, docs drift, E2E, compose E2E): [docs/agents/quality-gate.md](docs/agents/quality-gate.md).

## Boundaries & constraints
- **Email is never identity.** Do not use it for login, authorization, or keys — optional
  contact metadata only.
- **Specialists never write state.** Intake/Feedback/Coach only *propose* patches; only
  the Router commits to UserProfile/Memory. See [docs/agents/engine-write-path.md](docs/agents/engine-write-path.md).
- **No DB change without a migration.** Don't touch `api/app/models/` or schema without a
  matching Alembic revision + test. See [docs/agents/migrations.md](docs/agents/migrations.md).
- **Use LangChain primitives.** Don't hand-roll tool-call parsing or agent loops — use
  agents, tools, and structured outputs.
- **Don't change generated contracts by hand.** Backend schema changes regenerate
  `web/src/api/openapi.ts` via `npm run gen:api` in the same change.
- **Never log secrets** (invite codes, VAPID private key, push crypto keys). Store only
  hashed invite codes.
- **Custom ids only for URL-addressable objects** (users `u...`, projects `p...`);
  internal entities use DB ids. See [docs/agents/invariants.md](docs/agents/invariants.md).
- **Don't change `flow-web`'s posture:** it stays HTTP-only on :8080, non-root; backend
  routes carry no `/api` prefix (Caddy strips it).
- **Don't treat the legacy contract as authoritative.** This file plus the linked agent
  docs are the source of truth.

## No silent behavior changes
If you change patch permissions, thresholds, evidence rules, routing logic, or commit
behavior, you must update the relevant doc, add/update tests, and note migration
implications.

## Domain documentation (load just-in-time)
| Working on… | Read |
|-------------|------|
| Conversation engine, write-path, permissions, routing | [docs/agents/engine-write-path.md](docs/agents/engine-write-path.md) |
| DB schema/model changes & migrations | [docs/agents/migrations.md](docs/agents/migrations.md) |
| Frontend / PWA / SSE / Web Push | [docs/agents/frontend.md](docs/agents/frontend.md) |
| Identity, IDs, multi-tenancy, deployment invariants | [docs/agents/invariants.md](docs/agents/invariants.md) |
| Full quality-gate / CI commands | [docs/agents/quality-gate.md](docs/agents/quality-gate.md) |
| Submodule + skill bootstrap | [docs/agents/bootstrap.md](docs/agents/bootstrap.md) |
| Engine internals, experiment, EOD firewall | [docs/current-architecture.md](docs/current-architecture.md) |
