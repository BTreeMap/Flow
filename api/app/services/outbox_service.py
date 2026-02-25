from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent, ProjectMembership


def _parse_preferred_time(preferred_time: str) -> tuple[int, int]:
    value = preferred_time.strip().lower()
    if not value:
        return 9, 0
    match_24h = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value)
    if match_24h:
        return int(match_24h.group(1)), int(match_24h.group(2))
    match_ampm = re.fullmatch(r"(\d{1,2})(?::([0-5]\d))?\s*(am|pm)", value)
    if match_ampm:
        hour = int(match_ampm.group(1)) % 12
        if match_ampm.group(3) == "pm":
            hour += 12
        minute = int(match_ampm.group(2) or "0")
        return hour, minute
    return 9, 0


def next_run_at(preferred_time: str, now: datetime) -> datetime:
    hour, minute = _parse_preferred_time(preferred_time)
    candidate = now.astimezone(UTC).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if candidate <= now.astimezone(UTC):
        candidate += timedelta(days=1)
    return candidate


async def enqueue_outbox_event(
    db: AsyncSession,
    *,
    project_id: str,
    membership_id: int,
    event_type: str,
    payload: dict[str, object],
    dedupe_key: str,
    available_at: datetime,
) -> OutboxEvent:
    existing_result = await db.execute(
        select(OutboxEvent).where(OutboxEvent.dedupe_key == dedupe_key)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing
    event = OutboxEvent(
        project_id=project_id,
        membership_id=membership_id,
        type=event_type,
        payload_json=json.dumps(payload),
        dedupe_key=dedupe_key,
        available_at=available_at,
    )
    db.add(event)
    await db.flush()
    return event


async def enqueue_next_scheduled_prompt(
    db: AsyncSession,
    *,
    membership: ProjectMembership,
    preferred_time: str,
    now: datetime | None = None,
) -> OutboxEvent:
    run_now = now or datetime.now(UTC)
    run_at = next_run_at(preferred_time, run_now)
    dedupe_key = f"scheduled_prompt:{membership.id}:{run_at.date().isoformat()}"
    return await enqueue_outbox_event(
        db,
        project_id=membership.project_id,
        membership_id=membership.id,
        event_type="scheduled_prompt",
        payload={"project_id": membership.project_id},
        dedupe_key=dedupe_key,
        available_at=run_at,
    )


async def replace_next_scheduled_prompt(
    db: AsyncSession,
    *,
    membership: ProjectMembership,
    preferred_time: str,
    now: datetime | None = None,
) -> OutboxEvent:
    run_now = now or datetime.now(UTC)
    await db.execute(
        delete(OutboxEvent).where(
            OutboxEvent.membership_id == membership.id,
            OutboxEvent.type == "scheduled_prompt",
            OutboxEvent.available_at > run_now,
        )
    )
    return await enqueue_next_scheduled_prompt(
        db,
        membership=membership,
        preferred_time=preferred_time,
        now=run_now,
    )
