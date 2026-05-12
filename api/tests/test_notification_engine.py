"""Tests for the unified notification engine: timezone, rule evaluation, idempotency."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import AsyncGenerator
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.id_utils import generate_project_id
from app.models import (
    Base,
    Conversation,
    FlowUserProfile,
    Message,
    Notification,
    NotificationDelivery,
    NotificationRule,
    NotificationRuleState,
    Project,
    ProjectMembership,
)
from app.services.notification_engine import (
    compute_local_date_for_rule,
    compute_next_due_utc,
    get_user_timezone,
    recompute_rule_due_time,
    validate_iana_timezone,
)

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _session_factory() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded(db: AsyncSession) -> dict[str, int | str]:
    """Seed a project, membership, and user profile with timezone."""
    project_id = generate_project_id()
    db.add(Project(id=project_id, display_name="Test"))
    membership = ProjectMembership(
        project_id=project_id, user_id="u_tz_test", status="active"
    )
    db.add(membership)
    db.add(
        FlowUserProfile(
            user_id="u_tz_test",
            timezone="America/Toronto",
            tz_updated_at=datetime.now(UTC),
        )
    )
    await db.commit()
    return {"project_id": project_id, "membership_id": membership.id}


# ---------------------------------------------------------------------------
# Timezone validation
# ---------------------------------------------------------------------------


class TestTimezoneValidation:
    def test_valid_timezone(self) -> None:
        tz = validate_iana_timezone("America/Toronto")
        assert str(tz) == "America/Toronto"

    def test_utc_timezone(self) -> None:
        tz = validate_iana_timezone("UTC")
        assert str(tz) == "UTC"

    def test_invalid_timezone_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid IANA timezone"):
            validate_iana_timezone("Narnia/Lamppost")


# ---------------------------------------------------------------------------
# compute_next_due_utc
# ---------------------------------------------------------------------------


class TestComputeNextDueUtc:
    def test_basic_next_due(self) -> None:
        """A rule at 08:00 America/Toronto when now is 06:00 Toronto → fires today."""
        rule = NotificationRule(
            id=1,
            membership_id=1,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "test", "time": "08:00"}),
            tz_policy="floating_user_tz",
            is_active=True,
        )
        # 06:00 Toronto = 11:00 UTC (EST, no DST)
        now_utc = datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC)
        result = compute_next_due_utc(rule, "America/Toronto", now_utc)

        assert result is not None
        # 08:00 Toronto = 13:00 UTC in January (EST = UTC-5)
        expected = datetime(2026, 1, 15, 13, 0, 0, tzinfo=UTC)
        assert result == expected

    def test_past_time_rolls_to_tomorrow(self) -> None:
        """If 08:00 local already passed, schedule for tomorrow."""
        rule = NotificationRule(
            id=1,
            membership_id=1,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "test", "time": "08:00"}),
            tz_policy="floating_user_tz",
            is_active=True,
        )
        # 10:00 Toronto = 15:00 UTC (EST)
        now_utc = datetime(2026, 1, 15, 15, 0, 0, tzinfo=UTC)
        result = compute_next_due_utc(rule, "America/Toronto", now_utc)

        assert result is not None
        # Tomorrow 08:00 Toronto = 13:00 UTC
        expected = datetime(2026, 1, 16, 13, 0, 0, tzinfo=UTC)
        assert result == expected

    def test_dst_spring_forward(self) -> None:
        """2026-03-08 is spring forward day in America/Toronto.
        02:30 doesn't exist — should shift to 03:30 (next valid time).
        Actually fold=0 on nonexistent time in zoneinfo shifts to the wall clock
        time after the gap, which is fine for our purposes."""
        rule = NotificationRule(
            id=1,
            membership_id=1,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "test", "time": "02:30"}),
            tz_policy="floating_user_tz",
            is_active=True,
        )
        # Before spring forward: 2026-03-08 01:00 Toronto = 06:00 UTC
        now_utc = datetime(2026, 3, 8, 6, 0, 0, tzinfo=UTC)
        result = compute_next_due_utc(rule, "America/Toronto", now_utc)

        assert result is not None
        # The result should be a valid UTC time after 06:00
        assert result > now_utc
        # Convert back to Toronto to verify it's a valid time
        toronto = ZoneInfo("America/Toronto")
        local_result = result.astimezone(toronto)
        # On spring forward day, 02:30 doesn't exist, zoneinfo will handle it
        # The important thing is the result is valid and after now
        assert local_result.hour in (2, 3)  # Depending on zoneinfo behavior

    def test_dst_fall_back_deterministic(self) -> None:
        """2026-11-01 is fall-back day in America/Toronto.
        01:30 is ambiguous. fold=0 picks the first (EDT) occurrence."""
        rule = NotificationRule(
            id=1,
            membership_id=1,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "test", "time": "01:30"}),
            tz_policy="floating_user_tz",
            is_active=True,
        )
        # Before fall back: 2026-11-01 00:00 Toronto = 04:00 UTC (EDT)
        now_utc = datetime(2026, 11, 1, 4, 0, 0, tzinfo=UTC)
        result = compute_next_due_utc(rule, "America/Toronto", now_utc)

        assert result is not None
        # fold=0 should give us the EDT interpretation: 01:30 EDT = 05:30 UTC
        expected = datetime(2026, 11, 1, 5, 30, 0, tzinfo=UTC)
        assert result == expected

    def test_no_timezone_defaults_to_app_default(self) -> None:
        """When no user timezone is set, default to app default (America/Toronto)."""
        from app.config import clear_config_cache

        # Ensure TZ env does not interfere
        import os

        old_tz = os.environ.pop("TZ", None)
        clear_config_cache()
        try:
            rule = NotificationRule(
                id=1,
                membership_id=1,
                kind="daily_local_time",
                config_json=json.dumps({"topic": "test", "time": "09:00"}),
                tz_policy="floating_user_tz",
                is_active=True,
            )
            # 08:00 UTC → 03:00 Toronto (EST, UTC-5), so 09:00 Toronto = 14:00 UTC
            now_utc = datetime(2026, 1, 15, 8, 0, 0, tzinfo=UTC)
            result = compute_next_due_utc(rule, None, now_utc)

            assert result is not None
            # 09:00 America/Toronto in January (EST) = 14:00 UTC
            expected = datetime(2026, 1, 15, 14, 0, 0, tzinfo=UTC)
            assert result == expected
        finally:
            if old_tz is not None:
                os.environ["TZ"] = old_tz
            else:
                os.environ.pop("TZ", None)
            clear_config_cache()

    def test_pinned_timezone_ignores_user_tz(self) -> None:
        """A pinned-tz rule uses its own timezone, not the user's."""
        rule = NotificationRule(
            id=1,
            membership_id=1,
            kind="daily_local_time",
            config_json=json.dumps({"topic": "test", "time": "08:00"}),
            tz_policy="pinned_tz",
            timezone="Europe/London",
            is_active=True,
        )
        now_utc = datetime(2026, 1, 15, 7, 0, 0, tzinfo=UTC)
        result = compute_next_due_utc(rule, "America/Toronto", now_utc)

        assert result is not None
        # 08:00 London in January = 08:00 UTC (GMT)
        expected = datetime(2026, 1, 15, 8, 0, 0, tzinfo=UTC)
        assert result == expected


