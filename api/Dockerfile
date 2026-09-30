# ---- Builder stage ----
FROM python:3.14.7-slim-bookworm AS builder

# Install uv (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv

WORKDIR /build

# Ensure uv installs into /opt/venv (not /build/.venv)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy only dependency manifests first for caching
COPY pyproject.toml uv.lock ./

# Create venv and install deps (frozen, no dev)
RUN uv venv /opt/venv && \
    uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY config/ ./config/

# Install project itself into the venv
RUN uv sync --frozen --no-dev


# ---- Runtime stage ----
FROM python:3.14.7-slim-bookworm AS runtime

# OCI labels for traceability
ARG BUILD_DATE
ARG VCS_REF
ARG SOURCE_URL
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.title="flow-app-backend" \
      org.opencontainers.image.description="Flow App Backend API"

# Environment: no bytecode, unbuffered output, venv on PATH
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    API_HOST=:: \
    FLOW_BAKED_PROMPTS_DIR=/opt/flow/prompts \
    FLOW_BAKED_CONFIG_DIR=/opt/flow/config \
    BUILD_DATE="${BUILD_DATE}" \
    VCS_REF="${VCS_REF}"

# Create non-root user
RUN groupadd --system app && \
    useradd --system --gid app --home-dir /app --no-create-home app && \
    mkdir -p /app/data && \
    chown app:app /app/data

WORKDIR /app

# Copy venv and app code from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/app ./app
COPY --from=builder /build/prompts ./prompts
# Static JSON config (interventions.json, spark_library.json) read directly off
# disk by app/services/* at a fixed path relative to the app package — must be
# baked into the image since nothing bind-mounts over ./config in production.
COPY --from=builder /build/config ./config
# Baked fallback copies OUTSIDE the /app working tree. Production bind-mounts
# host directories over paths under /app (./prompts -> /app/prompts,
# ./app -> /app/data); these copies at /opt/flow/* can never be shadowed by
# such a mount, so newly added prompts/config always resolve even when a
# mounted directory is stale or absent. See app/prompt_loader.py and
# app/config_loader.py for the matching dual-location resolution logic.
COPY --from=builder /build/prompts /opt/flow/prompts
COPY --from=builder /build/config /opt/flow/config

# Switch to non-root user
USER app

EXPOSE 8000

# Role-agnostic healthcheck baked into the shared image. ``app.healthcheck`` is
# healthy if EITHER GET /healthz on $API_PORT returns 2xx (API role) OR a fresh
# worker heartbeat file exists (worker role) — so the same probe fits both
# containers with no env flag that older deployments would lack. The worker
# writes its heartbeat to a container-local temp path (never the shared volume),
# so the two signals stay mutually exclusive per container. Stdlib only (the
# slim image has no curl).
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD ["/opt/venv/bin/python", "-m", "app.healthcheck"]

# Entrypoint: run uvicorn through custom launcher script
ENTRYPOINT ["/opt/venv/bin/python", "-m", "app.serve"]
