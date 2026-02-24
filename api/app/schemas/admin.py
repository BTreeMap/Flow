from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AdminCreateProjectRequest(BaseModel):
    display_name: str = Field(
        min_length=1, max_length=255, description="Project display name."
    )
    study_settings: dict[str, Any] | None = Field(
        default=None, description="Optional project-level study settings."
    )


class AdminProjectItem(BaseModel):
    project_id: str = Field(description="Project identifier.")
    display_name: str | None = Field(default=None, description="Project display name.")
    status: str = Field(default="active", description="Project status.")
    created_at: datetime = Field(description="Project creation timestamp.")
    member_count: int = Field(ge=0, description="Number of members in the project.")


class AdminProjectsResponse(BaseModel):
    projects: list[AdminProjectItem] = Field(
        default_factory=list, description="Admin-visible project list."
    )


class AdminCreateInviteRequest(BaseModel):
    count: int = Field(
        default=1, ge=1, le=100, description="Number of invite codes to create."
    )
    expires_at: datetime = Field(description="Invite expiration timestamp.")
    max_uses: int | None = Field(
        default=None, ge=1, description="Maximum successful claims per code."
    )
    label: str | None = Field(
        default=None, max_length=255, description="Optional admin-only invite label."
    )


class AdminCreateInvitesResponse(BaseModel):
    invite_codes: list[str] = Field(
        default_factory=list, description="Newly generated plain invite codes."
    )


class AdminParticipantItem(BaseModel):
    user_id: str = Field(description="Participant user id.")
    status: str = Field(description="Membership status.")
    created_at: datetime = Field(description="Membership creation timestamp.")
    ended_at: datetime | None = Field(
        default=None, description="Membership end timestamp."
    )
    email: str | None = Field(
        default=None, description="Optional contact email metadata."
    )
    push_subscription_count: int = Field(
        ge=0, description="Count of active push subscriptions."
    )
    last_push_success_at: datetime | None = Field(
        default=None, description="Most recent successful push timestamp."
    )
    last_push_failure_at: datetime | None = Field(
        default=None, description="Most recent failed push timestamp."
    )


class AdminParticipantsResponse(BaseModel):
    participants: list[AdminParticipantItem] = Field(
        default_factory=list, description="Participants for a project."
    )


class AdminProjectUpdateRequest(BaseModel):
    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated project display name.",
    )
    status: Literal["active", "ended"] | None = Field(
        default=None, description="Updated project status."
    )


class AdminDebugStatusResponse(BaseModel):
    llm_mode: str = Field(description="Current LLM operation mode.")
    openai_api_key_configured: bool = Field(
        description="Whether an OpenAI API key is configured."
    )
    vapid_public_key_configured: bool = Field(
        description="Whether VAPID public key is configured."
    )
    vapid_private_key_configured: bool = Field(
        description="Whether VAPID private key is configured."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Operational warnings for admins."
    )


class AdminLLMConnectivityRequest(BaseModel):
    model: str = Field(
        default="gpt-4o-mini", min_length=1, description="Model id to test against."
    )
    prompt: str = Field(
        default="Reply with exactly: OK",
        min_length=1,
        description="Prompt sent to test model connectivity.",
    )
    max_tokens: int = Field(
        default=128,
        ge=1,
        le=4096,
        description="Token limit for connectivity test call.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for connectivity test call.",
    )


class AdminLLMConnectivityResponse(BaseModel):
    ok: bool = Field(description="Whether connectivity check succeeded.")
    model: str = Field(description="Model used for the test.")
    latency_ms: int = Field(ge=0, description="Round-trip latency in milliseconds.")
    response_text: str | None = Field(
        default=None, description="Model response text when successful."
    )
    error: str | None = Field(
        default=None, description="Error string when unsuccessful."
    )
