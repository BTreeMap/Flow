"""API routes for the HCI research platform."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.db import get_db
from app.id_utils import generate_server_msg_id
from app.models import (
    Conversation,
    Message,
    ParticipantContact,
    Project,
    ProjectInvite,
    ProjectMembership,
    PushSubscription,
)
from h4ckath0n.auth import require_user
from h4ckath0n.auth.models import User
from h4ckath0n.realtime import AuthError, authenticate_sse_request, sse_response
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory SSE fan-out queues: conversation_id -> set of asyncio.Queue
# ---------------------------------------------------------------------------
_sse_queues: dict[int, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)


def _publish_event(conversation_id: int, event: dict[str, Any]) -> None:
    """Push an SSE event to all listeners on a conversation."""
    for q in _sse_queues.get(conversation_id, set()):
        q.put_nowait(event)


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
    membership = result.scalar_one_or_none()
    if membership is None:
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
    conv = result.scalar_one_or_none()
    if conv is None:
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


class DashboardResponse(BaseModel):
    memberships: list[MembershipInfo]


class ClaimRequest(BaseModel):
    invite_code: str
    email: str


class ClaimResponse(BaseModel):
    project_id: str
    membership_status: str
    conversation_id: int


class MeResponse(BaseModel):
    membership_status: str
    conversation_id: int | None = None
    email: str | None = None


class SendMessageRequest(BaseModel):
    text: str
    client_msg_id: str | None = None


class SendMessageResponse(BaseModel):
    message_id: int
    server_msg_id: str
    role: str
    content: str


class MessageItem(BaseModel):
    message_id: int
    server_msg_id: str
    role: str
    content: str
    created_at: str


class MessageListResponse(BaseModel):
    messages: list[MessageItem]


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: dict[str, str]
    user_agent: str | None = None


class PushSubscribeResponse(BaseModel):
    subscription_id: int


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class PushUnsubscribeResponse(BaseModel):
    ok: bool


class VapidPublicKeyResponse(BaseModel):
    public_key: str


# ---------------------------------------------------------------------------
# 1. Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", tags=["dashboard"])
async def dashboard(
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Return all memberships with project info for the current user."""
    result = await db.execute(
        select(ProjectMembership).where(ProjectMembership.user_id == user.id)
    )
    memberships = result.scalars().all()

    items: list[MembershipInfo] = []
    for m in memberships:
        # Fetch project display name
        proj_result = await db.execute(
            select(Project).where(Project.id == m.project_id)
        )
        project = proj_result.scalar_one_or_none()

        # Fetch conversation id
        conv_result = await db.execute(
            select(Conversation).where(Conversation.membership_id == m.id)
        )
        conv = conv_result.scalar_one_or_none()

        items.append(
            MembershipInfo(
                project_id=m.project_id,
                display_name=project.display_name if project else None,
                status=m.status,
                conversation_id=conv.id if conv else None,
            )
        )

    return DashboardResponse(memberships=items)


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
    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Hash the invite code and look up a matching, unexpired, unconsumed invite
    code_hash = hashlib.sha256(body.invite_code.encode()).hexdigest()
    now = datetime.now(UTC)

    invite_result = await db.execute(
        select(ProjectInvite).where(
            ProjectInvite.project_id == project_id,
            ProjectInvite.invite_code_hash == code_hash,
            ProjectInvite.expires_at > now,
            ProjectInvite.consumed_at.is_(None),
        )
    )
    invite = invite_result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invite code",
        )

    # Check for existing membership
    existing_result = await db.execute(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user.id,
        )
    )
    membership = existing_result.scalar_one_or_none()

    if membership is None:
        membership = ProjectMembership(
            project_id=project_id,
            user_id=user.id,
            status="active",
        )
        db.add(membership)
        await db.flush()

        # Mark invite as consumed
        invite.consumed_at = now
        await db.flush()

    # Store email contact metadata
    if body.email:
        contact = ParticipantContact(
            membership_id=membership.id,
            email_raw=body.email,
            email_normalized=body.email.strip().lower() if body.email else None,
        )
        db.add(contact)
        await db.flush()

    # Create conversation if absent
    conv_result = await db.execute(
        select(Conversation).where(Conversation.membership_id == membership.id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv is None:
        conv = Conversation(membership_id=membership.id)
        db.add(conv)
        await db.flush()

    await db.commit()
    await db.refresh(membership)
    await db.refresh(conv)

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

    return MeResponse(
        membership_status=membership.status,
        conversation_id=conv.id if conv else None,
        email=contact.email_raw if contact else None,
    )


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
    membership = await _get_membership(db, project_id, user.id)
    conv = await _get_conversation(db, membership.id)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id.asc())
    )
    items = [
        MessageItem(
            message_id=msg.id,
            server_msg_id=msg.server_msg_id,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at.isoformat(),
        )
        for msg in result.scalars().all()
    ]
    return MessageListResponse(messages=items)


