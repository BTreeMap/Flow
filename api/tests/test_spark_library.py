"""Unit tests for the Spark A/B library: file loading, Sheets parsing, cache."""

from __future__ import annotations

import asyncio
import csv
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from unittest.mock import MagicMock, patch

import pytest
from app.config_loader import resolve_config_path
from app.services.spark_library import (
    ALL_FRAMES,
    SparkLibraryEntry,
    _compute_hash,
    _load_from_file,
    clear_library_cache,
    library_version,
    pick_one_spark_per_frame,
    pick_random_sparks,
)
from app.services.spark_sheets_source import (
    RowDiagnostic,
    SheetParseResult,
    _parse_rows,
    _validate_id,
    _validate_tags,
    _validate_text,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_entries(count_per_frame: int = 2) -> tuple[SparkLibraryEntry, ...]:
    """Minimal valid library: ``count_per_frame`` entries per frame."""
    return tuple(
        SparkLibraryEntry(
            id=f"fake-{frame}-{i}",
            tags=(frame,),
            title=f"Fake {frame} {i}",
            action="act",
            reward="rew",
        )
        for frame in ALL_FRAMES
        for i in range(count_per_frame)
    )


def _make_fake_result(
    entries: tuple[SparkLibraryEntry, ...] | None = None,
) -> SheetParseResult:
    """Wrap a tuple of entries (or freshly generated ones) in a SheetParseResult."""
    e = entries if entries is not None else _make_fake_entries()
    return SheetParseResult(entries=e, diagnostics=(), total_rows=len(e))


@contextmanager
def _capture_library_logs(level: int) -> Iterator[list[str]]:
    """Collect Spark-library logs despite root logger reconfiguration in tests."""
    messages: list[str] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    target = logging.getLogger("app.services.spark_library")
    handler = _Collector(level)
    prior_level = target.level
    prior_disabled = target.disabled
    prior_disable = logging.root.manager.disable
    target.addHandler(handler)
    target.setLevel(level)
    target.disabled = False
    logging.disable(logging.NOTSET)
    try:
        yield messages
    finally:
        target.removeHandler(handler)
        target.setLevel(prior_level)
        target.disabled = prior_disabled
        logging.disable(prior_disable)


# ---------------------------------------------------------------------------
# Autouse fixture: reset cache between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_library_cache() -> None:  # type: ignore[return]
    clear_library_cache()
    yield  # type: ignore[misc]
    clear_library_cache()


# ---------------------------------------------------------------------------
# File-based loading
# ---------------------------------------------------------------------------


def test_load_from_file_satisfies_tag_count_invariant() -> None:
    entries = _load_from_file()
    assert len(entries) >= 1
    for frame in ALL_FRAMES:
        count = sum(1 for entry in entries if frame in entry.tags)
        assert count >= 2, f"tag '{frame}' has fewer than 2 entries"


def test_load_from_file_entries_have_no_video_links() -> None:
    entries = _load_from_file()
    for entry in entries:
        blob = f"{entry.title} {entry.action} {entry.reward}".lower()
        assert "http://" not in blob
        assert "https://" not in blob
        assert "loom.com" not in blob
        assert "youtube" not in blob
        assert "youtu.be" not in blob


def test_sheets_import_csv_matches_bundled_library() -> None:
    """Keep the researcher-facing Sheets import CSV aligned with source data."""
    with resolve_config_path("spark_library_sheets.csv").open(
        encoding="utf-8",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)
        assert reader.fieldnames == ["id", "title", "action", "reward", "tags"]
        rows = list(reader)

    assert rows == [
        {
            "id": entry.id,
            "title": entry.title,
            "action": entry.action,
            "reward": entry.reward,
            "tags": ",".join(entry.tags),
        }
        for entry in _load_from_file()
    ]


# ---------------------------------------------------------------------------
# library_version()
# ---------------------------------------------------------------------------


def test_library_version_is_stable_dict_shape() -> None:
    version = library_version()
    assert version["prompt_file"] == "spark_library"
    assert isinstance(version["prompt_sha256"], str)
    assert len(version["prompt_sha256"]) == 64
    assert version["source"] == "bundled-file"


@pytest.mark.asyncio
async def test_library_version_reflects_cache_after_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    await pick_random_sparks(1)
    version = library_version()
    assert version["prompt_file"] == "spark_library"
    assert len(version["prompt_sha256"]) == 64
    assert version["source"] == "bundled-file"

    clear_config_cache()


# ---------------------------------------------------------------------------
# _compute_hash()
# ---------------------------------------------------------------------------


def test_compute_hash_is_deterministic() -> None:
    entries = _load_from_file()
    assert _compute_hash(entries) == _compute_hash(entries)
    assert len(_compute_hash(entries)) == 64


def test_compute_hash_changes_on_content_change() -> None:
    entries = _load_from_file()
    old = entries[0]
    modified = (
        SparkLibraryEntry(
            id=old.id,
            tags=old.tags,
            title="CHANGED: " + old.title,
            action=old.action,
            reward=old.reward,
        ),
        *entries[1:],
    )
    assert _compute_hash(entries) != _compute_hash(modified)


def test_compute_hash_is_order_independent() -> None:
    entries = _load_from_file()
    assert _compute_hash(entries) == _compute_hash(tuple(reversed(entries)))


# ---------------------------------------------------------------------------
# RowDiagnostic formatting
# ---------------------------------------------------------------------------


def test_row_diagnostic_str_with_raw_and_normalized() -> None:
    d = RowDiagnostic(
        severity="warning",
        row=3,
        field="tags",
        message="tag normalised to lowercase",
        raw="Calm",
        normalized="calm",
    )
    s = str(d)
    assert "[WARNING]" in s
    assert "row 3 [tags]" in s
    assert "Calm" in s
    assert "calm" in s


def test_row_diagnostic_str_error_no_normalized() -> None:
    d = RowDiagnostic(
        severity="error", row=7, field="id", message="empty id — row skipped"
    )
    s = str(d)
    assert "[ERROR]" in s
    assert "row 7 [id]" in s


def test_row_diagnostic_str_no_field() -> None:
    d = RowDiagnostic(severity="warning", row=2, field=None, message="row-level issue")
    assert "row 2:" in str(d)
    assert "[" not in str(d).split("row 2")[1].split(":")[0]


# ---------------------------------------------------------------------------
# SheetParseResult properties
# ---------------------------------------------------------------------------


def test_sheet_parse_result_counts() -> None:
    diags = (
        RowDiagnostic(severity="warning", row=2, field="tags", message="w1"),
        RowDiagnostic(severity="error", row=3, field="id", message="e1"),
        RowDiagnostic(severity="warning", row=4, field="action", message="w2"),
    )
    result = SheetParseResult(entries=(), diagnostics=diags, total_rows=3)
    assert result.error_count == 1
    assert result.warning_count == 2
    assert result.skipped_count == 3  # 3 total_rows - 0 entries


def test_sheet_parse_result_frame_distribution() -> None:
    entries = (
        SparkLibraryEntry(
            id="a", tags=("calm", "zoomies"), title="T", action="A", reward="R"
        ),
        SparkLibraryEntry(id="b", tags=("calm",), title="T2", action="A2", reward="R2"),
    )
    result = SheetParseResult(entries=entries, diagnostics=(), total_rows=2)
    dist = result.frame_distribution()
    assert dist["calm"] == 2
    assert dist["zoomies"] == 1
    assert "silly" not in dist


def test_sheet_parse_result_log_summary_emits_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    diags = (
        RowDiagnostic(severity="warning", row=2, field="tags", message="unknown tag"),
        RowDiagnostic(severity="error", row=3, field="id", message="empty id"),
    )
    entries = (
        SparkLibraryEntry(id="x", tags=("calm",), title="T", action="A", reward="R"),
    )
    result = SheetParseResult(entries=entries, diagnostics=diags, total_rows=2)
    log = logging.getLogger("test_log_summary")
    with caplog.at_level(logging.WARNING, logger="test_log_summary"):
        result.log_summary(log, "Sheet1!A:E")

    messages = caplog.text
    assert "unknown tag" in messages
    assert "empty id" in messages
    assert "Sheet1!A:E" in messages


def test_sheet_parse_result_log_summary_info_when_clean(
    caplog: pytest.LogCaptureFixture,
) -> None:
    entries = (
        SparkLibraryEntry(id="x", tags=("calm",), title="T", action="A", reward="R"),
    )
    result = SheetParseResult(entries=entries, diagnostics=(), total_rows=1)
    log = logging.getLogger("test_log_summary_clean")
    with caplog.at_level(logging.INFO, logger="test_log_summary_clean"):
        result.log_summary(log, "MyRange")

    assert "0 warning(s), 0 error(s)" in caplog.text


# ---------------------------------------------------------------------------
# Per-field validators
# ---------------------------------------------------------------------------


def test_validate_id_empty_returns_error() -> None:
    value, diags = _validate_id(row=2, raw="   ")
    assert value is None
    assert len(diags) == 1
    assert diags[0].severity == "error"
    assert diags[0].field == "id"


def test_validate_id_valid_passes() -> None:
    value, diags = _validate_id(row=2, raw="  my-id  ")
    assert value == "my-id"
    assert diags == []


def test_validate_id_too_long_truncates_with_warning() -> None:
    long_id = "x" * 200
    value, diags = _validate_id(row=2, raw=long_id)
    assert value is not None
    assert len(value) == 100
    assert len(diags) == 1
    assert diags[0].severity == "warning"
    assert "truncated" in diags[0].message


def test_validate_text_empty_returns_error() -> None:
    value, diags = _validate_text(row=3, field="title", raw="", max_len=120)
    assert value is None
    assert diags[0].severity == "error"


def test_validate_text_url_produces_warning() -> None:
    value, diags = _validate_text(
        row=3, field="action", raw="See https://example.com for details", max_len=600
    )
    assert value is not None  # row is kept despite warning
    assert any(d.severity == "warning" and "URL" in d.message for d in diags)


def test_validate_text_too_long_truncates_with_warning() -> None:
    long_text = "A" * 700
    value, diags = _validate_text(row=4, field="action", raw=long_text, max_len=600)
    assert value is not None
    assert len(value) == 600
    assert any("truncated" in d.message for d in diags)


def test_validate_tags_empty_cell_returns_error() -> None:
    value, diags = _validate_tags(row=2, raw="   ,   ")
    assert value is None
    assert diags[0].severity == "error"


def test_validate_tags_all_unknown_returns_error() -> None:
    value, diags = _validate_tags(row=2, raw="bogus,nope")
    assert value is None
    # Warnings for each unknown tag, then an error for no valid tags
    assert any(d.severity == "error" for d in diags)


def test_validate_tags_case_normalisation_produces_warning() -> None:
    value, diags = _validate_tags(row=2, raw="Calm,ZOOMIES")
    assert value == ("calm", "zoomies")
    assert all(d.severity == "warning" and "normalised" in d.message for d in diags)


def test_validate_tags_duplicate_produces_warning() -> None:
    value, diags = _validate_tags(row=2, raw="calm,calm,zoomies")
    assert value is not None
    assert "calm" in value
    assert "zoomies" in value
    assert len(value) == 2  # deduplicated
    assert any("duplicate" in d.message for d in diags)


def test_validate_tags_mixed_known_unknown_keeps_valid() -> None:
    value, diags = _validate_tags(row=2, raw="calm,unknown_vibe")
    assert value == ("calm",)
    assert any("unknown tag" in d.message for d in diags)


# ---------------------------------------------------------------------------
# _parse_rows — SheetParseResult-based assertions
# ---------------------------------------------------------------------------


def test_parse_rows_valid_entries_and_no_diagnostics() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "Title A", "Do X", "Feel Y", "calm,zoomies"],
        ["r2", "Title B", "Do Z", "Feel W", "silly"],
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 2
    assert result.diagnostics == ()
    assert result.total_rows == 2
    assert result.entries[0].id == "r1"
    assert result.entries[0].tags == ("calm", "zoomies")
    assert result.entries[1].id == "r2"


