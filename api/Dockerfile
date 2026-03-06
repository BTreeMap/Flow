# ---- Builder stage ----
FROM python:3.14.3-slim-bookworm AS builder

# Install uv (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv

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

# Install project itself into the venv
RUN uv sync --frozen --no-dev


# ---- Runtime stage ----
FROM python:3.14.3-slim-bookworm AS runtime

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

# Switch to non-root user
USER app

EXPOSE 8000

# Entrypoint: run uvicorn directly (no uv sync, no network)
ENTRYPOINT ["/opt/venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
