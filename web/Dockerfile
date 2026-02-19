FROM caddy:2-alpine

# OCI labels for traceability
ARG BUILD_DATE
ARG VCS_REF
ARG SOURCE_URL
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.title="flow-web" \
      org.opencontainers.image.description="Flow frontend and reverse proxy"

# Copy Caddy configuration
COPY Caddyfile /etc/caddy/Caddyfile

# Copy and extract pre-built frontend assets
# frontend.tar.xz is produced by scripts/ci/package_frontend.sh
ADD frontend.tar.xz /srv/

# Create non-root user and set ownership
RUN addgroup -S caddy && \
    adduser -S -G caddy caddy && \
    chown -R caddy:caddy /srv /data /config

# Run as non-root user
USER caddy

EXPOSE 8080