def test_parse_rows_column_order_independent() -> None:
    rows: list[list[str]] = [
        ["tags", "reward", "action", "title", "id"],
        ["calm", "Feel good", "Do calm thing", "Calm Title", "c1"],
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 1
    assert result.entries[0].id == "c1"
    assert result.entries[0].tags == ("calm",)
    assert result.entries[0].title == "Calm Title"


def test_parse_rows_missing_required_column_raises() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward"],  # no "tags"
        ["r1", "Title", "Act", "Reward"],
    ]
    with pytest.raises(ValueError, match="missing required column"):
        _parse_rows(rows)


def test_parse_rows_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        _parse_rows([])


def test_parse_rows_only_header_returns_empty_result() -> None:
    """Only a header row → no data rows, empty entries, no diagnostics."""
    rows: list[list[str]] = [["id", "title", "action", "reward", "tags"]]
    result = _parse_rows(rows)
    assert result.entries == ()
    assert result.total_rows == 0
    assert result.diagnostics == ()


def test_parse_rows_unknown_tags_warns_and_keeps_valid() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T", "A", "R", "calm,unknown_vibe"],
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 1
    assert result.entries[0].tags == ("calm",)
    assert result.warning_count >= 1


def test_parse_rows_all_unknown_tags_drops_row_with_error() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T1", "A1", "R1", "bogus,nope"],
        ["r2", "T2", "A2", "R2", "science"],
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 1
    assert result.entries[0].id == "r2"
    assert result.error_count >= 1


