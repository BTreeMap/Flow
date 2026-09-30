"""Dashboard, auth-me, user profile, timezone, and session routes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from h4ckath0n.auth import require_user
from h4ckath0n.auth.models import Device, User
from h4ckath0n.realtime import (
    AuthContext,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db import get_db
from app.errors import AppError, Fault
from app.models import (
    Conversation,
    FlowUserProfile,
    Message,
    NotificationRule,
    NotificationRuleState,
    ProjectMembership,
)
from app.routes._shared import (
    MESSAGE_PREVIEW_MAX_LENGTH,
    _require_auth_context,
)
from app.routes.schemas import (
    AuthMeResponse,
    AuthSessionItem,
    AuthSessionRevokeResponse,
    AuthSessionsResponse,
    DashboardResponse,
    MembershipInfo,
    TimezoneUpdateRequest,
    UserMeResponse,
    UserMeUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/dashboard", tags=["dashboard"])
async def dashboard(
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Return all memberships with project info for the current user."""
    try:
        result = await db.execute(
            select(ProjectMembership)
            .where(ProjectMembership.user_id == user.id)
            .options(
                joinedload(ProjectMembership.project),
                selectinload(ProjectMembership.conversations),
            )
        )
        memberships = result.scalars().all()

        # Batch: fetch last message per conversation to avoid N+1
        membership_ids = [m.id for m in memberships]
        last_msg_map: dict[int, Message] = {}
        if membership_ids:
            # Subquery for the max message id per conversation
            latest_msg_subq = (
                select(
                    Conversation.membership_id,
                    func.max(Message.id).label("max_msg_id"),
                )
                .join(Message, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.membership_id.in_(membership_ids),
                    or_(
                        Message.client_msg_id.is_(None),
                        ~Message.client_msg_id.startswith("feedback_action:"),
                    ),
                )
                .group_by(Conversation.membership_id)
                .subquery()
            )
            last_msgs_result = await db.execute(
                select(latest_msg_subq.c.membership_id, Message).join(
                    Message, Message.id == latest_msg_subq.c.max_msg_id
                )
            )
            for row in last_msgs_result:
                last_msg_map[row[0]] = row[1]

        items: list[MembershipInfo] = []
        for m in memberships:
            # Fetch project display name
            project = m.project

            # Fetch conversation id
            conv = m.conversations[0] if m.conversations else None

            last_msg = last_msg_map.get(m.id)

            items.append(
                MembershipInfo(
                    project_id=m.project_id,
                    display_name=project.display_name if project else None,
                    status=m.status,
                    conversation_id=conv.id if conv else None,
                    last_message_preview=last_msg.content[:MESSAGE_PREVIEW_MAX_LENGTH]
                    if last_msg
                    else None,
                    last_message_at=last_msg.created_at.isoformat()
                    if last_msg
                    else None,
                )
            )

        return DashboardResponse(memberships=items)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load dashboard")
        raise AppError(Fault.INTERNAL, "Failed to load dashboard") from exc


@router.get("/auth/me", tags=["auth"])
async def auth_me(user: User = require_user()) -> AuthMeResponse:
    return AuthMeResponse(user_id=user.id, role=user.role)


