#!/usr/bin/env bash
set -euo pipefail
# package_frontend.sh - Build and archive the frontend static assets.
#
# Produces:
#   frontend.zip
#   frontend.tar.xz
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
zip -r ../../frontend.zip .
tar -cJf ../../frontend.tar.xz .
cd ..

echo "Created frontend.zip and frontend.tar.xz"
ls -lh ../frontend.zip ../frontend.tar.xz
