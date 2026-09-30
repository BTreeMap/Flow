"""Thin loader for static JSON config files with dual-location resolution.

Mirrors ``app.prompt_loader``'s resolution strategy: a mountable directory is
checked first so an override can be dropped in without rebuilding the image,
falling back to a copy baked into the image at a location that lives
**completely outside** the application working tree. This matters in
production where ``docker-compose`` bind-mounts host directories over paths
under ``/app`` (e.g. ``./prompts -> /app/prompts`` and ``./app -> /app/data``):
a stale or absent mount would otherwise shadow a config file and raise
``FileNotFoundError`` (surfacing as a 500/503) at request time instead of at
boot.

Resolution order (first match wins):

1. ``$FLOW_CONFIG_DIR`` (explicit override, optional).
2. ``<repo>/config`` — the mountable directory (``/app/config`` in Docker).
3. ``$FLOW_BAKED_CONFIG_DIR`` / ``/opt/flow/config`` — baked into the image
   outside ``/app``, so no bind-mount under ``/app`` can ever shadow it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent

# Absolute, image-baked fallback that lives outside the /app working tree so it
# cannot be shadowed by any bind-mount under /app. Overridable via env for
# tests and bespoke deployments. The Dockerfile copies config here and sets
# the var.
_BAKED_CONFIG_DIR = Path(os.environ.get("FLOW_BAKED_CONFIG_DIR", "/opt/flow/config"))

# Candidate directories in priority order. The mountable directory is checked
# first so operators can override individual config files; the image-baked
# copy is the always-present fallback that a bind-mount under /app cannot
# shadow.
_CANDIDATE_DIRS: list[Path] = [
    _PACKAGE_DIR.parent / "config",  # mountable: api/config or /app/config
    _BAKED_CONFIG_DIR,  # baked fallback outside /app: /opt/flow/config
]


def resolve_config_path(filename: str) -> Path:
    """Return the first existing path for ``config/{filename}``.

    The optional ``FLOW_CONFIG_DIR`` environment variable is consulted first so
    it can be changed at runtime without reimporting the module.

    Resolution is intentionally *loud*: if a higher-priority directory exists
    but does not contain the file, we log a WARNING before falling back. That
    single log line is what turns an invisible "stale bind-mount" deployment
    bug into an obvious one.
    """
    candidates: list[Path] = []
    override = os.environ.get("FLOW_CONFIG_DIR")
    if override:
        candidates.append(Path(override))
    candidates.extend(_CANDIDATE_DIRS)

    skipped: list[Path] = []
    for directory in candidates:
        path = directory / filename
        if path.is_file():
            if skipped:
                logger.warning(
                    "Config file '%s' not found in higher-priority dir(s) %s; "
                    "resolved from fallback '%s'. A stale or incomplete mount "
                    "may be shadowing it.",
                    filename,
                    ", ".join(str(d) for d in skipped),
                    path.parent,
                )
            return path
        # Only record directories that actually exist as "skipped"; a
        # non-existent candidate is expected (e.g. no override configured).
        if directory.is_dir():
            skipped.append(directory)

    logger.error(
        "Config file '%s' not found in any candidate directory: %s",
        filename,
        ", ".join(str(directory) for directory in candidates),
    )
    raise FileNotFoundError(
        f"Config file '{filename}' not found in any of: "
        + ", ".join(str(directory) for directory in candidates)
    )


def describe_resolution() -> list[tuple[str, bool]]:
    """Return ``(directory, exists)`` for each config candidate, in priority order.

    Used by startup diagnostics so the docker log shows exactly which config
    directories are in effect — making a missing or shadowing mount obvious at
    boot rather than at first request.
    """
    dirs: list[Path] = []
    override = os.environ.get("FLOW_CONFIG_DIR")
    if override:
        dirs.append(Path(override))
    dirs.extend(_CANDIDATE_DIRS)
    return [(str(directory), directory.is_dir()) for directory in dirs]