# ---------------------------------------------------------------------------
# compute_local_date_for_rule
# ---------------------------------------------------------------------------


class TestComputeLocalDate:
    def test_local_date_different_from_utc(self) -> None:
        """23:30 UTC on Jan 15 = 18:30 Toronto (Jan 15 local)."""
        rule = NotificationRule(
            id=1,
            membership_id=1,
            kind="daily_local_time",
            config_json="{}",
            tz_policy="floating_user_tz",
            is_active=True,
        )
        fire_utc = datetime(2026, 1, 15, 23, 30, 0, tzinfo=UTC)
        result = compute_local_date_for_rule(rule, "America/Toronto", fire_utc)
        assert result == date(2026, 1, 15)

    def test_utc_midnight_crosses_date_boundary(self) -> None:
        """02:00 UTC on Jan 16 = 21:00 Toronto (Jan 15 local, EST)."""
        rule = NotificationRule(
            id=1,
            membership_id=1,
            kind="daily_local_time",
            config_json="{}",
            tz_policy="floating_user_tz",
            is_active=True,
        )
        fire_utc = datetime(2026, 1, 16, 2, 0, 0, tzinfo=UTC)
        result = compute_local_date_for_rule(rule, "America/Toronto", fire_utc)
        assert result == date(2026, 1, 15)


# ---------------------------------------------------------------------------
# get_user_timezone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_timezone(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    membership_id = int(seeded["membership_id"])
    tz = await get_user_timezone(db, membership_id)
    assert tz == "America/Toronto"


@pytest.mark.asyncio
async def test_get_user_timezone_none(db: AsyncSession) -> None:
    """Returns None when no profile exists."""
    project_id = generate_project_id()
    db.add(Project(id=project_id))
    membership = ProjectMembership(
        project_id=project_id, user_id="u_no_profile", status="active"
    )
    db.add(membership)
    await db.commit()
    tz = await get_user_timezone(db, membership.id)
    assert tz is None


