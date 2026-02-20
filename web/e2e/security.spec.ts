import { test, expect, type Page } from "@playwright/test";
import {
  addVirtualAuthenticator,
  removeVirtualAuthenticator,
  type VirtualAuthenticator,
} from "./webauthn-helpers";

/**
 * Security-focused E2E tests (attacker / pentester grade).
 *
 * These tests validate authentication invariants across HTTP, WS,
 * and SSE to catch security regressions early.
 *
 * Tests run serially (shared SQLite state) with a fresh virtual
 * authenticator per test.
 */

let auth: VirtualAuthenticator;

/** Register a new user and return to dashboard. */
async function registerUser(
  page: Page,
  name = "Security Test User",
): Promise<void> {
  await page.goto("/register");
  await page.getByTestId("register-display-name").fill(name);
  await page.getByTestId("register-submit").click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
}

test.describe("Security: stable device identity", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) await removeVirtualAuthenticator(auth);
  });

  // -----------------------------------------------------------------------
  // S1) Device ID is reused across logout → login cycle
  // -----------------------------------------------------------------------
  test("device_id is stable across logout and re-login", async ({ page }) => {
    // Register
    await registerUser(page, "DID Stability User");

    // Capture the device_id from IndexedDB via the deviceKey module
    const deviceId1 = await page.evaluate(async () => {
      const { getDeviceIdentity } = await import("/src/auth/deviceKey.ts");
      const id = await getDeviceIdentity();
      return id?.deviceId ?? null;
    });
    expect(deviceId1).toBeTruthy();
    expect(deviceId1!.startsWith("d")).toBe(true);

    // Logout
    await page.getByTestId("nav-logout").click();
    await expect(page).toHaveURL(/\/(login)?$/, { timeout: 10_000 });

    // After logout, key material should persist but authorization cleared.
    // Verify via the public helpers: getDeviceIdentity → null, but key
    // material still present (ensureDeviceKeyMaterial returns without generating).
    const postLogoutState = await page.evaluate(async () => {
      const { getDeviceIdentity, getPrivateKey, getPublicJwk } =
        await import("/src/auth/deviceKey.ts");
      const identity = await getDeviceIdentity();
      const pk = await getPrivateKey();
      const pub = await getPublicJwk();
      return {
        hasPrivateKey: !!pk,
        hasPublicJwk: !!pub,
        identityCleared: identity === null,
      };
    });

    // Key material must survive logout
    expect(postLogoutState.hasPrivateKey).toBe(true);
    expect(postLogoutState.hasPublicJwk).toBe(true);
    // But authorization binding must be cleared
    expect(postLogoutState.identityCleared).toBe(true);

    // Login again
    await page.goto("/login");
    await page.getByTestId("login-submit").click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    // Capture device_id after re-login
    const deviceId2 = await page.evaluate(async () => {
      const { getDeviceIdentity } = await import("/src/auth/deviceKey.ts");
      const id = await getDeviceIdentity();
      return id?.deviceId ?? null;
    });

    // The same device key → same fingerprint → same device_id
    expect(deviceId2).toBe(deviceId1);
  });
});

test.describe("Security: unauthenticated access", () => {
  // -----------------------------------------------------------------------
  // S2) Protected endpoints reject unauthenticated requests
  // -----------------------------------------------------------------------
  test("GET /auth/passkeys returns 401/403 without token", async ({ page }) => {
    const res = await page.request.get("http://localhost:8000/auth/passkeys");
    expect([401, 403]).toContain(res.status());
  });

  test("POST /auth/passkey/add/start returns 401/403 without token", async ({
    page,
  }) => {
    const res = await page.request.post(
      "http://localhost:8000/auth/passkey/add/start",
    );
    expect([401, 403]).toContain(res.status());
  });

  test("GET /demo/sse returns 401 without token", async ({ page }) => {
    const res = await page.request.get("http://localhost:8000/demo/sse");
    expect(res.status()).toBe(401);
  });
});

