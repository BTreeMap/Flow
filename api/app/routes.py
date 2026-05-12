"""API routes for the HCI research platform."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.db import async_session_factory, get_db
from app.id_utils import generate_server_msg_id
from app.prompt_loader import prompt_version
from app.models import (
    ConversationTurn,
    FlowUserProfile,
    MemoryItem,
    Notification,
    NotificationDelivery,
    NotificationRule,
    NotificationRuleState,
    PatchAuditLog,
    Conversation,
    Message,
    ParticipantContact,
    Project,
    ProjectInvite,
    ProjectMembership,
    PushSubscription,
    ScheduledTask,
    UserProfileStore,
)
from app.schemas.patches import UserProfileData
from app.services.event_service import load_events_since, persist_event
from app.services.profile_service import load_user_profile, save_user_profile
from app import config
from app.agents.engine import process_turn as engine_process_turn
from h4ckath0n.auth import require_user
from h4ckath0n.auth.dependencies import require_admin
from h4ckath0n.auth.models import Device, User
from h4ckath0n.realtime import (
    AuthContext,
    AuthError,
    authenticate_http_request,
    authenticate_sse_request,
    sse_response,
)
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

router = APIRouter()

MESSAGE_PREVIEW_MAX_LENGTH = 120
FEEDBACK_ACTION_CLIENT_MSG_PREFIX = "feedback_action:"

# ---------------------------------------------------------------------------
# In-memory SSE fan-out queues: conversation_id -> set of asyncio.Queue
# ---------------------------------------------------------------------------
_sse_queues: dict[int, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)


def _publish_event(conversation_id: int, event: dict[str, Any]) -> None:
    """Push an SSE event to all listeners on a conversation."""
    for q in _sse_queues.get(conversation_id, set()):
        q.put_nowait(event)


def _resolve_feedback_action_title(
    deliveries: list[NotificationDelivery], action_id: str
) -> str:
    """Resolve human-readable action title from delivery payload actions."""
    for delivery in deliveries:
        try:
            payload = json.loads(delivery.payload_json)
        except json.JSONDecodeError:
            continue
        for action in payload.get("actions", []):
            if action.get("action") == action_id:
                return str(action.get("title") or action_id)
    return action_id


def _format_feedback_system_message(action_title: str, notification_id: int) -> str:
    return (
        f"[System: User provided feedback '{action_title}' on notification "
        f"{notification_id}]"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_membership(
    db: AsyncSession, project_id: str, user_id: str
) -> ProjectMembership:
    """Return active membership or raise 404."""
    result = await db.execute(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
        )
    )
    if (membership := result.scalar_one_or_none()) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )
    return membership


async def _get_conversation(db: AsyncSession, membership_id: int) -> Conversation:
    """Return conversation for a membership or raise 404."""
    result = await db.execute(
        select(Conversation).where(Conversation.membership_id == membership_id)
    )
    if (conv := result.scalar_one_or_none()) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conv


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class MembershipInfo(BaseModel):
    project_id: str
    display_name: str | None = None
    status: str
    conversation_id: int | None = None
    last_message_preview: str | None = None
    last_message_at: str | None = None


class DashboardResponse(BaseModel):
    memberships: list[MembershipInfo]


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_code: str


class ClaimResponse(BaseModel):
    project_id: str
    membership_status: str
    conversation_id: int


class MeResponse(BaseModel):
    membership_status: str
    conversation_id: int | None = None
    email: str | None = None


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    client_msg_id: str | None = None
    current_notification_id: int | None = None


class FeedbackAction(BaseModel):
    id: str
    title: str


class FeedbackPollMetadata(BaseModel):
    type: Literal["feedback_poll"]
    notification_id: int
    status: Literal["pending", "completed"]
    selected_action_id: str | None = None
    actions: list[FeedbackAction]


class MessageItem(BaseModel):
    message_id: int
    server_msg_id: str
    role: str
    content: str
    created_at: str
    metadata: FeedbackPollMetadata | dict[str, Any] | None = None


class SendMessageResponse(BaseModel):
    message_id: int
    server_msg_id: str
    role: str
    content: str
    user_message: MessageItem | None = None
    debug_info: dict[str, Any] | None = None


class MessageListResponse(BaseModel):
    messages: list[MessageItem]


class FeedbackEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    notification_id: int
    project_id: str | None = None


class PushKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str
    keys: PushKeys
    user_agent: str | None = None


class PushSubscribeResponse(BaseModel):
    subscription_id: int


class NotificationUnreadCountResponse(BaseModel):
    count: int


class VapidPublicKeyResponse(BaseModel):
    public_key: str


class UnifiedNotificationItem(BaseModel):
    id: int
    title: str
    body: str
    created_at: str
    read_at: str | None
    payload_json: str
    project_id: str
    project_display_name: str | None
    membership_id: int
    rule_id: int | None = None
    local_date: str | None = None


class UnifiedNotificationListResponse(BaseModel):
    notifications: list[UnifiedNotificationItem]
    next_cursor: str | None = None


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_anchor: str
    preferred_time: str
    habit_domain: str = ""
    motivational_frame: str = ""


class AdminCreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    study_settings: dict[str, Any] | None = None


class AdminProjectItem(BaseModel):
    project_id: str
    display_name: str | None = None
    status: str = "active"
    created_at: str
    member_count: int


class AdminProjectsResponse(BaseModel):
    projects: list[AdminProjectItem]


class AdminCreateInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = 1
    expires_at: datetime
    max_uses: int | None = None
    label: str | None = None


class AdminCreateInvitesResponse(BaseModel):
    invite_codes: list[str]


class AdminParticipantItem(BaseModel):
    user_id: str
    status: str
    created_at: str
    ended_at: str | None = None
    email: str | None = None
    push_subscription_count: int
    last_push_success_at: str | None = None
    last_push_failure_at: str | None = None


class AdminParticipantsResponse(BaseModel):
    participants: list[AdminParticipantItem]


class AuthMeResponse(BaseModel):
    user_id: str
    role: str


class UserMeResponse(BaseModel):
    user_id: str
    email: str | None = None
    display_name: str | None = None
    is_admin: bool = False


class UserMeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    display_name: str | None = None


class TimezoneUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str
    offset_minutes: int | None = None


class AdminProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    status: Literal["active", "paused", "ended"] | None = None


class AdminPushChannelItem(BaseModel):
    subscription_id: int
    membership_id: int
    user_id: str
    user_email: str | None = None
    display_name: str | None = None
    endpoint_hint: str
    created_at: str
    last_success_at: str | None = None
    last_failure_at: str | None = None


class AdminPushChannelsResponse(BaseModel):
    channels: list[AdminPushChannelItem]


class AdminPushTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: Annotated[str, Field(pattern=r"^p[a-z2-7]{31}$")]
    subscription_ids: list[int]
    title: str
    body: str
    url: str | None = None


class AdminPushTestResultItem(BaseModel):
    subscription_id: int
    ok: bool
    error: str | None = None


class AdminPushTestResponse(BaseModel):
    results: list[AdminPushTestResultItem]


class AuthSessionItem(BaseModel):
    device_id: str
    label: str | None = None
    created_at: str
    revoked_at: str | None = None
    is_current: bool


class AuthSessionsResponse(BaseModel):
    sessions: list[AuthSessionItem]


class AuthSessionRevokeResponse(BaseModel):
    ok: bool


class AdminDebugStatusResponse(BaseModel):
    llm_mode: str
    openai_api_key_configured: bool
    vapid_public_key_configured: bool
    vapid_private_key_configured: bool
    warnings: list[str]


class AdminLLMConnectivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        default_factory=lambda: os.environ.get("LLM_MODEL", "gpt-4o-mini")
    )
    prompt: str = "Reply with exactly: OK"
    max_tokens: int = 128
    temperature: float = 0.0


class AdminLLMConnectivityResponse(BaseModel):
    ok: bool
    model: str
    latency_ms: int
    response_text: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# 1. Dashboard
# ---------------------------------------------------------------------------


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
    except Exception:
        logger.exception("Failed to load dashboard")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")


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
    except Exception:
        logger.exception("Failed to load user profile")
        raise HTTPException(status_code=500, detail="Failed to load user profile")


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
                raise HTTPException(
                    status_code=422, detail="Display name too long (max 255)"
                )
            if len(trimmed) == 0:
                raise HTTPException(
                    status_code=422, detail="Display name cannot be empty"
                )

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
    except Exception:
        logger.exception("Failed to update user profile")
        raise HTTPException(status_code=500, detail="Failed to update user profile")


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
            raise HTTPException(
                status_code=422, detail=f"Invalid IANA timezone: {body.timezone}"
            )

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
    except Exception:
        logger.exception("Failed to update timezone")
        raise HTTPException(status_code=500, detail="Failed to update timezone")


async def _require_auth_context(request: Request) -> AuthContext:
    try:
        return await authenticate_http_request(request)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.detail) from None


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
    except Exception:
        logger.exception("Failed to load sessions")
        raise HTTPException(status_code=500, detail="Failed to load sessions")


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
            raise HTTPException(status_code=404, detail="Session not found")
        if device.revoked_at is None:
            device.revoked_at = datetime.now(UTC)
            await db.commit()
        return AuthSessionRevokeResponse(ok=True)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to revoke session")
        raise HTTPException(status_code=500, detail="Failed to revoke session")


@router.get("/admin/debug/status", tags=["admin"])
async def admin_debug_status(
    _admin_user: User = require_admin(),
) -> AdminDebugStatusResponse:
    llm_key_present = bool(config.get_openai_api_key())
    vapid_public_present = bool(config.get_vapid_public_key())
    vapid_private_present = bool(config.get_vapid_private_key())
    warnings: list[str] = []
    if not llm_key_present:
        warnings.append("OpenAI API key missing: chat runs in stub mode")
    if not vapid_public_present or not vapid_private_present:
        warnings.append("VAPID keys missing: push notifications disabled")
    return AdminDebugStatusResponse(
        llm_mode="openai" if llm_key_present else "stub",
        openai_api_key_configured=llm_key_present,
        vapid_public_key_configured=vapid_public_present,
        vapid_private_key_configured=vapid_private_present,
        warnings=warnings,
    )


@router.post("/admin/debug/llm-connectivity", tags=["admin"])
async def admin_debug_llm_connectivity(
    body: AdminLLMConnectivityRequest,
    _admin_user: User = require_admin(),
) -> AdminLLMConnectivityResponse:
    llm_key = os.environ.get("OPENAI_API_KEY") or os.environ.get(
        "H4CKATH0N_OPENAI_API_KEY"
    )
    if not llm_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key not configured",
        )

    started = time.perf_counter()
    try:
        llm = ChatOpenAI(
            model=body.model,
            api_key=llm_key,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        )
        response = await asyncio.wait_for(
            llm.ainvoke(body.prompt),
            timeout=15,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        response_text = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )[:2000]
        return AdminLLMConnectivityResponse(
            ok=True,
            model=body.model,
            latency_ms=latency_ms,
            response_text=response_text,
        )
    except Exception as exc:  # pragma: no cover - depends on environment/network
        latency_ms = int((time.perf_counter() - started) * 1000)
        return AdminLLMConnectivityResponse(
            ok=False,
            model=body.model,
            latency_ms=latency_ms,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# 2. Activate / Claim invite
# ---------------------------------------------------------------------------


@router.post("/p/{project_id}/activate/claim", tags=["activation"])
async def claim_invite(
    project_id: str,
    body: ClaimRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> ClaimResponse:
    """Validate invite code, create membership and conversation."""
    try:
        return await _claim_invite_impl(project_id, body, user, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Claim invite failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


async def _claim_invite_impl(
    project_id: str,
    body: ClaimRequest,
    user: User,
    db: AsyncSession,
) -> ClaimResponse:
    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Require email on Flow user profile before joining
    profile_result = await db.execute(
        select(FlowUserProfile).where(FlowUserProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    profile_email_raw = profile.email_raw if profile else None
    profile_email_normalized = profile.email_normalized if profile else None
    if not (profile_email_raw or profile_email_normalized):
        return JSONResponse(
            status_code=409,
            content={
                "code": "EMAIL_REQUIRED",
                "message": "Email required before joining a project",
            },
        )

    # Check for existing membership BEFORE invite lookup
    existing_result = await db.execute(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user.id,
        )
    )
    membership = existing_result.scalar_one_or_none()

    if membership is not None and (
        membership.status == "ended" or membership.ended_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Membership ended",
        )

    if membership is not None:
        # Existing non-ended membership: idempotent success regardless of invite validity
        pass
    else:
        # New membership: validate invite code
        now = datetime.now(UTC)
        code_hash = hashlib.sha256(body.invite_code.encode()).hexdigest()

        invite_result = await db.execute(
            select(ProjectInvite).where(
                ProjectInvite.project_id == project_id,
                ProjectInvite.invite_code_hash == code_hash,
            )
        )
        if (invite := invite_result.scalar_one_or_none()) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invite code",
            )

        expires_at = invite.expires_at
        compare_now = now if expires_at.tzinfo else now.replace(tzinfo=None)
        if invite.revoked_at is not None or expires_at <= compare_now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invite code",
            )

        membership = ProjectMembership(
            project_id=project_id, user_id=user.id, status="active"
        )
        db.add(membership)
        created_membership = False
        try:
            await db.flush()
            created_membership = True
        except IntegrityError:
            await db.rollback()
            existing_retry = await db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == user.id,
                )
            )
            membership = existing_retry.scalar_one_or_none()
            if membership is None:
                raise

        if created_membership:
            consume_result = await db.execute(
                update(ProjectInvite)
                .where(
                    ProjectInvite.id == invite.id,
                    ProjectInvite.expires_at > now,
                    ProjectInvite.revoked_at.is_(None),
                    or_(
                        ProjectInvite.max_uses.is_(None),
                        ProjectInvite.uses < ProjectInvite.max_uses,
                    ),
                )
                .values(uses=ProjectInvite.uses + 1)
                .execution_options(synchronize_session=False)
            )
            if consume_result.rowcount != 1:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired invite code",
                )

    # Create conversation if absent
    conv_result = await db.execute(
        select(Conversation).where(Conversation.membership_id == membership.id)
    )
    if (conv := conv_result.scalar_one_or_none()) is None:
        conv = Conversation(membership_id=membership.id)
        db.add(conv)
        await db.flush()

    contact_result = await db.execute(
        select(ParticipantContact)
        .where(ParticipantContact.membership_id == membership.id)
        .order_by(ParticipantContact.created_at.desc())
        .limit(1)
    )
    contact = contact_result.scalar_one_or_none()
    contact_email_raw = (
        profile_email_raw if profile_email_raw is not None else profile_email_normalized
    )
    if contact is None or (
        contact.email_raw != profile_email_raw
        or contact.email_normalized != profile_email_normalized
    ):
        db.add(
            ParticipantContact(
                membership_id=membership.id,
                email_raw=contact_email_raw,
                email_normalized=profile_email_normalized,
            )
        )

    await db.commit()
    await db.refresh(membership)
    await db.refresh(conv)

    # --- Trigger initial greeting if conversation is empty ---
    try:
        msg_count_res = await db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conv.id)
        )
        msg_count = msg_count_res.scalar() or 0

        if msg_count == 0:
            llm_key = os.environ.get("H4CKATH0N_OPENAI_API_KEY") or os.environ.get(
                "OPENAI_API_KEY"
            )
            if llm_key:
                llm = ChatOpenAI(
                    model=os.environ.get("LLM_MODEL", "gpt-4o-mini"), api_key=llm_key
                )

                from app.agents.engine import process_turn as engine_process_turn

                # Run engine with system trigger
                (
                    assistant_content,
                    _decision,
                    debug_info,
                    participation_id,
                ) = await engine_process_turn(
                    db=db,
                    conversation=conv,
                    membership_id=membership.id,
                    user_msg=None,
                    user_text="[USER_JOINED]",
                    llm=llm,
                    router_llm=llm,
                )

                current_condition = debug_info.get("condition")
                if (
                    not isinstance(current_condition, str)
                    or current_condition == "NONE"
                ):
                    current_condition = None
                # Persist assistant message
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=assistant_content,
                    server_msg_id=generate_server_msg_id(),
                    condition_source=(
                        f"COND_{current_condition}" if current_condition else "SYSTEM"
                    ),
                    metadata_={"debug_info": debug_info},
                    participation_id=participation_id,
                )
                db.add(assistant_msg)
                await db.flush()

                # Build SSE payload
                _route_to_prompt = {
                    "INTAKE": "intake_system",
                    "FEEDBACK": "feedback_system",
                    "COACH": "coach_system",
                }
                _prompt_name = _route_to_prompt.get(_decision.route, "coach_system")
                sse_payload = {
                    "message_id": assistant_msg.id,
                    "server_msg_id": assistant_msg.server_msg_id,
                    "role": "assistant",
                    "content": assistant_content,
                    "created_at": assistant_msg.created_at.isoformat()
                    if assistant_msg.created_at
                    else datetime.now(UTC).isoformat(),
                    "prompt_versions": prompt_version(_prompt_name),
                }

                await persist_event(db, conv.id, "message.final", sse_payload)
                await db.commit()

    except Exception:
        logger.exception("Failed to generate initial greeting")
        # Don't fail the claim request

    return ClaimResponse(
        project_id=project_id,
        membership_status=membership.status,
        conversation_id=conv.id,
    )


# ---------------------------------------------------------------------------
# 3. Project membership info
# ---------------------------------------------------------------------------


@router.get("/p/{project_id}/me", tags=["activation"])
async def project_me(
    project_id: str,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Return membership status, conversation id, and stored email."""
    try:
        membership = await _get_membership(db, project_id, user.id)

        # Get conversation
        conv_result = await db.execute(
            select(Conversation).where(Conversation.membership_id == membership.id)
        )
        conv = conv_result.scalar_one_or_none()

        # Get latest email contact
        contact_result = await db.execute(
            select(ParticipantContact)
            .where(ParticipantContact.membership_id == membership.id)
            .order_by(ParticipantContact.created_at.desc())
            .limit(1)
        )
        contact = contact_result.scalar_one_or_none()
        profile_result = await db.execute(
            select(FlowUserProfile).where(FlowUserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()

        return MeResponse(
            membership_status=membership.status,
            conversation_id=conv.id if conv else None,
            email=contact.email_raw
            if contact
            else (profile.email_raw if profile else None),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to load project membership info")
        raise HTTPException(
            status_code=500, detail="Failed to load project membership info"
        )


@router.get("/p/{project_id}/profile", tags=["profile"])
async def get_profile(
    project_id: str,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> UserProfileData:
    try:
        membership = await _get_membership(db, project_id, user.id)
        return await load_user_profile(db, membership.id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to load profile")
        raise HTTPException(status_code=500, detail="Failed to load profile")


@router.put("/p/{project_id}/profile", tags=["profile"])
async def put_profile(
    project_id: str,
    body: ProfileUpdateRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> UserProfileData:
    try:
        membership = await _get_membership(db, project_id, user.id)
        current = await load_user_profile(db, membership.id)
        merged = current.model_dump()
        merged.update(body.model_dump())
        profile = UserProfileData.model_validate(merged)
        await save_user_profile(db, membership.id, profile)
        await db.commit()
        return profile
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to update profile")
        raise HTTPException(status_code=500, detail="Failed to update profile")


# ---------------------------------------------------------------------------
# 4. Send message
# ---------------------------------------------------------------------------


@router.get("/p/{project_id}/messages", tags=["messaging"])
async def list_messages(
    project_id: str,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    """Return persisted messages for a project conversation."""
    try:
        membership = await _get_membership(db, project_id, user.id)
        conv = await _get_conversation(db, membership.id)
        result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conv.id,
                or_(
                    Message.client_msg_id.is_(None),
                    ~Message.client_msg_id.startswith(
                        FEEDBACK_ACTION_CLIENT_MSG_PREFIX
                    ),
                ),
            )
            .order_by(Message.id.asc())
        )
        items = [
            MessageItem(
                message_id=msg.id,
                server_msg_id=msg.server_msg_id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at.isoformat(),
                metadata=msg.metadata_,
            )
            for msg in result.scalars().all()
        ]
        return MessageListResponse(messages=items)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to load messages")
        raise HTTPException(status_code=500, detail="Failed to load messages")


@router.post("/p/{project_id}/messages", tags=["messaging"])
async def send_message(
    project_id: str,
    body: SendMessageRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Persist user message, run engine turn, persist assistant reply."""
    membership = await _get_membership(db, project_id, user.id)
    conv = await _get_conversation(db, membership.id)

    await db.execute(
        update(ScheduledTask)
        .where(
            ScheduledTask.membership_id == membership.id,
            ScheduledTask.task_type == "feedback_request",
            ScheduledTask.status == "pending",
        )
        .values(status="cancelled")
    )
    if body.current_notification_id is not None:
        await db.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.parent_instance_id == body.current_notification_id,
                ScheduledTask.membership_id == membership.id,
                ScheduledTask.status == "pending",
            )
            .values(status="cancelled")
        )

    # Eagerly capture IDs to survive potential rollback
    conv_id = conv.id
    membership_id = membership.id

    # --- Turn gating (idempotent when client_msg_id is provided) ----------
    turn: ConversationTurn | None = None
    if body.client_msg_id:
        # Try to claim the turn by inserting a row with status=processing
        turn = ConversationTurn(
            conversation_id=conv_id,
            client_msg_id=body.client_msg_id,
            status="processing",
        )
        db.add(turn)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # A turn with this client_msg_id already exists
            existing = await db.execute(
                select(ConversationTurn).where(
                    ConversationTurn.conversation_id == conv_id,
                    ConversationTurn.client_msg_id == body.client_msg_id,
                )
            )
            if (turn := existing.scalars().first()) is None:
                raise HTTPException(status_code=500, detail="Turn conflict")
            if turn.status == "completed" and turn.assistant_message_id is not None:
                asst_result = await db.execute(
                    select(Message).where(
                        Message.id == turn.assistant_message_id,
                    )
                )
                asst = asst_result.scalars().first()
                if asst:
                    # Fetch user message for response
                    user_msg_result = await db.execute(
                        select(Message).where(Message.id == turn.user_message_id)
                    )
                    user_msg = user_msg_result.scalars().first()

                    return SendMessageResponse(
                        message_id=asst.id,
                        server_msg_id=asst.server_msg_id,
                        role="assistant",
                        content=asst.content,
                        user_message=MessageItem(
                            message_id=user_msg.id,
                            server_msg_id=user_msg.server_msg_id,
                            role=user_msg.role,
                            content=user_msg.content,
                            created_at=user_msg.created_at.isoformat(),
                        )
                        if user_msg
                        else None,
                    )
            if turn.status == "processing":
                # Another request is processing this turn; wait briefly
                turn_id = turn.id
                for _ in range(6):
                    await asyncio.sleep(0.5)
                    re_result = await db.execute(
                        select(ConversationTurn).where(
                            ConversationTurn.id == turn_id,
                        )
                    )
                    if (turn := re_result.scalars().first()) is None:
                        break
                    if (
                        turn.status == "completed"
                        and turn.assistant_message_id is not None
                    ):
                        asst_result = await db.execute(
                            select(Message).where(
                                Message.id == turn.assistant_message_id,
                            )
                        )
                        asst = asst_result.scalars().first()
                        if asst:
                            # Fetch user message for response
                            user_msg_result = await db.execute(
                                select(Message).where(
                                    Message.id == turn.user_message_id
                                )
                            )
                            user_msg = user_msg_result.scalars().first()

                            return SendMessageResponse(
                                message_id=asst.id,
                                server_msg_id=asst.server_msg_id,
                                role="assistant",
                                content=asst.content,
                                user_message=MessageItem(
                                    message_id=user_msg.id,
                                    server_msg_id=user_msg.server_msg_id,
                                    role=user_msg.role,
                                    content=user_msg.content,
                                    created_at=user_msg.created_at.isoformat(),
                                )
                                if user_msg
                                else None,
                            )
                return JSONResponse(
                    status_code=202,
                    content={"detail": "Turn is still processing"},
                )
            if turn.status == "failed":
                # Previous attempt failed; allow retry by resetting
                turn.status = "processing"
                turn.error = None
                await db.flush()
            else:
                return JSONResponse(
                    status_code=202,
                    content={"detail": "Turn is still processing"},
                )

        # Re-fetch conversation after potential rollback
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        conv = conv_result.scalars().first()
        if conv is None:
            raise HTTPException(status_code=500, detail="Conversation not found")

    # --- Process the turn (winner path) -----------------------------------
    try:
        llm_key = os.environ.get("H4CKATH0N_OPENAI_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        llm = (
            ChatOpenAI(
                model=os.environ.get("LLM_MODEL", "gpt-4o-mini"), api_key=llm_key
            )
            if llm_key
            else None
        )

        # Persist user message
        user_msg = Message(
            conversation_id=conv_id,
            role="user",
            content=body.text,
            client_msg_id=body.client_msg_id,
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        # Update turn with user_message_id
        if body.client_msg_id and turn is not None:
            turn.user_message_id = user_msg.id
            await db.flush()

        # Run new architecture engine turn (Router + specialist)
        from app.agents.engine import process_turn as engine_process_turn

        # Generate assistant server_msg_id upfront for streaming
        asst_server_msg_id = generate_server_msg_id()

        async def on_token(token: str) -> None:
            """Callback for streaming tokens to the client."""
            _publish_event(
                conv_id,
                {
                    "event": "message.chunk",
                    "data": json.dumps(
                        {
                            "server_msg_id": asst_server_msg_id,
                            "delta": token,
                        }
                    ),
                },
            )

        try:
            (
                assistant_content,
                _decision,
                debug_info,
                participation_id,
            ) = await engine_process_turn(
                db=db,
                conversation=conv,
                membership_id=membership_id,
                user_msg=user_msg,
                user_text=body.text,
                llm=llm,
                router_llm=llm,
                on_token=on_token,
            )
        except Exception:
            logger.exception("Engine process_turn failed")
            raise

        current_condition = debug_info.get("condition")
        if not isinstance(current_condition, str) or current_condition == "NONE":
            current_condition = None
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=assistant_content,
            server_msg_id=asst_server_msg_id,
            condition_source=(
                f"COND_{current_condition}" if current_condition else "SYSTEM"
            ),
            metadata_={"debug_info": debug_info},
            participation_id=participation_id,
        )
        db.add(assistant_msg)
        await db.flush()

        # Mark turn as completed
        if body.client_msg_id and turn is not None:
            turn.assistant_message_id = assistant_msg.id
            turn.status = "completed"
            await db.flush()

        # Build SSE payload
        _route_to_prompt = {
            "INTAKE": "intake_system",
            "FEEDBACK": "feedback_system",
            "COACH": "coach_system",
        }
        _prompt_name = _route_to_prompt.get(_decision.route, "coach_system")
        sse_payload = {
            "message_id": assistant_msg.id,
            "server_msg_id": assistant_msg.server_msg_id,
            "role": "assistant",
            "content": assistant_content,
            "created_at": assistant_msg.created_at.isoformat()
            if assistant_msg.created_at
            else datetime.now(UTC).isoformat(),
            "prompt_versions": prompt_version(_prompt_name),
        }

        # Persist event for durable SSE replay
        conv_event = await persist_event(
            db,
            conv_id,
            "message.final",
            sse_payload,
        )

        await db.commit()
        await db.refresh(assistant_msg)

        # Publish SSE events (use ConversationEvent.id, not Message.id)
        _publish_event(
            conv_id,
            {
                "event": "message.final",
                "id": str(conv_event.id),
                "data": json.dumps(sse_payload),
            },
        )

        return SendMessageResponse(
            message_id=assistant_msg.id,
            server_msg_id=assistant_msg.server_msg_id,
            role="assistant",
            content=assistant_content,
            user_message=MessageItem(
                message_id=user_msg.id,
                server_msg_id=user_msg.server_msg_id,
                role=user_msg.role,
                content=user_msg.content,
                created_at=user_msg.created_at.isoformat(),
            ),
            debug_info=debug_info,
        )
    except Exception:
        # Mark turn as failed on error
        if body.client_msg_id:
            try:
                await db.rollback()
                async with async_session_factory() as err_db:
                    result = await err_db.execute(
                        select(ConversationTurn).where(
                            ConversationTurn.conversation_id == conv_id,
                            ConversationTurn.client_msg_id == body.client_msg_id,
                        )
                    )
                    err_turn = result.scalars().first()
                    if err_turn and err_turn.status == "processing":
                        err_turn.status = "failed"
                        err_turn.error = "Internal processing error"
                        await err_db.commit()
            except Exception:
                logger.exception("Failed to mark turn as failed")
        raise


async def _submit_feedback_event_impl(
    body: FeedbackEventRequest,
    resolved_project_id: str,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Persist push action feedback and run an engine turn for contextual follow-up."""
    try:
        membership = await _get_membership(db, resolved_project_id, user.id)
        notif_result = await db.execute(
            select(Notification).where(
                Notification.id == body.notification_id,
                Notification.membership_id == membership.id,
            )
        )
        notification = notif_result.scalar_one_or_none()
        if notification is None:
            raise HTTPException(status_code=404, detail="Notification not found")

        conv = await _get_conversation(db, notification.membership_id)
        poll_msg_result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.metadata_["type"].as_string() == "feedback_poll",
                Message.metadata_["notification_id"].as_integer()
                == body.notification_id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        poll_msg = poll_msg_result.scalar_one_or_none()
        if poll_msg is None:
            fallback_result = await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conv.id,
                    Message.metadata_.is_not(None),
                )
                .order_by(Message.id.desc())
            )
            for candidate in fallback_result.scalars():
                metadata = candidate.metadata_ or {}
                if metadata.get("type") == "feedback_poll" and str(
                    metadata.get("notification_id")
                ) == str(body.notification_id):
                    poll_msg = candidate
                    break
        if poll_msg is None:
            raise HTTPException(status_code=404, detail="Poll message not found")

        poll_metadata = dict(poll_msg.metadata_ or {})
        if poll_metadata.get("status") == "completed":
            if notification.read_at is None:
                notification.read_at = datetime.now(UTC)
                await db.commit()
            return {"status": "already_recorded"}

        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)

        delivery_result = await db.execute(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.instance_id == notification.id,
                NotificationDelivery.channel == "push_notify",
            )
            .order_by(NotificationDelivery.id.desc())
        )
        action_title = _resolve_feedback_action_title(
            delivery_result.scalars().all(),
            body.action_id,
        )
        selected_action_id = None
        for action in poll_metadata.get("actions", []):
            if action.get("id") == body.action_id:
                selected_action_id = body.action_id
                action_title = str(action.get("title") or action_title)
                break
        if selected_action_id is None:
            raise HTTPException(status_code=400, detail="Invalid feedback action")

        poll_metadata["status"] = "completed"
        poll_metadata["selected_action_id"] = selected_action_id
        await db.execute(
            update(Message)
            .where(Message.id == poll_msg.id)
            .values({Message.metadata_: poll_metadata})
        )

        update_payload = {
            "message_id": poll_msg.id,
            "server_msg_id": poll_msg.server_msg_id,
            "metadata": poll_metadata,
        }
        update_event = await persist_event(
            db, conv.id, "message.updated", update_payload
        )

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=_format_feedback_system_message(action_title, notification.id),
            server_msg_id=generate_server_msg_id(),
            client_msg_id=(
                f"{FEEDBACK_ACTION_CLIENT_MSG_PREFIX}{notification.id}:{body.action_id}"
            ),
        )
        db.add(user_msg)
        await db.flush()

        llm_key = os.environ.get("H4CKATH0N_OPENAI_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        llm = (
            ChatOpenAI(
                model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                api_key=llm_key,
            )
            if llm_key
            else None
        )
        (
            assistant_content,
            decision,
            debug_info,
            participation_id,
        ) = await engine_process_turn(
            db=db,
            conversation=conv,
            membership_id=notification.membership_id,
            user_msg=user_msg,
            user_text=user_msg.content,
            llm=llm,
            router_llm=llm,
        )

        current_condition = debug_info.get("condition")
        if not isinstance(current_condition, str) or current_condition == "NONE":
            current_condition = None
        asst_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=assistant_content,
            server_msg_id=generate_server_msg_id(),
            condition_source=(
                f"COND_{current_condition}" if current_condition else "SYSTEM"
            ),
            metadata_={"debug_info": debug_info},
            participation_id=participation_id,
        )
        db.add(asst_msg)
        await db.flush()

        route_to_prompt = {
            "INTAKE": "intake_system",
            "FEEDBACK": "feedback_system",
            "COACH": "coach_system",
        }
        prompt_name = route_to_prompt.get(decision.route, "coach_system")
        sse_payload = {
            "message_id": asst_msg.id,
            "server_msg_id": asst_msg.server_msg_id,
            "role": "assistant",
            "content": assistant_content,
            "created_at": asst_msg.created_at.isoformat()
            if asst_msg.created_at
            else datetime.now(UTC).isoformat(),
            "prompt_versions": prompt_version(prompt_name),
        }
        conv_event = await persist_event(db, conv.id, "message.final", sse_payload)
        await db.commit()
        _publish_event(
            conv.id,
            {
                "event": "message.updated",
                "id": str(update_event.id),
                "data": json.dumps(update_payload),
            },
        )
        _publish_event(
            conv.id,
            {
                "event": "message.final",
                "id": str(conv_event.id),
                "data": json.dumps(sse_payload),
            },
        )
        return {"status": "success"}
    except IntegrityError:
        await db.rollback()
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to store feedback event")
        raise HTTPException(status_code=500, detail="Failed to store feedback event")


