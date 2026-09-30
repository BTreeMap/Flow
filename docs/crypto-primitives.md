# Cryptographic primitives

This document records the cryptographic boundary of Flow. It distinguishes
Flow-owned operations that use BLAKE3 from protocol and persistence contracts
that deliberately retain their existing primitive.

## Flow-owned BLAKE3 operations

| Operation | Construction | Code | Reason |
| --- | --- | --- | --- |
| Feature-key derivation | BLAKE3 derive-key mode with fixed context | `app.services.crypto.derive_subkey()` | Separates master-key use by feature. |
| Spark pseudonymous identity | BLAKE3 keyed mode | `app.services.spark_research._identity_keyed_hash()` | Gives a deterministic, non-reversible keyed identifier without storing raw browser data. |
| Experiment block selection | BLAKE3 keyed mode | `app.services.randomization.get_daily_condition()` | Provides a deterministic keyed PRF for randomized-block permutation selection. |
| Static A/B template selection | Unkeyed BLAKE3 content hash | `app.services.intervention_config.get_static_intervention()` | Selects one reproducible template; this is not a security boundary. |

`app.services.crypto` is the only location that imports the Python `blake3`
package. Callers must use its helpers rather than constructing ad-hoc keyed
hashes or directly reading `FLOW_CRYPTO_MASTER_KEY`.

## Deliberate exceptions

| Operation | Primitive | Why it remains |
| --- | --- | --- |
| Project invite lookup | SHA-256 | Existing invite hashes are persisted and raw codes are intentionally unavailable for rehashing. A transition requires an explicit versioned migration and reissue policy. |
| Prompt and Spark-library audit versions | SHA-256 | The persisted `prompt_sha256` field and API metadata explicitly identify the algorithm. Changing it requires a new audit-version field and data migration. |
| Project/message IDs and invite generation | CSPRNG (`random_base32`, `secrets.token_urlsafe`) | These generate entropy; hashing is not a substitute for a secure random source. |
| Spark browser installation ID | Web Crypto CSPRNG (`randomUUID` / `getRandomValues`) | The browser-local longitudinal anchor must be randomly generated, not deterministically derived. |
| Passkeys, device tokens, and Web Push | WebAuthn/ES256/VAPID protocol crypto | Interoperability and standards require these algorithms and key formats. |

## Keyed-mode boundary

BLAKE3 keyed mode is appropriate for Flow-internal MAC/PRF-style operations
with a 32-byte key from `derive_subkey()`. It is **not** a replacement for an
HMAC, signature, or KDF mandated by an external protocol. All keyed inputs are
UTF-8 encoded or canonical bytes before hashing, and no key material or raw
pseudonymous identifiers may be logged.

## Rotation behavior

Changing `FLOW_CRYPTO_MASTER_KEY` changes all BLAKE3-derived keys. Future
experiment assignments are recomputed with the new keyed construction. Spark
requests resolve to new pseudonymous rows because historical keyed hashes cannot
be rekeyed without the deliberately unpersisted browser identifier. Existing
research rows remain intact for analysis.
