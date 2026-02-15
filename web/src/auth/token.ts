import { SignJWT } from "jose";
import { getPrivateKey, getDeviceIdentity } from "./deviceKey";

/** Map from usage to { token, exp } for per-channel caching. */
const tokenCache = new Map<string, { token: string; exp: number }>();

const TOKEN_LIFETIME = 900; // 15 minutes in seconds
const RENEWAL_BUFFER = 60; // renew 60s before expiry

/** Audience constants matching server-side values. */
export const AUD_HTTP = "h4ckath0n:http";
export const AUD_WS = "h4ckath0n:ws";
export const AUD_SSE = "h4ckath0n:sse";

type TokenUsage = "http" | "ws" | "sse";

function audForUsage(usage: TokenUsage): string {
  switch (usage) {
    case "http":
      return AUD_HTTP;
    case "ws":
      return AUD_WS;
    case "sse":
      return AUD_SSE;
  }
}

export function isTokenValid(usage: TokenUsage = "http"): boolean {
  const entry = tokenCache.get(usage);
  if (!entry) return false;
  const now = Math.floor(Date.now() / 1000);
  return now < entry.exp - RENEWAL_BUFFER;
}

export async function getOrMintToken(usage: TokenUsage = "http"): Promise<string> {
  if (isTokenValid(usage)) {
    return tokenCache.get(usage)!.token;
  }
  return mintToken(usage);
}

export async function mintToken(usage: TokenUsage = "http"): Promise<string> {
  const privateKey = await getPrivateKey();
  const identity = await getDeviceIdentity();
  if (!privateKey || !identity) {
    throw new Error("No device key material or identity found");
  }

  const now = Math.floor(Date.now() / 1000);
  const exp = now + TOKEN_LIFETIME;
  const aud = audForUsage(usage);

  const token = await new SignJWT({ sub: identity.userId })
    .setProtectedHeader({
      alg: "ES256",
      typ: "JWT",
      kid: identity.deviceId,
    })
    .setIssuedAt(now)
    .setExpirationTime(exp)
    .setAudience(aud)
    .sign(privateKey);

  tokenCache.set(usage, { token, exp });
  return token;
}

export function clearCachedToken(): void {
  tokenCache.clear();
}

export function shouldRenewToken(usage: TokenUsage = "http"): boolean {
  const entry = tokenCache.get(usage);
  if (!entry) return true;
  const now = Math.floor(Date.now() / 1000);
  return now >= entry.exp - RENEWAL_BUFFER;
}
