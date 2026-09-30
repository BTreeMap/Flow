"""Configuration management for the application.

Consolidates access to environment variables in a single place with caching.
"""

from __future__ import annotations

import os
import socket
from functools import cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@cache
def get_data_dir() -> str:
    """Return the data directory for persistent storage."""
    # Priority:
    # 1. Environment variable
    # 2. Container path (/app/data) if it exists
    # 3. Local fallback (./data)
    env_val = os.environ.get("FLOW_DATA_DIR")
    if env_val:
        return env_val
    if os.path.isdir("/app/data"):
        return "/app/data"
    return os.path.abspath("data")


@cache
def get_database_url() -> str:
    """Return the database URL from environment."""
    default_db = f"sqlite+aiosqlite:///{get_data_dir()}/flow-app.db"
    return os.environ.get(
        "H4CKATH0N_DATABASE_URL",
        default_db,
    )


@cache
def get_env() -> str:
    """Return the current environment (e.g. 'development', 'production')."""
    return os.environ.get("H4CKATH0N_ENV", "development")


@cache
def get_worker_id() -> str:
    """Return the worker ID for the current process."""
    return os.environ.get("FLOW_WORKER_ID") or socket.gethostname()


@cache
def get_openai_api_key() -> str | None:
    """Return the OpenAI API key."""
    return os.environ.get("H4CKATH0N_OPENAI_API_KEY") or os.environ.get(
        "OPENAI_API_KEY"
    )


@cache
def get_llm_model() -> str:
    """Return the LLM model to use."""
    return os.environ.get("LLM_MODEL", "gpt-4o-mini")


@cache
def get_vapid_public_key() -> str:
    """Return the VAPID public key."""
    key = os.environ.get("VAPID_PUBLIC_KEY")
    return key or os.environ.get("FLOW_VAPID_PUBLIC_KEY", "")


@cache
def get_vapid_private_key() -> str:
    """Return the VAPID private key."""
    key = os.environ.get("VAPID_PRIVATE_KEY")
    return key or os.environ.get("FLOW_VAPID_PRIVATE_KEY", "")


@cache
def get_vapid_sub() -> str:
    """Return the VAPID subject claim."""
    sub = os.environ.get("VAPID_CLAIM_SUB")
    return sub or "mailto:flow@oss.joefang.org"


@cache
def get_push_gone_410_threshold() -> int:
    """Return the consecutive 410 count before revoking a push subscription."""
    val = os.environ.get("FLOW_PUSH_GONE_410_THRESHOLD", "2")
    try:
        return int(val)
    except (ValueError, TypeError):
        return 2


@cache
def is_feedback_loop_enabled() -> bool:
    """Return whether automated delayed feedback requests are enabled."""
    return os.environ.get("ENABLE_AUTOMATED_FEEDBACK", "true").lower() == "true"


@cache
def get_feedback_delay_minutes() -> int:
    """Return delay (minutes) before automated feedback is queued."""
    val = os.environ.get("FEEDBACK_DELAY_MINUTES", "120")
    try:
        return max(1, int(val))
    except (ValueError, TypeError):
        return 120


@cache
def get_feedback_prompt_text() -> str:
    """Return the global prompt text used for delayed feedback requests."""
    return os.environ.get(
        "FEEDBACK_PROMPT_TEXT",
        "How did this prompt work for you?",
    )


@cache
def get_feedback_options() -> list[str]:
    """Return up to two global feedback options for push action buttons."""
    raw = os.environ.get("FEEDBACK_OPTIONS", "Works perfectly,Needs tweaks")
    options = [opt.strip() for opt in raw.split(",") if opt.strip()]
    return options[:2] if options else ["Works perfectly", "Needs tweaks"]


def build_feedback_actions() -> list[dict[str, str]]:
    """Build canonical push action payloads for feedback options."""
    return [
        {"action": f"fb_{i}", "title": opt}
        for i, opt in enumerate(get_feedback_options())
    ]


_FALLBACK_TZ = "America/Toronto"


@cache
def get_default_timezone() -> str:
    """Return the default timezone: TZ env if valid IANA, else America/Toronto."""
    tz_env = os.environ.get("TZ", "").strip()
    if tz_env:
        try:
            ZoneInfo(tz_env)
            return tz_env
        except (ZoneInfoNotFoundError, KeyError):
            pass
    return _FALLBACK_TZ


@cache
def get_port() -> int:
    """Return the port the API server should listen on."""
    try:
        return int(os.environ.get("API_PORT") or os.environ.get("PORT", "8000"))
    except (ValueError, TypeError):
        return 8000


