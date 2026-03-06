# Flow Documentation

> **Start here.** This page indexes all project documentation and points you to the right place.

## Source of Truth

| Document | Status | Description |
|----------|--------|-------------|
| [`AGENTS.md`](../AGENTS.md) | **Authoritative** | Top-level project rules: identity, deployment, state model, write-path rules, permissions, CI gates |
| [`docs/current-architecture.md`](current-architecture.md) | **Authoritative** | Conversation engine architecture: Router + specialists, stores, proposals, audit trail |
| [`README.md`](../README.md) | **Authoritative** | Quick start, project structure, API endpoints, env vars, frontend pages |

## Reference

| Document | Status | Description |
|----------|--------|-------------|
| [`docs/release-process.md`](release-process.md) | Current | CI/CD workflows, versioning policy, Docker tags, image signing, local builds |
| [`docs/parity-matrix.md`](parity-matrix.md) | Historical | Maps legacy Go behaviors to Python implementation (legacy engine now removed) |
| [`docs/web-rescaffold-plan.md`](web-rescaffold-plan.md) | Historical | Frontend migration plan from original scaffold |

## Legacy (deprecated)

| Document | Status | Description |
|----------|--------|-------------|
| [`docs/legacy-conversation-flow-contract.md`](legacy-conversation-flow-contract.md) | **Deprecated** | Original Go PromptPipe behavioral contract. Not authoritative — retained for historical reference only. |

## Debug & Operations

| Document | Description |
|----------|-------------|
| [`docs/debug/ci-failures.md`](debug/ci-failures.md) | Root causes and fixes for past CI failures |
| [`docs/debug/docs-parity-report.md`](debug/docs-parity-report.md) | Documentation parity audit report and verification |

## Quick Links

- **Run the project:** See [README.md Quick Start](../README.md#quick-start)
- **API endpoints:** See [README.md API Endpoints](../README.md#api-endpoints)
- **Environment variables:** See [README.md Environment Variables](../README.md#environment-variables)
- **CI quality gate:** See [AGENTS.md Quality Gate](../AGENTS.md#quality-gate)
- **Architecture invariants:** See [AGENTS.md Core Invariants](../AGENTS.md#core-invariants)
- **Drift prevention:** See [README.md Drift Prevention](../README.md#drift-prevention)
