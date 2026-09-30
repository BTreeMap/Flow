# Quality gate — full command reference

All checks must pass before merging. The fastest path is the standard pre-push runner;
the sections below document each gate it wraps plus the browser/E2E gates.

## Standard pre-push gate (runs backend + frontend + docs drift)
```bash
bash scripts/ci/pre_push_quality_gate.sh
# include browser gates where a browser runtime exists:
RUN_PLAYWRIGHT=1 RUN_COMPOSE_E2E=1 bash scripts/ci/pre_push_quality_gate.sh
```

## Backend
```bash
cd api
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest tests/ -v --tb=short --cov
```
See [`../code-quality.md`](../code-quality.md) for lint/type/coverage conventions.

## Frontend (unit / integration)
```bash
cd web
npm ci
npm run lint
npm run typecheck
npm run test
```

## OpenAPI contract sync (required on backend schema changes)
```bash
cd web
npm run gen:api:check   # fails with a diff if web/src/api/openapi.ts is stale
npm run gen:api         # regenerate, then commit the updated file
```

## Documentation drift (required on route/env changes)
```bash
python3 scripts/docs/check_docs.py
```
Keep the README route table and env var table in sync with code.

## End-to-end (Playwright)
```bash
cd web
npx playwright install --with-deps chromium
npx playwright test
```
When frontend UI changes (new pages, renamed test IDs, changed nav), update the matching
specs under [`web/e2e/`](../../web/e2e/) and run E2E as the final validation step.

## End-to-end (compose-based)
```bash
bash scripts/ci/package_frontend.sh web
cp frontend.tar.xz web/frontend.tar.xz
docker build -t flow-web:local web/
docker build -t flow:local api/
FLOW_WEB_IMAGE=flow-web:local FLOW_IMAGE=flow:local docker compose up -d
cd web
PLAYWRIGHT_BASE_URL=http://localhost:8080 npx playwright test e2e/compose.spec.ts
```

## Notes
- Backend tests run on SQLite by default; CI also runs Postgres (`asyncpg`).
- Compose E2E validates Caddy static serving, SPA deep links, `/api` reverse proxy, SSE.
- All database URLs use async drivers (`aiosqlite` / `asyncpg`). No `psycopg2`.
