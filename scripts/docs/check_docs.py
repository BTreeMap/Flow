#!/usr/bin/env python3
"""Documentation drift checker.

Validates that documentation stays in sync with the codebase:
  1. API route table in README.md matches the current OpenAPI schema.
  2. Env var table in README.md matches api/app/config.py and .env.example.
  3. Relative markdown links in README.md and docs/**/*.md resolve to existing files.

Usage:
    python3 scripts/docs/check_docs.py

Exit codes:
    0 — all checks passed
    1 — one or more drift issues found
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def find_repo_root() -> Path:
    """Walk up from this script to find the repo root (contains README.md)."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "README.md").exists() and (p / "AGENTS.md").exists():
            return p
        p = p.parent
    raise RuntimeError("Could not find repo root")


REPO = find_repo_root()
ERRORS: list[str] = []


def error(msg: str) -> None:
    ERRORS.append(msg)
    print(f"  ✗ {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"  ✓ {msg}")


# ── 1. API route table vs OpenAPI schema ─────────────────────────────────

def check_api_routes() -> None:
    """Compare documented route table against OpenAPI spec."""
    print("\n[1/3] Checking API route table against OpenAPI schema …")

    readme = (REPO / "README.md").read_text()

    # Extract routes from the marker-delimited table
    m = re.search(
        r"<!-- ROUTE_TABLE_START -->\s*\n(.*?)\n\s*<!-- ROUTE_TABLE_END -->",
        readme,
        re.DOTALL,
    )
    if not m:
        error("README.md missing <!-- ROUTE_TABLE_START/END --> markers")
        return

    table_text = m.group(1)
    doc_routes: set[tuple[str, str]] = set()
    for line in table_text.strip().splitlines():
        # Match table rows like: | `GET` | `/healthz` | …
        row = re.match(
            r"\|\s*`(\w+)`\s*\|\s*`([^`]+)`\s*\|", line
        )
        if row:
            method = row.group(1).upper()
            path = row.group(2)
            doc_routes.add((method, path))

    if not doc_routes:
        error("Could not parse any routes from README route table")
        return

    # Get routes from OpenAPI JSON (generate it)
    openapi_json = REPO / "api" / "openapi.json"

    # Try to generate fresh OpenAPI via uv (for dependency resolution)
    import shutil
    import subprocess

    uv_bin = shutil.which("uv")
    if uv_bin:
        cmd = [uv_bin, "run", "python", "-m", "scripts.dump_openapi", "--out", str(openapi_json)]
    else:
        cmd = [sys.executable, "-m", "scripts.dump_openapi", "--out", str(openapi_json)]

    result = subprocess.run(
        cmd,
        cwd=REPO / "api",
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        error(f"Failed to generate OpenAPI: {result.stderr.strip()}")
        return

    import json
    schema = json.loads(openapi_json.read_text())
    openapi_routes: set[tuple[str, str]] = set()
    for path, methods in schema.get("paths", {}).items():
        for method in methods:
            if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                openapi_routes.add((method.upper(), path))

    # WebSocket routes are not in OpenAPI, keep them in doc_routes for comparison
    doc_http_routes = {r for r in doc_routes if r[0] != "WS"}

    missing_in_docs = openapi_routes - doc_http_routes
    extra_in_docs = doc_http_routes - openapi_routes

    if missing_in_docs:
        for method, path in sorted(missing_in_docs):
            error(f"Route in OpenAPI but missing from README: {method} {path}")
    if extra_in_docs:
        for method, path in sorted(extra_in_docs):
            error(f"Route in README but missing from OpenAPI: {method} {path}")

    if not missing_in_docs and not extra_in_docs:
        info(f"All {len(doc_http_routes)} HTTP routes match OpenAPI schema")

    # Check WS routes exist in main.py (OpenAPI doesn't include websockets)
    ws_routes = {r for r in doc_routes if r[0] == "WS"}
    if ws_routes:
        main_py = (REPO / "api" / "app" / "main.py").read_text()
        for _, path in ws_routes:
            if path not in main_py:
                error(f"WebSocket route {path} documented but not found in main.py")
            else:
                info(f"WebSocket route {path} verified in main.py")


# ── 2. Env var table vs config.py and .env.example ──────────────────────

def check_env_vars() -> None:
    """Compare documented env vars against config.py and .env.example."""
    print("\n[2/3] Checking environment variable documentation …")

    readme = (REPO / "README.md").read_text()

    # Extract env vars from the marker-delimited table
    m = re.search(
        r"<!-- ENV_TABLE_START -->\s*\n(.*?)\n\s*<!-- ENV_TABLE_END -->",
        readme,
        re.DOTALL,
    )
    if not m:
        error("README.md missing <!-- ENV_TABLE_START/END --> markers")
        return

    table_text = m.group(1)
    doc_vars: set[str] = set()
    for line in table_text.strip().splitlines():
        row = re.match(r"\|\s*`([^`]+)`\s*\|", line)
        if row:
            doc_vars.add(row.group(1))

    if not doc_vars:
        error("Could not parse any env vars from README env var table")
        return

    # Extract env vars from config.py
    config_py = (REPO / "api" / "app" / "config.py").read_text()
    config_vars: set[str] = set()
    for match in re.finditer(r'os\.environ\.get\(\s*"([^"]+)"', config_py):
        config_vars.add(match.group(1))

    # Check config.py vars are documented
    missing_config_vars = config_vars - doc_vars
    if missing_config_vars:
        for v in sorted(missing_config_vars):
            error(f"Env var in config.py but missing from README: {v}")
    else:
        info(f"All {len(config_vars)} config.py env vars are documented")

    # Extract env vars from .env.example
    env_example = (REPO / ".env.example").read_text()
    example_vars: set[str] = set()
    for line in env_example.splitlines():
        line = line.strip()
        if line.startswith("#") and "=" in line:
            # Commented-out vars like: # FLOW_DATA_DIR=/app/data
            m2 = re.match(r"#\s*([A-Z_][A-Z0-9_]*)=", line)
            if m2:
                example_vars.add(m2.group(1))
        elif "=" in line and not line.startswith("#"):
            var = line.split("=", 1)[0].strip()
            if var and re.match(r"^[A-Z_][A-Z0-9_]*$", var):
                example_vars.add(var)

    # Check .env.example vars are documented (only check vars that are in config.py)
    config_in_example = config_vars & example_vars
    missing_example_vars = config_in_example - doc_vars
    if missing_example_vars:
        for v in sorted(missing_example_vars):
            error(f"Env var in .env.example and config.py but missing from README: {v}")
    else:
        info(f".env.example vars that are in config.py are all documented")


# ── 3. Relative link hygiene ─────────────────────────────────────────────

def check_links() -> None:
    """Verify all relative markdown links resolve to existing files."""
    print("\n[3/3] Checking relative markdown links …")

    md_files = list(REPO.glob("docs/**/*.md")) + [REPO / "README.md"]
    broken = 0
    checked = 0

    for md_file in md_files:
        content = md_file.read_text()
        # Match [text](link) patterns, excluding URLs and anchors-only
        for match in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", content):
            link = match.group(2)

            # Skip external URLs, mailto, anchors-only
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue

            # Strip anchor from link
            link_path = link.split("#")[0]
            if not link_path:
                continue

            checked += 1
            target = (md_file.parent / link_path).resolve()
            if not target.exists():
                try:
                    display = target.relative_to(REPO)
                except ValueError:
                    display = target
                error(f"Broken link in {md_file.relative_to(REPO)}: [{match.group(1)}]({link}) → {display}")
                broken += 1

    if broken == 0:
        info(f"All {checked} relative links resolve correctly")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 60)
    print("Documentation Drift Checker")
    print("=" * 60)

    check_api_routes()
    check_env_vars()
    check_links()

    print()
    if ERRORS:
        print(f"FAILED: {len(ERRORS)} issue(s) found", file=sys.stderr)
        return 1
    else:
        print("PASSED: All checks passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