test.describe("Security: JWT aud binding", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) await removeVirtualAuthenticator(auth);
  });

  // -----------------------------------------------------------------------
  // S3) HTTP token rejected for WebSocket
  // -----------------------------------------------------------------------
  test("HTTP-aud token rejected for WebSocket", async ({ page }) => {
    await registerUser(page, "WS Aud Test");

    const result = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("http"); // wrong aud for WS

      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${proto}//${window.location.host}/api/demo/ws?token=${encodeURIComponent(token)}`;

      return new Promise<{ code: number; gotMessage: boolean }>((resolve) => {
        let gotMessage = false;
        const ws = new WebSocket(wsUrl);
        ws.addEventListener("message", () => {
          gotMessage = true;
        });
        ws.addEventListener("close", (ev) => {
          resolve({ code: ev.code, gotMessage });
        });
        ws.addEventListener("error", () => {});
        setTimeout(() => resolve({ code: -1, gotMessage }), 10_000);
      });
    });

    expect(result.gotMessage).toBe(false);
    expect([1006, 1008]).toContain(result.code);
  });

  // -----------------------------------------------------------------------
  // S4) SSE-aud token rejected for HTTP
  // -----------------------------------------------------------------------
  test("SSE-aud token rejected for HTTP endpoints", async ({ page }) => {
    await registerUser(page, "HTTP Aud Test");

    const status = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("sse"); // wrong aud for HTTP

      const res = await fetch("/api/auth/passkeys", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });

  // -----------------------------------------------------------------------
  // S5) WS-aud token rejected for SSE
  // -----------------------------------------------------------------------
  test("WS-aud token rejected for SSE", async ({ page }) => {
    await registerUser(page, "SSE Aud Test");

    const status = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("ws"); // wrong aud for SSE

      const res = await fetch("/api/demo/sse", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });

  // -----------------------------------------------------------------------
  // S6) HTTP-aud token rejected for SSE
  // -----------------------------------------------------------------------
  test("HTTP-aud token rejected for SSE", async ({ page }) => {
    await registerUser(page, "SSE Aud Test 2");

    const status = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("http"); // wrong aud for SSE

      const res = await fetch("/api/demo/sse", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });

  // -----------------------------------------------------------------------
  // S7) WS-aud token rejected for HTTP
  // -----------------------------------------------------------------------
  test("WS-aud token rejected for HTTP endpoints", async ({ page }) => {
    await registerUser(page, "HTTP Aud Test 2");

    const status = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("ws"); // wrong aud for HTTP

      const res = await fetch("/api/auth/passkeys", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });

  // -----------------------------------------------------------------------
  // S8) SSE-aud token rejected for WebSocket
  // -----------------------------------------------------------------------
  test("SSE-aud token rejected for WebSocket", async ({ page }) => {
    await registerUser(page, "WS Aud Test 2");

    const result = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("sse"); // wrong aud for WS

      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${proto}//${window.location.host}/api/demo/ws?token=${encodeURIComponent(token)}`;

      return new Promise<{ code: number; gotMessage: boolean }>((resolve) => {
        let gotMessage = false;
        const ws = new WebSocket(wsUrl);
        ws.addEventListener("message", () => {
          gotMessage = true;
        });
        ws.addEventListener("close", (ev) => {
          resolve({ code: ev.code, gotMessage });
        });
        ws.addEventListener("error", () => {});
        setTimeout(() => resolve({ code: -1, gotMessage }), 10_000);
      });
    });

    expect(result.gotMessage).toBe(false);
    expect([1006, 1008]).toContain(result.code);
  });
});

