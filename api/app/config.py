"""Configuration management for the application.

Consolidates access to environment variables in a single place with caching.
"""

from __future__ import annotations

import os
import socket
from functools import cache


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
