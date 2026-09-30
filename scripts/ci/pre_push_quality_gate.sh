#!/usr/bin/env bash
set -euo pipefail

# pre_push_quality_gate.sh
#
# Standard local quality-gate runner before push.
#
# Default scope (always runs):
#   - backend lint/format/typecheck/tests
#   - frontend OpenAPI sync/lint/typecheck/tests
#   - docs drift checker
#
# Optional browser-dependent gates:
#   RUN_PLAYWRIGHT=1  -> run Playwright E2E
#   RUN_COMPOSE_E2E=1 -> run compose-based E2E

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Backend quality gate"
pushd "$REPO_ROOT/api" >/dev/null
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest tests/ -v --tb=short --cov
popd >/dev/null

echo "==> Frontend quality gate"
pushd "$REPO_ROOT/web" >/dev/null
npm ci
npm run gen:api:check
npm run lint
npm run typecheck
npm run test
popd >/dev/null

echo "==> Documentation drift gate"
pushd "$REPO_ROOT" >/dev/null
python3 scripts/docs/check_docs.py
popd >/dev/null

if [[ "${RUN_PLAYWRIGHT:-0}" == "1" ]]; then
  echo "==> Playwright browser gate"
  pushd "$REPO_ROOT/web" >/dev/null
  npx playwright install --with-deps chromium
  npx playwright test
  popd >/dev/null
else
  echo "==> Skipping Playwright browser gate (set RUN_PLAYWRIGHT=1 to enable)"
fi

if [[ "${RUN_COMPOSE_E2E:-0}" == "1" ]]; then
  echo "==> Compose E2E gate"
  pushd "$REPO_ROOT" >/dev/null
  bash scripts/ci/package_frontend.sh web
  cp frontend.tar.xz web/frontend.tar.xz
  docker build -t flow-web:local web/
  docker build -t flow:local api/
  FLOW_WEB_IMAGE=flow-web:local FLOW_IMAGE=flow:local docker compose up -d
  pushd "$REPO_ROOT/web" >/dev/null
  PLAYWRIGHT_BASE_URL=http://localhost:8080 npx playwright test e2e/compose.spec.ts
  popd >/dev/null
  popd >/dev/null
else
  echo "==> Skipping compose E2E gate (set RUN_COMPOSE_E2E=1 to enable)"
fi

echo "==> Pre-push quality gate completed successfully"
