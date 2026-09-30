"""Google Sheets source for the Spark A/B prompt library.

Fetches rows from a researcher-maintained spreadsheet and parses them into
:class:`~app.services.spark_library.SparkLibraryEntry` objects.

Expected spreadsheet layout (header row mandatory, column order independent):

    id | title | action | reward | tags

Where:
- ``id``     — unique identifier for the entry (up to 100 chars).
- ``title``  — short display name (up to 120 chars).
- ``action`` — the one-minute movement prompt text (up to 600 chars).
- ``reward`` — benefit / immediate reward text (up to 300 chars).
- ``tags``   — comma-separated :data:`~app.services.spark_library.SparkFrame`
               names, case-insensitive, e.g. ``calm,zoomies``.

Validation model
----------------
Parsing never fails silently.  This module uses compiler-style error
accumulation: every row is fully validated and all findings are collected into
a :class:`SheetParseResult` value that carries both the accepted entries *and*
a typed :class:`RowDiagnostic` list.

* **Structural errors** (empty sheet, missing required columns) — ``ValueError``
  is raised immediately; there is nothing useful to return.
* **Row-level issues** — collected as :class:`RowDiagnostic` entries.  A row
  that receives at least one ``"error"``-severity diagnostic is *skipped*; a
  row with ``"warning"``-only diagnostics is *kept* with the normalised value.

Callers call :meth:`SheetParseResult.log_summary` once to surface all
diagnostics plus a machine-readable summary through the logger.

Security notes
--------------
* Credentials JSON is never logged; only a short service-account e-mail
  prefix appears in debug output.
* The OAuth scope is ``spreadsheets.readonly`` — the service account cannot
  write to any sheet.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from typing import Literal

import requests

from app.services.spark_library import ALL_FRAMES, SparkFrame, SparkLibraryEntry
from app.services.spark_sheets_credentials import (
    load_readonly_service_account_credentials,
    load_readonly_service_account_credentials_from_file,
    make_timeout_bound_google_request,
)

logger = logging.getLogger(__name__)

_SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

# Field length limits mirror the SparkCard Pydantic constraints in routes/spark.py.
_ID_MAX_LEN = 100
_TITLE_MAX_LEN = 120
_ACTION_MAX_LEN = 600
_REWARD_MAX_LEN = 300
_URL_RE = re.compile(r"https?://", re.IGNORECASE)

# Raw cell values are truncated to this length in diagnostic output to keep
# log lines readable and prevent accidental large-payload logging.
_DIAG_RAW_MAX = 80


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RowDiagnostic:
    """A single validation finding for one cell or row.

    Attributes
    ----------
    severity:
        ``"warning"`` — row kept with the normalised value;
        ``"error"``   — row skipped entirely.
    row:
        1-based sheet row number (header row = 1, first data row = 2).
    field:
        Column name the finding applies to, or ``None`` for row-level issues.
    message:
        Human-readable description of the finding.
    raw:
        Raw cell value, truncated to ``_DIAG_RAW_MAX`` chars for log safety.
    normalized:
        The value actually used after normalisation, when applicable.
    """

    severity: Literal["warning", "error"]
    row: int
    field: str | None
    message: str
    raw: str | None = None
    normalized: str | None = None

    def __str__(self) -> str:
        loc = f"row {self.row}" + (f" [{self.field}]" if self.field else "")
        detail = ""
        if self.raw is not None and self.normalized is not None:
            detail = f" (raw={self.raw!r} → {self.normalized!r})"
        elif self.raw is not None:
            detail = f" (raw={self.raw!r})"
        return f"[{self.severity.upper()}] {loc}: {self.message}{detail}"


@dataclass(frozen=True)
class SheetParseResult:
    """The outcome of parsing a Sheets response.

    Attributes
    ----------
    entries:
        Valid, normalised :class:`SparkLibraryEntry` objects ready for use.
    diagnostics:
        All :class:`RowDiagnostic` entries accumulated during parsing, in
        row order.  Empty when the sheet had no issues.
    total_rows:
        Number of data rows examined (excluding the header).
    """

    entries: tuple[SparkLibraryEntry, ...]
    diagnostics: tuple[RowDiagnostic, ...]
    total_rows: int

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "warning")

    @property
    def skipped_count(self) -> int:
        return self.total_rows - len(self.entries)

    def frame_distribution(self) -> dict[str, int]:
        """Return ``{frame: entry_count}`` for every frame in valid entries."""
        counts: Counter[str] = Counter(
            tag for entry in self.entries for tag in entry.tags
        )
        return dict(counts)

    def log_summary(self, log: logging.Logger, range_name: str = "") -> None:
        """Emit every diagnostic at its own severity, then a structured summary.

        The summary line is logged at WARNING when errors were found, INFO
        otherwise — so it is always visible at the operator's configured level.
        """
        for diag in self.diagnostics:
            if diag.severity == "error":
                log.error("%s", diag)
            else:
                log.warning("%s", diag)

        dist = self.frame_distribution()
        dist_str = (
            ", ".join(f"{f}×{dist[f]}" for f in ALL_FRAMES if f in dist) or "none"
        )
        level = logging.WARNING if self.error_count else logging.INFO
        log.log(
            level,
            "Sheets parse%s: %d/%d valid entries | frames: %s"
            " | %d warning(s), %d error(s)",
            f" ({range_name!r})" if range_name else "",
            len(self.entries),
            self.total_rows,
            dist_str,
            self.warning_count,
            self.error_count,
        )


# ---------------------------------------------------------------------------
# Per-field validators — pure functions, accumulate diagnostics, no I/O
# ---------------------------------------------------------------------------


def _validate_id(row: int, raw: str) -> tuple[str | None, list[RowDiagnostic]]:
    """Normalise and validate the ``id`` cell.  Returns (value | None, diags)."""
    value = raw.strip()
    if not value:
        return None, [
            RowDiagnostic(
                severity="error",
                row=row,
                field="id",
                message="empty id — row skipped",
                raw=raw[:_DIAG_RAW_MAX],
            )
        ]
    diags: list[RowDiagnostic] = []
    if len(value) > _ID_MAX_LEN:
        truncated = value[:_ID_MAX_LEN]
        diags.append(
            RowDiagnostic(
                severity="warning",
                row=row,
                field="id",
                message=f"id exceeds {_ID_MAX_LEN} chars ({len(value)}), truncated",
                raw=value[:_DIAG_RAW_MAX],
                normalized=truncated[:_DIAG_RAW_MAX],
            )
        )
        value = truncated
    return value, diags


def _validate_text(
    row: int, field: str, raw: str, max_len: int
) -> tuple[str | None, list[RowDiagnostic]]:
    """Normalise and validate a free-text cell.  Returns (value | None, diags)."""
    value = raw.strip()
    if not value:
        return None, [
            RowDiagnostic(
                severity="error",
                row=row,
                field=field,
                message=f"empty {field} — row skipped",
                raw=raw[:_DIAG_RAW_MAX],
            )
        ]
    diags: list[RowDiagnostic] = []
    if _URL_RE.search(value):
        diags.append(
            RowDiagnostic(
                severity="warning",
                row=row,
                field=field,
                message="contains URL — review content policy",
                raw=value[:_DIAG_RAW_MAX],
            )
        )
    if len(value) > max_len:
        truncated = value[:max_len]
        diags.append(
            RowDiagnostic(
                severity="warning",
                row=row,
                field=field,
                message=f"exceeds max {max_len} chars ({len(value)} given), truncated",
                raw=value[:_DIAG_RAW_MAX],
                normalized=truncated[:_DIAG_RAW_MAX],
            )
        )
        value = truncated
    return value, diags


def _validate_tags(
    row: int, raw: str
) -> tuple[tuple[SparkFrame, ...] | None, list[RowDiagnostic]]:
    """Parse and validate the comma-separated ``tags`` cell."""
    diags: list[RowDiagnostic] = []
    parts = [t.strip() for t in raw.split(",") if t.strip()]
    if not parts:
        return None, [
            RowDiagnostic(
                severity="error",
                row=row,
                field="tags",
                message="empty tags cell — row skipped",
                raw=raw[:_DIAG_RAW_MAX],
            )
        ]

    seen: set[str] = set()
    valid: list[SparkFrame] = []
    for raw_tag in parts:
        normalised = raw_tag.lower()
        if normalised in seen:
            diags.append(
                RowDiagnostic(
                    severity="warning",
                    row=row,
                    field="tags",
                    message="duplicate tag ignored",
                    raw=raw_tag[:_DIAG_RAW_MAX],
                    normalized=normalised,
                )
            )
            continue
        seen.add(normalised)
        if normalised != raw_tag:
            diags.append(
                RowDiagnostic(
                    severity="warning",
                    row=row,
                    field="tags",
                    message="tag normalised to lowercase",
                    raw=raw_tag[:_DIAG_RAW_MAX],
                    normalized=normalised,
                )
            )
        if normalised in ALL_FRAMES:
            valid.append(normalised)  # type: ignore[arg-type]
        else:
            diags.append(
                RowDiagnostic(
                    severity="warning",
                    row=row,
                    field="tags",
                    message=f"unknown tag ignored (valid: {', '.join(ALL_FRAMES)})",
                    raw=raw_tag[:_DIAG_RAW_MAX],
                )
            )

    if not valid:
        diags.append(
            RowDiagnostic(
                severity="error",
                row=row,
                field="tags",
                message="no valid tags after validation — row skipped",
                raw=raw[:_DIAG_RAW_MAX],
            )
        )
        return None, diags

    return tuple(valid), diags


# ---------------------------------------------------------------------------
# Row accumulator
# ---------------------------------------------------------------------------


def _parse_rows(rows: list[list[str]]) -> SheetParseResult:
    """Parse raw sheet rows into a :class:`SheetParseResult`.

    Raises ``ValueError`` on *structural* failures that make row-level
    parsing impossible (empty sheet, missing required columns).  All other
    issues — invalid field values, unknown tags, duplicate ids — are
    accumulated as :class:`RowDiagnostic` entries in the returned result.
    """
    if not rows:
        raise ValueError("Google Sheet is empty (no rows found)")

    header = [col.strip().lower() for col in rows[0]]
    required = {"id", "title", "action", "reward", "tags"}
    missing = required - set(header)
    if missing:
        raise ValueError(
            "Google Sheet is missing required column(s): " + ", ".join(sorted(missing))
        )

    col = {name: header.index(name) for name in required}
    diagnostics: list[RowDiagnostic] = []
    entries: list[SparkLibraryEntry] = []
    seen_ids: set[str] = set()
    data_rows = rows[1:]

    for row_idx, row in enumerate(data_rows, start=2):
        # Pad short rows (trailing empty cells omitted by the Sheets API).
        padded = list(row) + [""] * (len(header) - len(row))
        row_diags: list[RowDiagnostic] = []
        skip = False

        # ── id ──────────────────────────────────────────────────────────────
        entry_id, id_diags = _validate_id(row_idx, padded[col["id"]])
        row_diags.extend(id_diags)
        if entry_id is None:
            skip = True
        elif entry_id in seen_ids:
            row_diags.append(
                RowDiagnostic(
                    severity="warning",
                    row=row_idx,
                    field="id",
                    message=f"duplicate id {entry_id!r} — first occurrence kept, row skipped",
                    raw=entry_id[:_DIAG_RAW_MAX],
                )
            )
            skip = True

        # ── text fields ──────────────────────────────────────────────────────
        title, title_diags = _validate_text(
            row_idx, "title", padded[col["title"]], _TITLE_MAX_LEN
        )
        action, action_diags = _validate_text(
            row_idx, "action", padded[col["action"]], _ACTION_MAX_LEN
        )
        reward, reward_diags = _validate_text(
            row_idx, "reward", padded[col["reward"]], _REWARD_MAX_LEN
        )
        row_diags.extend(title_diags + action_diags + reward_diags)
        if title is None or action is None or reward is None:
            skip = True

        # ── tags ─────────────────────────────────────────────────────────────
        valid_tags, tags_diags = _validate_tags(row_idx, padded[col["tags"]])
        row_diags.extend(tags_diags)
        if valid_tags is None:
            skip = True

        diagnostics.extend(row_diags)

        if not skip:
            # All four fields are non-None when skip is False; assert to narrow.
            assert entry_id is not None
            assert title is not None
            assert action is not None
            assert reward is not None
            assert valid_tags is not None
            seen_ids.add(entry_id)
            entries.append(
                SparkLibraryEntry(
                    id=entry_id,
                    tags=valid_tags,
                    title=title,
                    action=action,
                    reward=reward,
                )
            )

    return SheetParseResult(
        entries=tuple(entries),
        diagnostics=tuple(diagnostics),
        total_rows=len(data_rows),
    )


# ---------------------------------------------------------------------------
# Public fetch entry-point
# ---------------------------------------------------------------------------


def fetch_entries_from_sheets(
    credentials_json: str,
    spreadsheet_id: str,
    range_name: str,
    timeout: float,
    *,
    credentials_file: str = "",
) -> SheetParseResult:
    """Fetch and parse Spark library entries from Google Sheets (synchronous).

    Always calls :meth:`SheetParseResult.log_summary` before returning so
    every validation finding is surfaced through the logger regardless of
    call site.

    Raises
    ------
    ValueError
        Sheet is structurally invalid (empty, missing columns) or yielded
        zero valid entries after row-level validation.
    RuntimeError
        Sheets API returned a non-200 HTTP status.
    google.auth.exceptions.TransportError
        Token refresh failed (bad credentials or network error).
    """
    creds = (
        load_readonly_service_account_credentials(credentials_json)
        if credentials_json
        else load_readonly_service_account_credentials_from_file(credentials_file)
    )
    key_hint = creds.service_account_email[:24] or "<unknown>"
    logger.debug("Refreshing Sheets token for service account %r", key_hint)

    # Apply the configured bound to both OAuth token refresh and the Sheets
    # API GET. Credentials.refresh() otherwise uses google-auth's 120 s
    # default independently of SPARK_SHEETS_REQUEST_TIMEOUT_SECS.
    session = requests.Session()
    creds.refresh(make_timeout_bound_google_request(session, timeout))

    url = (
        f"{_SHEETS_API_BASE}"
        f"/{urllib.parse.quote(spreadsheet_id, safe='')}"
        f"/values/{urllib.parse.quote(range_name)}"
    )
    response = session.get(
        url,
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Sheets API returned HTTP {response.status_code} for "
            f"spreadsheet {spreadsheet_id!r}: {response.text[:200]}"
        )

    raw_rows: list[list[str]] = response.json().get("values", [])
    result = _parse_rows(raw_rows)  # raises on structural errors
    result.log_summary(logger, range_name)

    if not result.entries:
        raise ValueError(
            f"No valid entries found in Google Sheet "
            f"({result.error_count} error(s), {result.warning_count} warning(s))"
        )
    return result
