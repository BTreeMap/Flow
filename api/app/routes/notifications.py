"""Unified notifications and Web Push subscription routes."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from h4ckath0n.auth import require_user
from h4ckath0n.auth.models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.db import get_db
from app.errors import AppError, Fault
from app.models import (
    Notification,
    NotificationDelivery,
    Project,
    ProjectMembership,
    PushSubscription,
)
from app.routes.schemas import (
    NotificationUnreadCountResponse,
    PushSubscribeRequest,
    PushSubscribeResponse,
    UnifiedNotificationItem,
    UnifiedNotificationListResponse,
    VapidPublicKeyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
    import binascii

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
            except (ValueError, binascii.Error):
                logger.warning("Ignoring malformed notification cursor")

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
    except Exception as exc:
        logger.exception("Failed to list unified notifications")
        raise AppError(Fault.INTERNAL, "Failed to load notifications") from exc


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
    except Exception as exc:
        logger.exception("Failed to get unified unread count")
        raise AppError(Fault.INTERNAL, "Failed to load unread count") from exc


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
            raise AppError(Fault.NOT_FOUND, "Notification not found")

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
    except Exception as exc:
        logger.exception("Failed to mark notification as read")
        raise AppError(Fault.INTERNAL, "Failed to mark notification as read") from exc


@router.get("/notifications/webpush/vapid-public-key", tags=["notifications"])
async def webpush_vapid_public_key(
    user: User = require_user(),
) -> VapidPublicKeyResponse:
    """Return the VAPID public key for Web Push subscription."""
    try:
        key = config.get_vapid_public_key()
        if not key:
            raise AppError(Fault.INTERNAL, "VAPID public key not configured")
        return VapidPublicKeyResponse(public_key=key)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get VAPID public key")
        raise AppError(Fault.INTERNAL, "Failed to get VAPID public key") from exc


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
    except Exception as exc:
        logger.exception("Push subscription failed")
        raise AppError(Fault.INTERNAL, "Internal server error") from exc


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
            raise AppError(Fault.NOT_FOUND, "Subscription not found")
        sub.revoked_at = datetime.now(UTC)
        await db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Push unsubscribe failed")
        raise AppError(Fault.INTERNAL, "Failed to unsubscribe") from exc


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
    except Exception as exc:
        logger.exception("Failed to list push subscriptions")
        raise AppError(Fault.INTERNAL, "Failed to list subscriptions") from exc
