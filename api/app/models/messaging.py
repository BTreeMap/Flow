"""Message persistence, runtime state, and conversation event/turn models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.core import Conversation


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_msg_id",
            name="uq_message_conversation_client_msg",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    client_msg_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    server_msg_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    participation_id: Mapped[int | None] = mapped_column(
        ForeignKey("participations.id"), nullable=True
    )
    condition_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SYSTEM", index=True
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ConversationRuntimeState(Base):
    __tablename__ = "conversation_runtime_state"

    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), primary_key=True
    )
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="runtime_state")


class ConversationEvent(Base):
    """Persisted SSE event for durable replay via Last-Event-ID."""

    __tablename__ = "conversation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConversationTurn(Base):
    """Deduplicate user messages via client_msg_id with turn gating."""

    __tablename__ = "conversation_turns"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_msg_id",
            name="uq_turn_conversation_client_msg",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False
    )
    client_msg_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="processing", server_default="processing"
    )
    user_message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("messages.id"), nullable=True
    )
    assistant_message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("messages.id"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