def test_parse_rows_short_row_padded_skips_row() -> None:
    """Row shorter than header is padded with empty strings; no valid tags → skipped."""
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T", "A", "R"],  # missing tags cell → padded to ""
    ]
    result = _parse_rows(rows)
    assert result.entries == ()
    assert result.error_count >= 1


def test_parse_rows_empty_id_skipped_with_error() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["", "T", "A", "R", "calm"],
        ["r2", "T2", "A2", "R2", "science"],
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 1
    assert result.entries[0].id == "r2"
    assert result.error_count == 1


def test_parse_rows_empty_title_skips_row() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "", "Do something", "Feel good", "calm"],
    ]
    result = _parse_rows(rows)
    assert result.entries == ()
    assert result.error_count >= 1


def test_parse_rows_empty_action_skips_row() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "Title", "", "Feel good", "calm"],
    ]
    result = _parse_rows(rows)
    assert result.entries == ()


def test_parse_rows_empty_reward_skips_row() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "Title", "Do something", "", "calm"],
    ]
    result = _parse_rows(rows)
    assert result.entries == ()


def test_parse_rows_tag_case_normalisation_warns() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T", "A", "R", "Calm,ZOOMIES"],
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 1
    assert result.entries[0].tags == ("calm", "zoomies")
    assert result.warning_count >= 2  # one per capitalised tag


