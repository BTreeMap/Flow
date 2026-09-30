"""Render a Google service-account key file as a Spark Sheets env-var value.

Usage:
    uv run python -m scripts.format_spark_sheets_credentials path/to/key.json

The default output is a shell-safe, single-line ``export`` assignment suitable
for sourcing in the current shell.  The output is a secret: do not commit it,
write it to logs, or paste it into shared channels.
"""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Literal

from app.services.spark_sheets_credentials import (
    load_readonly_service_account_credentials,
)

_ENV_VAR_NAME = "SPARK_SHEETS_CREDENTIALS_JSON"
_OutputFormat = Literal["shell", "dotenv", "value"]


def compact_credentials_json(credential_file: Path) -> str:
    """Read, validate, and compact a Google service-account JSON document.

    The compact representation is a single line.  JSON encoding preserves PEM
    line boundaries as literal ``\\n`` escapes, which is the form expected by
    ``SPARK_SHEETS_CREDENTIALS_JSON`` at runtime.
    """
    try:
        raw = credential_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("Unable to read service-account credential file") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Credential file must contain valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Credential file must contain a JSON object")

    # Share the same strict, secret-safe validation used by the production
    # Sheets client; discard the resulting credential because this tool emits
    # the canonical source JSON, not an OAuth token.
    load_readonly_service_account_credentials(json.dumps(payload))

    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def render_env_assignment(
    compact_json: str,
    output_format: _OutputFormat = "shell",
) -> str:
    """Render compact credentials as a safe shell, dotenv, or raw value string."""
    if output_format == "value":
        return compact_json

    assignment = f"{_ENV_VAR_NAME}={shlex.quote(compact_json)}"
    if output_format == "shell":
        return f"export {assignment}"
    if output_format == "dotenv":
        return assignment
    raise ValueError(f"Unsupported output format: {output_format}")


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, then print exactly one secret-bearing line to stdout."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert a Google service-account key file into a single-line "
            "SPARK_SHEETS_CREDENTIALS_JSON value. Output contains a secret."
        )
    )
    parser.add_argument(
        "credential_file",
        type=Path,
        help="Path to the downloaded Google service-account JSON key file",
    )
    parser.add_argument(
        "--format",
        choices=("shell", "dotenv", "value"),
        default="shell",
        help="Output format: shell export (default), dotenv assignment, or raw value",
    )
    args = parser.parse_args(argv)

    try:
        compact_json = compact_credentials_json(args.credential_file)
    except ValueError as exc:
        parser.error(str(exc))

    print(render_env_assignment(compact_json, args.format))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
