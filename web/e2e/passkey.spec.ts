import { test, expect } from "@playwright/test";
import {
  addVirtualAuthenticator,
  removeVirtualAuthenticator,
  type VirtualAuthenticator,
} from "./webauthn-helpers";

/**
 * End-to-end tests for the passkey (WebAuthn) authentication flows.
 *
 * These tests use Chromium's CDP virtual authenticator to simulate
 * passkey operations without a physical security key or biometric.
 *
 * The tests run **serially** (fullyParallel: false, workers: 1) because
 * they share server-side state (SQLite database) and each test builds
 * on the state established by previous tests.
 *
 * Registration is a 3-step stepper: email → passkey enrollment → display name.
 */

let auth: VirtualAuthenticator;

/** Perform the full 3-step registration flow and land on /dashboard. */
async function registerViaPasskey(
  page: import("@playwright/test").Page,
  email: string,
  displayName?: string,
): Promise<void> {
  // Step 1: Email
  await page.getByTestId("register-email").fill(email);
  await page.getByTestId("register-email-submit").click();

  // Step 2: Passkey enrollment
  await page.getByTestId("register-submit").click();

  // Step 3: Display name (pre-filled from email local-part)
  await expect(page.getByTestId("register-display-name")).toBeVisible({
    timeout: 15_000,
  });
  if (displayName) {
    await page.getByTestId("register-display-name").fill(displayName);
  }
  await page.getByTestId("register-finish").click();

  // Should arrive at /dashboard
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
}

test.describe("Passkey auth flows", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) {
      await removeVirtualAuthenticator(auth);
    }
  });

  // -----------------------------------------------------------------------
  // 1) Registration – user registers via passkey and reaches Dashboard
  // -----------------------------------------------------------------------
  test("register with passkey and reach dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("landing-register")).toBeVisible();

    // Navigate to register page
    await page.getByTestId("landing-register").click();
    await expect(page).toHaveURL(/\/register/);

    // Complete 3-step registration
    await registerViaPasskey(page, "e2e-test@example.com", "E2E Test User");
    await expect(page.getByTestId("dashboard-heading")).toBeVisible();

    // Verify backend auth works – hit /api/health (library-provided)
    const healthRes = await page.request.get("http://localhost:8000/health");
    expect(healthRes.ok()).toBe(true);
    const healthBody = await healthRes.json();
    expect(healthBody.status).toBe("healthy");

    // ── Library endpoint: GET /auth/passkeys via the UI ───────────────
    // The Settings page uses the typed openapi-fetch client to list passkeys.
    await page.getByTestId("nav-settings").click();
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.getByTestId("passkey-item")).toHaveCount(1, {
      timeout: 10_000,
    });
  });

  // -----------------------------------------------------------------------
  // 2) Demo endpoints return correct data via direct API calls
  // -----------------------------------------------------------------------
  test("demo endpoints return expected shapes", async ({ page }) => {
    // GET /demo/ping – unauthenticated
    const pingRes = await page.request.get("http://localhost:8000/demo/ping");
    expect(pingRes.ok()).toBe(true);
    const ping = await pingRes.json();
    expect(ping).toEqual({ ok: true });

    // POST /demo/echo – unauthenticated
    const echoRes = await page.request.post("http://localhost:8000/demo/echo", {
      data: { message: "hello" },
    });
    expect(echoRes.ok()).toBe(true);
    const echo = await echoRes.json();
    expect(echo).toEqual({ message: "hello", reversed: "olleh" });
  });

  // -----------------------------------------------------------------------
  // 3) Logout then login with passkey
  // -----------------------------------------------------------------------
  test("logout and login with passkey", async ({ page }) => {
    // First register
    await page.goto("/register");
    await registerViaPasskey(page, "e2e-login@example.com", "E2E Login User");

    // Logout via Settings page
    await page.getByTestId("nav-settings").click();
    await expect(page).toHaveURL(/\/settings/, { timeout: 10_000 });
    await page.getByTestId("settings-logout").click();
    // After logout, app may navigate to "/" or ProtectedRoute may redirect to "/login"
    await expect(page).toHaveURL(/\/(login)?$/, { timeout: 10_000 });

    // Login with passkey
    await page.goto("/login");
    await page.getByTestId("login-submit").click();

    // Should redirect to dashboard
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
    await expect(page.getByTestId("dashboard-heading")).toBeVisible();
  });

  // -----------------------------------------------------------------------
  // 4) Add a second passkey
  // -----------------------------------------------------------------------
  test("add a second passkey", async ({ page }) => {
    // Register
    await page.goto("/register");
    await registerViaPasskey(page, "e2e-multikey@example.com", "E2E Multi Key");

    // Go to settings
    await page.getByTestId("nav-settings").click();
    await expect(page).toHaveURL(/\/settings/);

    // Wait for passkey list to load – should show 1 active
    await expect(page.getByTestId("passkey-item")).toHaveCount(1, {
      timeout: 10_000,
    });

    // Swap to a fresh virtual authenticator to simulate a different device.
    // The excludeCredentials check would reject the same authenticator.
    await removeVirtualAuthenticator(auth);
    auth = await addVirtualAuthenticator(page);

    // Add second passkey
    await page.getByTestId("add-passkey-btn").click();

    // Wait for the second passkey to appear
    await expect(page.getByTestId("passkey-item")).toHaveCount(2, {
      timeout: 15_000,
    });

    await page.getByTestId("passkey-edit-btn").first().click();
    await page.getByTestId("passkey-name-input").fill("Laptop key");
    await page.getByTestId("passkey-name-save").click();
    await expect(page.getByTestId("passkey-name").first()).toContainText(
      "Laptop key",
    );
  });

  // -----------------------------------------------------------------------
  // 5) Revoke passkey + LAST_PASSKEY invariant
  // -----------------------------------------------------------------------
  test("revoke passkey and LAST_PASSKEY invariant", async ({ page }) => {
    // Register
    await page.goto("/register");
    await registerViaPasskey(
      page,
      "e2e-revoke@example.com",
      "E2E Revoke User",
    );

    // Go to settings
    await page.getByTestId("nav-settings").click();
    await expect(page).toHaveURL(/\/settings/);

    // Should have 1 passkey
    await expect(page.getByTestId("passkey-item")).toHaveCount(1, {
      timeout: 10_000,
    });

    // Try to revoke the only passkey – should fail with LAST_PASSKEY error
    await page.getByTestId("revoke-passkey-btn").click();
    await expect(page.getByTestId("last-passkey-error")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("last-passkey-error")).toContainText(
      "Cannot revoke your last active passkey",
    );

    // Swap to a fresh authenticator to simulate a different device
    await removeVirtualAuthenticator(auth);
    auth = await addVirtualAuthenticator(page);

    // Add a second passkey
    await page.getByTestId("add-passkey-btn").click();
    await expect(page.getByTestId("passkey-item")).toHaveCount(2, {
      timeout: 15_000,
    });

    // Now we should have 2 active passkeys – revoke the first one
    const revokeButtons = page.getByTestId("revoke-passkey-btn");
    await expect(revokeButtons).toHaveCount(2);
    await revokeButtons.first().click();

    // Wait for revocation to complete – one item should show "(revoked)"
    await expect(page.getByText("(revoked)")).toBeVisible({ timeout: 10_000 });

    // Only 1 revoke button should remain (the other passkey is revoked)
    await expect(page.getByTestId("revoke-passkey-btn")).toHaveCount(1);
  });
});
