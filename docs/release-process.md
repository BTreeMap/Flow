# Release Process

## CI and Release Triggers

### CI Quality Gate (`ci.yml`)

Triggers:

- **Pull requests** — all branches
- **Push to `main`**

Jobs (all blocking):

1. **backend-unit-integration** — pytest on SQLite and Postgres (matrix)
2. **frontend-unit-integration** — lint, typecheck, vitest
3. **e2e** — Playwright end-to-end on SQLite and Postgres (matrix, Vite dev server)
4. **e2e-compose** — Playwright end-to-end against Docker Compose stack on SQLite and Postgres (matrix)
5. **container-security** — Trivy scan of backend Docker image (fail on CRITICAL)
6. **container-security-web** — Trivy scan of flow-web Docker image (fail on CRITICAL)

PR concurrency: cancels redundant runs on the same PR branch.

### Release Workflow (`release.yml`)

Triggers:

- **Push to `main`**
- **`release: published`** (GitHub release event)
- **`workflow_dispatch`** (manual trigger)

Gating: release is gated by backend unit+integration tests and frontend unit tests **only**. End-to-end tests run in parallel but do not block the release.

Concurrency: serialized — newer runs wait rather than cancel in-progress runs (`cancel-in-progress: false`).

---

## Versioning Policy

### Dev release version string

Given the latest stable tag `vX.Y.Z`, the next automated dev release version is:

```
vX.Y.(Z+1)-dev.YYYY-MM-DD.HH-MM-SS.SHORT_SHA
```

- Patch number is incremented from the latest stable tag.
- `-dev.` prerelease segment encodes UTC timestamp and 7-char short SHA.
- No `+` character is used anywhere.
- If no stable tag exists, the base version is `v0.1.0`.

### Stable releases

Stable releases (`vX.Y.Z` without prerelease suffix) are created manually by tagging a commit. The CI and release workflows recognize these as stable base versions.

---

## Docker Tag Policy

### Image registry

Two images are published to GHCR:

| Image | Package | Description |
|-------|---------|-------------|
| `ghcr.io/<owner>/<repo>` | `flow` | Backend API (FastAPI + uvicorn) |
| `ghcr.io/<owner>/<repo>-web` | `flow-web` | Frontend + reverse proxy (Caddy) |

### Dev build tags (always published)

| Tag | Example |
|-----|---------|
| `:dev` | `:dev` |
| `:dev.YYYY-MM-DD` | `:dev.2026-02-15` |
| `:dev.SHORT_SHA` | `:dev.abc1234` |
| `:dev.YYYY-MM-DD.SHORT_SHA` | `:dev.2026-02-15.abc1234` |
| `:latest` | `:latest` |

Both images use the same tag scheme.

### Release tags (published with GitHub release)

| Tag | Example |
|-----|---------|
| `:stable` | `:stable` |
| `:YYYY-MM-DD` | `:2026-02-15` |
| `:SHORT_SHA` | `:abc1234` |
| `:YYYY-MM-DD.SHORT_SHA` | `:2026-02-15.abc1234` |

### Multi-arch manifest strategy

Images are built natively on separate runners:

- `linux/amd64` on `ubuntu-24.04`
- `linux/arm64` on `ubuntu-24.04-arm`

Each architecture job pushes a single-platform image under a temporary tag. A final manifest job creates multi-arch manifest lists using `docker buildx imagetools create`.

**No QEMU emulation is used.**

---

## How to Cut a Release Manually

### Automated dev release

Push to `main` or use the GitHub Actions UI:

1. Go to **Actions** → **Release** → **Run workflow**
2. Select the `main` branch
3. Click **Run workflow**

### Stable release

1. Tag a commit with a stable version: `git tag v1.0.0`
2. Push the tag: `git push origin v1.0.0`
3. Future dev releases will increment from this tag.

---

## How to Reproduce Builds Locally

### Backend Docker image

