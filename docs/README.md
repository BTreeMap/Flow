# Flow — Documentation Index

| Document | Purpose |
|----------|---------|
| [`../README.md`](../README.md) | Quick start, project structure, API endpoints, env vars |
| [`../AGENTS.md`](../AGENTS.md) | Lean agent operating manual: tooling, boundaries, doc pointers |
| [`current-architecture.md`](current-architecture.md) | Conversation engine: Router + specialists, stores, 4-condition experiment, EOD memory firewall |
| [`crypto-primitives.md`](crypto-primitives.md) | BLAKE3 usage policy, remaining protocol exceptions, and rotation behavior |
| [`release-process.md`](release-process.md) | CI/CD workflows, versioning, Docker tags, image signing |

## Agent domain docs (progressive disclosure)

Load just-in-time per task; referenced from [`../AGENTS.md`](../AGENTS.md).

| Document | Purpose |
|----------|---------|
| [`agents/engine-write-path.md`](agents/engine-write-path.md) | Authoritative state/authority/write-path rules, permission matrix, module duties |
| [`agents/migrations.md`](agents/migrations.md) | DB & migration discipline; data-integrity guarantee |
| [`agents/frontend.md`](agents/frontend.md) | Frontend / PWA / SSE / Web Push responsibilities |
| [`agents/invariants.md`](agents/invariants.md) | Identity, IDs, multi-tenancy, deployment invariants |
| [`agents/quality-gate.md`](agents/quality-gate.md) | Full quality-gate / CI command reference |
| [`agents/bootstrap.md`](agents/bootstrap.md) | Submodule + required skill loading |