def test_parse_rows_duplicate_tags_deduped_with_warning() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T", "A", "R", "calm,calm,zoomies"],
    ]
    result = _parse_rows(rows)
    assert result.entries[0].tags == ("calm", "zoomies")
    assert any("duplicate" in d.message for d in result.diagnostics)


def test_parse_rows_url_in_action_warns_but_keeps_entry() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T", "See https://example.com to do it", "R", "calm"],
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 1
    assert any("URL" in d.message for d in result.diagnostics)
    assert result.error_count == 0


def test_parse_rows_text_too_long_truncates_with_warning() -> None:
    long_action = "A" * 700  # exceeds _ACTION_MAX_LEN = 600
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T", long_action, "R", "calm"],
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 1
    assert len(result.entries[0].action) == 600
    assert any("truncated" in d.message for d in result.diagnostics)


def test_parse_rows_duplicate_ids_first_wins() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["dup", "First", "Do X", "Feel Y", "calm"],
        ["dup", "Second", "Do Z", "Feel W", "zoomies"],  # duplicate id
    ]
    result = _parse_rows(rows)
    assert len(result.entries) == 1
    assert result.entries[0].title == "First"
    assert any("duplicate id" in d.message for d in result.diagnostics)


def test_parse_rows_total_rows_matches_data_rows() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T1", "A1", "R1", "calm"],
        ["r2", "T2", "A2", "R2", "silly"],
        ["r3", "T3", "A3", "R3", "zoomies"],
    ]
    result = _parse_rows(rows)
    assert result.total_rows == 3


# ---------------------------------------------------------------------------
# Spark selection (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pick_random_sparks_resolves_each_entry_to_its_own_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    resolved = await pick_random_sparks(1)
    assert len(resolved) == 1
    assert resolved[0].frame in ALL_FRAMES

    clear_config_cache()


@pytest.mark.asyncio
async def test_pick_random_sparks_caps_count_to_library_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asking for more Sparks than exist yields the whole library, not an error."""
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    everything = await pick_random_sparks(10_000)
    assert len(everything) == len(_load_from_file())
    assert len({entry.id for entry in everything}) == len(everything)

    clear_config_cache()


@pytest.mark.asyncio
async def test_pick_one_spark_per_frame_covers_every_frame_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Condition B's sampler is total and structurally one card per vibe."""
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    resolved = await pick_one_spark_per_frame()
    assert tuple(entry.frame for entry in resolved) == ALL_FRAMES
    # Each card carries its own vibe's rationale, not a neighbour's.
    assert all(entry.why for entry in resolved)

    clear_config_cache()


