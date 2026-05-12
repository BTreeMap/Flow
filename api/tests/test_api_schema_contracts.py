"""Contract tests for API request/response schemas."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.routes import (
    AdminCreateInviteRequest,
    AdminDebugStatusResponse,
    AdminLLMConnectivityRequest,
    AdminProjectItem,
    AdminProjectUpdateRequest,
    AdminPushChannelItem,
    AdminPushChannelsResponse,
    AdminPushTestRequest,
    AdminPushTestResponse,
    AdminPushTestResultItem,
    MessageItem,
    MessageListResponse,
    ProfileUpdateRequest,
    PushSubscribeRequest,
    SendMessageRequest,
    UserMeUpdateRequest,
)


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (SendMessageRequest, {"text": "hello", "client_msg_id": "c1"}),
        (
            PushSubscribeRequest,
            {
                "endpoint": "https://example.test/subscriptions/123",
                "keys": {"p256dh": "abc", "auth": "def"},
                "user_agent": "pytest",
            },
        ),
        (
            ProfileUpdateRequest,
            {
                "prompt_anchor": "morning",
                "preferred_time": "08:30",
                "habit_domain": "walking",
                "motivational_frame": "supportive",
            },
        ),
        (
            AdminCreateInviteRequest,
            {
                "count": 2,
                "expires_at": datetime.now(UTC).isoformat(),
                "max_uses": 3,
                "label": "pilot",
            },
        ),
        (
            UserMeUpdateRequest,
            {"email": "participant@example.com", "display_name": "Pat"},
        ),
        (AdminProjectUpdateRequest, {"display_name": "Week 2", "status": "paused"}),
        (
            AdminPushTestRequest,
            {
                "project_id": "paaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "subscription_ids": [1, 2],
                "title": "hello",
                "body": "world",
                "url": "/p/abc",
            },
        ),
        (
            AdminLLMConnectivityRequest,
            {
                "model": "gpt-4o-mini",
                "prompt": "ping",
                "max_tokens": 64,
                "temperature": 0.2,
            },
        ),
    ],
)
def test_major_request_models_accept_valid_payloads(
    model_cls: type, payload: dict[str, object]
) -> None:
    model = model_cls.model_validate(payload)
    assert model is not None


@pytest.mark.parametrize(
    ("model_cls", "payload", "invalid_fragment"),
    [
        (SendMessageRequest, {"client_msg_id": "c1"}, "text"),
        (
            PushSubscribeRequest,
            {
                "endpoint": "https://example.test/subscriptions/123",
                "keys": {"auth": "def"},
            },
            "p256dh",
        ),
        (ProfileUpdateRequest, {"preferred_time": "08:30"}, "prompt_anchor"),
        (AdminCreateInviteRequest, {"count": 2}, "expires_at"),
        (
            AdminPushTestRequest,
            {"project_id": "pbad", "subscription_ids": [1]},
            "title",
        ),
    ],
)
def test_major_request_models_reject_missing_required_fields(
    model_cls: type,
    payload: dict[str, object],
    invalid_fragment: str,
) -> None:
    with pytest.raises(ValidationError) as err:
        model_cls.model_validate(payload)
    assert invalid_fragment in str(err.value)


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (SendMessageRequest, {"text": "hello", "unknown": "x"}),
        (
            PushSubscribeRequest,
            {
                "endpoint": "https://example.test/subscriptions/123",
                "keys": {"p256dh": "abc", "auth": "def", "extra": "x"},
            },
        ),
        (
            ProfileUpdateRequest,
            {
                "prompt_anchor": "morning",
                "preferred_time": "08:30",
                "habit_domain": "walking",
                "motivational_frame": "supportive",
                "extra": "x",
            },
        ),
        (
            AdminPushTestRequest,
            {
                "project_id": "paaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "subscription_ids": [1],
                "title": "hello",
                "body": "world",
                "unexpected": True,
            },
        ),
        (AdminLLMConnectivityRequest, {"prompt": "hello", "extra": "bad"}),
    ],
)
def test_major_request_models_reject_unknown_fields(
    model_cls: type, payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model_cls.model_validate(payload)


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (AdminProjectUpdateRequest, {"status": "archived"}),
        (
            AdminCreateInviteRequest,
            {"count": 1, "expires_at": "tomorrow-ish"},
        ),
        (
            AdminPushTestRequest,
            {
                "project_id": "project-not-custom-id",
                "subscription_ids": [1],
                "title": "hello",
                "body": "world",
            },
        ),
        (UserMeUpdateRequest, {"email": "not-an-email"}),
    ],
)
def test_major_request_models_reject_invalid_literals_and_formats(
    model_cls: type,
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model_cls.model_validate(payload)


def test_response_model_dump_json_shape_for_messages() -> None:
    response = MessageListResponse(
        messages=[
            MessageItem(
                message_id=11,
                server_msg_id="m_01",
                role="assistant",
                content="Great work",
                created_at="2026-01-15T09:30:00+00:00",
                metadata={
                    "type": "feedback_poll",
                    "notification_id": 1042,
                    "status": "pending",
                    "actions": [{"id": "fb_0", "title": "Highly Relevant"}],
                },
            )
        ]
    )

    assert response.model_dump(mode="json") == {
        "messages": [
            {
                "message_id": 11,
                "server_msg_id": "m_01",
                "role": "assistant",
                "content": "Great work",
                "created_at": "2026-01-15T09:30:00+00:00",
                "metadata": {
                    "type": "feedback_poll",
                    "notification_id": 1042,
                    "status": "pending",
                    "selected_action_id": None,
                    "actions": [{"id": "fb_0", "title": "Highly Relevant"}],
                },
            }
        ]
    }


def test_response_model_dump_json_shape_for_push_and_admin() -> None:
    push_results = AdminPushTestResponse(
        results=[
            AdminPushTestResultItem(subscription_id=10, ok=True, error=None),
            AdminPushTestResultItem(subscription_id=11, ok=False, error="timeout"),
        ]
    )
    channels = AdminPushChannelsResponse(
        channels=[
            AdminPushChannelItem(
                subscription_id=1,
                membership_id=2,
                user_id="u_member",
                user_email="member@example.com",
                display_name="Member",
                endpoint_hint="https://push.example/abc",
                created_at="2026-01-16T11:00:00+00:00",
                last_success_at=None,
                last_failure_at="2026-01-16T11:05:00+00:00",
            )
        ]
    )
    debug_status = AdminDebugStatusResponse(
        llm_mode="stub",
        openai_api_key_configured=False,
        vapid_public_key_configured=True,
        vapid_private_key_configured=False,
        warnings=["no private key"],
    )

    assert push_results.model_dump(mode="json") == {
        "results": [
            {"subscription_id": 10, "ok": True, "error": None},
            {"subscription_id": 11, "ok": False, "error": "timeout"},
        ]
    }
    assert channels.model_dump(mode="json") == {
        "channels": [
            {
                "subscription_id": 1,
                "membership_id": 2,
                "user_id": "u_member",
                "user_email": "member@example.com",
                "display_name": "Member",
                "endpoint_hint": "https://push.example/abc",
                "created_at": "2026-01-16T11:00:00+00:00",
                "last_success_at": None,
                "last_failure_at": "2026-01-16T11:05:00+00:00",
            }
        ]
    }
    assert debug_status.model_dump(mode="json") == {
        "llm_mode": "stub",
        "openai_api_key_configured": False,
        "vapid_public_key_configured": True,
        "vapid_private_key_configured": False,
        "warnings": ["no private key"],
    }


def test_response_model_dump_json_shape_for_admin_project_item() -> None:
    item = AdminProjectItem(
        project_id="paaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        display_name="Week 1",
        status="active",
        created_at="2026-01-15T09:30:00+00:00",
        member_count=4,
    )

    assert item.model_dump(mode="json") == {
        "project_id": "paaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "display_name": "Week 1",
        "status": "active",
        "created_at": "2026-01-15T09:30:00+00:00",
        "member_count": 4,
    }
