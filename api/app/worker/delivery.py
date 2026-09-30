"""Push delivery sending for the notification worker.

Owns Web Push fan-out and the delivery-claim processing loop. ``async_session_factory``
is imported into this module's globals so the delivery loop opens its own sessions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from pywebpush import WebPushException
from sqlalchemy import select

from app import config
from app.db import async_session_factory
from app.models import (
    NotificationDelivery,
    PushSubscription,
)
from app.services.notification_engine import claim_due_deliveries
from app.services.push_service import send_webpush

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


def _push_enabled() -> bool:
    return bool(config.get_vapid_private_key() and config.get_vapid_public_key())


async def _send_push_notifications(
    db,
    user_id: str,
    title: str,
    body: str,
    url: str,
    data: dict | None = None,
    actions: list[dict] | None = None,
) -> tuple[int, int]:
    """Send Web Push to all active subscriptions for a user.

    Returns (success_count, total_count).
    """
    if not _push_enabled():
        return 0, 0

    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.revoked_at.is_(None),
        )
    )
    subscriptions = result.scalars().all()
    if not subscriptions:
        return 0, 0

    payload_dict: dict[str, object] = {
        "title": title,
        "body": body,
        "url": url,
        "data": data or {},
    }
    if actions:
        valid_actions: list[dict[str, str]] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_id = action.get("action")
            action_title = action.get("title")
            if isinstance(action_id, str) and isinstance(action_title, str):
                valid_actions.append({"action": action_id, "title": action_title})
        if valid_actions:
            payload_dict["actions"] = valid_actions
    payload = json.dumps(payload_dict)

    success_count = 0

    async def _send_single(sub: PushSubscription) -> bool:
        try:
            await send_webpush(
                endpoint=sub.endpoint,
                p256dh=sub.p256dh,
                auth=sub.auth,
                payload=payload,
            )
            sub.last_success_at = datetime.now(UTC)
            sub.consecutive_gone_410_count = 0
            return True
        except TimeoutError:
            sub.last_failure_at = datetime.now(UTC)
            sub.consecutive_gone_410_count = 0
            logger.warning("Push send timed out for subscription %s", sub.id)
            return False
        except WebPushException as exc:
            sub.last_failure_at = datetime.now(UTC)
            resp = getattr(exc, "response", None)
            try:
                status_code = resp.status_code if resp is not None else None
            except AttributeError:
                status_code = None
            if status_code == 404:
                # 404: revoke immediately
                sub.revoked_at = datetime.now(UTC)
                sub.consecutive_gone_410_count = 0
                logger.info("Revoking subscription %s: permanent error 404", sub.id)
            elif status_code == 410:
                # 410 Gone: increment counter, revoke only at threshold
                sub.consecutive_gone_410_count += 1
                threshold = config.get_push_gone_410_threshold()
                if sub.consecutive_gone_410_count >= threshold:
                    sub.revoked_at = datetime.now(UTC)
                    logger.info(
                        "Revoking subscription %s: %d consecutive 410s (threshold=%d)",
                        sub.id,
                        sub.consecutive_gone_410_count,
                        threshold,
                    )
                else:
                    logger.info(
                        "Subscription %s: 410 count %d/%d, not revoking yet",
                        sub.id,
                        sub.consecutive_gone_410_count,
                        threshold,
                    )
            else:
                sub.consecutive_gone_410_count = 0
                logger.warning("Push send failed for subscription %s: %s", sub.id, exc)
            return False

    results = await asyncio.gather(*[_send_single(sub) for sub in subscriptions])
    success_count = sum(1 for r in results if r)
    return success_count, len(subscriptions)


async def _process_due_deliveries(worker_id: str) -> int:
    """Claim and send due notification deliveries. Returns count processed."""
    processed = 0
    async with async_session_factory() as db:
        deliveries = await claim_due_deliveries(db, worker_id)
        await db.commit()

    for delivery in deliveries:
        try:
            await _send_delivery(delivery.id, worker_id)
            processed += 1
        except Exception as exc:
            logger.error("Failed sending delivery %s: %s", delivery.id, exc)
    return processed


async def _send_delivery(delivery_id: int, worker_id: str) -> None:
    """Send a single delivery (push notification) to all user subscriptions."""
    async with async_session_factory() as db:
        d_result = await db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.locked_by == worker_id,
            )
        )
        delivery = d_result.scalar_one_or_none()
        if not delivery:
            return

        try:
            payload = json.loads(delivery.payload_json)
            user_id = delivery.user_id

            if delivery.channel == "push_notify":
                success, total = await _send_push_notifications(
                    db,
                    user_id,
                    title=payload.get("title", ""),
                    body=payload.get("body", ""),
                    url=payload.get("url", ""),
                    data=payload.get("data"),
                    actions=payload.get("actions"),
                )
            elif delivery.channel == "push_dismiss":
                success, total = await _send_push_notifications(
                    db,
                    user_id,
                    title="",
                    body="",
                    url="",
                    data=payload.get("data"),
                    actions=payload.get("actions"),
                )
            else:
                success, total = 0, 0

            # Mark sent if at least one push succeeded, or if there are no subscriptions
            if success > 0 or total == 0:
                delivery.status = "sent"
            else:
                # All sends failed — retry with backoff
                delivery.attempts += 1
                if delivery.attempts >= MAX_ATTEMPTS:
                    delivery.status = "failed"
                else:
                    backoff_minutes = 2 ** min(delivery.attempts, 8)
                    delivery.run_at_utc = datetime.now(UTC) + timedelta(
                        minutes=backoff_minutes
                    )
                delivery.locked_by = None
                delivery.claimed_at = None
                delivery.locked_until = None

            await db.commit()

        except Exception as exc:
            await db.rollback()
            d_result = await db.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.id == delivery_id
                )
            )
            delivery = d_result.scalar_one_or_none()
            if delivery:
                delivery.attempts += 1
                delivery.last_error = str(exc)
                delivery.locked_by = None
                delivery.claimed_at = None
                delivery.locked_until = None
                if delivery.attempts >= MAX_ATTEMPTS:
                    delivery.status = "failed"
                else:
                    backoff_minutes = 2 ** min(delivery.attempts, 8)
                    delivery.run_at_utc = datetime.now(UTC) + timedelta(
                        minutes=backoff_minutes
                    )
                await db.commit()
            raise
