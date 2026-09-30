"""Pydantic request/response models for the API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import get_llm_model
from app.schemas.messaging import DebugInfo


class MembershipInfo(BaseModel):
    project_id: str
    display_name: str | None = None
    status: str
    conversation_id: int | None = None
    last_message_preview: str | None = None
    last_message_at: str | None = None


class DashboardResponse(BaseModel):
    memberships: list[MembershipInfo]


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_code: str


class ClaimResponse(BaseModel):
    project_id: str
    membership_status: str
    conversation_id: int


class MeResponse(BaseModel):
    membership_status: str
    conversation_id: int | None = None
    email: str | None = None


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    client_msg_id: str | None = None
    current_notification_id: int | None = None


class FeedbackAction(BaseModel):
    id: str
    title: str


class FeedbackPollMetadata(BaseModel):
    type: Literal["feedback_poll"]
    notification_id: int
    status: Literal["pending", "completed"]
    selected_action_id: str | None = None
    actions: list[FeedbackAction]


class MessageItem(BaseModel):
    message_id: int
    server_msg_id: str
    role: str
    content: str
    created_at: str
    metadata: FeedbackPollMetadata | dict[str, Any] | None = None


class SendMessageResponse(BaseModel):
    message_id: int
    server_msg_id: str
    role: str
    content: str
    user_message: MessageItem | None = None
    debug_info: DebugInfo | None = None


class MessageListResponse(BaseModel):
    messages: list[MessageItem]


class FeedbackEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    notification_id: int
    project_id: str | None = None


class PushKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str
    keys: PushKeys
    user_agent: str | None = None


class PushSubscribeResponse(BaseModel):
    subscription_id: int


class NotificationUnreadCountResponse(BaseModel):
    count: int


class VapidPublicKeyResponse(BaseModel):
    public_key: str


class UnifiedNotificationItem(BaseModel):
    id: int
    title: str
    body: str
    created_at: str
    read_at: str | None
    payload_json: str
    project_id: str
    project_display_name: str | None
    membership_id: int
    rule_id: int | None = None
    local_date: str | None = None


class UnifiedNotificationListResponse(BaseModel):
    notifications: list[UnifiedNotificationItem]
    next_cursor: str | None = None


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_anchor: str
    preferred_time: str
    habit_domain: str = ""
    motivational_frame: str = ""


class AdminCreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    study_settings: dict[str, Any] | None = None


class AdminProjectItem(BaseModel):
    project_id: str
    display_name: str | None = None
    status: str = "active"
    created_at: str
    member_count: int


class AdminProjectsResponse(BaseModel):
    projects: list[AdminProjectItem]


class AdminCreateInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = 1
    expires_at: datetime
    max_uses: int | None = None
    label: str | None = None


class AdminCreateInvitesResponse(BaseModel):
    invite_codes: list[str]


class AdminParticipantItem(BaseModel):
    user_id: str
    status: str
    created_at: str
    ended_at: str | None = None
    email: str | None = None
    push_subscription_count: int
    last_push_success_at: str | None = None
    last_push_failure_at: str | None = None


class AdminParticipantsResponse(BaseModel):
    participants: list[AdminParticipantItem]


class AuthMeResponse(BaseModel):
    user_id: str
    role: str


class UserMeResponse(BaseModel):
    user_id: str
    email: str | None = None
    display_name: str | None = None
    is_admin: bool = False


class UserMeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    display_name: str | None = None


class TimezoneUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str
    offset_minutes: int | None = None


class AdminProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    status: Literal["active", "paused", "ended"] | None = None


class AdminPushChannelItem(BaseModel):
    subscription_id: int
    membership_id: int
    user_id: str
    user_email: str | None = None
    display_name: str | None = None
    endpoint_hint: str
    created_at: str
    last_success_at: str | None = None
    last_failure_at: str | None = None


class AdminPushChannelsResponse(BaseModel):
    channels: list[AdminPushChannelItem]


class AdminPushTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: Annotated[str, Field(pattern=r"^p[a-z2-7]{31}$")]
    subscription_ids: list[int]
    title: str
    body: str
    url: str | None = None


class AdminPushTestResultItem(BaseModel):
    subscription_id: int
    ok: bool
    error: str | None = None


class AdminPushTestResponse(BaseModel):
    results: list[AdminPushTestResultItem]


class AuthSessionItem(BaseModel):
    device_id: str
    label: str | None = None
    created_at: str
    revoked_at: str | None = None
    is_current: bool


class AuthSessionsResponse(BaseModel):
    sessions: list[AuthSessionItem]


class AuthSessionRevokeResponse(BaseModel):
    ok: bool


class AdminDebugStatusResponse(BaseModel):
    llm_mode: str
    openai_api_key_configured: bool
    vapid_public_key_configured: bool
    vapid_private_key_configured: bool
    warnings: list[str]


class AdminLLMConnectivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(default_factory=get_llm_model)
    prompt: str = "Reply with exactly: OK"
    max_tokens: int = 128
    temperature: float = 0.0


class AdminLLMConnectivityResponse(BaseModel):
    ok: bool
    model: str
    latency_ms: int
    response_text: str | None = None
    error: str | None = None
