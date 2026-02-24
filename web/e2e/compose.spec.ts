import { test, expect } from "@playwright/test";
import {
  addVirtualAuthenticator,
  removeVirtualAuthenticator,
  type VirtualAuthenticator,
} from "./webauthn-helpers";

/**
 * Compose-stack E2E tests.
 *
 * These tests validate that the Caddy reverse proxy (flow-web) correctly:
 *   - Serves static frontend files
 *   - Handles SPA deep links (React Router)
 *   - Proxies /api/* to the backend with prefix stripping
 *   - Supports SSE streaming through the proxy
 *
 * Run with PLAYWRIGHT_BASE_URL=http://localhost:8080 to target the compose stack
 * instead of the Vite dev server. Playwright will NOT start local dev servers
 * when this env var is set.
 */

let auth: VirtualAuthenticator;

test.describe("Compose stack: static serving and SPA", () => {
  // -----------------------------------------------------------------------
  // C1) Landing page loads (static file serving)
  // -----------------------------------------------------------------------
  test("landing page loads", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("landing-register")).toBeVisible({
      timeout: 15_000,
    });
  });

  // -----------------------------------------------------------------------
  // C2) SPA deep link: /login
  // -----------------------------------------------------------------------
  test("SPA deep link /login returns the app", async ({ page }) => {
    await page.goto("/login");
    // The login page should render (not a 404)
    await expect(page.getByTestId("login-submit")).toBeVisible({
      timeout: 15_000,
    });
  });

  // -----------------------------------------------------------------------
  // C3) SPA deep link: /register
  // -----------------------------------------------------------------------
  test("SPA deep link /register returns the app", async ({ page }) => {
    await page.goto("/register");
    // The register page now starts with the email step
    await expect(page.getByTestId("register-email")).toBeVisible({
      timeout: 15_000,
    });
  });
});

test.describe("Compose stack: API proxy and SSE", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) {
      await removeVirtualAuthenticator(auth);
    }
  });

  // -----------------------------------------------------------------------
  // C4) API call through /api proxy (prefix stripped by Caddy)
  // -----------------------------------------------------------------------
  test("API call through /api proxy works", async ({ page }) => {
    // /api/demo/ping is unauthenticated; Caddy strips /api → backend /demo/ping
    await page.goto("/");
    const res = await page.request.get("/api/demo/ping");
    if (!res.ok()) {
      console.log("status", res.status());
      console.log("body", await res.text());
    }
    expect(res.ok()).toBe(true);
    const body = await res.json();
    expect(body).toEqual({ ok: true });
  });

  // -----------------------------------------------------------------------
  // C5) Health check through /api proxy
  // -----------------------------------------------------------------------
  test("health check through /api proxy", async ({ page }) => {
    await page.goto("/");
    const res = await page.request.get("/api/healthz");
    expect(res.ok()).toBe(true);
  });

  // -----------------------------------------------------------------------
  // C6) Register and reach dashboard through compose stack
  // -----------------------------------------------------------------------
  test("register via passkey and reach dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("landing-register")).toBeVisible();
    await page.getByTestId("landing-register").click();
    await expect(page).toHaveURL(/\/register/);

    // Step 1: Email
    await page.getByTestId("register-email").fill("compose-e2e@example.com");
    await page.getByTestId("register-email-submit").click();

    // Step 2: Passkey enrollment
    await page.getByTestId("register-submit").click();

    // Step 3: Display name (pre-filled from email) – confirm
    await expect(page.getByTestId("register-display-name")).toBeVisible({
      timeout: 15_000,
    });
    await page.getByTestId("register-display-name").fill("Compose E2E User");
    await page.getByTestId("register-finish").click();

    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
    await expect(page.getByTestId("dashboard-heading")).toBeVisible();
  });
});
