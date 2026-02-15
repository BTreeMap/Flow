/**
 * Typed API client built on openapi-fetch.
 *
 * Uses the generated OpenAPI types so every call is type-safe against the
 * backend schema.  Authentication follows the existing device-key / JWT
 * pattern used elsewhere in the app.
 */

import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "../gen/openapi";
import { getOrMintToken, clearCachedToken } from "../auth/token";
import { getDeviceIdentity } from "../auth/deviceKey";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

/**
 * Middleware that attaches the device-signed JWT to every request and
 * handles 401 responses by clearing the cached token.
 */
const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const identity = await getDeviceIdentity();
    if (identity) {
      const token = await getOrMintToken("http");
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401) {
      clearCachedToken();
    }
    return response;
  },
};

/**
 * Typed fetch client – every path, method and payload is checked at
 * compile time against the generated OpenAPI schema.
 */
const api = createClient<paths>({ baseUrl: API_BASE });
api.use(authMiddleware);

export default api;
