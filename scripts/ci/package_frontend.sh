#!/usr/bin/env bash
set -euo pipefail
# package_frontend.sh - Build and archive the frontend static assets.
#
# Produces:
#   frontend-dist.zip
#   frontend-dist.tar.xz
#
# Usage: ./scripts/ci/package_frontend.sh [web_dir]

WEB_DIR="${1:-web}"

if [ ! -d "$WEB_DIR" ]; then
  echo "Error: web directory '$WEB_DIR' not found" >&2
  exit 1
fi

cd "$WEB_DIR"

# Install dependencies deterministically
if [ -f package-lock.json ]; then
  npm ci
elif [ -f pnpm-lock.yaml ]; then
  pnpm install --frozen-lockfile
else
  echo "Error: no lockfile found" >&2
  exit 1
fi

# Build
npm run build

# Verify build output
if [ ! -d dist ]; then
  echo "Error: dist/ directory not created by build" >&2
  exit 1
fi

# Create archives
cd dist
zip -r ../../frontend-dist.zip .
tar -cJf ../../frontend-dist.tar.xz .
cd ..

echo "Created frontend-dist.zip and frontend-dist.tar.xz"
ls -lh ../frontend-dist.zip ../frontend-dist.tar.xz
