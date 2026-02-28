# Documentation Parity Report

> Generated during the documentation parity audit (2026-02-27).

## Summary

A full audit was performed against the codebase to identify every concrete mismatch between documentation and code. All mismatches listed below have been corrected.

---

## Mismatches Found and Fixed

### 1. README.md — Project structure tree listed removed files

**What was wrong:** The project structure tree referenced files that were removed during Milestone 2:
- `api/app/agents/router.py` — removed (routing logic moved into `engine.py`)
- `api/app/agents/orchestrator.py` — removed (pipeline consolidated into `engine.py`)
- `api/app/tools/langchain_tools.py` — removed (replaced by `proposal_tools.py` and `scheduler_tools.py`)
- `api/app/engine/` — entire directory removed (legacy engine deleted)
- `web/src/gen/` — never existed; generated file is at `web/src/api/openapi.ts`

**Verification:** `ls api/app/agents/` shows only: `__init__.py`, `coach.py`, `engine.py`, `feedback.py`, `intake.py`, `runner.py`, `tool_trace.py`. `ls api/app/engine/` returns "No such file or directory".

**Fix:** Updated tree to match actual directory contents. Added `runner.py`, `tool_trace.py`, `scheduler_tools.py`, `worker/`, and all services. Removed references to deleted files.

**Files changed:** `README.md`

### 2. README.md — API endpoints table was incomplete

**What was wrong:** The endpoint table was missing 20+ routes:
- All h4ckath0n-provided auth/passkey routes (`/auth/passkey/*`, `/auth/passkeys/*`, `/`, `/health`)
- Profile endpoints (`GET /p/{project_id}/profile`, `PUT /p/{project_id}/profile`)
- Message history (`GET /p/{project_id}/messages`)
- Notification endpoints (`GET /p/{project_id}/notifications`, `GET .../unread-count`, `POST .../read`)
- Many admin endpoints (`POST /admin/projects`, `GET /admin/projects`, `POST .../invites`, `GET .../participants`, `GET .../export`, `GET /admin/debug/status`, `POST /admin/debug/llm-connectivity`)

**Verification:** Generated OpenAPI via `cd api && uv run python -m scripts.dump_openapi` and compared with documented table.

**Fix:** Replaced table with complete list of all 44 HTTP routes + 1 WS route, verified against OpenAPI schema. Added `<!-- ROUTE_TABLE_START/END -->` markers for CI drift checking.

**Files changed:** `README.md`

### 3. README.md — Environment variables table was incomplete

**What was wrong:** Missing variables: `LOG_LEVEL`, `FLOW_DATA_DIR`, `FLOW_WORKER_ID`, `LLM_MODEL`, `VAPID_CLAIM_SUB`, `FLOW_VAPID_PUBLIC_KEY`, `FLOW_VAPID_PRIVATE_KEY`. Also missing default values for all variables.

**Verification:** Extracted all `os.environ.get()` calls from `api/app/config.py` and cross-referenced with `.env.example`.

**Fix:** Replaced table with complete variable list including defaults. Added `<!-- ENV_TABLE_START/END -->` markers for CI drift checking.

**Files changed:** `README.md`

### 4. README.md — "What Is Stubbed" section was stale

**What was wrong:**
- Claimed "no actual push messages are sent" — but push delivery IS implemented via `pywebpush` in `api/app/worker/outbox_worker.py`
- Claimed "no background worker processes [outbox events]" — but `flow-worker` service runs in `docker-compose.yml`
- Claimed message endpoint runs "in stub mode" without qualifying that it's only stub without API key

**Verification:** `docker-compose.yml` lines 54-78 show `flow-worker` service. `api/app/worker/outbox_worker.py` implements event processing including push delivery.

**Fix:** Updated to reflect current state: push delivery works when VAPID keys configured; outbox worker exists; message endpoint uses stub mode only when no API key present.

**Files changed:** `README.md`

### 5. README.md — Test modules list was stale

**What was wrong:** Listed test files that were removed with the legacy engine (`test_flow.py`, `test_scheduler.py`, `test_tone.py`, `test_tools.py`). Missing 12+ new test files added since.

**Verification:** `ls api/tests/` shows 19 test files, none of the listed legacy ones.

**Fix:** Updated list to match actual test files in `api/tests/`.

**Files changed:** `README.md`

