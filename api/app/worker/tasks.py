"""Scheduled-task item handlers for the notification worker.

These helpers operate on a caller-provided ``db`` session (opened by the
orchestrator's ``_process_scheduled_tasks`` via the patchable
``async_session_factory``), so they do not open sessions of their own.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.id_utils import generate_server_msg_id
from app.models import (
    Conversation,
    Message,
    Notification,
    NotificationDelivery,
    ProjectMembership,
    ScheduledTask,
)
from app.services.event_service import persist_event
from app.worker.nudge import _to_feedback_poll_actions

logger = logging.getLogger(__name__)


async def _create_feedback_request(db, task: ScheduledTask, now: datetime) -> None:
    """Create the message, notification, and push delivery for a feedback request."""
    payload = json.loads(task.payload_json)
    membership_result = await db.execute(
        select(ProjectMembership).where(ProjectMembership.id == task.membership_id)
    )
    membership = membership_result.scalar_one()

    conv_result = await db.execute(
        select(Conversation).where(Conversation.membership_id == task.membership_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(membership_id=task.membership_id)
        db.add(conversation)
        await db.flush()

    content = payload.get("text", "Feedback Request")
    server_msg_id = generate_server_msg_id()

    notification = Notification(
        membership_id=task.membership_id,
        title="Feedback Request",
        body=content,
        payload_json=json.dumps(
            {
                "server_msg_id": server_msg_id,
                "project_id": membership.project_id,
                "parent_notification_id": task.parent_instance_id,
            }
        ),
        local_date=now.date(),
        dedupe_key=f"feedback:{task.id}",
    )
    db.add(notification)
    await db.flush()

    message_metadata = {
        "type": "feedback_poll",
        "notification_id": notification.id,
        "status": "pending",
        "actions": _to_feedback_poll_actions(payload.get("actions")),
    }
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        server_msg_id=server_msg_id,
        client_msg_id=f"feedback:{task.id}",
        metadata_=message_metadata,
    )
    db.add(message)
    await db.flush()
    await persist_event(
        db,
        conversation.id,
        "message.final",
        {
            "message_id": message.id,
            "server_msg_id": message.server_msg_id,
            "role": "assistant",
            "content": message.content,
            "metadata": message_metadata,
            "created_at": message.created_at.isoformat()
            if message.created_at
            else datetime.now(UTC).isoformat(),
        },
    )

    chat_url = f"/p/{membership.project_id}/chat?nid={notification.id}"
    delivery = NotificationDelivery(
        instance_id=notification.id,
        membership_id=task.membership_id,
        user_id=membership.user_id,
        channel="push_notify",
        payload_json=json.dumps(
            {
                "title": "Feedback Request",
                "body": content,
                "url": chat_url,
                "actions": payload.get("actions", []),
                "data": {
                    "notification_id": notification.id,
                    "project_id": membership.project_id,
                    "action": "feedback",
                },
            }
        ),
        run_at_utc=now,
    )
    db.add(delivery)