@cache
def get_host() -> str:
    """Return the network interface the API server should bind to."""
    return os.environ.get("API_HOST") or os.environ.get("HOST", "::")


@cache
def get_log_level() -> str:
    """Return the global log level for the application."""
    return os.environ.get("LOG_LEVEL", "INFO").upper()


@cache
def get_flow_crypto_master_key() -> str:
    """Return Flow's Base64URL-encoded 32-byte cryptographic master key.

    Feature code must obtain a domain-separated subkey from
    ``app.services.crypto`` rather than using this value directly.
    """
    return os.environ.get("FLOW_CRYPTO_MASTER_KEY", "")


# ---------------------------------------------------------------------------
# Spark A/B Google Sheets source (additive; Sheets used only when configured)
# ---------------------------------------------------------------------------


@cache
def get_spark_sheets_credentials_json() -> str:
    """Return the Google service-account JSON string for Sheets read-only access.

    Set ``SPARK_SHEETS_CREDENTIALS_JSON`` to the full service-account JSON
    (the content of the downloaded key file, not a file path). It takes
    precedence over ``SPARK_SHEETS_CREDENTIALS_FILE`` when both are set.
    """
    return os.environ.get("SPARK_SHEETS_CREDENTIALS_JSON", "")


@cache
def get_spark_sheets_credentials_file() -> str:
    """Return the mounted service-account key-file path for Sheets access.

    Set ``SPARK_SHEETS_CREDENTIALS_FILE`` to a readable Google service-account
    JSON file. The file is used only when ``SPARK_SHEETS_CREDENTIALS_JSON`` is
    empty. When neither credential source is set, the Spark A/B library falls
    back to the bundled ``spark_library.json``.
    """
    return os.environ.get("SPARK_SHEETS_CREDENTIALS_FILE", "")


@cache
def get_spark_sheets_spreadsheet_id() -> str:
    """Return the Google Sheets spreadsheet ID for the Spark A/B prompt library."""
    return os.environ.get("SPARK_SHEETS_SPREADSHEET_ID", "")


@cache
def get_spark_sheets_range() -> str:
    """Return the A1-notation range to fetch from the Spark spreadsheet.

    Defaults to ``Sparks!A:E`` which reads all rows from a tab named
    *Sparks* with columns: id, title, action, reward, tags.
    """
    return os.environ.get("SPARK_SHEETS_RANGE", "Sparks!A:E")


@cache
def get_spark_sheets_cache_ttl() -> float:
    """Return the cache TTL in seconds for the Spark library dataset.

    After the TTL expires the cached data is served immediately (stale-
    while-revalidate) while a background refresh runs.  Defaults to 60 s.
    """
    val = os.environ.get("SPARK_SHEETS_CACHE_TTL_SECS", "60")
    try:
        return max(1.0, float(val))
    except (ValueError, TypeError):
        return 60.0


@cache
def get_spark_sheets_timeout() -> float:
    """Return the Sheets API request timeout in seconds.  Defaults to 10 s."""
    val = os.environ.get("SPARK_SHEETS_REQUEST_TIMEOUT_SECS", "10")
    try:
        return max(1.0, float(val))
    except (ValueError, TypeError):
        return 10.0


def clear_config_cache() -> None:
    """Clear all configuration caches (useful for testing)."""
    get_data_dir.cache_clear()
    get_database_url.cache_clear()
    get_env.cache_clear()
    get_worker_id.cache_clear()
    get_openai_api_key.cache_clear()
    get_llm_model.cache_clear()
    get_vapid_public_key.cache_clear()
    get_vapid_private_key.cache_clear()
    get_vapid_sub.cache_clear()
    get_push_gone_410_threshold.cache_clear()
    is_feedback_loop_enabled.cache_clear()
    get_feedback_delay_minutes.cache_clear()
    get_feedback_prompt_text.cache_clear()
    get_feedback_options.cache_clear()
    get_default_timezone.cache_clear()
    get_host.cache_clear()
    get_port.cache_clear()
    get_log_level.cache_clear()
    get_flow_crypto_master_key.cache_clear()
    get_spark_sheets_credentials_json.cache_clear()
    get_spark_sheets_credentials_file.cache_clear()
    get_spark_sheets_spreadsheet_id.cache_clear()
    get_spark_sheets_range.cache_clear()
    get_spark_sheets_cache_ttl.cache_clear()
    get_spark_sheets_timeout.cache_clear()
    from app.services.crypto import clear_crypto_key_cache

    clear_crypto_key_cache()
