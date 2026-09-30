"""Static, researcher-curated Spark library for conditions A and B.

Conditions A ("Random Spark") and B ("choose from one Spark per vibe, no
intake") are Spark's non-adaptive control groups: they never personalize to the
user, so unlike C/D they need no LLM call at all.

Data source (in priority order)
--------------------------------
1. **Google Sheets** — when ``SPARK_SHEETS_SPREADSHEET_ID`` *and* one of
    ``SPARK_SHEETS_CREDENTIALS_JSON`` or ``SPARK_SHEETS_CREDENTIALS_FILE`` are
    configured the library is loaded from a researcher-maintained spreadsheet.
    Collaborators can add or edit prompts without touching the repository.
2. **Bundled JSON** (``api/config/spark_library.json``) — always-present
   fallback loaded via :func:`app.config_loader.resolve_config_path`.

Cache strategy (stale-while-revalidate)
----------------------------------------
* Fresh (age < TTL, default 60 s): served immediately from memory.
* Stale: the current snapshot is returned *immediately*; a background task
  refreshes from Sheets without blocking the request.
* Sheets-never-succeeded (cold start failure): bundled JSON is used.
* Sheets-failed-after-success: the last-good Sheets snapshot is served
  indefinitely until a refresh succeeds.

Selection logic
----------------
  Condition A (:func:`pick_random_sparks`): pick uniformly at random from the
               *entire* library (true random, no choice).
  Condition B (:func:`pick_one_spark_per_frame`): return exactly one randomly
               chosen Spark *per vibe* — five concrete cards the participant
               chooses between. B no longer asks for a vibe up front: the vibe
               is a projection of whichever card the participant picks, so the
               "declared a vibe but has seen no Spark" state cannot occur.

Both selectors are total: :func:`_validate_entries` guarantees every frame has
at least two entries, so no pool is ever empty and neither function can fail on
a valid library.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from dataclasses import dataclass, field
from hashlib import sha256
from time import monotonic
from typing import Literal

from app.config_loader import resolve_config_path

logger = logging.getLogger(__name__)

SparkFrame = Literal["calm", "zoomies", "silly", "challenge", "science"]
ALL_FRAMES: tuple[SparkFrame, ...] = (
    "calm",
    "zoomies",
    "silly",
    "challenge",
    "science",
)

# Generic, frame-level rationale — mirrors the tone established for each vibe
# in sparkData.ts / spark_proxy_system.txt.
_WHY_BY_FRAME: dict[SparkFrame, str] = {
    "calm": (
        "A slow, low-effort reset like this can ease physical tension and "
        "help you refocus without raising your heart rate."
    ),
    "zoomies": (
        "A quick burst of movement gets your blood flowing and counters the "
        "energy dip that comes from sitting still."
    ),
    "silly": (
        "Movement doesn't have to be serious to work -- a playful break "
        "still delivers the same physical reset, and a grin is a bonus."
    ),
    "challenge": (
        "A higher-intensity option recruits more muscle groups and gives a "
        "stronger nudge to your alertness than a gentle stretch."
    ),
    "science": (
        "Short movement breaks are linked to better circulation and renewed "
        "focus, even in just sixty seconds."
    ),
}

_LIBRARY_FILENAME = "spark_library.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SparkLibraryEntry:
    id: str
    tags: tuple[SparkFrame, ...]
    title: str
    action: str
    reward: str


@dataclass(frozen=True)
class ResolvedSpark:
    """A library entry resolved to a single concrete frame for one response."""

    id: str
    frame: SparkFrame
    title: str
    action: str
    reward: str
    why: str


# ---------------------------------------------------------------------------
# In-memory cache state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CacheState:
    entries: tuple[SparkLibraryEntry, ...]
    version_hash: str
    source: Literal["sheets", "file"]
    fetched_at: float = field(default_factory=monotonic)


_cache: _CacheState | None = None
_refresh_task: asyncio.Task[bool] | None = None
_refresh_lock: asyncio.Lock | None = None
_refresh_lock_loop: asyncio.AbstractEventLoop | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_entries(entries: tuple[SparkLibraryEntry, ...]) -> None:
    """Raise ``ValueError`` unless every frame has ≥ 2 entries.

    This is the make-invalid-states-unrepresentable guard: every Spark vibe
    must be selectable in condition B so every frame needs at least two
    entries (one alone would make that vibe deterministic, not a choice).
    """
    if not entries:
        raise ValueError("Spark library must contain at least one entry")
    for frame in ALL_FRAMES:
        tag_count = sum(1 for entry in entries if frame in entry.tags)
        if tag_count < 2:
            raise ValueError(
                f"Spark library tag '{frame}' has only {tag_count} "
                "entry(ies); every tag needs at least 2"
            )


def _compute_hash(entries: tuple[SparkLibraryEntry, ...]) -> str:
    """Return a deterministic SHA-256 hex digest of the library content.

    The hash is sorted by entry id and uses canonical JSON so that identical
    data from any source produces the same digest — enabling reliable change
    detection in the ``prompt_version`` field regardless of Sheets vs file.
    """
    sorted_entries = sorted(entries, key=lambda e: e.id)
    payload = json.dumps(
        [
            {
                "id": e.id,
                "title": e.title,
                "action": e.action,
                "reward": e.reward,
                "tags": sorted(e.tags),
            }
            for e in sorted_entries
        ],
        sort_keys=True,
        ensure_ascii=True,
    )
    return sha256(payload.encode()).hexdigest()


def _load_from_file() -> tuple[SparkLibraryEntry, ...]:
    """Load and validate SparkLibraryEntry records from the bundled JSON file."""
    library_path = resolve_config_path(_LIBRARY_FILENAME)
    with library_path.open(encoding="utf-8") as config_file:
        raw = json.load(config_file)

    if not isinstance(raw, dict) or not isinstance(raw.get("sparks"), list):
        raise ValueError("spark_library.json must contain a 'sparks' array")

    entries: list[SparkLibraryEntry] = []
    for item in raw["sparks"]:
        if not isinstance(item, dict):
            raise ValueError("Each spark_library entry must be an object")
        tags = item.get("tags")
        if not isinstance(tags, list) or not tags:
            raise ValueError(
                f"Entry '{item.get('id')}' must have a non-empty 'tags' list"
            )
        for tag in tags:
            if tag not in ALL_FRAMES:
                raise ValueError(f"Entry '{item.get('id')}' has unknown tag '{tag}'")
        entries.append(
            SparkLibraryEntry(
                id=str(item["id"]),
                tags=tuple(tags),
                title=str(item["title"]),
                action=str(item["action"]),
                reward=str(item["reward"]),
            )
        )

    result = tuple(entries)
    _validate_entries(result)
    return result


def _sheets_is_configured() -> bool:
    from app.config import (
        get_spark_sheets_credentials_file,
        get_spark_sheets_credentials_json,
        get_spark_sheets_spreadsheet_id,
    )

    return bool(
        get_spark_sheets_spreadsheet_id()
        and (get_spark_sheets_credentials_json() or get_spark_sheets_credentials_file())
    )


# ---------------------------------------------------------------------------
# Async refresh pipeline
# ---------------------------------------------------------------------------


async def _do_refresh() -> None:
    """Load entries from Sheets (if configured) or the bundled JSON.

    On Sheets failure after a prior successful load the existing snapshot is
    preserved so the endpoint keeps serving stale-but-valid data.  ``fetched_at``
    is intentionally *not* updated in that case so the next request re-triggers
    a retry after the TTL expires.
    """
    global _cache

    if _sheets_is_configured():
        from app.config import (
            get_spark_sheets_credentials_file,
            get_spark_sheets_credentials_json,
            get_spark_sheets_range,
            get_spark_sheets_spreadsheet_id,
            get_spark_sheets_timeout,
        )
        from app.services.spark_sheets_source import fetch_entries_from_sheets

        try:
            result = await asyncio.to_thread(
                fetch_entries_from_sheets,
                get_spark_sheets_credentials_json(),
                get_spark_sheets_spreadsheet_id(),
                get_spark_sheets_range(),
                get_spark_sheets_timeout(),
                credentials_file=get_spark_sheets_credentials_file(),
            )
            _validate_entries(result.entries)
            _cache = _CacheState(
                entries=result.entries,
                version_hash=_compute_hash(result.entries),
                source="sheets",
            )
            logger.info(
                "Spark library loaded from remote Google Sheets: %d entries (hash %s…)",
                len(result.entries),
                _cache.version_hash[:8],
            )
            return
        except Exception as exc:
            fate = (
                "keeping last-good snapshot"
                if _cache is not None
                else "falling back to bundled JSON"
            )
            logger.warning(
                "Spark Sheets fetch failed (%s: %s); %s",
                type(exc).__name__,
                exc,
                fate,
            )
            if _cache is not None:
                # Keep serving existing snapshot; do NOT update fetched_at so
                # the next stale request triggers another retry after the TTL.
                return

    # Sheets not configured or first-ever Sheets fetch failed — load bundled JSON.
    file_entries = _load_from_file()  # propagates on failure
    _cache = _CacheState(
        entries=file_entries,
        version_hash=_compute_hash(file_entries),
        source="file",
    )
    logger.debug(
        "Spark library loaded from bundled JSON: %d entries", len(file_entries)
    )


def _get_refresh_lock() -> asyncio.Lock:
    """Return the single-flight lock for the current application event loop."""
    global _refresh_lock, _refresh_lock_loop

    loop = asyncio.get_running_loop()
    if _refresh_lock is None:
        _refresh_lock = asyncio.Lock()
        _refresh_lock_loop = loop
    elif _refresh_lock_loop is not loop:
        if _refresh_task is not None and not _refresh_task.done():
            raise RuntimeError("Spark library refresh cannot cross event loops")
        _refresh_lock = asyncio.Lock()
        _refresh_lock_loop = loop
    return _refresh_lock


async def _run_library_refresh() -> bool:
    """Refresh once, containing failures for all concurrent task joiners."""
    try:
        await _do_refresh()
        return _cache is not None
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error(
            "Spark library refresh failed entirely (%s): %s",
            type(exc).__name__,
            exc,
        )
        return False


async def _get_or_create_refresh_task() -> tuple[asyncio.Task[bool], bool]:
    """Return the one in-flight refresh task, creating it exactly once."""
    global _refresh_task

    async with _get_refresh_lock():
        if _refresh_task is None or _refresh_task.done():
            _refresh_task = asyncio.create_task(
                _run_library_refresh(),
                name="spark-library-refresh",
            )
            return _refresh_task, True
        return _refresh_task, False


async def schedule_sheets_startup_warmup() -> asyncio.Task[bool] | None:
    """Schedule one non-blocking startup fetch when Sheets is configured.

    The returned task loads, validates, and caches the remote library. API
    startup deliberately does not await it. A first A/B request that arrives
    during the warmup awaits this task rather than issuing a duplicate fetch.
    """
    if not _sheets_is_configured():
        return None

    task, created = await _get_or_create_refresh_task()
    if created:
        logger.info("Spark Sheets remote warmup scheduled; API startup will not wait")
    return task


async def cancel_library_refresh() -> None:
    """Cancel and join the single in-flight refresh during application shutdown."""
    async with _get_refresh_lock():
        task = _refresh_task
        if task is None or task.done():
            return
        task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _get_library() -> tuple[SparkLibraryEntry, ...]:
    """Return library entries, applying stale-while-revalidate semantics."""
    from app.config import get_spark_sheets_cache_ttl

    ttl = get_spark_sheets_cache_ttl()
    now = monotonic()
    snapshot = _cache

    if snapshot is not None:
        if (now - snapshot.fetched_at) < ttl:
            return snapshot.entries  # fresh: serve immediately

        # Stale: return current snapshot and kick off a background refresh.
        await _get_or_create_refresh_task()
        return snapshot.entries

    # Cold start: join a startup refresh or create exactly one new refresh.
    refresh_task, _ = await _get_or_create_refresh_task()
    loaded = await asyncio.shield(refresh_task)
    if loaded and _cache is not None:
        return _cache.entries

    raise RuntimeError("Spark library failed to load from all sources")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def library_version() -> dict[str, str]:
    """Return version and source metadata for the active Spark dataset.

    Mirrors the shape :func:`app.prompt_loader.prompt_version` uses for LLM
    prompts while adding ``source`` for operational diagnosis. ``source`` is
    ``"google-sheets"`` only after a successful remote fetch; it is
    ``"bundled-file"`` when serving the packaged fallback. The hash is computed
    over entry content (not raw file bytes) for determinism across sources.
    """
    if _cache is not None:
        return {
            "prompt_file": "spark_library",
            "prompt_sha256": _cache.version_hash,
            "source": "google-sheets" if _cache.source == "sheets" else "bundled-file",
        }
    # Pre-load fallback: called before any async request context (e.g. some tests).
    try:
        digest = sha256(resolve_config_path(_LIBRARY_FILENAME).read_bytes()).hexdigest()
    except FileNotFoundError:
        digest = "0" * 64
    return {
        "prompt_file": "spark_library",
        "prompt_sha256": digest,
        "source": "bundled-file",
    }


def clear_library_cache() -> None:
    """Reset the in-memory cache.  Used in tests to isolate cache state."""
    global _cache, _refresh_lock, _refresh_lock_loop, _refresh_task
    _cache = None
    if _refresh_task is None or _refresh_task.done():
        _refresh_task = None
        _refresh_lock = None
        _refresh_lock_loop = None


def _resolve(entry: SparkLibraryEntry, frame: SparkFrame) -> ResolvedSpark:
    """Project a multi-tag library entry onto the single frame it is served as."""
    return ResolvedSpark(
        id=entry.id,
        frame=frame,
        title=entry.title,
        action=entry.action,
        reward=entry.reward,
        why=_WHY_BY_FRAME[frame],
    )


async def pick_random_sparks(count: int) -> list[ResolvedSpark]:
    """Condition A — up to ``count`` uniformly random Sparks from the whole library.

    Fewer than ``count`` are returned only when the library itself is smaller.
    Each entry is resolved to one of its *own* tags, so the served frame is
    always one the researcher actually assigned to that Spark.
    """
    library = await _get_library()
    chosen = random.sample(library, k=min(count, len(library)))
    return [_resolve(entry, random.choice(entry.tags)) for entry in chosen]


async def pick_one_spark_per_frame() -> list[ResolvedSpark]:
    """Condition B — exactly one random Spark per vibe, in :data:`ALL_FRAMES` order.

    Entries may carry several tags, so a naive per-frame draw can serve the same
    Spark twice. Frames are therefore filled most-constrained-first and prefer an
    entry not already used; a frame whose whole pool is exhausted falls back to
    reuse rather than failing, which keeps the function total.
    """
    library = await _get_library()
    pools = {
        frame: tuple(entry for entry in library if frame in entry.tags)
        for frame in ALL_FRAMES
    }

    used: set[str] = set()
    picked: dict[SparkFrame, SparkLibraryEntry] = {}
    for frame in sorted(ALL_FRAMES, key=lambda f: len(pools[f])):
        pool = pools[frame]  # non-empty: _validate_entries requires >= 2 per frame
        unused = tuple(entry for entry in pool if entry.id not in used)
        entry = random.choice(unused or pool)
        used.add(entry.id)
        picked[frame] = entry

    return [_resolve(picked[frame], frame) for frame in ALL_FRAMES]
