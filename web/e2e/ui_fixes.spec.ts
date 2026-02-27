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

test.describe("Chat UI and Debugging", () => {
  test.beforeEach(async ({ page }) => {
    // Use mobile viewport to ensure "Back" button is visible (it is hidden in desktop "side" layout)
    await page.setViewportSize({ width: 390, height: 844 });
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) {
      await removeVirtualAuthenticator(auth);
    }
  });

  test("Chat messages are ordered correctly and left panel updates", async ({
    page,
  }) => {
    // -----------------------------------------------------------------------
    // STEP 0: Seed Data (Server-side)
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
    // STEP 1: Registration (Unique User)
    // -----------------------------------------------------------------------
    const uniqueId = Date.now().toString().slice(-6);
    const userEmail = `ui-test-${uniqueId}@example.com`;

    await page.goto("/");
    await page.getByTestId("landing-register").click();
    await page.getByTestId("register-email").fill(userEmail);
    await page.getByTestId("register-email-submit").click();
    await page.getByTestId("register-submit").click();
    await page.getByTestId("register-display-name").fill("UI Tester");
    await page.getByTestId("register-finish").click();

    // Wait for registration to complete (PATCH /me saves the email)
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 });

    // -----------------------------------------------------------------------
    // STEP 2: Join Project
    // -----------------------------------------------------------------------
    await page.goto(`/p/${projectId}/activate?invite=${inviteCodeStr}`);

    // Wait for the button to be enabled and click it
    const joinButton = page.getByRole("button", { name: "Join Project" });
    await expect(joinButton).toBeEnabled();

    // Use Promise.all to wait for navigation or response
    // The click triggers an API call then navigation
    await joinButton.click();

    // After claim, user lands on notifications onboarding
    await expect(page).toHaveURL(new RegExp(`/p/${projectId}/onboarding/notifications`), { timeout: 15000 });

    // Wait for "Skip for now" to be visible and clickable
    const skipButton = page.getByRole("button", { name: "Skip for now" });
    await expect(skipButton).toBeVisible();
    await expect(skipButton).toBeEnabled();
    await skipButton.click();

    // Finally verify we reached the chat
    await expect(page).toHaveURL(new RegExp(`/p/${projectId}/chat`), { timeout: 20000 });

    // -----------------------------------------------------------------------
    // STEP 3: Test Message Ordering & Left Panel Update
    // -----------------------------------------------------------------------
    const userMessage = "Test Ordering Message";
    await page.getByPlaceholder("Type a message…").fill(userMessage);
    await page.getByRole("button", { name: "Send" }).click();

    // Wait for response
    await expect(page.getByTestId("assistant-markdown")).toBeVisible({ timeout: 30000 });

    // Verify ordering: User message should appear before Assistant message
    const userMsgLocator = page.getByText(userMessage);
    await expect(userMsgLocator).toBeVisible();

    const userMsgBox = await userMsgLocator.boundingBox();

    // Get bounding box of assistant response
    const assistantBubbles = page.locator(".bg-bubble-in");
    await expect(assistantBubbles.last()).toBeVisible();
    const lastAssistantBubble = assistantBubbles.last();
    const asstMsgBox = await lastAssistantBubble.boundingBox();

    expect(userMsgBox).not.toBeNull();
    expect(asstMsgBox).not.toBeNull();

    // Assistant message (y) should be greater than User message (y) => below it
    expect(asstMsgBox!.y).toBeGreaterThan(userMsgBox!.y);

    // -----------------------------------------------------------------------
    // STEP 4: Verify Left Panel (Dashboard) Update
    // -----------------------------------------------------------------------
    // Go back to dashboard
    await page.getByRole("button", { name: "Back" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    // The preview should show the assistant's response (or at least not be empty/old)
    const preview = page.locator("a", { hasText: "E2E Project" }).locator("p").nth(1); // Secondary text
    await expect(preview).not.toHaveText("No messages yet");
  });
});
