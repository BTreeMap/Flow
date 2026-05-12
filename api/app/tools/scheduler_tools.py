from __future__ import annotations

import json
import logging

from langchain_core.tools import BaseTool, tool

from app.db import async_session_factory
from app.models import NotificationRule
from sqlalchemy import select

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers — NOT LangChain tools, never exposed to the LLM.
# Used by make_scoped_list_schedules_tool and by tests for DB setup.
# ---------------------------------------------------------------------------


async def _list_schedules_for_membership(membership_id: int) -> str:
    """Return a formatted list of active notification rules for *membership_id*.

    This is a plain async function, not a tool.  It uses the module-level
    ``async_session_factory`` so tests can monkeypatch it.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(NotificationRule).where(
                NotificationRule.membership_id == membership_id,
                NotificationRule.is_active.is_(True),
            )
        )
        rules = result.scalars().all()
        if not rules:
            return "No active schedules found."

        lines = []
        for r in rules:
            config = json.loads(r.config_json)
            topic = config.get("topic", "?")
            time_str = config.get("time", "?")
            lines.append(f"ID: {r.id}, Topic: {topic}, Time: {time_str}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scoped LLM tool — the ONLY tool from this module that may be given to an
# LLM agent.  It captures membership_id at construction time so the LLM
# never needs to supply tenant-scoping identifiers.
# ---------------------------------------------------------------------------


def make_scoped_list_schedules_tool(membership_id: int) -> BaseTool:
    """Create a list_schedules tool scoped to a specific membership.

    The returned tool accepts NO arguments — the membership_id is captured
    from the runtime context so the LLM cannot supply a foreign id.
    """

    @tool("list_schedules")
    async def _scoped_list_schedules() -> str:
        """List active notification schedules for this project only.

        Takes no arguments — the project scope is determined automatically.
        """
        return await _list_schedules_for_membership(membership_id)

    return _scoped_list_schedules
