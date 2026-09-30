"""Feedback event submission route and helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from h4ckath0n.auth import require_user
from h4ckath0n.auth.models import User
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.engine import process_turn as engine_process_turn
from app.config import get_llm_model, get_openai_api_key
from app.db import get_db
from app.errors import AppError, Fault
from app.id_utils import generate_server_msg_id
from app.llm import make_chat_llm
from app.models import (
    Message,
    Notification,
    NotificationDelivery,
)
from app.prompt_loader import prompt_version
from app.routes._shared import (
    FEEDBACK_ACTION_CLIENT_MSG_PREFIX,
    _get_conversation,
    _get_membership,
    _publish_event,
)
from app.routes.schemas import (
    FeedbackEventRequest,
)
from app.services.event_service import persist_event

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_feedback_action_title(
    deliveries: Sequence[NotificationDelivery], action_id: str
) -> str:
    """Resolve human-readable action title from delivery payload actions."""
    for delivery in deliveries:
        try:
            payload = json.loads(delivery.payload_json)
        except json.JSONDecodeError:
            continue
        for action in payload.get("actions", []):
            if action.get("action") == action_id:
                return str(action.get("title") or action_id)
    return action_id


def _format_feedback_system_message(action_title: str, notification_id: int) -> str:
    return f"[System: User provided feedback '{action_title}' on notification {notification_id}]"


async def _submit_feedback_event_impl(
    body: FeedbackEventRequest,
    resolved_project_id: str,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Persist push action feedback and run an engine turn for contextual follow-up."""
    try:
        membership = await _get_membership(db, resolved_project_id, user.id)
        notif_result = await db.execute(
            select(Notification).where(
                Notification.id == body.notification_id,
                Notification.membership_id == membership.id,
            )
        )
        notification = notif_result.scalar_one_or_none()
        if notification is None:
            raise AppError(Fault.NOT_FOUND, "Notification not found")

        conv = await _get_conversation(db, notification.membership_id)
        poll_msg_result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.metadata_["type"].as_string() == "feedback_poll",
                Message.metadata_["notification_id"].as_integer()
                == body.notification_id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        poll_msg = poll_msg_result.scalar_one_or_none()
        if poll_msg is None:
            fallback_result = await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conv.id,
                    Message.metadata_.is_not(None),
                )
                .order_by(Message.id.desc())
            )
            for candidate in fallback_result.scalars():
                metadata = candidate.metadata_ or {}
                if metadata.get("type") == "feedback_poll" and str(
                    metadata.get("notification_id")
                ) == str(body.notification_id):
                    poll_msg = candidate
                    break
        if poll_msg is None:
            raise AppError(Fault.NOT_FOUND, "Poll message not found")

        poll_metadata = dict(poll_msg.metadata_ or {})
        if poll_metadata.get("status") == "completed":
            if notification.read_at is None:
                notification.read_at = datetime.now(UTC)
                await db.commit()
            return {"status": "already_recorded"}

        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)

        delivery_result = await db.execute(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.instance_id == notification.id,
                NotificationDelivery.channel == "push_notify",
            )
            .order_by(NotificationDelivery.id.desc())
        )
        action_title = _resolve_feedback_action_title(
            delivery_result.scalars().all(),
            body.action_id,
        )
        selected_action_id = None
        for action in poll_metadata.get("actions", []):
            if action.get("id") == body.action_id:
                selected_action_id = body.action_id
                action_title = str(action.get("title") or action_title)
                break
        if selected_action_id is None:
            raise AppError(Fault.MALFORMED, "Invalid feedback action")

        poll_metadata["status"] = "completed"
        poll_metadata["selected_action_id"] = selected_action_id
        await db.execute(
            update(Message)
            .where(Message.id == poll_msg.id)
            .values({Message.metadata_: poll_metadata})
        )

        update_payload = {
            "message_id": poll_msg.id,
            "server_msg_id": poll_msg.server_msg_id,
            "metadata": poll_metadata,
        }
        update_event = await persist_event(
            db, conv.id, "message.updated", update_payload
        )

        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=_format_feedback_system_message(action_title, notification.id),
            server_msg_id=generate_server_msg_id(),
            client_msg_id=(
                f"{FEEDBACK_ACTION_CLIENT_MSG_PREFIX}{notification.id}:{body.action_id}"
            ),
        )
        db.add(user_msg)
        await db.flush()

        llm_key = get_openai_api_key()
        llm = (
            make_chat_llm(
                model=get_llm_model(),
                api_key=llm_key,
            )
            if llm_key
            else None
        )
        (
            assistant_content,
            decision,
            debug_info,
            participation_id,
        ) = await engine_process_turn(
            db=db,
            conversation=conv,
            membership_id=notification.membership_id,
            user_msg=user_msg,
            user_text=user_msg.content,
            llm=llm,
            router_llm=llm,
        )

        current_condition = (
            debug_info.condition if debug_info.condition != "NONE" else None
        )
        asst_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=assistant_content,
            server_msg_id=generate_server_msg_id(),
            condition_source=(
                f"COND_{current_condition}" if current_condition else "SYSTEM"
            ),
            metadata_={"debug_info": debug_info.model_dump()},
            participation_id=participation_id,
        )
        db.add(asst_msg)
        await db.flush()

        route_to_prompt = {
            "INTAKE": "intake_system",
            "FEEDBACK": "feedback_system",
            "COACH": "coach_system",
        }
        prompt_name = route_to_prompt.get(decision.route, "coach_system")
        sse_payload = {
            "message_id": asst_msg.id,
            "server_msg_id": asst_msg.server_msg_id,
            "role": "assistant",
            "content": assistant_content,
            "created_at": asst_msg.created_at.isoformat()
            if asst_msg.created_at
            else datetime.now(UTC).isoformat(),
            "prompt_versions": prompt_version(prompt_name),
        }
        conv_event = await persist_event(db, conv.id, "message.final", sse_payload)
        await db.commit()
        _publish_event(
            conv.id,
            {
                "event": "message.updated",
                "id": str(update_event.id),
                "data": json.dumps(update_payload),
            },
        )
        _publish_event(
            conv.id,
            {
                "event": "message.final",
                "id": str(conv_event.id),
                "data": json.dumps(sse_payload),
            },
        )
        return {"status": "success"}
    except IntegrityError:
        await db.rollback()
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to store feedback event")
        raise AppError(Fault.INTERNAL, "Failed to store feedback event") from exc


@router.post("/p/{project_id}/chat/events/feedback", tags=["notifications"])
async def submit_feedback_event(
    project_id: str,
    body: FeedbackEventRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    return await _submit_feedback_event_impl(
        body=body,
        resolved_project_id=project_id,
        user=user,
        db=db,
    )
