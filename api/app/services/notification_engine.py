"""Notification engine: timezone-aware rule evaluation, instance creation, delivery.

Core concepts:
- Rules: what should happen and when (e.g. daily nudge at 08:00 local)
- Instances: what the user sees (notification rows)
- Deliveries: how it gets delivered (push commands)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_default_timezone
from app.models import (
    FlowUserProfile,
    NotificationDelivery,
    NotificationRule,
    NotificationRuleState,
    ProjectMembership,
)

logger = logging.getLogger(__name__)


def validate_iana_timezone(tz_name: str) -> ZoneInfo:
    """Validate and return a ZoneInfo. Raises ValueError if invalid."""
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError) as exc:
        raise ValueError(f"Invalid IANA timezone: {tz_name}") from exc


def compute_next_due_utc(
    rule: NotificationRule,
    user_tz_name: str | None,
    now_utc: datetime | None = None,
) -> datetime | None:
    """Compute the next UTC time this rule should fire.

    For daily_local_time rules:
    1. Determine the user's timezone (rule.timezone for pinned, user_tz_name for floating)
    2. Get the local time from config
    3. Find the next occurrence in local time
    4. Convert to UTC

    DST safety:
    - Nonexistent local time (spring forward): round-trip through UTC to find next valid time.
    - Ambiguous local time (fall back): pick first occurrence (fold=0), rely on dedupe.
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)

    if rule.kind != "daily_local_time":
        logger.warning("Unsupported rule kind: %s", rule.kind)
        return None

    config = json.loads(rule.config_json)
    time_str = config.get("time", "09:00")
    hour, minute = _parse_time(time_str)

    # Resolve timezone
    if rule.tz_policy == "pinned_tz" and rule.timezone:
        tz_name = rule.timezone
    else:
        tz_name = user_tz_name or get_default_timezone()

    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        fallback = get_default_timezone()
        logger.warning("Invalid timezone %s, falling back to %s", tz_name, fallback)
        tz = ZoneInfo(fallback)

    # Current time in user's timezone
    now_local = now_utc.astimezone(tz)
    target_time = time(hour, minute)

    # Candidate: today's occurrence in local time
    candidate_local = datetime.combine(now_local.date(), target_time)
    candidate_local = candidate_local.replace(tzinfo=tz, fold=0)

    # If this time has already passed, move to tomorrow
    if candidate_local <= now_local:
        candidate_local = datetime.combine(
            now_local.date() + timedelta(days=1), target_time
        )
        candidate_local = candidate_local.replace(tzinfo=tz, fold=0)

    # DST gap handling: round-trip through UTC and back to local
    candidate_utc = candidate_local.astimezone(UTC)
    round_tripped = candidate_utc.astimezone(tz)

    # If the round-tripped local time doesn't match requested, the time was nonexistent
    if round_tripped.hour != hour or round_tripped.minute != minute:
        # Use the round-tripped UTC instant, which represents the next valid
        # local time after the gap (not a manual shift).
        logger.info(
            "DST gap: requested %02d:%02d but got %02d:%02d in %s, using shifted time",
            hour,
            minute,
            round_tripped.hour,
            round_tripped.minute,
            tz_name,
        )
        return candidate_utc

    return candidate_utc


def compute_local_date_for_rule(
    rule: NotificationRule,
    user_tz_name: str | None,
    fire_utc: datetime,
) -> date:
    """Compute the local date a rule firing corresponds to."""
    if rule.tz_policy == "pinned_tz" and rule.timezone:
        tz_name = rule.timezone
    else:
        tz_name = user_tz_name or get_default_timezone()

    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo(get_default_timezone())

    return fire_utc.astimezone(tz).date()


def _parse_time(preferred_time: str) -> tuple[int, int]:
    """Parse HH:MM or h:mm am/pm to (hour, minute)."""
    import re

    value = preferred_time.strip().lower()
    if not value:
        logger.warning("Empty preferred_time, defaulting to 09:00")
        return 9, 0
    if match_24h := re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value):
        return int(match_24h.group(1)), int(match_24h.group(2))
    if match_ampm := re.fullmatch(r"(\d{1,2})(?::([0-5]\d))?\s*(am|pm)", value):
        hour = int(match_ampm.group(1)) % 12
        if match_ampm.group(3) == "pm":
            hour += 12
        minute = int(match_ampm.group(2) or "0")
        return hour, minute
    logger.warning("Unparseable preferred_time '%s', defaulting to 09:00", value)
    return 9, 0


async def get_user_timezone(db: AsyncSession, membership_id: int) -> str | None:
    """Look up the user's timezone via membership → FlowUserProfile."""
    result = await db.execute(
        select(FlowUserProfile.timezone)
        .join(
            ProjectMembership,
            ProjectMembership.user_id == FlowUserProfile.user_id,
        )
        .where(ProjectMembership.id == membership_id)
    )
    row = result.first()
    return row[0] if row else None


