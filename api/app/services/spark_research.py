"""Pseudonymous identity resolution and immutable event persistence for Spark."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SparkFingerprintObservation, SparkInteraction, SparkParticipant
from app.services.crypto import (
    CryptoConfigurationError,
    get_spark_identity_key,
    keyed_hexdigest,
)


class SparkResearchConfigurationError(RuntimeError):
    """Raised when the deployment cannot safely persist Spark research data."""


@dataclass(frozen=True)
class ResolvedSparkParticipant:
    """The internal identity available to Spark telemetry writers."""

    participant_id: int


def _identity_keyed_hash(value: str) -> str:
    try:
        key = get_spark_identity_key()
    except CryptoConfigurationError as exc:
        raise SparkResearchConfigurationError(
            "FLOW_CRYPTO_MASTER_KEY must be a valid 32-byte Base64URL key"
        ) from exc
    return keyed_hexdigest(key, value.encode("utf-8"))


async def _find_participant(
    db: AsyncSession, installation_key_hash: str
) -> SparkParticipant | None:
    return await db.scalar(
        select(SparkParticipant).where(
            SparkParticipant.installation_key_hash == installation_key_hash
        )
    )


async def _get_or_create_participant(
    db: AsyncSession, installation_key_hash: str, now: datetime
) -> SparkParticipant:
    participant = await _find_participant(db, installation_key_hash)
    if participant is not None:
        participant.last_seen_at = now
        return participant

    candidate = SparkParticipant(
        installation_key_hash=installation_key_hash,
        first_seen_at=now,
        last_seen_at=now,
    )
    savepoint = await db.begin_nested()
    try:
        db.add(candidate)
        await db.flush()
        await savepoint.commit()
    except IntegrityError:
        await savepoint.rollback()
        participant = await _find_participant(db, installation_key_hash)
        if participant is None:  # pragma: no cover - defensive concurrency guard
            raise
        participant.last_seen_at = now
        return participant
    return candidate


async def _record_fingerprint_observation(
    db: AsyncSession,
    *,
    participant_id: int,
    fingerprint_hash: str,
    fingerprint_version: str | None,
    timezone: str | None,
    locale: str | None,
    now: datetime,
) -> None:
    observation = await db.scalar(
        select(SparkFingerprintObservation).where(
            SparkFingerprintObservation.participant_id == participant_id,
            SparkFingerprintObservation.fingerprint_hash == fingerprint_hash,
        )
    )
    if observation is not None:
        observation.last_seen_at = now
        observation.observation_count += 1
        observation.fingerprint_version = fingerprint_version
        observation.last_timezone = timezone
        observation.last_locale = locale
        return

    candidate = SparkFingerprintObservation(
        participant_id=participant_id,
        fingerprint_hash=fingerprint_hash,
        fingerprint_version=fingerprint_version,
        last_timezone=timezone,
        last_locale=locale,
        first_seen_at=now,
        last_seen_at=now,
        observation_count=1,
    )
    savepoint = await db.begin_nested()
    try:
        db.add(candidate)
        await db.flush()
        await savepoint.commit()
    except IntegrityError:
        await savepoint.rollback()
        observation = await db.scalar(
            select(SparkFingerprintObservation).where(
                SparkFingerprintObservation.participant_id == participant_id,
                SparkFingerprintObservation.fingerprint_hash == fingerprint_hash,
            )
        )
        if observation is None:  # pragma: no cover - defensive concurrency guard
            raise
        observation.last_seen_at = now
        observation.observation_count += 1
        observation.fingerprint_version = fingerprint_version
        observation.last_timezone = timezone
        observation.last_locale = locale


async def resolve_spark_participant(
    db: AsyncSession,
    *,
    installation_id: str,
    fingerprint: str | None,
    fingerprint_version: str | None,
    timezone: str | None,
    locale: str | None,
) -> ResolvedSparkParticipant:
    """Resolve an installation identity and record its optional fingerprint.

    The local installation id is the identity anchor. The fingerprint is an
    independent measurement used to quantify instability and duplication; it
    never causes automatic participant merging.
    """
    now = datetime.now(UTC)
    participant = await _get_or_create_participant(
        db, _identity_keyed_hash(installation_id), now
    )
    if fingerprint is not None:
        await _record_fingerprint_observation(
            db,
            participant_id=participant.id,
            fingerprint_hash=_identity_keyed_hash(fingerprint),
            fingerprint_version=fingerprint_version,
            timezone=timezone,
            locale=locale,
            now=now,
        )
    return ResolvedSparkParticipant(participant_id=participant.id)


async def get_spark_interaction(
    db: AsyncSession, *, participant_id: int, client_event_id: str
) -> SparkInteraction | None:
    """Return the event previously persisted for an idempotency key."""
    return await db.scalar(
        select(SparkInteraction).where(
            SparkInteraction.participant_id == participant_id,
            SparkInteraction.client_event_id == client_event_id,
        )
    )


async def persist_spark_interaction(
    db: AsyncSession,
    *,
    participant_id: int,
    flow_id: str,
    client_event_id: str,
    condition: str,
    event_type: str,
    payload: dict[str, Any],
) -> tuple[SparkInteraction, bool]:
    """Persist an immutable Spark event, returning ``(event, was_created)``."""
    existing = await get_spark_interaction(
        db,
        participant_id=participant_id,
        client_event_id=client_event_id,
    )
    if existing is not None:
        return existing, False

    candidate = SparkInteraction(
        participant_id=participant_id,
        flow_id=flow_id,
        client_event_id=client_event_id,
        condition=condition,
        event_type=event_type,
        payload_json=payload,
    )
    savepoint = await db.begin_nested()
    try:
        db.add(candidate)
        await db.flush()
        await savepoint.commit()
    except IntegrityError:
        await savepoint.rollback()
        existing = await get_spark_interaction(
            db,
            participant_id=participant_id,
            client_event_id=client_event_id,
        )
        if existing is None:  # pragma: no cover - defensive concurrency guard
            raise
        return existing, False
    return candidate, True
