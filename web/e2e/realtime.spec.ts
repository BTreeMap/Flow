import { test, expect, type Page } from "@playwright/test";
import {
  addVirtualAuthenticator,
  removeVirtualAuthenticator,
  type VirtualAuthenticator,
} from "./webauthn-helpers";

/**
 * End-to-end tests for the WebSocket and SSE realtime demo.
 *
 * These tests run serially (shared SQLite state) and each test
 * registers a fresh user via passkey before exercising the realtime
 * features.
 */

let auth: VirtualAuthenticator;

/** Register a new user via passkey and navigate to the realtime demo page. */
async function registerAndGoToRealtime(page: Page): Promise<void> {
  await page.goto("/register");
  await page.getByTestId("register-display-name").fill("RT E2E User");
  await page.getByTestId("register-submit").click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
  await page.goto("/demo/realtime");
  await expect(page.getByTestId("realtime-heading")).toBeVisible({
    timeout: 10_000,
  });
}

test.describe("Realtime demo", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) {
      await removeVirtualAuthenticator(auth);
    }
  });

  // -----------------------------------------------------------------------
  // D1) WebSocket – positive test
  // -----------------------------------------------------------------------
  test("WebSocket: connect, receive welcome and heartbeat, send echo", async ({
    page,
  }) => {
    await registerAndGoToRealtime(page);

    // Click Connect
    await page.getByTestId("ws-connect").click();

    const wsLog = page.getByTestId("ws-log");

    // Wait for welcome message
    await expect(wsLog).toContainText('"type":"welcome"', { timeout: 10_000 });

    // Wait for at least one heartbeat
    await expect(wsLog).toContainText('"type":"heartbeat"', {
      timeout: 10_000,
    });

    // Send echo message
    await page.getByTestId("ws-input").fill("hello realtime");
    await page.getByTestId("ws-send").click();

    // Expect echo with reversed text
    await expect(wsLog).toContainText('"type":"echo"', { timeout: 5_000 });
    await expect(wsLog).toContainText("emitlaer olleh", {
      timeout: 5_000,
    });

    // Disconnect
    await page.getByTestId("ws-disconnect").click();
    await expect(wsLog).toContainText("[closed", { timeout: 5_000 });
  });

  // -----------------------------------------------------------------------
  // D2) WebSocket – negative test (wrong aud)
  // -----------------------------------------------------------------------
  test("WebSocket: wrong aud token is rejected", async ({ page }) => {
    await registerAndGoToRealtime(page);

    // Mint a token with http usage (wrong for WS) and try to connect
    const result = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("http"); // Wrong aud!

      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${proto}//${window.location.host}/api/demo/ws?token=${encodeURIComponent(token)}`;

      return new Promise<{ code: number; reason: string; gotMessage: boolean }>(
        (resolve) => {
          let gotMessage = false;
          const ws = new WebSocket(wsUrl);
          ws.addEventListener("message", () => {
            gotMessage = true;
          });
          ws.addEventListener("close", (event) => {
            resolve({
              code: event.code,
              reason: event.reason,
              gotMessage,
            });
          });
          ws.addEventListener("error", () => {
            // error fires before close for rejected connections
          });
          setTimeout(
            () => resolve({ code: -1, reason: "timeout", gotMessage }),
            10_000,
          );
        },
      );
    });

    // The connection should close without receiving any application messages.
    // The exact close code may vary (1008 or 1006) depending on the server
    // closing before or after accept, but the key assertion is: no welcome
    // message was received.
    expect(result.gotMessage).toBe(false);
    // Close code should be either 1008 (policy violation) or 1006 (abnormal)
    expect([1006, 1008]).toContain(result.code);
  });

  // -----------------------------------------------------------------------
  // D3) SSE – positive test
  // -----------------------------------------------------------------------
  test("SSE: start stream, receive chunks and done event", async ({
    page,
  }) => {
    await registerAndGoToRealtime(page);

    // Click Start Stream
    await page.getByTestId("sse-start").click();

    const sseLog = page.getByTestId("sse-log");

    // Wait for stream opened
    await expect(sseLog).toContainText("[stream opened]", { timeout: 10_000 });

    // Wait for at least one chunk
    await expect(sseLog).toContainText("[chunk]", { timeout: 10_000 });

    // Wait for done
    await expect(sseLog).toContainText("[done]", { timeout: 15_000 });
    await expect(sseLog).toContainText('"ok": true', { timeout: 5_000 });

    // Verify multiple chunks arrived in order
    const logText = await sseLog.textContent();
    const chunkMatches = logText?.match(/\[chunk\]/g);
    expect(chunkMatches?.length).toBeGreaterThanOrEqual(3);
  });

  // -----------------------------------------------------------------------
  // D4) SSE – negative test (wrong aud)
  // -----------------------------------------------------------------------
  test("SSE: wrong aud token is rejected with 401", async ({ page }) => {
    await registerAndGoToRealtime(page);

    // Use page.evaluate to make a direct SSE-style fetch with a ws-aud token
    const status = await page.evaluate(async () => {
      const { getOrMintToken } = await import("/src/auth/token.ts");
      const token = await getOrMintToken("ws"); // Wrong aud for SSE!

      const res = await fetch("/api/demo/sse", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status;
    });

    expect(status).toBe(401);
  });
});
