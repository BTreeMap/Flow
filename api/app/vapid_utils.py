"""VAPID configuration utilities."""

from app import config


def get_vapid_public_key() -> str:
    """Return the VAPID public key from environment."""
    return config.get_vapid_public_key()


def get_vapid_private_key() -> str:
    """Return the VAPID private key from environment."""
    return config.get_vapid_private_key()


def get_vapid_sub() -> str:
    """Return the VAPID 'sub' (subject) claim from environment."""
    return config.get_vapid_sub()


def get_vapid_claims() -> dict[str, str]:
    """Return the VAPID claims dictionary."""
    return {"sub": get_vapid_sub()}


def clear_vapid_cache() -> None:
    """Clear the VAPID configuration cache (used for tests)."""
    config.clear_config_cache()
