from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class AuthMeResponse(BaseModel):
    user_id: str = Field(description="Authenticated h4ckath0n user id.")
    role: Literal["user", "admin"] = Field(description="Effective authenticated role.")


class UserMeResponse(BaseModel):
    user_id: str = Field(description="Authenticated user id.")
    email: str | None = Field(
        default=None, description="Optional contact email metadata."
    )
    display_name: str | None = Field(default=None, description="Optional display name.")
    is_admin: bool = Field(
        default=False, description="Whether the user has admin privileges."
    )


class UserMeUpdateRequest(BaseModel):
    email: EmailStr | None = Field(
        default=None, description="Optional email metadata to store for contact."
    )
    display_name: str | None = Field(
        default=None, min_length=1, max_length=255, description="Optional display name."
    )


class AuthSessionItem(BaseModel):
    device_id: str = Field(description="Device/session identifier.")
    label: str | None = Field(
        default=None, description="Optional user-provided device label."
    )
    created_at: datetime = Field(description="Session creation timestamp.")
    revoked_at: datetime | None = Field(
        default=None, description="Session revocation timestamp, if revoked."
    )
    is_current: bool = Field(
        description="True when this is the currently active session."
    )


class AuthSessionsResponse(BaseModel):
    sessions: list[AuthSessionItem] = Field(
        default_factory=list, description="Active and historical sessions for the user."
    )


class AuthSessionRevokeResponse(BaseModel):
    ok: bool = Field(description="Indicates whether revoke action succeeded.")
