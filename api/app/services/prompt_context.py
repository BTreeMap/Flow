"""Centralized prompt context for all product LLM prompts.

Provides a unified dict of template variables (time, display_name, etc.) that
are pre-substituted into every prompt via ``string.Template.safe_substitute``.

Adding a new variable here automatically makes it available to every agent
(Intake, Coach, Feedback) and the notification worker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_default_timezone
from app.services.notification_engine import get_user_timezone
from app.services.profile_service import get_display_name_for_membership


def _resolve_tz(tz_name: str | None) -> str:
    """Return valid IANA timezone: user tz → app default."""
    if tz_name:
        try:
            ZoneInfo(tz_name)
            return tz_name
        except (ZoneInfoNotFoundError, KeyError):
            pass
    return get_default_timezone()


def _build_time_context(
    tz_name: str | None,
    now_utc: datetime | None = None,
) -> dict[str, str]:
    """Build localized time context dict from a timezone name."""
    effective_tz = _resolve_tz(tz_name)
    if now_utc is None:
        now_utc = datetime.now(UTC)
    local_now = now_utc.astimezone(ZoneInfo(effective_tz))
    return {
        "timezone": effective_tz,
        "current_date": local_now.strftime("%Y-%m-%d"),
        "current_time": local_now.strftime("%H:%M"),
        "current_datetime": local_now.strftime("%Y-%m-%d %H:%M"),
    }


async def get_prompt_context_for_membership(
    db: AsyncSession,
    membership_id: int,
    now_utc: datetime | None = None,
) -> dict[str, str]:
    """Build the full set of standard template variables for any LLM prompt.

    Returns a dict suitable for ``string.Template.safe_substitute``.
    Currently includes:
        - display_name
        - timezone, current_date, current_time, current_datetime

    All agents and the notification worker should call this single function
    so that every prompt receives the same baseline context.
    """
    user_tz = await get_user_timezone(db, membership_id)
    time_ctx = _build_time_context(user_tz, now_utc)
    display_name = await get_display_name_for_membership(db, membership_id)
    return {
        "display_name": display_name or "the user (name unknown)",
        **time_ctx,
    }
