"""Production-shape tests for Spark Google service-account credentials.

Tests use a locally generated RSA key and fake identifiers.  No Google project,
service account, spreadsheet, or private key is contacted or embedded here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests
from app.services.spark_sheets_credentials import (
    load_readonly_service_account_credentials,
    load_readonly_service_account_credentials_from_file,
)
from app.services.spark_sheets_source import fetch_entries_from_sheets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SPREADSHEET_ID = "1productionShapeTestSpreadsheet"
_RANGE = "Sparks!A:E"
_TIMEOUT = 7.5


def _production_shape_credentials_json() -> str:
    """Build a complete standard Google service-account document safely."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "spark-production-shape-test",
            "private_key_id": "0123456789abcdef0123456789abcdef01234567",
            # json.dumps deliberately serializes PEM newlines as \n, exactly
            # as a JSON value injected through an environment variable does.
            "private_key": pem,
            "client_email": (
                "spark-test@spark-production-shape-test.iam.gserviceaccount.com"
            ),
            "client_id": "100000000000000000000",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": _TOKEN_URI,
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": (
                "https://www.googleapis.com/robot/v1/metadata/x509/"
                "spark-test%40spark-production-shape-test.iam.gserviceaccount.com"
            ),
            "universe_domain": "googleapis.com",
        }
    )


def _json_response(
    status_code: int, payload: dict[str, Any], url: str
) -> requests.Response:
    """Construct the minimal concrete requests response google-auth expects."""
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps(payload).encode("utf-8")
    return response


def test_load_credentials_accepts_full_google_service_account_shape() -> None:
    credentials = load_readonly_service_account_credentials(
        _production_shape_credentials_json()
    )

    assert credentials.service_account_email == (
        "spark-test@spark-production-shape-test.iam.gserviceaccount.com"
    )
    assert credentials.project_id == "spark-production-shape-test"
    assert credentials.scopes == [
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ]
    assert credentials.universe_domain == "googleapis.com"


def test_load_credentials_from_file_accepts_full_google_service_account_shape(
    tmp_path: Path,
) -> None:
    credentials_file = tmp_path / "service-account.json"
    credentials_file.write_text(_production_shape_credentials_json(), encoding="utf-8")

    credentials = load_readonly_service_account_credentials_from_file(
        str(credentials_file)
    )

    assert credentials.service_account_email == (
        "spark-test@spark-production-shape-test.iam.gserviceaccount.com"
    )
    assert credentials.scopes == [
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ]


def test_load_credentials_from_file_hides_path_in_read_errors(tmp_path: Path) -> None:
    missing_file = tmp_path / "credential-path-must-not-appear.json"

    with pytest.raises(ValueError) as exc_info:
        load_readonly_service_account_credentials_from_file(str(missing_file))

    assert str(missing_file) not in str(exc_info.value)
    assert "SPARK_SHEETS_CREDENTIALS_FILE" in str(exc_info.value)


def test_load_credentials_rejects_non_service_account_type() -> None:
    payload = json.loads(_production_shape_credentials_json())
    payload["type"] = "authorized_user"

    with pytest.raises(ValueError, match="type 'service_account'"):
        load_readonly_service_account_credentials(json.dumps(payload))


def test_load_credentials_never_includes_source_json_in_errors() -> None:
    secret_marker = "do-not-log-this-private-material"
    malformed = json.dumps(
        {
            "type": "service_account",
            "client_email": "test@example.invalid",
            "private_key": secret_marker,
            # token_uri intentionally omitted
        }
    )

    with pytest.raises(ValueError) as exc_info:
        load_readonly_service_account_credentials(malformed)

    assert secret_marker not in str(exc_info.value)
    assert "token_uri" in str(exc_info.value)


@pytest.mark.parametrize(
    "use_credentials_file",
    (False, True),
    ids=("inline-json", "mounted-file"),
)
def test_fetch_uses_full_credentials_for_token_and_sheets_requests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    use_credentials_file: bool,
) -> None:
    """Exercise real JWT signing with a generated PEM, not a mocked credential."""
    requests_seen: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(
        _session: requests.Session,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        requests_seen.append((method, url, kwargs))
        if url == _TOKEN_URI:
            # google-auth has signed the JWT with the generated private key.
            body = kwargs["data"]
            assert b"assertion=" in body
            assert kwargs["timeout"] == _TIMEOUT
            return _json_response(
                200,
                {
                    "access_token": "test-access-token",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
                url,
            )

        expected_sheets_url = (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{_SPREADSHEET_ID}/values/Sparks%21A%3AE"
        )
        assert url == expected_sheets_url
        assert method == "GET"
        assert kwargs["headers"]["Authorization"] == "Bearer test-access-token"
        assert kwargs["timeout"] == _TIMEOUT
        return _json_response(
            200,
            {
                "values": [
                    ["id", "title", "action", "reward", "tags"],
                    ["spark-1", "Stand up", "Walk for one minute", "Reset", "calm"],
                ]
            },
            url,
        )

    monkeypatch.setattr(requests.Session, "request", fake_request)

    credentials_json = _production_shape_credentials_json()
    credentials_file = tmp_path / "service-account.json"
    if use_credentials_file:
        credentials_file.write_text(credentials_json, encoding="utf-8")

    result = fetch_entries_from_sheets(
        credentials_json="" if use_credentials_file else credentials_json,
        spreadsheet_id=_SPREADSHEET_ID,
        range_name=_RANGE,
        timeout=_TIMEOUT,
        credentials_file=str(credentials_file) if use_credentials_file else "",
    )

    assert len(result.entries) == 1
    assert result.entries[0].id == "spark-1"
    assert result.entries[0].tags == ("calm",)
    assert [(method, url) for method, url, _ in requests_seen] == [
        ("POST", _TOKEN_URI),
        (
            "GET",
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{_SPREADSHEET_ID}/values/Sparks%21A%3AE",
        ),
    ]
