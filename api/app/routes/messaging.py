"""Message listing and send (turn processing) routes."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from h4ckath0n.auth import require_user
from h4ckath0n.auth.models import User
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.config import get_llm_model, get_openai_api_key
from app.db import async_session_factory, get_db
from app.errors import AppError, Fault
from app.id_utils import generate_server_msg_id
from app.llm import make_chat_llm
from app.models import (
    Conversation,
    ConversationTurn,
    Message,
    ScheduledTask,
)
from app.prompt_loader import prompt_version
from app.routes._shared import (
    FEEDBACK_ACTION_CLIENT_MSG_PREFIX,
    _get_conversation,
    _get_membership,
    _publish_event,
)
from app.routes.schemas import (
    MessageItem,
    MessageListResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services.event_service import persist_event

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/p/{project_id}/messages", tags=["messaging"])
async def list_messages(
    project_id: str,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    """Return persisted messages for a project conversation."""
    try:
        membership = await _get_membership(db, project_id, user.id)
        conv = await _get_conversation(db, membership.id)
        result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conv.id,
                or_(
                    Message.client_msg_id.is_(None),
                    ~Message.client_msg_id.startswith(
                        FEEDBACK_ACTION_CLIENT_MSG_PREFIX
                    ),
                ),
            )
            .order_by(Message.id.asc())
        )
        items = [
            MessageItem(
                message_id=msg.id,
                server_msg_id=msg.server_msg_id,
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at.isoformat(),
                metadata=msg.metadata_,
            )
            for msg in result.scalars().all()
        ]
        return MessageListResponse(messages=items)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load messages")
        raise AppError(Fault.INTERNAL, "Failed to load messages") from exc


@router.post("/p/{project_id}/messages", tags=["messaging"])
async def send_message(
    project_id: str,
    body: SendMessageRequest,
    user: User = require_user(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Persist user message, run engine turn, persist assistant reply."""
    membership = await _get_membership(db, project_id, user.id)
    conv = await _get_conversation(db, membership.id)

    await db.execute(
        update(ScheduledTask)
        .where(
            ScheduledTask.membership_id == membership.id,
            ScheduledTask.task_type == "feedback_request",
            ScheduledTask.status == "pending",
        )
        .values(status="cancelled")
    )
    if body.current_notification_id is not None:
        await db.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.parent_instance_id == body.current_notification_id,
                ScheduledTask.membership_id == membership.id,
                ScheduledTask.status == "pending",
            )
            .values(status="cancelled")
        )

    # Eagerly capture IDs to survive potential rollback
    conv_id = conv.id
    membership_id = membership.id

    # --- Turn gating (idempotent when client_msg_id is provided) ----------
    turn: ConversationTurn | None = None
    if body.client_msg_id:
        # Try to claim the turn by inserting a row with status=processing
        turn = ConversationTurn(
            conversation_id=conv_id,
            client_msg_id=body.client_msg_id,
            status="processing",
        )
        db.add(turn)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # A turn with this client_msg_id already exists
            existing = await db.execute(
                select(ConversationTurn).where(
                    ConversationTurn.conversation_id == conv_id,
                    ConversationTurn.client_msg_id == body.client_msg_id,
                )
            )
            if (turn := existing.scalars().first()) is None:
                raise AppError(Fault.INTERNAL, "Turn conflict") from None
            if turn.status == "completed" and turn.assistant_message_id is not None:
                asst_result = await db.execute(
                    select(Message).where(
                        Message.id == turn.assistant_message_id,
                    )
                )
                asst = asst_result.scalars().first()
                if asst:
                    # Fetch user message for response
                    user_msg_result = await db.execute(
                        select(Message).where(Message.id == turn.user_message_id)
                    )
                    user_msg = user_msg_result.scalars().first()

                    return SendMessageResponse(
                        message_id=asst.id,
                        server_msg_id=asst.server_msg_id,
                        role="assistant",
                        content=asst.content,
                        user_message=MessageItem(
                            message_id=user_msg.id,
                            server_msg_id=user_msg.server_msg_id,
                            role=user_msg.role,
                            content=user_msg.content,
                            created_at=user_msg.created_at.isoformat(),
                        )
                        if user_msg
                        else None,
                    )
            if turn.status == "processing":
                # Another request is processing this turn; wait briefly
                turn_id = turn.id
                for _ in range(6):
                    await asyncio.sleep(0.5)
                    re_result = await db.execute(
                        select(ConversationTurn).where(
                            ConversationTurn.id == turn_id,
                        )
                    )
                    if (turn := re_result.scalars().first()) is None:
                        break
                    if (
                        turn.status == "completed"
                        and turn.assistant_message_id is not None
                    ):
                        asst_result = await db.execute(
                            select(Message).where(
                                Message.id == turn.assistant_message_id,
                            )
                        )
                        asst = asst_result.scalars().first()
                        if asst:
                            # Fetch user message for response
                            user_msg_result = await db.execute(
                                select(Message).where(
                                    Message.id == turn.user_message_id
                                )
                            )
                            user_msg = user_msg_result.scalars().first()

                            return SendMessageResponse(
                                message_id=asst.id,
                                server_msg_id=asst.server_msg_id,
                                role="assistant",
                                content=asst.content,
                                user_message=MessageItem(
                                    message_id=user_msg.id,
                                    server_msg_id=user_msg.server_msg_id,
                                    role=user_msg.role,
                                    content=user_msg.content,
                                    created_at=user_msg.created_at.isoformat(),
                                )
                                if user_msg
                                else None,
                            )
                return JSONResponse(
                    status_code=202,
                    content={"detail": "Turn is still processing"},
                )
            if turn.status == "failed":
                # Previous attempt failed; allow retry by resetting
                turn.status = "processing"
                turn.error = None
                await db.flush()
            else:
                return JSONResponse(
                    status_code=202,
                    content={"detail": "Turn is still processing"},
                )

        # Re-fetch conversation after potential rollback
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        conv = conv_result.scalars().first()
        if conv is None:
            raise AppError(Fault.INTERNAL, "Conversation not found")

    # --- Process the turn (winner path) -----------------------------------
    try:
        llm_key = get_openai_api_key()
        llm = make_chat_llm(model=get_llm_model(), api_key=llm_key) if llm_key else None

        # Persist user message
        user_msg = Message(
            conversation_id=conv_id,
            role="user",
            content=body.text,
            client_msg_id=body.client_msg_id,
            server_msg_id=generate_server_msg_id(),
        )
        db.add(user_msg)
        await db.flush()

        # Update turn with user_message_id
        if body.client_msg_id and turn is not None:
            turn.user_message_id = user_msg.id
            await db.flush()

        # Run new architecture engine turn (Router + specialist)
        from app.agents.engine import process_turn as engine_process_turn

        # Generate assistant server_msg_id upfront for streaming
        asst_server_msg_id = generate_server_msg_id()

        async def on_token(token: str) -> None:
            """Callback for streaming tokens to the client."""
            _publish_event(
                conv_id,
                {
                    "event": "message.chunk",
                    "data": json.dumps(
                        {
                            "server_msg_id": asst_server_msg_id,
                            "delta": token,
                        }
                    ),
                },
            )

        try:
            (
                assistant_content,
                _decision,
                debug_info,
                participation_id,
            ) = await engine_process_turn(
                db=db,
                conversation=conv,
                membership_id=membership_id,
                user_msg=user_msg,
                user_text=body.text,
                llm=llm,
                router_llm=llm,
                on_token=on_token,
            )
        except Exception:
            logger.exception("Engine process_turn failed")
            raise

        current_condition = (
            debug_info.condition if debug_info.condition != "NONE" else None
        )
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=assistant_content,
            server_msg_id=asst_server_msg_id,
            condition_source=(
                f"COND_{current_condition}" if current_condition else "SYSTEM"
            ),
            metadata_={"debug_info": debug_info.model_dump()},
            participation_id=participation_id,
        )
        db.add(assistant_msg)
        await db.flush()

        # Mark turn as completed
        if body.client_msg_id and turn is not None:
            turn.assistant_message_id = assistant_msg.id
            turn.status = "completed"
            await db.flush()

        # Build SSE payload
        _route_to_prompt = {
            "INTAKE": "intake_system",
            "FEEDBACK": "feedback_system",
            "COACH": "coach_system",
        }
        _prompt_name = _route_to_prompt.get(_decision.route, "coach_system")
        sse_payload = {
            "message_id": assistant_msg.id,
            "server_msg_id": assistant_msg.server_msg_id,
            "role": "assistant",
            "content": assistant_content,
            "created_at": assistant_msg.created_at.isoformat()
            if assistant_msg.created_at
            else datetime.now(UTC).isoformat(),
            "prompt_versions": prompt_version(_prompt_name),
        }

        # Persist event for durable SSE replay
        conv_event = await persist_event(
            db,
            conv_id,
            "message.final",
            sse_payload,
        )

        await db.commit()
        await db.refresh(assistant_msg)

        # Publish SSE events (use ConversationEvent.id, not Message.id)
        _publish_event(
            conv_id,
            {
                "event": "message.final",
                "id": str(conv_event.id),
                "data": json.dumps(sse_payload),
            },
        )

        return SendMessageResponse(
            message_id=assistant_msg.id,
            server_msg_id=assistant_msg.server_msg_id,
            role="assistant",
            content=assistant_content,
            user_message=MessageItem(
                message_id=user_msg.id,
                server_msg_id=user_msg.server_msg_id,
                role=user_msg.role,
                content=user_msg.content,
                created_at=user_msg.created_at.isoformat(),
            ),
            debug_info=debug_info,
        )
    except Exception:
        # Log the full traceback here: the outer LoggingMiddleware only sees the
        # Starlette-converted 500 response, so without this the failure would be
        # invisible in the container logs.
        logger.exception(
            "send_message failed (project_id=%s, membership_id=%s, client_msg_id=%s)",
            project_id,
            membership_id,
            body.client_msg_id,
        )
        # Mark turn as failed on error
        if body.client_msg_id:
            try:
                await db.rollback()
                async with async_session_factory() as err_db:
                    result = await err_db.execute(
                        select(ConversationTurn).where(
                            ConversationTurn.conversation_id == conv_id,
                            ConversationTurn.client_msg_id == body.client_msg_id,
                        )
                    )
                    err_turn = result.scalars().first()
                    if err_turn and err_turn.status == "processing":
                        err_turn.status = "failed"
                        err_turn.error = "Internal processing error"
                        await err_db.commit()
            except Exception:
                logger.exception("Failed to mark turn as failed")
        raise
