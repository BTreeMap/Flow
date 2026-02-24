from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    text: str = Field(
        min_length=1, max_length=8000, description="User-authored message text."
    )
    client_msg_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional client-generated id for idempotency/tracing.",
    )


class SendMessageResponse(BaseModel):
    message_id: int = Field(description="Internal message row id.")
    server_msg_id: str = Field(
        description="Server-generated stable message identifier."
    )
    role: str = Field(description="Message role.")
    content: str = Field(description="Message content.")


class MessageItem(BaseModel):
    message_id: int = Field(description="Internal message row id.")
    server_msg_id: str = Field(
        description="Server-generated stable message identifier."
    )
    role: str = Field(description="Message role.")
    content: str = Field(description="Message content.")
    created_at: datetime = Field(description="Message creation timestamp.")


class MessageListResponse(BaseModel):
    messages: list[MessageItem] = Field(
        description="Conversation messages ordered by creation."
    )


class ProfileUpdateRequest(BaseModel):
    prompt_anchor: str = Field(
        min_length=1,
        max_length=255,
        description="Anchor phrase used for prompt framing.",
    )
    preferred_time: str = Field(
        min_length=1, max_length=64, description="Preferred reminder or coaching time."
    )
    habit_domain: str = Field(
        default="", max_length=255, description="Optional target habit domain."
    )
    motivational_frame: str = Field(
        default="",
        max_length=255,
        description="Optional motivational framing preference.",
    )