@pytest.mark.asyncio
async def test_pick_one_spark_per_frame_avoids_repeating_a_multi_tag_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Spark tagged with several vibes must not fill two columns at once.

    Repeated because the draw is random: a single pass could pass by luck.
    """
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    for _ in range(25):
        resolved = await pick_one_spark_per_frame()
        assert len({entry.id for entry in resolved}) == len(ALL_FRAMES)

    clear_config_cache()


@pytest.mark.asyncio
async def test_pick_one_spark_per_frame_reuses_when_a_pool_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Total, not partial: an over-shared library still yields all five vibes."""
    from app.config import clear_config_cache

    clear_config_cache()

    # Two entries, each tagged with every frame: distinctness is impossible, so
    # the selector must fall back to reuse rather than fail or return fewer.
    shared = tuple(
        SparkLibraryEntry(
            id=f"shared-{i}",
            tags=ALL_FRAMES,
            title=f"Shared {i}",
            action="act",
            reward="rew",
        )
        for i in range(2)
    )

    async def _fake_library() -> tuple[SparkLibraryEntry, ...]:
        return shared

    monkeypatch.setattr("app.services.spark_library._get_library", _fake_library)

    resolved = await pick_one_spark_per_frame()
    assert tuple(entry.frame for entry in resolved) == ALL_FRAMES

    clear_config_cache()


# ---------------------------------------------------------------------------
# Cache and fallback behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_library_uses_file_when_sheets_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache
    from app.services import spark_library

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    await pick_random_sparks(1)

    assert spark_library._cache is not None
    assert spark_library._cache.source == "file"

    clear_config_cache()


@pytest.mark.asyncio
async def test_get_library_uses_sheets_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache
    from app.services import spark_library

    fake_result = _make_fake_result()
    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_JSON", '{"type": "service_account"}')
    clear_config_cache()

    with (
        _capture_library_logs(logging.INFO) as messages,
        patch(
            "app.services.spark_sheets_source.fetch_entries_from_sheets",
            MagicMock(return_value=fake_result),
        ),
    ):
        await pick_random_sparks(1)

    assert spark_library._cache is not None
    assert spark_library._cache.source == "sheets"
    assert spark_library._cache.entries == fake_result.entries
    assert any("loaded from remote Google Sheets" in message for message in messages)
    assert library_version()["source"] == "google-sheets"

    clear_config_cache()


@pytest.mark.asyncio
async def test_sheets_startup_warmup_is_nonblocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup schedules remote work without delaying application readiness."""
    from app.services import spark_library

    refresh_started = asyncio.Event()
    allow_refresh_to_finish = asyncio.Event()

    async def delayed_refresh() -> None:
        refresh_started.set()
        await allow_refresh_to_finish.wait()

    monkeypatch.setattr(spark_library, "_sheets_is_configured", lambda: True)
    monkeypatch.setattr(spark_library, "_do_refresh", delayed_refresh)

    with _capture_library_logs(logging.INFO) as messages:
        tasks = await asyncio.gather(
            *(spark_library.schedule_sheets_startup_warmup() for _ in range(8))
        )
        task = tasks[0]
        assert task is not None
        assert all(scheduled_task is task for scheduled_task in tasks)
        assert not task.done()
        await refresh_started.wait()
        assert not task.done()
        assert any("API startup will not wait" in message for message in messages)

        allow_refresh_to_finish.set()
        await task


@pytest.mark.asyncio
async def test_first_request_awaits_sheets_startup_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not duplicate the remote fetch when an A/B request races startup."""
    from app.services import spark_library

    entries = _make_fake_entries()
    refresh_started = asyncio.Event()
    allow_refresh_to_finish = asyncio.Event()
    refresh_count = 0

    async def delayed_refresh() -> None:
        nonlocal refresh_count
        refresh_count += 1
        refresh_started.set()
        await allow_refresh_to_finish.wait()
        spark_library._cache = spark_library._CacheState(
            entries=entries,
            version_hash=spark_library._compute_hash(entries),
            source="sheets",
        )

    monkeypatch.setattr(spark_library, "_sheets_is_configured", lambda: True)
    monkeypatch.setattr(spark_library, "_do_refresh", delayed_refresh)
    warmup_task = await spark_library.schedule_sheets_startup_warmup()
    assert warmup_task is not None
    await refresh_started.wait()

    request_task = asyncio.create_task(pick_random_sparks(1))
    await asyncio.sleep(0)
    assert not request_task.done()
    assert refresh_count == 1

    allow_refresh_to_finish.set()
    resolved = await request_task

    assert len(resolved) == 1
    assert refresh_count == 1


