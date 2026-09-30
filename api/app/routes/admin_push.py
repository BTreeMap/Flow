"""Admin Web Push channel inspection and test routes."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from h4ckath0n.auth.dependencies import require_admin
from h4ckath0n.auth.models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.db import get_db
from app.errors import AppError, Fault
from app.models import (
    FlowUserProfile,
    ProjectMembership,
    PushSubscription,
)
from app.routes.schemas import (
    AdminPushChannelItem,
    AdminPushChannelsResponse,
    AdminPushTestRequest,
    AdminPushTestResponse,
    AdminPushTestResultItem,
)
from app.services.push_service import send_webpush

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/admin/projects/{project_id}/push/channels", tags=["admin"])
async def admin_push_channels(
    project_id: str,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> AdminPushChannelsResponse:
    result = await db.execute(
        select(PushSubscription, ProjectMembership, User, FlowUserProfile)
        .join(ProjectMembership, PushSubscription.user_id == ProjectMembership.user_id)
        .outerjoin(User, User.id == PushSubscription.user_id)
        .outerjoin(FlowUserProfile, FlowUserProfile.user_id == PushSubscription.user_id)
        .where(
            ProjectMembership.project_id == project_id,
            PushSubscription.revoked_at.is_(None),
        )
    )
    channels = []
    for sub, membership, user, profile in result.all():
        endpoint_hint = (
            sub.endpoint[:80] + "..." if len(sub.endpoint) > 80 else sub.endpoint
        )

        channels.append(
            AdminPushChannelItem(
                subscription_id=sub.id,
                membership_id=membership.id,
                user_id=sub.user_id,
                user_email=user.email if user else None,
                display_name=profile.display_name if profile else None,
                endpoint_hint=endpoint_hint,
                created_at=sub.created_at.isoformat(),
                last_success_at=sub.last_success_at.isoformat()
                if sub.last_success_at
                else None,
                last_failure_at=sub.last_failure_at.isoformat()
                if sub.last_failure_at
                else None,
            )
        )
    return AdminPushChannelsResponse(channels=channels)


@router.post("/admin/push/test", tags=["admin"])
async def admin_push_test(
    body: AdminPushTestRequest,
    _admin_user: User = require_admin(),
    db: AsyncSession = Depends(get_db),
) -> AdminPushTestResponse:
    vapid_private_key = config.get_vapid_private_key()

    if not vapid_private_key:
        raise AppError(Fault.INTERNAL, "VAPID private key not configured")

    # Load subscriptions
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.id.in_(body.subscription_ids),
            PushSubscription.revoked_at.is_(None),
        )
    )
    subscriptions = result.scalars().all()

    payload = json.dumps(
        {
            "title": body.title,
            "body": body.body,
            "url": body.url,
            "data": {
                "url": body.url,
                "project_id": body.project_id,
            },
        }
    )

    now = datetime.now(UTC)

    async def _send_one(sub: PushSubscription) -> AdminPushTestResultItem:
        try:
            await send_webpush(
                endpoint=sub.endpoint,
                p256dh=sub.p256dh,
                auth=sub.auth,
                payload=payload,
            )
            sub.last_success_at = now
            return AdminPushTestResultItem(subscription_id=sub.id, ok=True)
        except Exception as exc:
            sub.last_failure_at = now
            return AdminPushTestResultItem(
                subscription_id=sub.id, ok=False, error=str(exc)[:500]
            )

    results = await asyncio.gather(*[_send_one(sub) for sub in subscriptions])

    await db.commit()
    return AdminPushTestResponse(results=results)
