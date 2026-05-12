/**
 * Compile-time type assertions for generated OpenAPI types.
 *
 * If the backend schema drifts (routes removed, shapes changed) these
 * assertions will cause a TypeScript compilation error, catching drift
 * before it reaches production.
 *
 * These types are also re-exported for use in app code.
 */

import type { components, paths } from "./openapi";

// ── Library-supplied types ────────────────────────────────────────────────

/** Response body for GET /auth/passkeys */
export type PasskeyListResponse = components["schemas"]["PasskeyListResponse"];

/** Single passkey info object */
export type PasskeyInfo = components["schemas"]["PasskeyInfo"];

/** Response body for PATCH /auth/passkeys/{key_id} */
export type PasskeyRenameResponse =
  components["schemas"]["PasskeyRenameResponse"];

/** Response body for POST /auth/passkey/register/finish (and login/finish) */
export type PasskeyFinishResponse =
  components["schemas"]["PasskeyFinishResponse"];

export type AuthSessionsResponse =
  components["schemas"]["AuthSessionsResponse"];
export type AuthSessionItem = components["schemas"]["AuthSessionItem"];
export type AdminDebugStatusResponse =
  components["schemas"]["AdminDebugStatusResponse"];
export type AdminLLMConnectivityRequest =
  components["schemas"]["AdminLLMConnectivityRequest"];
export type AdminLLMConnectivityResponse =
  components["schemas"]["AdminLLMConnectivityResponse"];
export type AdminProjectsResponse =
  components["schemas"]["AdminProjectsResponse"];
export type AdminCreateProjectRequest =
  components["schemas"]["AdminCreateProjectRequest"];
export type AdminCreateInvitesResponse =
  components["schemas"]["AdminCreateInvitesResponse"];
export type AdminProjectItem = components["schemas"]["AdminProjectItem"];
export type AdminProjectUpdateRequest =
  components["schemas"]["AdminProjectUpdateRequest"];
export type AdminPushChannelItem =
  components["schemas"]["AdminPushChannelItem"];
export type AdminPushChannelsResponse =
  components["schemas"]["AdminPushChannelsResponse"];
export type AdminPushTestRequest =
  components["schemas"]["AdminPushTestRequest"];
export type AdminPushTestResponse =
  components["schemas"]["AdminPushTestResponse"];
export type AdminPushTestResultItem =
  components["schemas"]["AdminPushTestResultItem"];
export type UserMeResponse = components["schemas"]["UserMeResponse"];
export type UserMeUpdateRequest = components["schemas"]["UserMeUpdateRequest"];
export type TimezoneUpdateRequest =
  components["schemas"]["TimezoneUpdateRequest"];
export type DashboardResponse = components["schemas"]["DashboardResponse"];
export type MembershipInfo = components["schemas"]["MembershipInfo"];
export type FeedbackPollMetadata = components["schemas"]["FeedbackPollMetadata"];

// ── Notification types (unified) ──────────────────────────────────────────

export type NotificationUnreadCountResponse =
  components["schemas"]["NotificationUnreadCountResponse"];
export type UnifiedNotificationItem =
  components["schemas"]["UnifiedNotificationItem"];
export type UnifiedNotificationListResponse =
  components["schemas"]["UnifiedNotificationListResponse"];

// ── User-defined (demo) types ─────────────────────────────────────────────

/** Response body for GET /demo/ping */
export type PingResponse = components["schemas"]["PingResponse"];

/** Request body for POST /demo/echo */
export type EchoRequest = components["schemas"]["EchoRequest"];

/** Response body for POST /demo/echo */
export type EchoResponse = components["schemas"]["EchoResponse"];

// ── Path-level assertions (ensure routes exist in the schema) ─────────────

type _AssertPasskeysGet = paths["/auth/passkeys"]["get"];
type _AssertPasskeysPatch = paths["/auth/passkeys/{key_id}"]["patch"];
type _AssertAuthSessionsGet = paths["/auth/sessions"]["get"];
type _AssertAuthSessionRevokePost =
  paths["/auth/sessions/{device_id}/revoke"]["post"];
type _AssertAdminDebugStatusGet = paths["/admin/debug/status"]["get"];
type _AssertAdminDebugConnectivityPost =
  paths["/admin/debug/llm-connectivity"]["post"];
type _AssertDemoEchoPost = paths["/demo/echo"]["post"];
type _AssertDemoPingGet = paths["/demo/ping"]["get"];
type _AssertDemoSseGet = paths["/demo/sse"]["get"];
type _AssertMeGet = paths["/me"]["get"];
type _AssertMePatch = paths["/me"]["patch"];
type _AssertMeTimezonePost = paths["/me/timezone"]["post"];
type _AssertDashboardGet = paths["/dashboard"]["get"];
type _AssertAdminProjectPatch = paths["/admin/projects/{project_id}"]["patch"];
type _AssertAdminPushChannelsGet =
  paths["/admin/projects/{project_id}/push/channels"]["get"];
type _AssertAdminPushTestPost = paths["/admin/push/test"]["post"];
type _AssertNotificationsGet = paths["/notifications"]["get"];
type _AssertFeedbackEventPost =
  paths["/p/{project_id}/chat/events/feedback"]["post"];
type _AssertNotificationsUnreadCountGet =
  paths["/notifications/unread-count"]["get"];
type _AssertNotificationReadPost =
  paths["/notifications/{notification_id}/read"]["post"];
type _AssertWebpushVapidGet =
  paths["/notifications/webpush/vapid-public-key"]["get"];
type _AssertWebpushSubscriptionsPost =
  paths["/notifications/webpush/subscriptions"]["post"];
type _AssertWebpushSubscriptionsGet =
  paths["/notifications/webpush/subscriptions"]["get"];
type _AssertWebpushSubscriptionDelete =
  paths["/notifications/webpush/subscriptions/{subscription_id}"]["delete"];

// Suppress "declared but never read" – they exist purely for the type check.
export type {
  _AssertPasskeysGet,
  _AssertPasskeysPatch,
  _AssertAuthSessionsGet,
  _AssertAuthSessionRevokePost,
  _AssertAdminDebugStatusGet,
  _AssertAdminDebugConnectivityPost,
  _AssertDemoEchoPost,
  _AssertDemoPingGet,
  _AssertDemoSseGet,
  _AssertMeGet,
  _AssertMePatch,
  _AssertMeTimezonePost,
  _AssertDashboardGet,
  _AssertAdminProjectPatch,
  _AssertAdminPushChannelsGet,
  _AssertAdminPushTestPost,
  _AssertNotificationsGet,
  _AssertFeedbackEventPost,
  _AssertNotificationsUnreadCountGet,
  _AssertNotificationReadPost,
  _AssertWebpushVapidGet,
  _AssertWebpushSubscriptionsPost,
  _AssertWebpushSubscriptionsGet,
  _AssertWebpushSubscriptionDelete,
};