test.describe("Security: tampered and malformed JWTs", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) await removeVirtualAuthenticator(auth);
  });

  // -----------------------------------------------------------------------
  // S9) Tampered JWT signature rejected
  // -----------------------------------------------------------------------
  test("tampered JWT signature is rejected", async ({ page }) => {
    await registerUser(page, "Tamper Test");

    const status = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("http");

      // Tamper with the signature (last segment)
      const parts = token.split(".");
      const sig = parts[2]!;
      // Flip a character in the signature
      const tampered = sig[0] === "A" ? "B" + sig.slice(1) : "A" + sig.slice(1);
      const badToken = `${parts[0]}.${parts[1]}.${tampered}`;

      const res = await fetch("/api/auth/passkeys", {
        headers: { Authorization: `Bearer ${badToken}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });

  // -----------------------------------------------------------------------
  // S10) Missing Authorization header rejected
  // -----------------------------------------------------------------------
  test("missing Authorization header is rejected", async ({ page }) => {
    await page.goto("/");
    const res = await page.request.get("http://localhost:8000/auth/passkeys");
    expect([401, 403]).toContain(res.status());
  });

  // -----------------------------------------------------------------------
  // S11) Garbage token rejected
  // -----------------------------------------------------------------------
  test("garbage token is rejected", async ({ page }) => {
    await page.goto("/");
    const res = await page.request.get("http://localhost:8000/auth/passkeys", {
      headers: { Authorization: "Bearer not.a.valid.jwt.at.all" },
    });
    expect(res.status()).toBe(401);
  });

  // -----------------------------------------------------------------------
  // S12) Token signed by a different key is rejected
  // -----------------------------------------------------------------------
  test("token signed by unknown device key is rejected", async ({ page }) => {
    await registerUser(page, "Wrong Key Test");

    const status = await page.evaluate(async () => {
      const { getDeviceIdentity } = await import("/src/auth/deviceKey.ts");
      const identity = await getDeviceIdentity();

      // Generate a completely new key pair (not registered with backend)
      const keyPair = await crypto.subtle.generateKey(
        { name: "ECDSA", namedCurve: "P-256" },
        false,
        ["sign", "verify"],
      );

      // Manually build a JWT signed by the unknown key
      const header = btoa(
        JSON.stringify({
          alg: "ES256",
          typ: "JWT",
          kid: identity!.deviceId,
        }),
      )
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const now = Math.floor(Date.now() / 1000);
      const payload = btoa(
        JSON.stringify({
          sub: identity!.userId,
          iat: now,
          exp: now + 900,
          aud: "h4ckath0n:http",
        }),
      )
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const signingInput = new TextEncoder().encode(`${header}.${payload}`);
      const sigBytes = await crypto.subtle.sign(
        { name: "ECDSA", hash: "SHA-256" },
        keyPair.privateKey,
        signingInput,
      );
      const sig = btoa(String.fromCharCode(...new Uint8Array(sigBytes)))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const token = `${header}.${payload}.${sig}`;

      const res = await fetch("/api/auth/passkeys", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });

  // -----------------------------------------------------------------------
  // S13) Token with missing aud claim is rejected
  // -----------------------------------------------------------------------
  test("token without aud claim is rejected", async ({ page }) => {
    await registerUser(page, "No Aud Test");

    const status = await page.evaluate(async () => {
      const { getPrivateKey, getDeviceIdentity } =
        await import("/src/auth/deviceKey.ts");
      const privateKey = await getPrivateKey();
      const identity = await getDeviceIdentity();

      // Manually build a JWT WITHOUT aud claim
      const header = btoa(
        JSON.stringify({
          alg: "ES256",
          typ: "JWT",
          kid: identity!.deviceId,
        }),
      )
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const now = Math.floor(Date.now() / 1000);
      const payload = btoa(
        JSON.stringify({
          sub: identity!.userId,
          iat: now,
          exp: now + 900,
          // NO aud claim
        }),
      )
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const signingInput = new TextEncoder().encode(`${header}.${payload}`);
      const sigBytes = await crypto.subtle.sign(
        { name: "ECDSA", hash: "SHA-256" },
        privateKey!,
        signingInput,
      );
      const sig = btoa(String.fromCharCode(...new Uint8Array(sigBytes)))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const token = `${header}.${payload}.${sig}`;

      const res = await fetch("/api/auth/passkeys", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });

  // -----------------------------------------------------------------------
  // S14) Token with non-existent kid is rejected
  // -----------------------------------------------------------------------
  test("token with non-existent kid is rejected", async ({ page }) => {
    await registerUser(page, "Bad Kid Test");

    const status = await page.evaluate(async () => {
      const { getPrivateKey } = await import("/src/auth/deviceKey.ts");
      const privateKey = await getPrivateKey();

      // Manually build a JWT with a kid that doesn't exist in the DB
      const header = btoa(
        JSON.stringify({
          alg: "ES256",
          typ: "JWT",
          kid: "dfakedevice00000000000000000000",
        }),
      )
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const now = Math.floor(Date.now() / 1000);
      const payload = btoa(
        JSON.stringify({
          sub: "ufakeuser0000000000000000000000",
          iat: now,
          exp: now + 900,
          aud: "h4ckath0n:http",
        }),
      )
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const signingInput = new TextEncoder().encode(`${header}.${payload}`);
      const sigBytes = await crypto.subtle.sign(
        { name: "ECDSA", hash: "SHA-256" },
        privateKey!,
        signingInput,
      );
      const sig = btoa(String.fromCharCode(...new Uint8Array(sigBytes)))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      const token = `${header}.${payload}.${sig}`;

      const res = await fetch("/api/auth/passkeys", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });
});

test.describe("Security: WebSocket without token", () => {
  // -----------------------------------------------------------------------
  // S15) WebSocket without token is rejected
  // -----------------------------------------------------------------------
  test("WebSocket connection without token is rejected", async ({ page }) => {
    await page.goto("/");

    const result = await page.evaluate(async () => {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${proto}//${window.location.host}/api/demo/ws`;

      return new Promise<{ code: number; gotMessage: boolean }>((resolve) => {
        let gotMessage = false;
        const ws = new WebSocket(wsUrl);
        ws.addEventListener("message", () => {
          gotMessage = true;
        });
        ws.addEventListener("close", (ev) => {
          resolve({ code: ev.code, gotMessage });
        });
        ws.addEventListener("error", () => {});
        setTimeout(() => resolve({ code: -1, gotMessage }), 10_000);
      });
    });

    expect(result.gotMessage).toBe(false);
    expect([1006, 1008]).toContain(result.code);
  });
});
