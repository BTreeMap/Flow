"""Invite claim, project membership, and profile routes."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from h4ckath0n.auth import require_user
from h4ckath0n.auth.models import User
from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.config import get_llm_model, get_openai_api_key
from app.db import get_db
from app.errors import AppError, Fault
from app.id_utils import generate_server_msg_id
from app.llm import make_chat_llm
from app.models import (
    Conversation,
    FlowUserProfile,
    Message,
    ParticipantContact,
    Project,
    ProjectInvite,
    ProjectMembership,
)
from app.prompt_loader import prompt_version
from app.routes._shared import (
    _get_membership,
)
from app.routes.schemas import (
    ClaimRequest,
    ClaimResponse,
    MeResponse,
    ProfileUpdateRequest,
)
from app.schemas.patches import UserProfileData
from app.services.event_service import persist_event
from app.services.profile_service import load_user_profile, save_user_profile

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/p/{project_id}/activate/claim", tags=["activation"], response_model=ClaimResponse
)
async def claim_invite(
    project_id: str,
    body: ClaimRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> ClaimResponse | JSONResponse:
    """Validate invite code, create membership and conversation."""
    try:
        return await _claim_invite_impl(project_id, body, user, db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Claim invite failed")
        raise AppError(Fault.INTERNAL, "Internal server error") from exc


async def _claim_invite_impl(
    project_id: str,
    body: ClaimRequest,
    user: User,
    db: AsyncSession,
) -> ClaimResponse | JSONResponse:
    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise AppError(Fault.NOT_FOUND, "Project not found")

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
        raise AppError(Fault.FORBIDDEN, "Membership ended")

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
            raise AppError(Fault.MALFORMED, "Invalid or expired invite code")

        expires_at = invite.expires_at
        compare_now = now if expires_at.tzinfo else now.replace(tzinfo=None)
        if invite.revoked_at is not None or expires_at <= compare_now:
            raise AppError(Fault.MALFORMED, "Invalid or expired invite code")

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
            if cast("CursorResult[Any]", consume_result).rowcount != 1:
                await db.rollback()
                raise AppError(Fault.MALFORMED, "Invalid or expired invite code")

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
            llm_key = get_openai_api_key()
            if llm_key:
                llm = make_chat_llm(model=get_llm_model(), api_key=llm_key)

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

                current_condition = (
                    debug_info.condition if debug_info.condition != "NONE" else None
                )
                # Persist assistant message
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=assistant_content,
                    server_msg_id=generate_server_msg_id(),
                    condition_source=(
                        f"COND_{current_condition}" if current_condition else "SYSTEM"
                    ),
                    metadata_={"debug_info": debug_info.model_dump()},
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
    except Exception as exc:
        logger.exception("Failed to load project membership info")
        raise AppError(
            Fault.INTERNAL, "Failed to load project membership info"
        ) from exc


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
    except Exception as exc:
        logger.exception("Failed to load profile")
        raise AppError(Fault.INTERNAL, "Failed to load profile") from exc


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
    except Exception as exc:
        logger.exception("Failed to update profile")
        raise AppError(Fault.INTERNAL, "Failed to update profile") from exc
