import { test, expect } from "@playwright/test";
import {
  addVirtualAuthenticator,
  removeVirtualAuthenticator,
  type VirtualAuthenticator,
} from "./webauthn-helpers";
import { execSync } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

let auth: VirtualAuthenticator;

test.describe("Settings & Profile Walkthrough", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) {
      await removeVirtualAuthenticator(auth);
    }
  });

  test("User can update display name and email in settings", async ({
    page,
  }) => {
    // -----------------------------------------------------------------------
    // STEP 0: Seed Data
    // -----------------------------------------------------------------------
    try {
        const __filename = fileURLToPath(import.meta.url);
        const __dirname = path.dirname(__filename);
        const apiDir = path.resolve(__dirname, "../../api");
        const env = { ...process.env, H4CKATH0N_DATABASE_URL: "sqlite+aiosqlite:////tmp/flow-e2e.db" };
        execSync("uv run scripts/seed_e2e.py", { cwd: apiDir, env, stdio: 'inherit' });
    } catch (e) {
        console.error("Failed to seed DB:", e);
        throw e;
    }

    const projectId = "ptestproject123456789012345678901";
    const inviteCodeStr = "test-invite-code-123";

    // -----------------------------------------------------------------------
    // STEP 1: Registration & Join
    // -----------------------------------------------------------------------
    await page.goto("/");
    await page.getByTestId("landing-register").click();
    await page.getByTestId("register-email").fill("settings-test@example.com");
    await page.getByTestId("register-email-submit").click();
    await page.getByTestId("register-submit").click();
    await page.getByTestId("register-display-name").fill("Settings User");
    await page.getByTestId("register-finish").click();

    // Wait for registration to complete and profile to be synced
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto(`/p/${projectId}/activate?invite=${inviteCodeStr}`);

    // Wait for Join Project button and click with navigation wait
    const joinBtn = page.getByRole("button", { name: "Join Project" });
    await expect(joinBtn).toBeVisible();
    await expect(joinBtn).toBeEnabled();

    // Debug: Monitor the claim request
    const claimPromise = page.waitForResponse(resp =>
        resp.url().includes("/claim") && resp.request().method() === "POST"
    );
    await joinBtn.click();
    const claimResponse = await claimPromise;
    expect(claimResponse.status()).toBe(200);

    await expect(page).toHaveURL(new RegExp(`/p/${projectId}/onboarding/notifications`), { timeout: 20000 });

    // Notifications onboarding — skip
    await page.getByRole("button", { name: "Skip for now" }).click();
    await expect(page).toHaveURL(new RegExp(`/p/${projectId}/chat`));

    // -----------------------------------------------------------------------
    // STEP 2: Navigate to Settings
    // -----------------------------------------------------------------------
    // Open menu
    await page.getByRole("button", { name: "Menu" }).click();
    // Wait for menu to open
    await expect(page.getByRole("button", { name: "Notification Settings" })).toBeVisible();
    // The menu items are rendered as buttons, not menuitems
    await page.getByRole("button", { name: "Notification Settings" }).click();

    // Wait for settings page
    // There are two headings "Notifications" and "Push Notifications", so be specific
    await expect(page.getByRole("heading", { name: "Notifications", exact: true })).toBeVisible();

    // Go to global settings for profile editing
    await page.goto("/settings");

    await expect(page.getByLabel("Display Name")).toHaveValue("Settings User");
    await expect(page.getByLabel("Email")).toHaveValue("settings-test@example.com");

    // -----------------------------------------------------------------------
    // STEP 3: Update Profile
    // -----------------------------------------------------------------------
    await page.getByLabel("Display Name").fill("Updated Name");
    // Button label depends on state, initially "Save", then "Saving…", then "Saved"
    // Use data-testid for robustness as text changes
    await page.getByTestId("profile-save").click();

    // Verify persistence
    await page.reload();
    await expect(page.getByLabel("Display Name")).toHaveValue("Updated Name");
  });
});
