/**
 * Compile-time type assertions for generated OpenAPI types.
 *
 * If the backend schema drifts (routes removed, shapes changed) these
 * assertions will cause a TypeScript compilation error, catching drift
 * before it reaches production.
 *
 * These types are also re-exported for use in app code.
 */

import type { components, paths } from "../gen/openapi";

// ── Library-supplied types ────────────────────────────────────────────────

/** Response body for GET /auth/passkeys */
export type PasskeyListResponse = components["schemas"]["PasskeyListResponse"];

/** Single passkey info object */
export type PasskeyInfo = components["schemas"]["PasskeyInfo"];

/** Response body for POST /auth/passkey/register/finish (and login/finish) */
export type PasskeyFinishResponse =
  components["schemas"]["PasskeyFinishResponse"];

// ── User-defined (demo) types ─────────────────────────────────────────────

/** Response body for GET /demo/ping */
export type PingResponse = components["schemas"]["PingResponse"];

/** Request body for POST /demo/echo */
export type EchoRequest = components["schemas"]["EchoRequest"];

/** Response body for POST /demo/echo */
export type EchoResponse = components["schemas"]["EchoResponse"];

// ── Path-level assertions (ensure routes exist in the schema) ─────────────

type _AssertPasskeysGet = paths["/auth/passkeys"]["get"];
type _AssertDemoEchoPost = paths["/demo/echo"]["post"];
type _AssertDemoPingGet = paths["/demo/ping"]["get"];
type _AssertDemoSseGet = paths["/demo/sse"]["get"];

// Suppress "declared but never read" – they exist purely for the type check.
export type {
  _AssertPasskeysGet,
  _AssertDemoEchoPost,
  _AssertDemoPingGet,
  _AssertDemoSseGet,
};
