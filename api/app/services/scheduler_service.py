"""Scheduler service — logic for managing nudge schedules and outbox events."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NudgeSchedule, ProjectMembership
from app.services.outbox_service import enqueue_outbox_event, next_run_at


async def list_active_schedules(
    db: AsyncSession, membership_id: int
) -> list[NudgeSchedule]:
    """List all active nudge schedules for a membership."""
    result = await db.execute(
        select(NudgeSchedule).where(
            NudgeSchedule.membership_id == membership_id, NudgeSchedule.is_active
        )
    )
    return list(result.scalars().all())


async def create_nudge_schedule(
    db: AsyncSession, membership_id: int, topic: str, cron_rule: str
) -> NudgeSchedule:
    """Create a new daily nudge schedule and enqueue the first event."""
    # Check membership exists
    mem_result = await db.execute(
        select(ProjectMembership).where(ProjectMembership.id == membership_id)
    )
    membership = mem_result.scalar_one_or_none()
    if not membership:
        raise ValueError(f"Membership {membership_id} not found.")

    # Create schedule
    schedule = NudgeSchedule(
        membership_id=membership_id, topic=topic, cron_rule=cron_rule, is_active=True
    )
    db.add(schedule)
    await db.flush()

    run_at = next_run_at(cron_rule, datetime.now(UTC))
    dedupe_key = f"nudge:{schedule.id}:{run_at.date().isoformat()}"

    # Enqueue first event
    await enqueue_outbox_event(
        db,
        project_id=membership.project_id,
        membership_id=membership.id,
        event_type="scheduled_nudge",
        payload={
            "schedule_id": schedule.id,
            "topic": topic,
            "project_id": membership.project_id,
        },
        dedupe_key=dedupe_key,
        available_at=run_at,
    )

    return schedule


async def deactivate_schedule(db: AsyncSession, schedule_id: int) -> bool:
    """Deactivate a nudge schedule. Returns True if found and deactivated."""
    result = await db.execute(
        select(NudgeSchedule).where(NudgeSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        return False

    schedule.is_active = False
    return True
