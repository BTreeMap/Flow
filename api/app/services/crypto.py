"""Domain-separated BLAKE3 primitives for Flow-owned cryptographic operations.

The service provides BLAKE3's three distinct modes: derive-key mode for
domain-separated subkeys, keyed mode for Flow-owned MAC/PRF-style operations,
and unkeyed mode for non-security content fingerprints. Calling code must never
use the master secret directly or reuse a subkey across contexts.
"""

from __future__ import annotations

import base64
import binascii
import re
from functools import cache

from blake3 import blake3

from app.config import get_flow_crypto_master_key

MASTER_KEY_BYTES = 32
DERIVED_KEY_BYTES = 32

_SPARK_IDENTITY_CONTEXT = "flow.spark.identity-keyed-hash.v1"
_RANDOMIZATION_CONTEXT = "flow.experiment.randomization-keyed-hash.v1"


class CryptoConfigurationError(RuntimeError):
    """Raised when the deployment master key is absent or malformed."""


def _decode_master_key(encoded_key: str) -> bytes:
    normalized = encoded_key.strip()
    if not normalized:
        raise CryptoConfigurationError("FLOW_CRYPTO_MASTER_KEY must be configured")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
        raise CryptoConfigurationError(
            "FLOW_CRYPTO_MASTER_KEY must be unpadded Base64URL-encoded key material"
        )

    try:
        padded = normalized + "=" * (-len(normalized) % 4)
        key = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CryptoConfigurationError(
            "FLOW_CRYPTO_MASTER_KEY must be unpadded Base64URL-encoded key material"
        ) from exc

    if len(key) != MASTER_KEY_BYTES:
        raise CryptoConfigurationError(
            "FLOW_CRYPTO_MASTER_KEY must decode to exactly 32 bytes"
        )
    return key


@cache
def _master_key() -> bytes:
    return _decode_master_key(get_flow_crypto_master_key())


def derive_subkey(context: str) -> bytes:
    """Derive a 32-byte subkey in BLAKE3's dedicated derivation mode."""
    return blake3(_master_key(), derive_key_context=context).digest(DERIVED_KEY_BYTES)


def keyed_digest(key: bytes, payload: bytes) -> bytes:
    """Return BLAKE3's fixed-length keyed digest for a Flow-owned payload.

    BLAKE3 keyed mode is suitable for MAC/PRF-style internal uses. It is not a
    replacement for an interoperable HMAC required by an external protocol.
    """
    if len(key) != DERIVED_KEY_BYTES:
        raise ValueError("BLAKE3 keyed mode requires exactly 32 bytes of key material")
    return blake3(payload, key=key).digest(DERIVED_KEY_BYTES)


def keyed_hexdigest(key: bytes, payload: bytes) -> str:
    """Return a lowercase hexadecimal BLAKE3 keyed digest."""
    return keyed_digest(key, payload).hex()


def content_hexdigest(payload: bytes) -> str:
    """Return a non-secret BLAKE3 content fingerprint in hexadecimal."""
    return blake3(payload).hexdigest()


def get_spark_identity_key() -> bytes:
    """Return the domain-separated BLAKE3 key for Spark pseudonymous identity."""
    return derive_subkey(_SPARK_IDENTITY_CONTEXT)


def get_randomization_key() -> bytes:
    """Return the domain-separated key for experiment block randomization."""
    return derive_subkey(_RANDOMIZATION_CONTEXT)


def is_crypto_master_key_configured() -> bool:
    """Report key validity without exposing master-key contents."""
    try:
        _master_key()
    except CryptoConfigurationError:
        return False
    return True


def clear_crypto_key_cache() -> None:
    """Clear derived-key cache for configuration tests."""
    _master_key.cache_clear()