# ---------------------------------------------------------------------------
# Rule evaluation idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notification_dedupe_key_prevents_duplicates(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """Two notifications with the same dedupe_key cannot exist."""
    membership_id = int(seeded["membership_id"])
    n1 = Notification(
        membership_id=membership_id,
        title="Test",
        body="Body",
        payload_json="{}",
        dedupe_key="rule:1:2026-01-15",
    )
    db.add(n1)
    await db.flush()

    n2 = Notification(
        membership_id=membership_id,
        title="Dupe",
        body="Dupe body",
        payload_json="{}",
        dedupe_key="rule:1:2026-01-15",
    )
    db.add(n2)
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_notification_null_dedupe_key_allowed(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """Multiple notifications with NULL dedupe_key should be allowed."""
    membership_id = int(seeded["membership_id"])
    for i in range(3):
        db.add(
            Notification(
                membership_id=membership_id,
                title=f"Test {i}",
                body=f"Body {i}",
                payload_json="{}",
                dedupe_key=None,
            )
        )
    await db.flush()
    result = await db.execute(select(Notification))
    assert len(result.scalars().all()) == 3


# ---------------------------------------------------------------------------
# Message idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_client_msg_id_dedupe(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """Two messages with the same (conversation_id, client_msg_id) fail."""
    membership_id = int(seeded["membership_id"])
    conv = Conversation(membership_id=membership_id)
    db.add(conv)
    await db.flush()

    from app.id_utils import generate_server_msg_id

    m1 = Message(
        conversation_id=conv.id,
        role="assistant",
        content="msg1",
        server_msg_id=generate_server_msg_id(),
        client_msg_id="dedup-key-1",
    )
    db.add(m1)
    await db.flush()

    m2 = Message(
        conversation_id=conv.id,
        role="assistant",
        content="msg2",
        server_msg_id=generate_server_msg_id(),
        client_msg_id="dedup-key-1",
    )
    db.add(m2)
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_message_null_client_msg_id_allowed(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """Messages with NULL client_msg_id should not conflict."""
    membership_id = int(seeded["membership_id"])
    conv = Conversation(membership_id=membership_id)
    db.add(conv)
    await db.flush()

    from app.id_utils import generate_server_msg_id

    for _ in range(3):
        db.add(
            Message(
                conversation_id=conv.id,
                role="user",
                content="hello",
                server_msg_id=generate_server_msg_id(),
                client_msg_id=None,
            )
        )
    await db.flush()
    result = await db.execute(select(Message))
    assert len(result.scalars().all()) == 3


# ---------------------------------------------------------------------------
# Rule + State lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rule_state_recompute(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """recompute_rule_due_time updates next_due_at_utc and clears locks."""
    membership_id = int(seeded["membership_id"])
    rule = NotificationRule(
        membership_id=membership_id,
        kind="daily_local_time",
        config_json=json.dumps({"topic": "walk", "time": "08:00"}),
        tz_policy="floating_user_tz",
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    state = NotificationRuleState(
        rule_id=rule.id,
        next_due_at_utc=datetime.now(UTC),
        locked_by="worker-1",
        claimed_at=datetime.now(UTC),
        locked_until=datetime.now(UTC) + timedelta(minutes=5),
    )
    db.add(state)
    await db.flush()

    await recompute_rule_due_time(db, rule, state)

    assert state.locked_by is None
    assert state.claimed_at is None
    assert state.locked_until is None
    assert state.next_due_at_utc is not None
    # Should be in the future (08:00 Toronto time)
    assert state.next_due_at_utc > datetime.now(UTC)


# ---------------------------------------------------------------------------
# Delivery model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delivery_creation(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """Can create notification deliveries linked to instances."""
    membership_id = int(seeded["membership_id"])
    notification = Notification(
        membership_id=membership_id,
        title="Test",
        body="Body",
        payload_json="{}",
    )
    db.add(notification)
    await db.flush()

    delivery = NotificationDelivery(
        instance_id=notification.id,
        membership_id=membership_id,
        channel="push_notify",
        payload_json=json.dumps({"title": "Test"}),
        run_at_utc=datetime.now(UTC),
    )
    db.add(delivery)
    await db.flush()

    assert delivery.id is not None
    assert delivery.status == "pending"


# ---------------------------------------------------------------------------
# Timezone change does NOT require stale row cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timezone_change_takes_effect_immediately(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """When user changes timezone, recompute_rule_due_time uses the new tz."""
    membership_id = int(seeded["membership_id"])

    rule = NotificationRule(
        membership_id=membership_id,
        kind="daily_local_time",
        config_json=json.dumps({"topic": "walk", "time": "08:00"}),
        tz_policy="floating_user_tz",
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    state = NotificationRuleState(rule_id=rule.id)
    db.add(state)
    await db.flush()

    # With America/Toronto timezone
    await recompute_rule_due_time(db, rule, state)
    toronto_due = state.next_due_at_utc
    assert toronto_due is not None

    # Change user's timezone to Asia/Tokyo
    profile_result = await db.execute(
        select(FlowUserProfile).where(FlowUserProfile.user_id == "u_tz_test")
    )
    profile = profile_result.scalar_one()
    profile.timezone = "Asia/Tokyo"
    await db.flush()

    # Recompute — should now use Asia/Tokyo
    await recompute_rule_due_time(db, rule, state)
    tokyo_due = state.next_due_at_utc
    assert tokyo_due is not None

    # The two due times should be different (Toronto and Tokyo are 14h apart)
    assert toronto_due != tokyo_due