@router.get("/me", tags=["user"])
async def get_me(
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> UserMeResponse:
    """Return current user profile including email and display name."""
    try:
        profile_result = await db.execute(
            select(FlowUserProfile).where(FlowUserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()
        return UserMeResponse(
            user_id=user.id,
            email=(
                profile.email_raw or profile.email_normalized
                if profile is not None
                else None
            ),
            display_name=profile.display_name if profile else None,
            is_admin=user.role == "admin",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load user profile")
        raise AppError(Fault.INTERNAL, "Failed to load user profile") from exc


@router.patch("/me", tags=["user"])
async def update_me(
    body: UserMeUpdateRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> UserMeResponse:
    """Update current user's email and/or display name."""
    try:
        profile_result = await db.execute(
            select(FlowUserProfile).where(FlowUserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            profile = FlowUserProfile(user_id=user.id)
            db.add(profile)

        if body.email is not None:
            trimmed_email = str(body.email).strip()
            profile.email_raw = trimmed_email
            profile.email_normalized = trimmed_email.lower()

        if body.display_name is not None:
            # None = don't update; empty string = invalid
            trimmed = body.display_name.strip()
            if len(trimmed) > 255:
                raise AppError(Fault.UNPROCESSABLE, "Display name too long (max 255)")
            if len(trimmed) == 0:
                raise AppError(Fault.UNPROCESSABLE, "Display name cannot be empty")

            profile.display_name = trimmed

        await db.commit()

        # Reload for response
        profile_result = await db.execute(
            select(FlowUserProfile).where(FlowUserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()
        return UserMeResponse(
            user_id=user.id,
            email=(
                profile.email_raw or profile.email_normalized
                if profile is not None
                else None
            ),
            display_name=profile.display_name if profile else None,
            is_admin=user.role == "admin",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update user profile")
        raise AppError(Fault.INTERNAL, "Failed to update user profile") from exc


@router.post("/me/timezone", tags=["user"])
async def update_timezone(
    body: TimezoneUpdateRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Store the user's IANA timezone. Called automatically by the frontend."""
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, KeyError):
            raise AppError(
                Fault.UNPROCESSABLE, f"Invalid IANA timezone: {body.timezone}"
            ) from None

        profile_result = await db.execute(
            select(FlowUserProfile).where(FlowUserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            profile = FlowUserProfile(user_id=user.id)
            db.add(profile)

        profile.timezone = body.timezone
        profile.tz_offset_minutes = body.offset_minutes
        profile.tz_updated_at = datetime.now(UTC)

        await db.commit()

        # Recompute next_due_at_utc for floating notification rules
        try:
            from app.services.notification_engine import recompute_rule_due_time

            mem_result = await db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.user_id == user.id,
                    ProjectMembership.status == "active",
                )
            )
            memberships = mem_result.scalars().all()
            for mem in memberships:
                rule_result = await db.execute(
                    select(NotificationRule, NotificationRuleState)
                    .join(
                        NotificationRuleState,
                        NotificationRule.id == NotificationRuleState.rule_id,
                    )
                    .where(
                        NotificationRule.membership_id == mem.id,
                        NotificationRule.is_active.is_(True),
                        NotificationRule.tz_policy == "floating_user_tz",
                    )
                )
                for rule, state in rule_result.all():
                    if state.locked_by is None:
                        await recompute_rule_due_time(db, rule, state)
            await db.commit()
        except Exception:
            logger.exception("Failed to recompute floating rules after timezone update")

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update timezone")
        raise AppError(Fault.INTERNAL, "Failed to update timezone") from exc


@router.get("/auth/sessions", tags=["auth"])
async def auth_sessions(
    auth_ctx: AuthContext = Depends(_require_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AuthSessionsResponse:
    try:
        result = await db.execute(
            select(Device)
            .where(Device.user_id == auth_ctx.user_id)
            .order_by(Device.created_at.desc())
        )
        sessions = [
            AuthSessionItem(
                device_id=device.id,
                label=device.label,
                created_at=device.created_at.isoformat(),
                revoked_at=device.revoked_at.isoformat() if device.revoked_at else None,
                is_current=device.id == auth_ctx.device_id,
            )
            for device in result.scalars().all()
        ]
        return AuthSessionsResponse(sessions=sessions)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load sessions")
        raise AppError(Fault.INTERNAL, "Failed to load sessions") from exc


@router.post("/auth/sessions/{device_id}/revoke", tags=["auth"])
async def revoke_auth_session(
    device_id: str,
    auth_ctx: AuthContext = Depends(_require_auth_context),
    db: AsyncSession = Depends(get_db),
) -> AuthSessionRevokeResponse:
    try:
        result = await db.execute(
            select(Device).where(
                Device.id == device_id, Device.user_id == auth_ctx.user_id
            )
        )
        device = result.scalar_one_or_none()
        if device is None:
            raise AppError(Fault.NOT_FOUND, "Session not found")
        if device.revoked_at is None:
            device.revoked_at = datetime.now(UTC)
            await db.commit()
        return AuthSessionRevokeResponse(ok=True)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to revoke session")
        raise AppError(Fault.INTERNAL, "Failed to revoke session") from exc
