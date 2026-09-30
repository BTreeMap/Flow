"""Aggregate API router assembled from cohesive submodules.

Re-exports the combined ``router`` plus the auth-context helper and all
Pydantic schema classes for backward compatibility with importers/tests.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.routes import (
    activation,
    admin_debug,
    admin_projects,
    admin_push,
    dashboard,
    feedback,
    messaging,
    notifications,
    spark,
    streaming,
)
from app.routes._shared import _require_auth_context
from app.routes.schemas import (
    AdminCreateInviteRequest,
    AdminCreateInvitesResponse,
    AdminCreateProjectRequest,
    AdminDebugStatusResponse,
    AdminLLMConnectivityRequest,
    AdminLLMConnectivityResponse,
    AdminParticipantItem,
    AdminParticipantsResponse,
    AdminProjectItem,
    AdminProjectsResponse,
    AdminProjectUpdateRequest,
    AdminPushChannelItem,
    AdminPushChannelsResponse,
    AdminPushTestRequest,
    AdminPushTestResponse,
    AdminPushTestResultItem,
    AuthMeResponse,
    AuthSessionItem,
    AuthSessionRevokeResponse,
    AuthSessionsResponse,
    ClaimRequest,
    ClaimResponse,
    DashboardResponse,
    FeedbackAction,
    FeedbackEventRequest,
    FeedbackPollMetadata,
    MembershipInfo,
    MeResponse,
    MessageItem,
    MessageListResponse,
    NotificationUnreadCountResponse,
    ProfileUpdateRequest,
    PushKeys,
    PushSubscribeRequest,
    PushSubscribeResponse,
    SendMessageRequest,
    SendMessageResponse,
    TimezoneUpdateRequest,
    UnifiedNotificationItem,
    UnifiedNotificationListResponse,
    UserMeResponse,
    UserMeUpdateRequest,
    VapidPublicKeyResponse,
)

router = APIRouter()
router.include_router(dashboard.router)
router.include_router(admin_debug.router)
router.include_router(activation.router)
router.include_router(messaging.router)
router.include_router(feedback.router)
router.include_router(streaming.router)
router.include_router(notifications.router)
router.include_router(admin_projects.router)
router.include_router(admin_push.router)
router.include_router(spark.router)

__all__ = [
    "AdminCreateInviteRequest",
    "AdminCreateInvitesResponse",
    "AdminCreateProjectRequest",
    "AdminDebugStatusResponse",
    "AdminLLMConnectivityRequest",
    "AdminLLMConnectivityResponse",
    "AdminParticipantItem",
    "AdminParticipantsResponse",
    "AdminProjectItem",
    "AdminProjectUpdateRequest",
    "AdminProjectsResponse",
    "AdminPushChannelItem",
    "AdminPushChannelsResponse",
    "AdminPushTestRequest",
    "AdminPushTestResponse",
    "AdminPushTestResultItem",
    "AuthMeResponse",
    "AuthSessionItem",
    "AuthSessionRevokeResponse",
    "AuthSessionsResponse",
    "ClaimRequest",
    "ClaimResponse",
    "DashboardResponse",
    "FeedbackAction",
    "FeedbackEventRequest",
    "FeedbackPollMetadata",
    "MeResponse",
    "MembershipInfo",
    "MessageItem",
    "MessageListResponse",
    "NotificationUnreadCountResponse",
    "ProfileUpdateRequest",
    "PushKeys",
    "PushSubscribeRequest",
    "PushSubscribeResponse",
    "SendMessageRequest",
    "SendMessageResponse",
    "TimezoneUpdateRequest",
    "UnifiedNotificationItem",
    "UnifiedNotificationListResponse",
    "UserMeResponse",
    "UserMeUpdateRequest",
    "VapidPublicKeyResponse",
    "_require_auth_context",
    "router",
]
