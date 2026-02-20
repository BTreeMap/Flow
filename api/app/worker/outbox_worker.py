from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta

from pywebpush import WebPushException, webpush
from sqlalchemy import Select, delete, select

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


async def _claim_due_events(limit: int = 20) -> list[OutboxEvent]:
    async with async_session_factory() as db:
        now = datetime.now(UTC)
        stmt: Select[tuple[OutboxEvent]] = (
            select(OutboxEvent)
            .where(OutboxEvent.available_at <= now)
            .order_by(OutboxEvent.available_at.asc(), OutboxEvent.id.asc())
            .limit(limit)
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        result = await db.execute(stmt)
        events = list(result.scalars().all())
        return events


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
    for sub in subscriptions:
        payload = json.dumps(
            {
                "title": "Flow",
                "body": SCHEDULED_PROMPT_TEXT,
                "url": f"/p/{project_id}/chat",
            }
        )
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY"),
                vapid_claims={"sub": "mailto:research@flow.local"},
            )
            sub.last_success_at = datetime.now(UTC)
        except WebPushException as exc:
            sub.last_failure_at = datetime.now(UTC)
            logger.warning("Push send failed for subscription %s: %s", sub.id, exc)


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

    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=SCHEDULED_PROMPT_TEXT,
            server_msg_id=generate_server_msg_id(),
        )
    )

    await _send_push_for_membership(db, membership.id, membership.project_id)

    profile = await load_user_profile(db, membership.id)
    await enqueue_next_scheduled_prompt(
        db,
        membership=membership,
        preferred_time=profile.preferred_time,
    )


async def _process_event(event: OutboxEvent) -> None:
    async with async_session_factory() as db:
        row_result = await db.execute(
            select(OutboxEvent).where(OutboxEvent.id == event.id)
        )
        row = row_result.scalar_one_or_none()
        if row is None:
            return
        try:
            if row.type == "scheduled_prompt":
                await _handle_scheduled_prompt(db, row)
            else:
                raise ValueError(f"Unsupported event type: {row.type}")
            await db.execute(delete(OutboxEvent).where(OutboxEvent.id == row.id))
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            row.attempts += 1
            row.last_error = str(exc)
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
    while True:
        events = await _claim_due_events()
        if not events:
            await asyncio.sleep(poll_seconds)
            continue
        for event in events:
            await _process_event(event)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
