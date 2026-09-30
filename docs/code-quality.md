# Code Quality Standards

This document describes the linting, type-checking, and formatting guardrails
that gate every change to the Flow codebase, and the conventions
they enforce.

## Goals

- **Make invalid states unrepresentable.** Prefer precise types (Pydantic
  models, `Literal`/`Enum`, discriminated unions on the backend; discriminated
  unions and `unknown`-narrowing on the frontend) over `Any`/`any`.
- **Never silently swallow errors.** Exceptions are chained (`raise ... from`)
  or surfaced; promises are awaited or explicitly discarded with `void`.
- **Keep modules focused.** Source files should stay well under ~500 lines;
  large files are decomposed into cohesive units.
- **Elegant and idiomatic** over clever. The tooling encodes the house style so
  reviews focus on design, not nits.

## Backend (`api/`)

All configuration lives in [api/pyproject.toml](../api/pyproject.toml).

### Ruff (lint + format)

```bash
cd api
uv run ruff check .
uv run ruff format --check .
```

Enabled rule families: `E`, `F`, `I` (import sorting), `UP` (pyupgrade), `B`
(bugbear), `SIM`, `C4`, `PIE`, `RET`, `TID` (banned relative imports), `ASYNC`,
`PERF`, and `RUF`. Line length is 88. Tests and generated migrations have
targeted per-file ignores.

Key consequences:

- `B904` — exceptions raised inside an `except` block must chain the cause with
  `raise ... from exc` (or `from None` when the cause is deliberately hidden).
- `TID` — relative imports across parent packages are banned; use absolute
  `app.*` imports.
- `ASYNC`/`PERF` — flags blocking calls in async code and obvious perf foot-guns.

### Type checking (basedpyright)

```bash
cd api
uv run basedpyright
```

Runs in `standard` mode over `app/` (migrations excluded). The build is green at
**zero** reported errors. New code must be fully typed; avoid `Any` except at
genuine system boundaries.

### Tests + coverage

```bash
cd api
uv run pytest tests/ -v --cov
```

`pytest` runs in strict mode (`--strict-markers --strict-config`) with
`asyncio_mode = "auto"`. Coverage is measured with branch coverage and a
`fail_under` floor; the floor ratchets upward as coverage improves — never down.

## Frontend (`web/`)

Configuration lives in [web/eslint.config.js](../web/eslint.config.js) and the
`tsconfig.*.json` files.

### ESLint (type-aware, strict)

```bash
cd web
npm run lint
```

The config extends `typescript-eslint`'s `strictTypeChecked` and
`stylisticTypeChecked` presets with the type-aware `projectService`. The safety
rules are non-negotiable and must be fixed at the call site:

- `no-floating-promises` / `no-misused-promises` — every promise is awaited, or
  explicitly discarded with `void fn()` (e.g. `onClick={() => void save()}`).
- `no-unsafe-*` / `no-explicit-any` — untyped data is given an explicit type
  (interface or `as` cast at the parse boundary), not left as `any`.
- `no-non-null-assertion` — replace `x!` with a real guard or narrowing.
- `no-deprecated` — avoid deprecated DOM/React APIs.

A few stylistic/behavior-risky rules are tuned rather than blindly applied:
`restrict-template-expressions` allows numbers/booleans,
`no-confusing-void-expression` allows arrow shorthand, and
`prefer-nullish-coalescing` / `no-unnecessary-condition` are disabled because
`||` fallbacks and defensive guards are intentional here. Test files relax the
`no-unsafe-*`, non-null, and mock-friendly rules.

### Type checking + tests

```bash
cd web
npm run typecheck   # tsc --noEmit (strict, noUncheckedIndexedAccess)
npm run test        # vitest
```

### OpenAPI contract

Backend schema changes must be reflected in the generated client types:

```bash
cd web
npm run gen:api:check   # fails if web/src/api/openapi.ts is stale
npm run gen:api         # regenerate, then commit
```

## Pre-commit hooks

Install the shared hooks to catch issues before they reach CI:

```bash
pipx install pre-commit
pre-commit install
pre-commit run --all-files
```

The hooks run ruff (lint + format) on `api/`, ESLint and `tsc` on `web/`, and a
set of generic hygiene checks. See
[.pre-commit-config.yaml](../.pre-commit-config.yaml).

## Continuous integration

[.github/workflows/ci.yml](../.github/workflows/ci.yml) enforces the same gates:

- **backend**: ruff lint + format, basedpyright, pytest with coverage (SQLite
  and Postgres matrices).
- **frontend**: OpenAPI drift check, ESLint, `tsc`, vitest.
- **e2e**: Playwright against both database backends and the compose stack.

All gates must pass before merge.

## Pre-push standard procedure

Use the repository helper script before every push:

```bash
bash scripts/ci/pre_push_quality_gate.sh
```

This runs, in order:

- Backend lint/format/typecheck/tests with coverage
- Frontend OpenAPI sync check, lint, typecheck, tests
- Documentation drift checker (`python3 scripts/docs/check_docs.py`)

If your local environment supports browser E2E, include those explicitly:

```bash
RUN_PLAYWRIGHT=1 RUN_COMPOSE_E2E=1 bash scripts/ci/pre_push_quality_gate.sh
```

In environments where Playwright/Chromium cannot run, you can run the default
script and rely on CI for browser gates while still enforcing all other
pre-push checks.
