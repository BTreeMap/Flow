"""Shared state, constants, and helpers used across route submodules."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TypedDict

from h4ckath0n.realtime import (
    AuthContext,
    AuthError,
    authenticate_http_request,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.errors import AppError, Fault
from app.models import Conversation, ProjectMembership

logger = logging.getLogger(__name__)

MESSAGE_PREVIEW_MAX_LENGTH = 120
FEEDBACK_ACTION_CLIENT_MSG_PREFIX = "feedback_action:"


class SSEEvent(TypedDict, total=False):
    """Wire-format payload for a server-sent event.

    Mirrors the fields consumed by ``sse_response``. ``event``/``id``/``data``
    describe a real event; ``comment`` is used for keepalive pings. Every field
    is optional because different event kinds populate different subsets.
    """

    event: str
    id: str
    data: str
    comment: str


_sse_queues: dict[int, set[asyncio.Queue[SSEEvent]]] = defaultdict(set)


def _publish_event(conversation_id: int, event: SSEEvent) -> None:
    """Push an SSE event to all listeners on a conversation."""
    for q in _sse_queues.get(conversation_id, set()):
        q.put_nowait(event)


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
        raise AppError(Fault.NOT_FOUND, "Membership not found")
    return membership


async def _get_conversation(db: AsyncSession, membership_id: int) -> Conversation:
    """Return conversation for a membership or raise 404."""
    result = await db.execute(
        select(Conversation).where(Conversation.membership_id == membership_id)
    )
    if (conv := result.scalar_one_or_none()) is None:
        raise AppError(Fault.NOT_FOUND, "Conversation not found")
    return conv


async def _require_auth_context(request: Request) -> AuthContext:
    try:
        return await authenticate_http_request(request)
    except AuthError as exc:
        raise AppError(Fault.UNAUTHENTICATED, exc.detail) from None
