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

test.describe("Chat Experience Walkthrough (Real Backend)", () => {
  test.beforeEach(async ({ page }) => {
    // Force mobile viewport for full navigation flow testing (Dashboard -> Chat -> Back)
    await page.setViewportSize({ width: 390, height: 844 });

    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) {
      await removeVirtualAuthenticator(auth);
    }
  });

  test("User creates account, joins seeded project, completes onboarding, and chats", async ({
    page,
  }) => {
    // -----------------------------------------------------------------------
    // STEP 0: Seed Data (Server-side)
    // -----------------------------------------------------------------------
    try {
        const __filename = fileURLToPath(import.meta.url);
        const __dirname = path.dirname(__filename);
        const apiDir = path.resolve(__dirname, "../../api");
        // Ensure H4CKATH0N_DATABASE_URL matches playwright.config.ts
        const env = { ...process.env, H4CKATH0N_DATABASE_URL: "sqlite+aiosqlite:////tmp/flow-e2e.db" };
        execSync("uv run scripts/seed_e2e.py", { cwd: apiDir, env, stdio: 'inherit' });
    } catch (e) {
        console.error("Failed to seed DB:", e);
        throw e;
    }

    const projectId = "ptestproject123456789012345678901";
    const inviteCodeStr = "test-invite-code-123";

    // -----------------------------------------------------------------------
    // STEP 1: Registration
    // -----------------------------------------------------------------------
    const userEmail = "chat-test@example.com";
    await page.goto("/");
    await page.getByTestId("landing-register").click();
    await page.getByTestId("register-email").fill(userEmail);
    await page.getByTestId("register-email-submit").click();
    await page.getByTestId("register-submit").click();
    await page.getByTestId("register-display-name").fill("Chat User");
    await page.getByTestId("register-finish").click();

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByTestId("dashboard-heading")).toHaveText("Chats");

    // -----------------------------------------------------------------------
    // STEP 3: Claim Invite (Project already created via seed)
    // -----------------------------------------------------------------------
    // Navigate directly to activation page with the invite code in query param
    await page.goto(`/p/${projectId}/activate?invite=${inviteCodeStr}`);

    // Now just click Join
    await page.getByRole("button", { name: "Join Project" }).click();

    // -----------------------------------------------------------------------
    // STEP 4: Notifications Onboarding
    // -----------------------------------------------------------------------
    // After claim, user lands on notifications onboarding
    await expect(page).toHaveURL(new RegExp(`/p/${projectId}/onboarding/notifications`), { timeout: 20000 });

    // VAPID keys are missing in test env, so "Enable" is disabled. Click Skip.
    await page.getByRole("button", { name: "Skip for now" }).click();

    // Finally, we should be at chat
    await expect(page).toHaveURL(new RegExp(`/p/${projectId}/chat`), { timeout: 20000 });

    // -----------------------------------------------------------------------
    // STEP 6: Chat Experience
    // -----------------------------------------------------------------------
    await expect(page.getByRole("heading", { name: "E2E Project" })).toBeVisible();

    // Note: The backend is supposed to send an initial greeting, but in Stub mode or some environments
    // it might fail silently or take time. To be robust, we proceed to send a message immediately
    // if the chat is ready.

    // -----------------------------------------------------------------------
    // STEP 7: Send Message
    // -----------------------------------------------------------------------
    const input = page.getByPlaceholder("Type a message…");
    await input.fill("Hello Real Backend");
    await page.getByRole("button", { name: "Send" }).click();

    // Verify Optimistic UI
    await expect(page.getByText("Hello Real Backend")).toBeVisible();
    await expect(input).toHaveValue("");

    // Verify Response (Assistant replies)
    // Now we definitely expect a response from the backend (Stub or LLM).
    // Stub response is usually immediate.
    // We look for ANY assistant message.
    // Note: With streaming, we might see partial content, but eventually full content.
    await expect(page.getByTestId("assistant-markdown")).toBeVisible({ timeout: 30000 });

    // -----------------------------------------------------------------------
    // STEP 8: Verify Persistence (Reload)
    // -----------------------------------------------------------------------
    // Ensure the user message is still there (fix verification)
    await expect(page.getByText("Hello Real Backend")).toBeVisible();

    await page.reload();
    await expect(page.getByText("Hello Real Backend")).toBeVisible();
    await expect(page.getByRole("heading", { name: "E2E Project" })).toBeVisible();

    // -----------------------------------------------------------------------
    // STEP 9: Back Navigation
    // -----------------------------------------------------------------------
    await page.getByRole("button", { name: "Back" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await expect(page.getByText("E2E Project")).toBeVisible();
  });
});