@pytest.mark.asyncio
async def test_concurrent_cold_requests_share_one_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent cold A/B requests must await one shared refresh task."""
    from app.services import spark_library

    entries = _make_fake_entries()
    refresh_started = asyncio.Event()
    allow_refresh_to_finish = asyncio.Event()
    refresh_count = 0

    async def delayed_refresh() -> None:
        nonlocal refresh_count
        refresh_count += 1
        refresh_started.set()
        await allow_refresh_to_finish.wait()
        spark_library._cache = spark_library._CacheState(
            entries=entries,
            version_hash=spark_library._compute_hash(entries),
            source="sheets",
        )

    monkeypatch.setattr(spark_library, "_do_refresh", delayed_refresh)
    requests = [asyncio.create_task(pick_random_sparks(1)) for _ in range(8)]
    await refresh_started.wait()

    assert refresh_count == 1
    assert all(not request.done() for request in requests)

    allow_refresh_to_finish.set()
    resolved = await asyncio.gather(*requests)

    assert refresh_count == 1
    assert all(len(result) == 1 for result in resolved)


@pytest.mark.asyncio
async def test_cancelled_cold_request_does_not_cancel_shared_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disconnected caller cannot cancel the shared cold-cache refresh."""
    from app.services import spark_library

    entries = _make_fake_entries()
    refresh_started = asyncio.Event()
    allow_refresh_to_finish = asyncio.Event()

    async def delayed_refresh() -> None:
        refresh_started.set()
        await allow_refresh_to_finish.wait()
        spark_library._cache = spark_library._CacheState(
            entries=entries,
            version_hash=spark_library._compute_hash(entries),
            source="sheets",
        )

    monkeypatch.setattr(spark_library, "_do_refresh", delayed_refresh)
    disconnected_request = asyncio.create_task(pick_random_sparks(1))
    surviving_request = asyncio.create_task(pick_random_sparks(1))
    await refresh_started.wait()

    disconnected_request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await disconnected_request

    assert spark_library._refresh_task is not None
    assert not spark_library._refresh_task.cancelled()
    assert not surviving_request.done()

    allow_refresh_to_finish.set()
    resolved = await surviving_request

    assert len(resolved) == 1


@pytest.mark.asyncio
async def test_concurrent_stale_requests_share_one_background_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale requests return immediately while exactly one refresh is active."""
    from app.config import clear_config_cache
    from app.services import spark_library

    stale_entries = _make_fake_entries()
    refreshed_entries = tuple(reversed(stale_entries))
    refresh_started = asyncio.Event()
    allow_refresh_to_finish = asyncio.Event()
    refresh_count = 0

    async def delayed_refresh() -> None:
        nonlocal refresh_count
        refresh_count += 1
        refresh_started.set()
        await allow_refresh_to_finish.wait()
        spark_library._cache = spark_library._CacheState(
            entries=refreshed_entries,
            version_hash=spark_library._compute_hash(refreshed_entries),
            source="sheets",
        )

    monkeypatch.setenv("SPARK_SHEETS_CACHE_TTL_SECS", "1")
    clear_config_cache()
    spark_library._cache = spark_library._CacheState(
        entries=stale_entries,
        version_hash=spark_library._compute_hash(stale_entries),
        source="file",
        fetched_at=monotonic() - 2,
    )
    monkeypatch.setattr(spark_library, "_do_refresh", delayed_refresh)

    resolved = await asyncio.gather(*(pick_random_sparks(1) for _ in range(8)))
    await refresh_started.wait()

    assert refresh_count == 1
    assert all(len(result) == 1 for result in resolved)

    allow_refresh_to_finish.set()
    assert spark_library._refresh_task is not None
    await spark_library._refresh_task
    assert spark_library._cache is not None
    assert spark_library._cache.entries == refreshed_entries

    clear_config_cache()


@pytest.mark.asyncio
async def test_cancel_library_refresh_cancels_active_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Application shutdown cancels an in-flight startup or stale refresh."""
    from app.services import spark_library

    refresh_started = asyncio.Event()

    async def delayed_refresh() -> None:
        refresh_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(spark_library, "_sheets_is_configured", lambda: True)
    monkeypatch.setattr(spark_library, "_do_refresh", delayed_refresh)

    task = await spark_library.schedule_sheets_startup_warmup()
    assert task is not None
    await refresh_started.wait()

    await spark_library.cancel_library_refresh()

    assert task.cancelled()


