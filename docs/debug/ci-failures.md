# CI Failures — Root Causes and Fixes

## Round 2: async migration (h4ckath0n 0.1.3)

### Failure: E2E SSE tests return 500 instead of 401
- **Tests**: `realtime.spec.ts`, `security.spec.ts` — 5 tests expecting 401 for SSE auth failures
- **Root cause**: `authenticate_sse_request()` was changed from sync to async in h4ckath0n 0.1.3. Calls in `app/main.py` and `app/routes.py` were missing `await`, causing the coroutine to be returned instead of raising `AuthError`.
- **Fix**: Added `await` to `authenticate_sse_request()` calls in both files.
- **Status**: Fixed.

### Failure: E2E passkey test — `demo-ping` element not found
- **Test**: `passkey.spec.ts` — "register with passkey and reach dashboard"
- **Root cause**: The Dashboard page didn't render demo API call results. The test expected `data-testid="demo-ping"` and `data-testid="demo-echo"` elements.
- **Fix**: Added demo-ping and demo-echo queries and rendering to `Dashboard.tsx`.
- **Status**: Fixed.

### Failure: E2E Postgres — `relation "project_memberships" does not exist`
- **Root cause**: `_sync_database_url()` converted `postgresql+asyncpg://` to `postgresql+psycopg://`, but h4ckath0n 0.1.3's `_sync_to_async_url()` didn't recognize this format and passed it unchanged to `create_async_engine`, causing connection to wrong database or failed initialization.
- **Fix**: Removed `_sync_database_url()` entirely. h4ckath0n 0.1.3 natively handles async URLs via `create_async_engine_from_settings()`.
- **Status**: Fixed.

### Improvement: deprecated `on_event("startup")` replaced with lifespan
- **Issue**: FastAPI deprecated `on_event("startup")` in favor of lifespan context managers.
- **Fix**: Replaced `@app.on_event("startup")` with a combined lifespan that wraps h4ckath0n's lifespan and initializes app tables.
- **Status**: Fixed.

---

## Round 1: initial CI setup

### Failure: `MissingGreenlet` in all `test_api.py` tests (13 errors)
- **Traceback**: `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called`
- **Root cause**: h4ckath0n (pre-0.1.3) `create_app()` used a sync engine but CI set async DB URLs.
- **Fix**: Initially used `_sync_database_url()` workaround. Now resolved by h4ckath0n 0.1.3 native async support.
- **Status**: Superseded by Round 2 fix.

### Failure: `No module named uvicorn` / `--locked has no effect`
- **Root cause**: `playwright.config.ts` path resolution went 5 levels up instead of 1.
- **Fix**: Changed `repoRoot` to `resolve(__dirname, "..")` and `--directory` to `apiDir`.
- **Status**: Fixed.

### Failure: Trivy scan exit code 1
- **Root cause**: Unfixed CRITICAL CVEs in base Debian image.
- **Fix**: Added `ignore-unfixed: true` to Trivy scans.
- **Status**: Fixed.

## frontend-unit-integration

- **Status**: Passed (no failures).

---

## Commands to reproduce locally

### Backend tests (SQLite)
```bash
cd api
export H4CKATH0N_ENV=testing
export H4CKATH0N_RP_ID=localhost
export H4CKATH0N_ORIGIN=http://localhost:5173
export H4CKATH0N_DATABASE_URL=sqlite+aiosqlite:///./data/test.db
mkdir -p data
uv run pytest tests/ -v --tb=short
```

### Backend tests (Postgres)
```bash
# Start Postgres (Docker)
docker run -d --name flow-pg -e POSTGRES_USER=flow -e POSTGRES_PASSWORD=flow -e POSTGRES_DB=flow_test -p 5432:5432 postgres:18.2

cd api
export H4CKATH0N_ENV=testing
export H4CKATH0N_RP_ID=localhost
export H4CKATH0N_ORIGIN=http://localhost:5173
export H4CKATH0N_DATABASE_URL=postgresql+asyncpg://flow:flow@localhost:5432/flow_test
uv run pytest tests/ -v --tb=short
```

### Frontend tests
```bash
cd web
npm ci
npm run lint
npm run typecheck
npm run test
```

### E2E tests
```bash
cd web
npm ci
npx playwright install --with-deps chromium
npx playwright test
```