@router.post("/p/{project_id}/messages", tags=["messaging"])
async def send_message(
    project_id: str,
    body: SendMessageRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> SendMessageResponse:
    """Persist user message, run engine turn, persist assistant reply."""
    membership = await _get_membership(db, project_id, user.id)
    conv = await _get_conversation(db, membership.id)
    llm_key = os.environ.get("H4CKATH0N_OPENAI_API_KEY") or os.environ.get(
        "OPENAI_API_KEY"
    )
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=llm_key) if llm_key else None

    # Persist user message
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=body.text,
        client_msg_id=body.client_msg_id,
        server_msg_id=generate_server_msg_id(),
    )
    db.add(user_msg)
    await db.flush()

    # Run new architecture engine turn (Router + specialist)
    from app.agents.engine import process_turn as engine_process_turn

    assistant_content, _decision = await engine_process_turn(
        db=db,
        conversation=conv,
        membership_id=membership.id,
        user_msg=user_msg,
        user_text=body.text,
        llm=llm,
        router_llm=llm,
    )

    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=assistant_content,
        server_msg_id=generate_server_msg_id(),
    )
    db.add(assistant_msg)
    await db.flush()

    await db.commit()
    await db.refresh(assistant_msg)

    # Publish SSE events
    _publish_event(
        conv.id,
        {
            "event": "message.final",
            "id": str(assistant_msg.id),
            "data": json.dumps(
                {
                    "message_id": assistant_msg.id,
                    "server_msg_id": assistant_msg.server_msg_id,
                    "role": "assistant",
                    "content": assistant_content,
                    "created_at": assistant_msg.created_at.isoformat()
                    if assistant_msg.created_at
                    else datetime.now(UTC).isoformat(),
                }
            ),
        },
    )

    return SendMessageResponse(
        message_id=assistant_msg.id,
        server_msg_id=assistant_msg.server_msg_id,
        role="assistant",
        content=assistant_content,
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

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _sse_queues[conv.id].add(queue)

    async def generate() -> Any:
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield {"comment": "keepalive"}
        finally:
            _sse_queues[conv.id].discard(queue)
            if not _sse_queues[conv.id]:
                del _sse_queues[conv.id]

    return sse_response(generate())


# ---------------------------------------------------------------------------
# 6. VAPID public key
# ---------------------------------------------------------------------------


@router.get("/p/{project_id}/push/vapid-public-key", tags=["push"])
async def vapid_public_key(
    project_id: str,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> VapidPublicKeyResponse:
    """Return the VAPID public key from environment."""
    # Verify membership exists
    await _get_membership(db, project_id, user.id)

    key = os.environ.get("VAPID_PUBLIC_KEY", "")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID public key not configured",
        )
    return VapidPublicKeyResponse(public_key=key)


# ---------------------------------------------------------------------------
# 7. Push subscribe
# ---------------------------------------------------------------------------


@router.post("/p/{project_id}/push/subscribe", tags=["push"])
async def push_subscribe(
    project_id: str,
    body: PushSubscribeRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> PushSubscribeResponse:
    """Store a push subscription for the current membership."""
    membership = await _get_membership(db, project_id, user.id)

    # Check for existing subscription with same endpoint
    existing_result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.revoked_at.is_(None),
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing is not None:
        # Update keys in case they changed
        existing.p256dh = body.keys.get("p256dh", existing.p256dh)
        existing.auth = body.keys.get("auth", existing.auth)
        existing.user_agent = body.user_agent or existing.user_agent
        await db.commit()
        await db.refresh(existing)
        return PushSubscribeResponse(subscription_id=existing.id)

    sub = PushSubscription(
        membership_id=membership.id,
        endpoint=body.endpoint,
        p256dh=body.keys.get("p256dh", ""),
        auth=body.keys.get("auth", ""),
        user_agent=body.user_agent or "",
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    return PushSubscribeResponse(subscription_id=sub.id)


# ---------------------------------------------------------------------------
# 8. Push unsubscribe
# ---------------------------------------------------------------------------


@router.post("/p/{project_id}/push/unsubscribe", tags=["push"])
async def push_unsubscribe(
    project_id: str,
    body: PushUnsubscribeRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> PushUnsubscribeResponse:
    """Revoke a push subscription by endpoint."""
    membership = await _get_membership(db, project_id, user.id)

    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.membership_id == membership.id,
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.revoked_at.is_(None),
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

    return PushUnsubscribeResponse(ok=True)
