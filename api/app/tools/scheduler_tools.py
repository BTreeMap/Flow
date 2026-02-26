from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from langchain_core.tools import tool
from sqlalchemy import select

from app.db import async_session_factory
from app.models import NudgeSchedule, ProjectMembership
from app.services.outbox_service import enqueue_outbox_event, next_run_at


@tool
async def list_schedules(
    membership_id: Annotated[
        int, "The ID of the project membership to list schedules for"
    ],
) -> str:
    """List all active nudge schedules for a user."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(NudgeSchedule).where(
                NudgeSchedule.membership_id == membership_id, NudgeSchedule.is_active
            )
        )
        schedules = result.scalars().all()
        if not schedules:
            return "No active schedules found."

        lines = []
        for s in schedules:
            lines.append(f"ID: {s.id}, Topic: {s.topic}, Time: {s.cron_rule}")
        return "\n".join(lines)


@tool
async def schedule_nudge(
    membership_id: Annotated[int, "The ID of the project membership"],
    topic: Annotated[str, "The topic or prompt for the daily nudge"],
    time: Annotated[str, "The time of day in HH:MM format (24h)"],
) -> str:
    """Schedule a new daily nudge."""
    async with async_session_factory() as db:
        # Check membership exists
        mem_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.id == membership_id)
        )
        membership = mem_result.scalar_one_or_none()
        if not membership:
            return f"Error: Membership {membership_id} not found."

        # Create schedule
        schedule = NudgeSchedule(
            membership_id=membership_id, topic=topic, cron_rule=time, is_active=True
        )
        db.add(schedule)
        await db.flush()

        run_at = next_run_at(time, datetime.now(UTC))
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

        await db.commit()
        return f"Scheduled nudge ID {schedule.id} for {time} daily."


@tool
async def delete_schedule(
    schedule_id: Annotated[int, "The ID of the schedule to delete"],
) -> str:
    """Delete (deactivate) a nudge schedule."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(NudgeSchedule).where(NudgeSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            return "Schedule not found."

        schedule.is_active = False
        await db.commit()
        return f"Schedule {schedule_id} deactivated."
