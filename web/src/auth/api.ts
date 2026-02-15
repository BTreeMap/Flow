import { getOrMintToken, clearCachedToken } from "./token";
import { getDeviceIdentity } from "./deviceKey";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthError";
  }
}

export interface ApiResponse<T = unknown> {
  ok: boolean;
  status: number;
  data: T;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {},
  auth = true,
): Promise<ApiResponse<T>> {
  const url = `${API_BASE}${path}`;
  const headers = new Headers(options.headers);

  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  if (auth) {
    const identity = await getDeviceIdentity();
    if (!identity) {
      throw new AuthError("Not authenticated");
    }
    const token = await getOrMintToken("http");
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    clearCachedToken();
    throw new AuthError("Unauthorized");
  }

  let data: T;
  try {
    data = (await response.json()) as T;
  } catch {
    // Non-JSON responses (e.g. 204 No Content) return null
    data = null as T;
  }
  return { ok: response.ok, status: response.status, data };
}

// Unauthenticated fetch for login/register endpoints
export async function publicFetch<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<ApiResponse<T>> {
  return apiFetch<T>(path, options, false);
}
