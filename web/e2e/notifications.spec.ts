import { test, expect } from "@playwright/test";
import {
  addVirtualAuthenticator,
  removeVirtualAuthenticator,
  type VirtualAuthenticator,
} from "./webauthn-helpers";

let auth: VirtualAuthenticator;

test.describe("Notifications Flow", () => {
  test.beforeEach(async ({ page }) => {
    auth = await addVirtualAuthenticator(page);
  });

  test.afterEach(async () => {
    if (auth) {
      await removeVirtualAuthenticator(auth);
    }
  });

  test("receive notification, view in updates, click to chat", async ({ page, request }) => {
    // 1. Register User
    await page.goto("/");
    await page.getByTestId("landing-register").click();
    await page.getByTestId("register-email").fill("notif-test@example.com");
    await page.getByTestId("register-email-submit").click();
    await page.getByTestId("register-submit").click();
    await page.getByTestId("register-display-name").fill("Notif User");
    await page.getByTestId("register-finish").click();
    await expect(page).toHaveURL(/\/dashboard/);

    // Get auth token for backend calls
    const storageState = await page.context().storageState();
    // In real app, token is in IndexedDB or memory, hard to grab in E2E directly without exposing it.
    // However, the session cookie/header might be sufficient if using cookie auth, but we use Bearer token.
    // Strategy: We can use the scheduled nudge tool via the agent API if exposed, OR just use the project ID to manually insert via a "test-only" endpoint if we had one.
    // BUT, we don't have a clean way to inject a notification from E2E without backend access.
    // Workaround: We will use the `schedule_nudge` tool via a new conversation if possible, OR we rely on the fact that `ChatThread` polls.
    // Actually, simply verifying that IF a notification exists, the UI works is enough if we can seed it.
    // Since we can't easily seed the DB from here without `psql` or a backdoor, we will skip the "creation" part in this specific E2E environment
    // UNLESS we can trigger it via a message to the bot like "schedule a nudge".
    // But the agent prompts might not support that explicitly yet.

    // Alternative: We can mock the `/api/p/:id/notifications` response using Playwright's route interception!
    // This allows us to test the frontend flow without relying on the complex backend worker timing.

    // 2. Identify Project ID
    // Extract project ID from URL or Dashboard
    const dashboardUrl = page.url();
    // wait for list to load
    await expect(page.getByText("Tap to manage notifications")).toBeVisible({ timeout: 10000 }).catch(() => {});

    // Actually, let's claim an invite to get a project if dashboard is empty?
    // But registration creates a user, does it create a project? No, usually landing -> register -> dashboard (empty).
    // User needs to CREATE a project or CLAIM an invite.
    // The previous E2E `compose.spec.ts` stops at dashboard.

    // Let's intercept the dashboard response to return a fake project membership to ensure we have one.
    // OR better, we use the `admin/projects` API if we were admin.

    // Let's go with Route Interception for Notifications API.
    // We need a project ID. Let's make up one "p_test_project_123" and navigate to it.
    const fakeProjectId = "p_testproject1234567890123456789"; // 32 chars 'p' + 31

    // Mock Dashboard to show this project
    await page.route("**/api/dashboard", async route => {
        const json = {
            memberships: [{
                project_id: fakeProjectId,
                display_name: "Test Project",
                status: "active"
            }]
        };
        await route.fulfill({ json });
    });

    // Mock Notifications List
    const notificationId = 999;
    await page.route(`**/api/p/${fakeProjectId}/notifications`, async route => {
        const json = {
            notifications: [{
                id: notificationId,
                title: "E2E Nudge",
                body: "This is a test nudge body.",
                created_at: new Date().toISOString(),
                read_at: null
            }]
        };
        await route.fulfill({ json });
    });

    // Mock Mark Read
    await page.route(`**/api/p/${fakeProjectId}/notifications/${notificationId}/read`, async route => {
         await route.fulfill({ json: { ok: true } });
    });

    // Reload dashboard to see the mocked project
    await page.goto("/dashboard");
    await expect(page.getByText("Test Project")).toBeVisible();

    // 3. Go to Updates Tab
    // Click the project or the "Updates" nav item.
    // The "Updates" page in the AppShell lists ALL updates? No, `UpdatesPage.tsx` takes `:projectId`.
    // Wait, `App.tsx` has `path="/updates"` (global?) AND `/p/:projectId/updates`.
    // The sidebar link `/updates` goes to `src/pages/Updates.tsx` which lists projects.
    // `src/pages/UpdatesPage.tsx` is the detail view for a project.

    // Click "Updates" in bottom nav/sidebar
    await page.click('a[href="/updates"]'); // Adjust selector based on AppShell

    // Should see the project listed in the Updates list
    // Use first() or specific role to check visibility without strict mode error
    await expect(page.getByRole("link", { name: "Test Project View daily" })).toBeVisible();

    // Click the project row to go to project updates
    await page.getByRole("link", { name: "Test Project View daily" }).click();

    // Now we are at /p/:id/updates (mocked)
    await expect(page).toHaveURL(new RegExp(`/p/${fakeProjectId}/updates`));
    await expect(page.getByText("E2E Nudge")).toBeVisible();
    await expect(page.getByText("This is a test nudge body.")).toBeVisible();

    // 4. Click the Notification Card
    await page.getByText("E2E Nudge").click();

    // 5. Verify Navigation to Chat
    await expect(page).toHaveURL(new RegExp(`/p/${fakeProjectId}/chat`));

    // Verify Chat Page loads (mock chat messages if needed, or just header)
    // We didn't mock chat messages, so it might error or show loading, but URL check confirms the "click -> nav" flow.
  });
});
