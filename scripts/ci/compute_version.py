#!/usr/bin/env python3
"""Compute the next dev release version from git tags.

Reads the latest stable tag matching vX.Y.Z (ignoring dev tags),
increments the patch number, and produces a dev version string
with UTC timestamp and short SHA.

Outputs JSON to stdout and optionally writes to release-metadata.json.
"""

import json
import re
import subprocess
import sys
from datetime import UTC, datetime


STABLE_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_latest_stable_tag() -> tuple[int, int, int] | None:
    """Find the latest stable tag matching vX.Y.Z (no prerelease)."""
    try:
        raw = git("tag", "--list", "--sort=-v:refname")
    except subprocess.CalledProcessError:
        return None

    for line in raw.splitlines():
        tag = line.strip()
        m = STABLE_TAG_RE.match(tag)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def get_short_sha() -> str:
    return git("rev-parse", "--short=7", "HEAD")


def main() -> None:
    now = datetime.now(UTC)
    short_sha = get_short_sha()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")

    stable = get_latest_stable_tag()
    if stable is None:
        major, minor, patch = 0, 1, 0
    else:
        major, minor, patch = stable
        patch += 1

    # Version string: vX.Y.Z-dev.YYYY-MM-DD.HH-MM-SS.SHORT_SHA
    version = f"v{major}.{minor}.{patch}-dev.{date_str}.{time_str}.{short_sha}"

    # Docker image name placeholder (filled by workflow)
    image_base = "ghcr.io/OWNER/REPO-backend"

    # Docker tags for dev builds
    docker_tags = [
        f"{image_base}:dev",
        f"{image_base}:dev.{date_str}",
        f"{image_base}:dev.{short_sha}",
        f"{image_base}:dev.{date_str}.{short_sha}",
    ]

    # Additional tags when a GitHub release is created
    release_docker_tags = [
        f"{image_base}:latest",
        f"{image_base}:{date_str}",
        f"{image_base}:{short_sha}",
        f"{image_base}:{date_str}.{short_sha}",
    ]

    metadata = {
        "version": version,
        "major": major,
        "minor": minor,
        "patch": patch,
        "date": date_str,
        "time": time_str,
        "short_sha": short_sha,
        "docker_tags_dev": docker_tags,
        "docker_tags_release": release_docker_tags,
    }

    # Write to file if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--write":
        with open("release-metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
            f.write("\n")
        print(f"Wrote release-metadata.json", file=sys.stderr)

    # Always print JSON to stdout
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