### 6. README.md — Legacy engine section was inaccurate

**What was wrong:** Stated "The legacy conversation flow engine (`api/app/engine/`) is retained for backward compatibility." The directory no longer exists.

**Verification:** `ls api/app/engine/` returns "No such file or directory".

**Fix:** Updated to: "The legacy conversation flow engine was fully removed."

**Files changed:** `README.md`

### 7. docs/release-process.md — Missing release trigger

**What was wrong:** Documented triggers as only "Push to main" and "workflow_dispatch". Actual `release.yml` also triggers on `release: published`.

**Verification:** `.github/workflows/release.yml` lines 3-6 show all three triggers.

**Fix:** Added `release: published` to triggers list.

**Files changed:** `docs/release-process.md`

### 8. docs/release-process.md — Docker tag `:latest` placement

**What was wrong:** `:latest` was listed under "Release tags" section. In code, `:latest` is in `DEV_TAGS` (always published), not `RELEASE_TAGS`.

**Verification:** `.github/workflows/release.yml` line 147: `:latest` is appended to `DEV_TAGS`.

**Fix:** Moved `:latest` to "Dev build tags" table. Added `:stable` to "Release tags" (created only for `release` events).

**Files changed:** `docs/release-process.md`

### 9. docs/release-process.md — Reproduce commands used wrong image name

**What was wrong:** Build command used `-t flow-backend:local` and compose command used `FLOW_IMAGE=flow-backend:local`. But `docker-compose.yml` expects just `flow:local` (no `-backend` suffix).

**Verification:** `docker-compose.yml` line 31: `image: ${FLOW_IMAGE:-ghcr.io/btreemap/flow:latest}`. README Quick Start also uses `flow:local`.

**Fix:** Changed to `flow:local` consistently.

**Files changed:** `docs/release-process.md`

### 10. docs/current-architecture.md — Stale code entrypoints

**What was wrong:** Key Code Entrypoints table referenced `api/app/agents/router.py` (removed). Missing `runner.py`, `tool_trace.py`, `scheduler_tools.py`, `outbox_service.py`, `scheduler_service.py`, `outbox_worker.py`.

**Verification:** `ls api/app/agents/` confirms `router.py` doesn't exist.

**Fix:** Updated table with correct file list.

**Files changed:** `docs/current-architecture.md`

### 11. docs/current-architecture.md — Legacy engine deprecation note was inaccurate

**What was wrong:** Stated legacy engine "is retained for test coverage of pure utility functions." It has been fully removed.

**Verification:** `ls api/app/engine/` returns "No such file or directory".

**Fix:** Updated to "has been fully removed."

**Files changed:** `docs/current-architecture.md`

### 12. docs/parity-matrix.md — Multiple stale file references

**What was wrong:** Section 5 referenced `agents/router.py`, `agents/orchestrator.py`, `tools/langchain_tools.py`, `engine/tools.py` — all removed. Behavior preservation table referenced non-existent test files (`test_flow.py`, `test_tone.py`, `test_scheduler.py`, `test_tools.py`).

**Verification:** `ls api/app/agents/` and `ls api/tests/` confirm absence.

**Fix:** Updated architecture table, key design decisions, and behavior preservation table. Added historical reference warning header.

**Files changed:** `docs/parity-matrix.md`

---

## New Files Created

| File | Purpose |
|------|---------|
| `docs/README.md` | Documentation landing page with navigation index |
| `scripts/docs/check_docs.py` | Drift prevention script (API routes, env vars, link hygiene) |
| `docs/debug/docs-parity-report.md` | This report |

## CI Integration

A `docs-check` job was added to `.github/workflows/ci.yml` that runs `scripts/docs/check_docs.py` on every PR and push to main. It validates:

1. Route table in README matches OpenAPI schema
2. Env var table matches `api/app/config.py` and `.env.example`
3. All relative markdown links resolve

## Verification Commands

```bash
# Run the docs drift check
python3 scripts/docs/check_docs.py

# Generate fresh OpenAPI schema
cd api && uv run python -m scripts.dump_openapi

# Backend lint and test
cd api && uv run ruff check . && uv run ruff format --check . && uv run pytest tests/ -v --tb=short

# Frontend lint and test
cd web && npm ci && npm run lint && npm run typecheck && npm run test
```
