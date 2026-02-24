"""VAPID configuration utilities."""

import os
from functools import cache


@cache
def get_vapid_public_key() -> str:
    """Return the VAPID public key from environment."""
    key = os.environ.get("VAPID_PUBLIC_KEY")
    return key or os.environ.get("FLOW_VAPID_PUBLIC_KEY", "")


@cache
def get_vapid_private_key() -> str:
    """Return the VAPID private key from environment."""
    key = os.environ.get("VAPID_PRIVATE_KEY")
    return key or os.environ.get("FLOW_VAPID_PRIVATE_KEY", "")


@cache
def get_vapid_sub() -> str:
    """Return the VAPID 'sub' (subject) claim from environment."""
    sub = os.environ.get("VAPID_CLAIM_SUB")
    return sub or "mailto:flow@oss.joefang.org"


def get_vapid_claims() -> dict[str, str]:
    """Return the VAPID claims dictionary."""
    return {"sub": get_vapid_sub()}


def clear_vapid_cache() -> None:
    """Clear the VAPID configuration cache (used for tests)."""
    get_vapid_public_key.cache_clear()
    get_vapid_private_key.cache_clear()
    get_vapid_sub.cache_clear()
