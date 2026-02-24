from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, description="Web Push endpoint URL.")
    keys: dict[str, str] = Field(
        min_length=1,
        description="Subscription crypto keys (typically p256dh and auth).",
    )
    user_agent: str | None = Field(
        default=None, description="Client user agent string."
    )


class PushSubscribeResponse(BaseModel):
    subscription_id: int = Field(description="Internal push subscription id.")


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, description="Web Push endpoint URL to remove.")


class PushUnsubscribeResponse(BaseModel):
    ok: bool = Field(description="Whether unsubscription succeeded.")


class VapidPublicKeyResponse(BaseModel):
    public_key: str = Field(
        min_length=1, description="Public VAPID key used for client subscription."
    )


class AdminPushChannelItem(BaseModel):
    subscription_id: int = Field(description="Internal subscription id.")
    membership_id: int = Field(description="Membership id owning the subscription.")
    user_id: str = Field(description="User id owning the subscription.")
    user_email: str | None = Field(
        default=None, description="Optional user contact email."
    )
    display_name: str | None = Field(default=None, description="Project display name.")
    endpoint_hint: str = Field(description="Redacted endpoint preview for diagnostics.")
    created_at: datetime = Field(description="Subscription creation timestamp.")
    last_success_at: datetime | None = Field(
        default=None, description="Most recent successful push timestamp."
    )
    last_failure_at: datetime | None = Field(
        default=None, description="Most recent failed push timestamp."
    )


class AdminPushChannelsResponse(BaseModel):
    channels: list[AdminPushChannelItem] = Field(
        description="Push channels visible to admins."
    )


class AdminPushTestRequest(BaseModel):
    project_id: str = Field(description="Project id whose subscriptions are targeted.")
    subscription_ids: list[int] = Field(
        min_length=1, description="Specific subscription ids to test."
    )
    title: str = Field(min_length=1, max_length=120, description="Notification title.")
    body: str = Field(
        min_length=1, max_length=500, description="Notification body text."
    )
    url: str | None = Field(
        default=None, description="Optional URL to open on notification click."
    )


class AdminPushTestResultItem(BaseModel):
    subscription_id: int = Field(description="Subscription id tested.")
    ok: bool = Field(description="Whether delivery succeeded.")
    error: str | None = Field(
        default=None, description="Error detail when delivery failed."
    )


class AdminPushTestResponse(BaseModel):
    results: list[AdminPushTestResultItem] = Field(
        description="Per-subscription push test results."
    )
