"""Tests for the Spark Sheets service-account environment formatter."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from scripts.format_spark_sheets_credentials import (
    compact_credentials_json,
    render_env_assignment,
)


def _credential_payload() -> dict[str, str]:
    """Build a valid, non-production service-account document for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return {
        "type": "service_account",
        "project_id": "formatter-test-project",
        "private_key_id": "0123456789abcdef0123456789abcdef01234567",
        "private_key": pem,
        "client_email": "formatter-test@formatter-test-project.iam.gserviceaccount.com",
        "client_id": "100000000000000000000",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": (
            "https://www.googleapis.com/robot/v1/metadata/x509/"
            "formatter-test%40formatter-test-project.iam.gserviceaccount.com"
        ),
        "universe_domain": "googleapis.com",
    }


def test_compact_credentials_json_validates_and_preserves_payload(
    tmp_path: Path,
) -> None:
    credential_file = tmp_path / "service-account.json"
    payload = _credential_payload()
    credential_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    compact = compact_credentials_json(credential_file)

    assert "\\n" in compact
    assert "\n" not in compact
    assert json.loads(compact) == payload


def test_render_shell_assignment_round_trips_compact_json() -> None:
    compact = '{"private_key":"line1\\nline2","type":"service_account"}'

    rendered = render_env_assignment(compact, "shell")

    parts = shlex.split(rendered)
    assert parts == ["export", f"SPARK_SHEETS_CREDENTIALS_JSON={compact}"]


def test_render_dotenv_and_raw_value_formats() -> None:
    compact = '{"type":"service_account"}'

    assert render_env_assignment(compact, "dotenv") == (
        f"SPARK_SHEETS_CREDENTIALS_JSON={shlex.quote(compact)}"
    )
    assert render_env_assignment(compact, "value") == compact


def test_compact_credentials_json_rejects_invalid_document_without_secret(
    tmp_path: Path,
) -> None:
    secret_marker = "do-not-print-this-private-value"
    credential_file = tmp_path / "invalid-service-account.json"
    credential_file.write_text(
        json.dumps(
            {
                "type": "service_account",
                "client_email": "test@example.invalid",
                "private_key": secret_marker,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        compact_credentials_json(credential_file)

    assert "token_uri" in str(exc_info.value)
    assert secret_marker not in str(exc_info.value)
