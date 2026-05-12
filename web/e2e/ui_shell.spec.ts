import { test, expect } from "@playwright/test";
import {
  addVirtualAuthenticator,
  removeVirtualAuthenticator,
  type VirtualAuthenticator,
} from "./webauthn-helpers";

/**
 * E2E tests for responsive UI shell behavior.
 *
 * Tests run across three viewports:
 * - Portrait phone: 390×844
 * - Landscape phone: 844×390
 * - Desktop: 1280×720
 */

let auth: VirtualAuthenticator;

/** Register a unique user and land on /dashboard. */
async function registerUser(
  page: import("@playwright/test").Page,
  email: string,
): Promise<void> {
  await page.goto("/register");
  await page.getByTestId("register-email").fill(email);
  await page.getByTestId("register-email-submit").click();
  await page.getByTestId("register-submit").click();
  await expect(page.getByTestId("register-display-name")).toBeVisible({
    timeout: 15_000,
  });
  await page.getByTestId("register-finish").click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
}

test.describe("Responsive nav switching", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });
  test.afterEach(async () => {
    await removeVirtualAuthenticator(auth);
  });

  test("portrait: bottom-nav visible, nav-rail not visible", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await registerUser(page, `portrait-nav-${Date.now()}@example.com`);
    await expect(page.getByTestId("bottom-nav")).toBeVisible();
    await expect(page.getByTestId("nav-rail")).not.toBeVisible();
  });

  test("landscape phone: bottom-nav visible, nav-rail not visible", async ({
    page,
  }) => {
    // Landscape phones (short edge < 600) stay in phone/bottom-nav mode
    await page.setViewportSize({ width: 844, height: 390 });
    await registerUser(page, `landscape-nav-${Date.now()}@example.com`);
    await expect(page.getByTestId("bottom-nav")).toBeVisible();
    await expect(page.getByTestId("nav-rail")).not.toBeVisible();
  });

  test("desktop: nav-rail visible, bottom-nav not visible", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await registerUser(page, `desktop-nav-${Date.now()}@example.com`);
    await expect(page.getByTestId("nav-rail")).toBeVisible();
    await expect(page.getByTestId("bottom-nav")).not.toBeVisible();
  });
});

test.describe("Split view chat behavior", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });
  test.afterEach(async () => {
    await removeVirtualAuthenticator(auth);
  });

  test("desktop dashboard shows chat-list-pane", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await registerUser(page, `desktop-split-${Date.now()}@example.com`);
    // On dashboard, chat-list-pane should be visible
    await expect(page.getByTestId("chat-list-pane")).toBeVisible();
  });
});

test.describe("Sessions error vs empty", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });
  test.afterEach(async () => {
    await removeVirtualAuthenticator(auth);
  });

  test("mock /auth/sessions to 500 shows error banner, not empty state", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await registerUser(page, `sessions-err-${Date.now()}@example.com`);

    // Intercept /auth/sessions to return 500
    await page.route("**/auth/sessions", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      }),
    );

    // Navigate to settings
    await page.getByTestId("nav-settings").click();
    await expect(page).toHaveURL(/\/settings/, { timeout: 10_000 });

    // Error banner should be visible
    await expect(page.getByTestId("sessions-error")).toBeVisible({
      timeout: 10_000,
    });
  });
});
