from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta

from pywebpush import WebPushException, webpush
from sqlalchemy import Select, delete, or_, select, update

from app.db import async_session_factory
from app.id_utils import generate_server_msg_id
from app.models import (
    Conversation,
    Message,
    OutboxEvent,
    ProjectMembership,
    PushSubscription,
)
from app.services.outbox_service import enqueue_next_scheduled_prompt
from app.services.profile_service import load_user_profile

logger = logging.getLogger(__name__)

SCHEDULED_PROMPT_TEXT = "Daily check-in: how did it go today?"
MAX_ATTEMPTS = 5
FAILED_EVENT_POSTPONE_DAYS = 3650
LOCK_DURATION_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 10


def _make_worker_id() -> str:
    base = os.environ.get("FLOW_WORKER_ID") or socket.gethostname()
    return f"{base}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


async def _claim_due_events(worker_id: str, limit: int = 20) -> list[OutboxEvent]:
    async with async_session_factory() as db:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=LOCK_DURATION_SECONDS)
        id_query: Select[tuple[int]] = (
            select(OutboxEvent.id)
            .where(
                OutboxEvent.available_at <= now,
                or_(
                    OutboxEvent.locked_until.is_(None),
                    OutboxEvent.locked_until < now,
                ),
            )
            .order_by(OutboxEvent.available_at.asc(), OutboxEvent.id.asc())
            .limit(limit)
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            id_query = id_query.with_for_update(skip_locked=True)

        result = await db.execute(id_query)
        ids = [event_id for (event_id,) in result.all()]
        if not ids:
            return []

        await db.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.id.in_(ids),
                or_(
                    OutboxEvent.locked_until.is_(None),
                    OutboxEvent.locked_until < now,
                ),
            )
            .values(locked_by=worker_id, claimed_at=now, locked_until=locked_until)
        )
        await db.commit()

        claimed_result = await db.execute(
            select(OutboxEvent).where(
                OutboxEvent.id.in_(ids),
                OutboxEvent.locked_by == worker_id,
            )
        )
        return list(claimed_result.scalars().all())


def _push_enabled() -> bool:
    return bool(
        os.environ.get("VAPID_PRIVATE_KEY") and os.environ.get("VAPID_PUBLIC_KEY")
    )


async def _send_push_for_membership(
    db,
    membership_id: int,
    project_id: str,
) -> None:
    if not _push_enabled():
        return
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.membership_id == membership_id,
            PushSubscription.revoked_at.is_(None),
        )
    )
    subscriptions = result.scalars().all()
    had_timeout = False
    for sub in subscriptions:
        payload = json.dumps(
            {
                "title": "Flow",
                "body": SCHEDULED_PROMPT_TEXT,
                "url": f"/p/{project_id}/chat",
            }
        )
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    webpush,
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY"),
                    vapid_claims={"sub": "mailto:research@flow.local"},
                ),
                timeout=PUSH_TIMEOUT_SECONDS,
            )
            sub.last_success_at = datetime.now(UTC)
        except asyncio.TimeoutError:
            had_timeout = True
            sub.last_failure_at = datetime.now(UTC)
            logger.warning("Push send timed out for subscription %s", sub.id)
        except WebPushException as exc:
            sub.last_failure_at = datetime.now(UTC)
            logger.warning("Push send failed for subscription %s: %s", sub.id, exc)
    if had_timeout:
        raise TimeoutError("Push send timed out")


async def _handle_scheduled_prompt(db, event: OutboxEvent) -> None:
    membership_result = await db.execute(
        select(ProjectMembership).where(ProjectMembership.id == event.membership_id)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        return
    conversation_result = await db.execute(
        select(Conversation).where(Conversation.membership_id == membership.id)
    )
    conversation = conversation_result.scalar_one_or_none()
    if conversation is None:
        return

    existing_message_result = await db.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.role == "assistant",
            Message.client_msg_id == event.dedupe_key,
        )
    )
    if existing_message_result.scalar_one_or_none() is None:
        db.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=SCHEDULED_PROMPT_TEXT,
                server_msg_id=generate_server_msg_id(),
                client_msg_id=event.dedupe_key,
            )
        )

    profile = await load_user_profile(db, membership.id)
    await enqueue_next_scheduled_prompt(
        db,
        membership=membership,
        preferred_time=profile.preferred_time,
    )
    await db.flush()
    await db.commit()

    await _send_push_for_membership(db, membership.id, membership.project_id)
    await db.flush()


async def _process_event(event: OutboxEvent, worker_id: str) -> None:
    async with async_session_factory() as db:
        row_result = await db.execute(
            select(OutboxEvent).where(
                OutboxEvent.id == event.id,
                OutboxEvent.locked_by == worker_id,
            )
        )
        row = row_result.scalar_one_or_none()
        if row is None:
            return
        try:
            if row.type == "scheduled_prompt":
                await _handle_scheduled_prompt(db, row)
            else:
                raise ValueError(f"Unsupported event type: {row.type}")
            await db.execute(
                delete(OutboxEvent).where(
                    OutboxEvent.id == row.id,
                    OutboxEvent.locked_by == worker_id,
                )
            )
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            # Reset failed transaction state before reloading the persisted row.
            await db.rollback()
            row_result = await db.execute(
                select(OutboxEvent).where(OutboxEvent.id == event.id)
            )
            row = row_result.scalar_one_or_none()
            if row is None:
                return
            row.attempts += 1
            row.last_error = str(exc)
            row.locked_by = None
            row.claimed_at = None
            row.locked_until = None
            if row.attempts >= MAX_ATTEMPTS:
                row.available_at = datetime.now(UTC) + timedelta(
                    days=FAILED_EVENT_POSTPONE_DAYS
                )
            else:
                row.available_at = datetime.now(UTC) + timedelta(
                    minutes=2 ** min(row.attempts, 8)
                )
            await db.commit()


async def run_worker_loop(poll_seconds: int = 5) -> None:
    worker_id = _make_worker_id()
    while True:
        events = await _claim_due_events(worker_id=worker_id)
        if not events:
            await asyncio.sleep(poll_seconds)
            continue
        for event in events:
            await _process_event(event, worker_id=worker_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
