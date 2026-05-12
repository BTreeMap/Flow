FROM caddy:2.11.2-alpine

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
COPY --chown=root:root Caddyfile /etc/caddy/Caddyfile

# Copy and extract pre-built frontend assets
# frontend.tar.xz is produced by scripts/ci/package_frontend.sh
ADD frontend.tar.xz /srv/

# Create non-root user and set ownership
RUN set -eux; \
    grep -q '^caddy:' /etc/group || addgroup -S caddy; \
    grep -q '^caddy:' /etc/passwd || adduser -S -D -H -G caddy caddy; \
    chmod 0644 /etc/caddy/Caddyfile; \
    chown -R caddy:caddy /srv /data /config; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'export WEB_PORT="${WEB_PORT:-${PORT:-8080}}"' \
      'exec "$@"' \
      > /usr/local/bin/flow-web-entrypoint.sh; \
    chmod 0755 /usr/local/bin/flow-web-entrypoint.sh

# Run as non-root user
USER caddy

ENTRYPOINT ["/usr/local/bin/flow-web-entrypoint.sh"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]

EXPOSE 8080
