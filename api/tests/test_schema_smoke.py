"""Smoke tests for API schema modules."""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas import (
    AdminCreateInviteRequest,
    AdminCreateProjectRequest,
    AdminLLMConnectivityRequest,
    AdminProjectUpdateRequest,
    AdminPushChannelItem,
    AdminPushTestRequest,
    AuthSessionItem,
    ClaimRequest,
    DashboardResponse,
    MembershipInfo,
    MessageItem,
    PushSubscribeRequest,
    SendMessageRequest,
    UserMeUpdateRequest,
)


def test_schema_modules_import_and_validate_representative_payloads() -> None:
    now = datetime.now(UTC)

    membership = MembershipInfo(
        project_id="pabc",
        status="active",
        conversation_id=1,
        last_message_at=now.isoformat(),
    )
    dashboard = DashboardResponse(memberships=[membership])
    assert dashboard.memberships[0].last_message_at == now

    claim = ClaimRequest(invite_code="invite-123")
    assert claim.invite_code == "invite-123"

    send = SendMessageRequest(text="hello")
    assert send.text == "hello"

    message = MessageItem(
        message_id=1,
        server_msg_id="m1",
        role="user",
        content="hello",
        created_at=now.isoformat(),
    )
    assert message.created_at == now

    subscribe = PushSubscribeRequest(
        endpoint="https://example.invalid/push",
        keys={"p256dh": "k", "auth": "a"},
    )
    assert subscribe.keys["auth"] == "a"

    admin_project = AdminCreateProjectRequest(display_name="Pilot")
    assert admin_project.display_name == "Pilot"

    invite = AdminCreateInviteRequest(expires_at=now)
    assert invite.count == 1

    update = AdminProjectUpdateRequest(status="ended")
    assert update.status == "ended"

    channel = AdminPushChannelItem(
        subscription_id=1,
        membership_id=2,
        user_id="u123",
        endpoint_hint="example.invalid/...",
        created_at=now.isoformat(),
    )
    assert channel.created_at == now

    push_test = AdminPushTestRequest(
        project_id="pabc",
        subscription_ids=[1],
        title="Test",
        body="Body",
    )
    assert push_test.subscription_ids == [1]

    auth_session = AuthSessionItem(
        device_id="d123",
        created_at=now.isoformat(),
        is_current=True,
    )
    assert auth_session.created_at == now

    user_update = UserMeUpdateRequest(email="user@example.com", display_name="Name")
    assert str(user_update.email) == "user@example.com"

    llm = AdminLLMConnectivityRequest()
    assert llm.model
