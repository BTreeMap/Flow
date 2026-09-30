"""Admin project, invite, participant, and export routes."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends
from h4ckath0n.auth.dependencies import require_admin
from h4ckath0n.auth.models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import AppError, Fault
from app.models import (
    Conversation,
    FlowUserProfile,
    MemoryItem,
    Message,
    ParticipantContact,
    PatchAuditLog,
    Project,
    ProjectInvite,
    ProjectMembership,
    PushSubscription,
    UserProfileStore,
)
from app.routes.schemas import (
    AdminCreateInviteRequest,
    AdminCreateInvitesResponse,
    AdminCreateProjectRequest,
    AdminParticipantItem,
    AdminParticipantsResponse,
    AdminProjectItem,
    AdminProjectsResponse,
    AdminProjectUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _json_safe(value: Any) -> Any:
    """Coerce an arbitrary value into JSON-native types for safe JSONB storage.

    The ``messages.metadata`` column is JSONB on Postgres and is serialized with
    a strict ``json.dumps`` (no ``default=``). Engine debug payloads can contain
    non-native types (datetimes, tuples, etc.) which would otherwise raise at
    flush time and abort the whole turn. Round-tripping through ``default=str``
    guarantees the value is storable.
    """
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        logger.warning("Could not coerce metadata to JSON-safe form; dropping it")
        return None


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
        raise AppError(Fault.NOT_FOUND, "Project not found")
    if body.display_name is not None:
        project.display_name = body.display_name.strip()
    if body.status is not None:
        if body.status not in ("active", "paused", "ended"):
            raise AppError(Fault.UNPROCESSABLE, "Invalid status")
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
        raise AppError(Fault.MALFORMED, "count must be >= 1")
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if project_result.scalar_one_or_none() is None:
        raise AppError(Fault.NOT_FOUND, "Project not found")

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
        member_profile = profile_by_user_id.get(membership.user_id)
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
                else (member_profile.email_raw if member_profile else None),
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