```bash
cd api
docker build \
  --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg VCS_REF="$(git rev-parse --short=7 HEAD)" \
  --build-arg SOURCE_URL="https://github.com/<owner>/<repo>" \
  -t flow:local .
```

### Frontend + reverse proxy Docker image (flow-web)

```bash
# Build the frontend archive first
bash scripts/ci/package_frontend.sh web
cp frontend.tar.xz web/frontend.tar.xz

# Build the flow-web image
cd web
docker build \
  --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg VCS_REF="$(git rev-parse --short=7 HEAD)" \
  --build-arg SOURCE_URL="https://github.com/<owner>/<repo>" \
  -t flow-web:local .
```

### Run with Docker Compose

```bash
FLOW_WEB_IMAGE=flow-web:local FLOW_IMAGE=flow:local docker compose up
```

The stack is accessible at `http://localhost:8080`.

### Frontend archives

```bash
bash scripts/ci/package_frontend.sh web
# Produces: frontend.zip, frontend.tar.xz
```

### Version computation

```bash
python3 scripts/ci/compute_version.py --write
# Produces: release-metadata.json + prints JSON to stdout
```

---

## Security Posture

### Container hardening

#### Backend (flow)

- **Multi-stage build**: build tools only in builder stage; runtime has no compilers, git, curl, or build-essential.
- **Non-root user**: dedicated `app` user in runtime stage.
- **No bytecode**: `PYTHONDONTWRITEBYTECODE=1`
- **No network at startup**: all Python deps pre-installed; no PyPI contact at runtime.
- **OCI labels**: source URL, revision SHA, build timestamp.
- **Base image pinned**: `python:3.14.3-slim-bookworm`

#### Frontend + reverse proxy (flow-web)

- **Pre-built assets**: consumes `frontend.tar.xz` from CI — no build tools in image.
- **Non-root user**: dedicated `caddy` user.
- **HTTP-only**: `auto_https off` — TLS terminated by Cloudflare Tunnel upstream.
- **Non-privileged port**: listens on 8080, not 80/443.
- **Admin API disabled**: `admin off`, `persist_config off`.
- **OCI labels**: source URL, revision SHA, build timestamp.
- **Base image**: official `caddy:2` (Alpine-based).

### Recommended runtime flags

```bash
docker run \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --read-only \
  --tmpfs /tmp \
  -p 8000:8000 \
  ghcr.io/<owner>/<repo>-backend:latest
```

### Supply chain security

- **Signing**: images signed with Sigstore Cosign keyless signing (OIDC-based, no stored keys).
- **SBOM and provenance**: generated by Docker Buildx during image push.
- **Vulnerability scanning**: Trivy scans in CI (fail on CRITICAL) and release (fail on CRITICAL).
- **Dependency locking**: `uv.lock` (backend, `--frozen`), `package-lock.json` (frontend, `npm ci`).
- **Least-privilege permissions**: CI workflows are read-only; release workflow has `contents: write`, `packages: write`, `id-token: write`.

### Verify image signature

```bash
# Backend
cosign verify \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  --certificate-identity-regexp="github.com/<owner>/<repo>" \
  ghcr.io/<owner>/<repo>:latest

# Frontend (flow-web)
cosign verify \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  --certificate-identity-regexp="github.com/<owner>/<repo>" \
  ghcr.io/<owner>/<repo>-web:latest
```

---

## ARM64 Runner Requirements

The release workflow uses `ubuntu-24.04-arm` (GitHub-hosted ARM64 runner) for native arm64 builds.

### If `ubuntu-24.04-arm` is unavailable

If the runner label is not available (e.g., private repo constraints):

1. Set up a self-hosted ARM64 runner or use an org/enterprise runner group.
2. Update the `runs-on` value in `build-push-arm64` job in `release.yml`:

   ```yaml
   runs-on: [self-hosted, linux, arm64]
   ```

3. Ensure the runner has Docker and Docker Buildx installed.

**Do not fall back to QEMU emulation.** Native builds are required for acceptable build times and image correctness.
