from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MembershipInfo(BaseModel):
    project_id: str = Field(description="Project identifier.")
    display_name: str | None = Field(default=None, description="Project display name.")
    status: str = Field(description="Membership status.")
    conversation_id: int | None = Field(
        default=None,
        description="Internal conversation id for the membership thread.",
    )
    last_message_preview: str | None = Field(
        default=None,
        description="Preview text of the latest message.",
    )
    last_message_at: datetime | None = Field(
        default=None,
        description="Timestamp of the latest message.",
    )


class DashboardResponse(BaseModel):
    memberships: list[MembershipInfo] = Field(
        description="All project memberships visible to the current user."
    )


class ClaimRequest(BaseModel):
    invite_code: str = Field(description="Plain invite code from activation link.")


class ClaimResponse(BaseModel):
    project_id: str = Field(description="Project identifier.")
    membership_status: str = Field(
        description="Resulting membership status after claim."
    )
    conversation_id: int = Field(
        description="Conversation id created or reused after claim."
    )


class MeResponse(BaseModel):
    membership_status: str = Field(
        description="Membership status in the target project."
    )
    conversation_id: int | None = Field(
        default=None, description="Conversation id for this project membership."
    )
    email: str | None = Field(
        default=None, description="Optional contact email metadata."
    )
