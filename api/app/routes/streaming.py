"""Server-sent events stream route."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends
from h4ckath0n.realtime import (
    AuthError,
    authenticate_sse_request,
    sse_response,
)
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.db import async_session_factory, get_db
from app.routes._shared import (
    SSEEvent,
    _get_conversation,
    _get_membership,
    _sse_queues,
)
from app.services.event_service import load_events_since

logger = logging.getLogger(__name__)

router = APIRouter()


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
        with contextlib.suppress(ValueError):
            last_event_id = int(raw_last_id)

    # Load missed events for replay
    missed_events = await load_events_since(db, conv.id, after_id=last_event_id)

    queue: asyncio.Queue[SSEEvent] = asyncio.Queue()
    _sse_queues[conv.id].add(queue)
    conversation_id = conv.id

    async def generate() -> AsyncGenerator[dict[str, Any], None]:
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
                    yield dict(event)
                    # Track last sent id from queue events
                    eid = event.get("id")
                    if eid:
                        with contextlib.suppress(ValueError, TypeError):
                            last_sent_event_id = int(eid)
                except TimeoutError:
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