@router.post("/p/{project_id}/chat/events/feedback", tags=["notifications"])
async def submit_feedback_event(
    project_id: str,
    body: FeedbackEventRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    return await _submit_feedback_event_impl(
        body=body,
        resolved_project_id=project_id,
        user=user,
        db=db,
    )


# ---------------------------------------------------------------------------
# 5. SSE event stream
# ---------------------------------------------------------------------------


@router.get("/p/{project_id}/events", tags=["streaming"])
async def event_stream(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """SSE stream for real-time events on a project conversation."""
    try:
        ctx = await authenticate_sse_request(request)
    except AuthError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=401)

    membership = await _get_membership(db, project_id, ctx.user_id)
    conv = await _get_conversation(db, membership.id)

    # Parse Last-Event-ID for durable replay
    last_event_id = 0
    raw_last_id = request.headers.get("Last-Event-ID", "").strip()
    if raw_last_id:
        try:
            last_event_id = int(raw_last_id)
        except ValueError:
            pass

    # Load missed events for replay
    missed_events = await load_events_since(db, conv.id, after_id=last_event_id)

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _sse_queues[conv.id].add(queue)
    conversation_id = conv.id

    async def generate() -> Any:
        nonlocal last_event_id
        last_sent_event_id = last_event_id
        try:
            # Replay missed events first
            for evt in missed_events:
                yield {
                    "event": evt.event_type,
                    "id": str(evt.id),
                    "data": evt.payload_json,
                }
                last_sent_event_id = evt.id
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                    # Track last sent id from queue events
                    eid = event.get("id")
                    if eid:
                        try:
                            last_sent_event_id = int(eid)
                        except (ValueError, TypeError):
                            pass
                except asyncio.TimeoutError:
                    # Poll DB for events created in other processes
                    async with async_session_factory() as poll_db:
                        db_events = await load_events_since(
                            poll_db, conversation_id, after_id=last_sent_event_id
                        )
                    if db_events:
                        for evt in db_events:
                            yield {
                                "event": evt.event_type,
                                "id": str(evt.id),
                                "data": evt.payload_json,
                            }
                            last_sent_event_id = evt.id
                    else:
                        # Send keepalive comment
                        yield {"comment": "keepalive"}
        except Exception:
            logger.exception("Event stream failed for project %s", project_id)
            raise
        finally:
            _sse_queues[conversation_id].discard(queue)
            if not _sse_queues[conversation_id]:
                del _sse_queues[conversation_id]

    return sse_response(generate())


# ---------------------------------------------------------------------------
# 6. Unified Notifications (cross-project)
# ---------------------------------------------------------------------------


@router.get("/notifications", tags=["notifications"])
async def list_unified_notifications(
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
    project_id: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> UnifiedNotificationListResponse:
    """List notifications across all projects for the current user, ordered by time.

    Supports optional project_id filtering and cursor-based pagination.
    """
    import base64

    try:
        limit = min(limit, 200)

        query = (
            select(Notification, ProjectMembership.project_id, Project.display_name)
            .join(
                ProjectMembership,
                Notification.membership_id == ProjectMembership.id,
            )
            .join(Project, ProjectMembership.project_id == Project.id)
            .where(ProjectMembership.user_id == user.id)
        )

        if project_id is not None:
            query = query.where(ProjectMembership.project_id == project_id)

        if cursor is not None:
            try:
                cursor_id = int(base64.b64decode(cursor).decode())
                query = query.where(Notification.id < cursor_id)
            except Exception:
                pass

        query = query.order_by(Notification.id.desc()).limit(limit + 1)

        result = await db.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        next_cursor = None
        if has_more and rows:
            last_id = rows[-1][0].id
            next_cursor = base64.b64encode(str(last_id).encode()).decode()

        return UnifiedNotificationListResponse(
            notifications=[
                UnifiedNotificationItem(
                    id=n.id,
                    title=n.title,
                    body=n.body,
                    created_at=n.created_at.isoformat(),
                    read_at=n.read_at.isoformat() if n.read_at else None,
                    payload_json=n.payload_json or "{}",
                    project_id=pid,
                    project_display_name=display_name,
                    membership_id=n.membership_id,
                    rule_id=n.rule_id,
                    local_date=n.local_date.isoformat() if n.local_date else None,
                )
                for n, pid, display_name in rows
            ],
            next_cursor=next_cursor,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list unified notifications")
        raise HTTPException(
            status_code=500,
            detail="Failed to load notifications",
        )


@router.get("/notifications/unread-count", tags=["notifications"])
async def get_unified_unread_count(
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
    project_id: str | None = None,
) -> NotificationUnreadCountResponse:
    """Get count of unread notifications across all projects (or filtered by project)."""
    try:
        query = (
            select(func.count(Notification.id))
            .join(
                ProjectMembership,
                Notification.membership_id == ProjectMembership.id,
            )
            .where(
                ProjectMembership.user_id == user.id,
                Notification.read_at.is_(None),
            )
        )
        if project_id is not None:
            query = query.where(ProjectMembership.project_id == project_id)
        result = await db.execute(query)
        count = result.scalar() or 0
        return NotificationUnreadCountResponse(count=count)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get unified unread count")
        raise HTTPException(
            status_code=500,
            detail="Failed to load unread count",
        )


@router.post("/notifications/{notification_id}/read", tags=["notifications"])
async def mark_unified_notification_read(
    notification_id: int,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Mark a notification as read and enqueue exactly one push_dismiss delivery."""
    try:
        result = await db.execute(
            select(Notification, ProjectMembership.project_id)
            .join(
                ProjectMembership,
                Notification.membership_id == ProjectMembership.id,
            )
            .where(
                Notification.id == notification_id,
                ProjectMembership.user_id == user.id,
            )
        )
        row = result.one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Notification not found")

        notification, _project_id = row
        if not notification.read_at:
            notification.read_at = datetime.now(UTC)

            # Enqueue exactly ONE push_dismiss delivery — the worker fans out to all subscriptions
            dismiss_payload = json.dumps(
                {
                    "data": {
                        "action": "dismiss",
                        "notification_id": notification_id,
                    }
                }
            )
            delivery = NotificationDelivery(
                instance_id=notification.id,
                membership_id=notification.membership_id,
                user_id=user.id,
                channel="push_dismiss",
                payload_json=dismiss_payload,
                run_at_utc=datetime.now(UTC),
            )
            db.add(delivery)
            await db.commit()

        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to mark notification as read")
        raise HTTPException(
            status_code=500,
            detail="Failed to mark notification as read",
        )


# ---------------------------------------------------------------------------
# 7. Web Push endpoints (unified, not per-project)
# ---------------------------------------------------------------------------


@router.get("/notifications/webpush/vapid-public-key", tags=["notifications"])
async def webpush_vapid_public_key(
    user: User = require_user(),
) -> VapidPublicKeyResponse:
    """Return the VAPID public key for Web Push subscription."""
    try:
        key = config.get_vapid_public_key()
        if not key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="VAPID public key not configured",
            )
        return VapidPublicKeyResponse(public_key=key)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get VAPID public key")
        raise HTTPException(status_code=500, detail="Failed to get VAPID public key")


@router.post("/notifications/webpush/subscriptions", tags=["notifications"])
async def webpush_subscribe(
    body: PushSubscribeRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> PushSubscribeResponse:
    """Create or upsert a push subscription for the current user (user-scoped)."""
    try:
        # Check for existing subscription with same user+endpoint (regardless of revoked_at)
        existing_result = await db.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user.id,
                PushSubscription.endpoint == body.endpoint,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            existing.p256dh = body.keys.p256dh
            existing.auth = body.keys.auth
            existing.user_agent = body.user_agent or existing.user_agent
            existing.revoked_at = None
            existing.consecutive_gone_410_count = 0
            existing.last_failure_at = None
            await db.commit()
            return PushSubscribeResponse(subscription_id=existing.id)
        else:
            sub = PushSubscription(
                user_id=user.id,
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
                user_agent=body.user_agent or "",
            )
            db.add(sub)
            await db.commit()
            return PushSubscribeResponse(subscription_id=sub.id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Push subscription failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete(
    "/notifications/webpush/subscriptions/{subscription_id}", tags=["notifications"]
)
async def webpush_unsubscribe(
    subscription_id: int,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Remove a push subscription."""
    try:
        result = await db.execute(
            select(PushSubscription).where(
                PushSubscription.id == subscription_id,
                PushSubscription.user_id == user.id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found",
            )
        sub.revoked_at = datetime.now(UTC)
        await db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Push unsubscribe failed")
        raise HTTPException(status_code=500, detail="Failed to unsubscribe")


@router.get("/notifications/webpush/subscriptions", tags=["notifications"])
async def webpush_list_subscriptions(
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List active push subscriptions for the current user (debug endpoint)."""
    try:
        result = await db.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user.id,
                PushSubscription.revoked_at.is_(None),
            )
        )
        subs = result.scalars().all()
        return {
            "subscriptions": [
                {
                    "id": s.id,
                    "endpoint": s.endpoint,
                    "user_agent": s.user_agent,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in subs
            ]
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list push subscriptions")
        raise HTTPException(status_code=500, detail="Failed to list subscriptions")


@router.post("/admin/projects", tags=["admin"])
async def admin_create_project(
    body: AdminCreateProjectRequest,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    from app.id_utils import generate_project_id

    project = Project(
        id=generate_project_id(),
        display_name=body.display_name,
        study_settings_json=json.dumps(body.study_settings)
        if body.study_settings is not None
        else None,
    )
    db.add(project)
    await db.commit()
    return {"project_id": project.id}


@router.get("/admin/projects", tags=["admin"])
async def admin_list_projects(
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> AdminProjectsResponse:
    result = await db.execute(
        select(Project, func.count(ProjectMembership.id))
        .outerjoin(ProjectMembership, ProjectMembership.project_id == Project.id)
        .group_by(Project.id)
        .order_by(Project.created_at.desc())
    )
    projects = [
        AdminProjectItem(
            project_id=project.id,
            display_name=project.display_name,
            status=project.status,
            created_at=project.created_at.isoformat(),
            member_count=member_count,
        )
        for project, member_count in result.all()
    ]
    return AdminProjectsResponse(projects=projects)


@router.patch("/admin/projects/{project_id}", tags=["admin"])
async def admin_update_project(
    project_id: str,
    body: AdminProjectUpdateRequest,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Project).where(Project.id == project_id))
    if (project := result.scalar_one_or_none()) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if body.display_name is not None:
        project.display_name = body.display_name.strip()
    if body.status is not None:
        if body.status not in ("active", "paused", "ended"):
            raise HTTPException(status_code=422, detail="Invalid status")
        project.status = body.status
    await db.commit()
    return {"project_id": project.id, "display_name": project.display_name or ""}


@router.post("/admin/projects/{project_id}/invites", tags=["admin"])
async def admin_create_invites(
    project_id: str,
    body: AdminCreateInviteRequest,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> AdminCreateInvitesResponse:
    if body.count < 1:
        raise HTTPException(status_code=400, detail="count must be >= 1")
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    invite_codes: list[str] = []
    for _ in range(body.count):
        code = secrets.token_urlsafe(16)
        db.add(
            ProjectInvite(
                project_id=project_id,
                invite_code_hash=hashlib.sha256(code.encode()).hexdigest(),
                expires_at=body.expires_at,
                max_uses=body.max_uses,
                uses=0,
                label=body.label,
            )
        )
        invite_codes.append(code)
    await db.commit()
    return AdminCreateInvitesResponse(invite_codes=invite_codes)


@router.get("/admin/projects/{project_id}/participants", tags=["admin"])
async def admin_project_participants(
    project_id: str,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> AdminParticipantsResponse:
    memberships_result = await db.execute(
        select(ProjectMembership).where(ProjectMembership.project_id == project_id)
    )
    memberships = memberships_result.scalars().all()
    membership_ids = [membership.id for membership in memberships]

    latest_contact_by_membership: dict[int, ParticipantContact] = {}
    if membership_ids:
        contacts_result = await db.execute(
            select(ParticipantContact)
            .where(ParticipantContact.membership_id.in_(membership_ids))
            .order_by(
                ParticipantContact.membership_id.asc(),
                ParticipantContact.created_at.desc(),
            )
        )
        for contact in contacts_result.scalars().all():
            latest_contact_by_membership.setdefault(contact.membership_id, contact)
    profile_by_user_id: dict[str, FlowUserProfile] = {}
    user_ids = list({membership.user_id for membership in memberships})
    if user_ids:
        profiles_result = await db.execute(
            select(FlowUserProfile).where(FlowUserProfile.user_id.in_(user_ids))
        )
        profile_by_user_id = {
            profile.user_id: profile for profile in profiles_result.scalars().all()
        }

    push_stats_by_user: dict[str, dict[str, Any]] = {}
    if user_ids:
        push_result = await db.execute(
            select(PushSubscription).where(
                PushSubscription.user_id.in_(user_ids),
                PushSubscription.revoked_at.is_(None),
            )
        )
        for sub in push_result.scalars().all():
            if sub.user_id not in push_stats_by_user:
                push_stats_by_user[sub.user_id] = {
                    "count": 0,
                    "last_success_at": None,
                    "last_failure_at": None,
                }
            stats = push_stats_by_user[sub.user_id]
            stats["count"] += 1
            if sub.last_success_at and (
                stats["last_success_at"] is None
                or sub.last_success_at > stats["last_success_at"]
            ):
                stats["last_success_at"] = sub.last_success_at
            if sub.last_failure_at and (
                stats["last_failure_at"] is None
                or sub.last_failure_at > stats["last_failure_at"]
            ):
                stats["last_failure_at"] = sub.last_failure_at

    participants: list[AdminParticipantItem] = []
    for membership in memberships:
        contact = latest_contact_by_membership.get(membership.id)
        stats = push_stats_by_user.get(
            membership.user_id,
            {"count": 0, "last_success_at": None, "last_failure_at": None},
        )
        participants.append(
            AdminParticipantItem(
                user_id=membership.user_id,
                status=membership.status,
                created_at=membership.created_at.isoformat(),
                ended_at=membership.ended_at.isoformat()
                if membership.ended_at
                else None,
                email=contact.email_raw
                if contact
                else (
                    profile_by_user_id.get(membership.user_id).email_raw
                    if profile_by_user_id.get(membership.user_id)
                    else None
                ),
                push_subscription_count=stats["count"],
                last_push_success_at=stats["last_success_at"].isoformat()
                if stats["last_success_at"]
                else None,
                last_push_failure_at=stats["last_failure_at"].isoformat()
                if stats["last_failure_at"]
                else None,
            )
        )
    return AdminParticipantsResponse(participants=participants)


@router.get("/admin/projects/{project_id}/export", tags=["admin"])
async def admin_project_export(
    project_id: str,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    memberships_result = await db.execute(
        select(ProjectMembership).where(ProjectMembership.project_id == project_id)
    )
    memberships = memberships_result.scalars().all()
    membership_ids = [m.id for m in memberships]
    conversations_result = await db.execute(
        select(Conversation).where(Conversation.membership_id.in_(membership_ids))
    )
    conversations = conversations_result.scalars().all()
    conversation_ids = [c.id for c in conversations]

    contacts_result = await db.execute(
        select(ParticipantContact).where(
            ParticipantContact.membership_id.in_(membership_ids)
        )
    )
    messages_result = await db.execute(
        select(Message).where(Message.conversation_id.in_(conversation_ids))
    )
    profiles_result = await db.execute(
        select(UserProfileStore).where(
            UserProfileStore.membership_id.in_(membership_ids)
        )
    )
    memory_result = await db.execute(
        select(MemoryItem).where(MemoryItem.membership_id.in_(membership_ids))
    )
    patch_result = await db.execute(
        select(PatchAuditLog).where(PatchAuditLog.membership_id.in_(membership_ids))
    )
    push_result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id.in_([m.user_id for m in memberships])
        )
    )

    return {
        "project_id": project_id,
        "memberships": [
            {
                # Keep both keys for backward compatibility with existing exports.
                "id": m.id,
                "membership_id": m.id,
                "project_id": m.project_id,
                "user_id": m.user_id,
                "status": m.status,
                "created_at": m.created_at.isoformat(),
                "ended_at": m.ended_at.isoformat() if m.ended_at else None,
            }
            for m in memberships
        ],
        "conversations": [
            {
                "conversation_id": c.id,
                "membership_id": c.membership_id,
                "created_at": c.created_at.isoformat(),
            }
            for c in conversations
        ],
        "contacts": [
            {
                "membership_id": c.membership_id,
                "email_raw": c.email_raw,
                "created_at": c.created_at.isoformat(),
            }
            for c in contacts_result.scalars().all()
        ],
        "messages": [
            {
                "id": m.id,
                "message_id": m.id,
                "project_id": project_id,
                "conversation_id": m.conversation_id,
                "role": m.role,
                "content": m.content,
                "server_msg_id": m.server_msg_id,
                "client_msg_id": m.client_msg_id,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages_result.scalars().all()
        ],
        "user_profiles": [
            {"membership_id": p.membership_id, "profile_json": p.profile_json}
            for p in profiles_result.scalars().all()
        ],
        "memory_items": [
            {
                "membership_id": i.membership_id,
                "content": i.content,
                "source_message_ids": i.source_message_ids,
                "created_at": i.created_at.isoformat(),
            }
            for i in memory_result.scalars().all()
        ],
        "patch_audit_log": [
            {
                "membership_id": p.membership_id,
                "proposal_type": p.proposal_type,
                "source_bot": p.source_bot,
                "patch_json": p.patch_json,
                "decision": p.decision,
                "created_at": p.created_at.isoformat(),
            }
            for p in patch_result.scalars().all()
        ],
        "push_subscriptions": [
            {
                "subscription_id": s.id,
                "user_id": s.user_id,
                "endpoint": s.endpoint,
                "created_at": s.created_at.isoformat(),
                "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
                "last_success_at": s.last_success_at.isoformat()
                if s.last_success_at
                else None,
                "last_failure_at": s.last_failure_at.isoformat()
                if s.last_failure_at
                else None,
            }
            for s in push_result.scalars().all()
        ],
    }


@router.get("/admin/projects/{project_id}/push/channels", tags=["admin"])
async def admin_push_channels(
    project_id: str,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> AdminPushChannelsResponse:
    result = await db.execute(
        select(PushSubscription, ProjectMembership, User, FlowUserProfile)
        .join(ProjectMembership, PushSubscription.user_id == ProjectMembership.user_id)
        .outerjoin(User, User.id == PushSubscription.user_id)
        .outerjoin(FlowUserProfile, FlowUserProfile.user_id == PushSubscription.user_id)
        .where(
            ProjectMembership.project_id == project_id,
            PushSubscription.revoked_at.is_(None),
        )
    )
    channels = []
    for sub, membership, user, profile in result.all():
        endpoint_hint = (
            sub.endpoint[:80] + "..." if len(sub.endpoint) > 80 else sub.endpoint
        )

        channels.append(
            AdminPushChannelItem(
                subscription_id=sub.id,
                membership_id=membership.id,
                user_id=sub.user_id,
                user_email=user.email if user else None,
                display_name=profile.display_name if profile else None,
                endpoint_hint=endpoint_hint,
                created_at=sub.created_at.isoformat(),
                last_success_at=sub.last_success_at.isoformat()
                if sub.last_success_at
                else None,
                last_failure_at=sub.last_failure_at.isoformat()
                if sub.last_failure_at
                else None,
            )
        )
    return AdminPushChannelsResponse(channels=channels)


@router.post("/admin/push/test", tags=["admin"])
async def admin_push_test(
    body: AdminPushTestRequest,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> AdminPushTestResponse:
    from pywebpush import webpush

    vapid_private_key = config.get_vapid_private_key()
    vapid_claims = {"sub": config.get_vapid_sub()}

    if not vapid_private_key:
        raise HTTPException(status_code=503, detail="VAPID private key not configured")

    # Load subscriptions
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.id.in_(body.subscription_ids),
            PushSubscription.revoked_at.is_(None),
        )
    )
    subscriptions = result.scalars().all()

    payload = json.dumps(
        {
            "title": body.title,
            "body": body.body,
            "url": body.url,
            "data": {
                "url": body.url,
                "project_id": body.project_id,
            },
        }
    )

    now = datetime.now(UTC)

    async def _send_one(sub: PushSubscription) -> AdminPushTestResultItem:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    webpush,
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                ),
                timeout=10,
            )
            sub.last_success_at = now
            return AdminPushTestResultItem(subscription_id=sub.id, ok=True)
        except Exception as exc:
            sub.last_failure_at = now
            return AdminPushTestResultItem(
                subscription_id=sub.id, ok=False, error=str(exc)[:500]
            )

    results = await asyncio.gather(*[_send_one(sub) for sub in subscriptions])

    await db.commit()
    return AdminPushTestResponse(results=results)
