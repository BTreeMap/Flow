from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from app.db import async_session_factory
from app.services.scheduler_service import (
    create_nudge_schedule,
    deactivate_schedule,
    list_active_schedules,
)


@tool
async def list_schedules(
    membership_id: Annotated[
        int, "The ID of the project membership to list schedules for"
    ],
) -> str:
    """List all active nudge schedules for a user."""
    async with async_session_factory() as db:
        schedules = await list_active_schedules(db, membership_id)
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
        try:
            schedule = await create_nudge_schedule(db, membership_id, topic, time)
            await db.commit()
            return f"Scheduled nudge ID {schedule.id} for {time} daily."
        except ValueError as e:
            return f"Error: {e}"


@tool
async def delete_schedule(
    schedule_id: Annotated[int, "The ID of the schedule to delete"],
) -> str:
    """Delete (deactivate) a nudge schedule."""
    async with async_session_factory() as db:
        success = await deactivate_schedule(db, schedule_id)
        if not success:
            return "Schedule not found."
        await db.commit()
        return f"Schedule {schedule_id} deactivated."
