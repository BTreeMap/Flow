"""Service for persisting and replaying conversation events."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConversationEvent


async def persist_event(
    db: AsyncSession,
    conversation_id: int,
    event_type: str,
    payload: dict[str, Any],
) -> ConversationEvent:
    """Persist a conversation event and return it."""
    event = ConversationEvent(
        conversation_id=conversation_id,
        event_type=event_type,
        payload_json=json.dumps(payload),
    )
    db.add(event)
    await db.flush()
    return event


async def load_events_since(
    db: AsyncSession,
    conversation_id: int,
    after_id: int = 0,
    limit: int = 100,
) -> list[ConversationEvent]:
    """Load events after a given event ID for replay."""
    result = await db.execute(
        select(ConversationEvent)
        .where(
            ConversationEvent.conversation_id == conversation_id,
            ConversationEvent.id > after_id,
        )
        .order_by(ConversationEvent.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())