@pytest.mark.asyncio
async def test_get_library_uses_sheets_credential_file_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.config import clear_config_cache
    from app.services import spark_library

    credential_file = tmp_path / "service-account.json"
    credential_file.write_text("{}", encoding="utf-8")
    fake_result = _make_fake_result()
    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_FILE", str(credential_file))
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(return_value=fake_result),
    ) as fetch_entries:
        await pick_random_sparks(1)

    fetch_entries.assert_called_once_with(
        "",
        "test-sheet-id",
        "Sparks!A:E",
        10.0,
        credentials_file=str(credential_file),
    )
    assert spark_library._cache is not None
    assert spark_library._cache.source == "sheets"

    clear_config_cache()


@pytest.mark.asyncio
async def test_do_refresh_falls_back_to_file_on_sheets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cold-start Sheets failure should transparently load the bundled JSON."""
    from app.config import clear_config_cache
    from app.services import spark_library

    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_JSON", '{"type": "service_account"}')
    clear_config_cache()

    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(side_effect=RuntimeError("connection refused")),
    ):
        resolved = await pick_random_sparks(1)

    assert len(resolved) == 1
    assert spark_library._cache is not None
    assert spark_library._cache.source == "file"
    assert library_version()["source"] == "bundled-file"

    clear_config_cache()


@pytest.mark.asyncio
async def test_do_refresh_preserves_snapshot_on_subsequent_sheets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a successful Sheets load, a later failure must keep the snapshot."""
    from app.config import clear_config_cache
    from app.services import spark_library
    from app.services.spark_library import _do_refresh

    fake_result = _make_fake_result()
    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_JSON", '{"type": "service_account"}')
    clear_config_cache()

    # First load succeeds from Sheets.
    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(return_value=fake_result),
    ):
        await _do_refresh()

    first_cache = spark_library._cache
    assert first_cache is not None
    assert first_cache.source == "sheets"

    # Second refresh fails; snapshot must be preserved.
    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(side_effect=RuntimeError("Sheets down")),
    ):
        await _do_refresh()

    assert spark_library._cache is first_cache

    clear_config_cache()


@pytest.mark.asyncio
async def test_stale_cache_served_immediately_and_refresh_triggered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale cache is returned without blocking; refresh is scheduled once."""
    import asyncio as _asyncio

    from app.config import clear_config_cache
    from app.services import spark_library
    from app.services.spark_library import _CacheState

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    await pick_random_sparks(1)
    assert spark_library._cache is not None

    stale_cache = _CacheState(
        entries=spark_library._cache.entries,
        version_hash=spark_library._cache.version_hash,
        source=spark_library._cache.source,
        fetched_at=spark_library._cache.fetched_at - 9999.0,
    )
    spark_library._cache = stale_cache

    resolved = await pick_random_sparks(1)
    assert len(resolved) == 1
    assert spark_library._refresh_task is not None

    await _asyncio.sleep(0.05)

    clear_config_cache()


@pytest.mark.asyncio
async def test_sheets_invariant_violation_falls_back_to_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sheets data that violates the ≥2 entries/frame rule falls back to bundled JSON."""
    from app.config import clear_config_cache
    from app.services import spark_library

    # Only one entry total — fails the ≥2 per frame invariant.
    bad_result = SheetParseResult(
        entries=(
            SparkLibraryEntry(
                id="only-one", tags=("calm",), title="T", action="A", reward="R"
            ),
        ),
        diagnostics=(),
        total_rows=1,
    )
    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_JSON", '{"type": "service_account"}')
    clear_config_cache()

    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(return_value=bad_result),
    ):
        await pick_random_sparks(1)

    assert spark_library._cache is not None
    assert spark_library._cache.source == "file"

    clear_config_cache()


# ---------------------------------------------------------------------------