async def claim_due_rules(
    db: AsyncSession,
    worker_id: str,
    now: datetime | None = None,
    limit: int = 20,
    lookahead_seconds: int = 60,
) -> list[tuple[NotificationRule, NotificationRuleState]]:
    """Claim rules whose next_due_at_utc <= now + lookahead. Returns (rule, state) pairs."""
    if now is None:
        now = datetime.now(UTC)
    horizon = now + timedelta(seconds=lookahead_seconds)
    locked_until = now + timedelta(seconds=300)

    # Select candidate rule_ids
    id_query = (
        select(NotificationRuleState.rule_id)
        .join(
            NotificationRule,
            NotificationRule.id == NotificationRuleState.rule_id,
        )
        .where(
            NotificationRule.is_active.is_(True),
            NotificationRuleState.next_due_at_utc.is_not(None),
            NotificationRuleState.next_due_at_utc <= horizon,
            or_(
                NotificationRuleState.locked_until.is_(None),
                NotificationRuleState.locked_until < now,
            ),
        )
        .order_by(NotificationRuleState.next_due_at_utc.asc())
        .limit(limit)
    )

    # Use FOR UPDATE SKIP LOCKED on Postgres
    if db.bind and db.bind.dialect.name == "postgresql":
        id_query = id_query.with_for_update(skip_locked=True)

    result = await db.execute(id_query)
    rule_ids = [rid for (rid,) in result.all()]
    if not rule_ids:
        return []

    # Lock the rows
    for rid in rule_ids:
        state_result = await db.execute(
            select(NotificationRuleState).where(
                NotificationRuleState.rule_id == rid,
                or_(
                    NotificationRuleState.locked_until.is_(None),
                    NotificationRuleState.locked_until < now,
                ),
            )
        )
        state = state_result.scalar_one_or_none()
        if state:
            state.locked_by = worker_id
            state.claimed_at = now
            state.locked_until = locked_until

    await db.flush()

    # Now load the full rule + state pairs
    pairs: list[tuple[NotificationRule, NotificationRuleState]] = []
    for rid in rule_ids:
        rule_result = await db.execute(
            select(NotificationRule).where(NotificationRule.id == rid)
        )
        rule = rule_result.scalar_one_or_none()
        state_result = await db.execute(
            select(NotificationRuleState).where(
                NotificationRuleState.rule_id == rid,
                NotificationRuleState.locked_by == worker_id,
            )
        )
        state = state_result.scalar_one_or_none()
        if rule and state:
            pairs.append((rule, state))

    return pairs


async def claim_due_deliveries(
    db: AsyncSession,
    worker_id: str,
    now: datetime | None = None,
    limit: int = 20,
) -> list[NotificationDelivery]:
    """Claim deliveries that are due for sending."""
    if now is None:
        now = datetime.now(UTC)
    locked_until = now + timedelta(seconds=300)

    id_query = (
        select(NotificationDelivery.id)
        .where(
            NotificationDelivery.run_at_utc <= now,
            NotificationDelivery.status == "pending",
            or_(
                NotificationDelivery.locked_until.is_(None),
                NotificationDelivery.locked_until < now,
            ),
        )
        .order_by(NotificationDelivery.run_at_utc.asc())
        .limit(limit)
    )

    if db.bind and db.bind.dialect.name == "postgresql":
        id_query = id_query.with_for_update(skip_locked=True)

    result = await db.execute(id_query)
    ids = [did for (did,) in result.all()]
    if not ids:
        return []

    for did in ids:
        d_result = await db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.id == did,
                NotificationDelivery.status == "pending",
                or_(
                    NotificationDelivery.locked_until.is_(None),
                    NotificationDelivery.locked_until < now,
                ),
            )
        )
        d = d_result.scalar_one_or_none()
        if d:
            d.locked_by = worker_id
            d.claimed_at = now
            d.locked_until = locked_until

    await db.flush()

    claimed_result = await db.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.id.in_(ids),
            NotificationDelivery.locked_by == worker_id,
        )
    )
    return list(claimed_result.scalars().all())


async def recompute_rule_due_time(
    db: AsyncSession,
    rule: NotificationRule,
    state: NotificationRuleState,
    now_utc: datetime | None = None,
) -> None:
    """Recompute and update next_due_at_utc for a rule, using current user timezone."""
    user_tz = await get_user_timezone(db, rule.membership_id)
    next_due = compute_next_due_utc(rule, user_tz, now_utc)
    state.next_due_at_utc = next_due
    state.locked_by = None
    state.claimed_at = None
    state.locked_until = None
    state.attempts = 0
    state.last_error = None
