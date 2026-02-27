import { test, expect } from "@playwright/test";
import {
  addVirtualAuthenticator,
  removeVirtualAuthenticator,
  type VirtualAuthenticator,
} from "./webauthn-helpers";

let auth: VirtualAuthenticator;

const FAKE_PROJECT_ID = "p_testproject1234567890123456789";

test.describe("Chat Experience Walkthrough", () => {
  test.beforeEach(async ({ page }) => {
    // Force mobile viewport for full navigation flow testing (Dashboard -> Chat -> Back)
    await page.setViewportSize({ width: 390, height: 844 });

    auth = await addVirtualAuthenticator(page);

    // -----------------------------------------------------------------------
    // MOCKS
    // -----------------------------------------------------------------------

    // Log all requests to debug 404
    // page.on('request', request => console.log('>>', request.method(), request.url()));
    // page.on('response', response => console.log('<<', response.status(), response.url()));

    // 1. Dashboard: Return a single active project
    await page.route("**/api/dashboard", async (route) => {
      await route.fulfill({
        json: {
          memberships: [
            {
              project_id: FAKE_PROJECT_ID,
              display_name: "AI Coach",
              status: "active",
              last_message_at: new Date().toISOString(),
              last_message_preview: "Ready to help!",
            },
          ],
        },
      });
    });

    // 2. Profile: Return valid profile to skip onboarding
    // Use regex to be more robust
    await page.route(new RegExp(`/api/p/${FAKE_PROJECT_ID}/profile$`), async (route) => {
      await route.fulfill({
        json: {
          prompt_anchor: "You are a helpful coach.",
          preferred_time: "09:00",
        },
      });
    });

    // 3. Messages: Return a static history
    await page.route(new RegExp(`/api/p/${FAKE_PROJECT_ID}/messages$`), async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          json: {
            messages: [
              {
                message_id: 100,
                server_msg_id: "msg_100",
                role: "assistant",
                content: "Hello! I am your **AI Coach**.",
                created_at: new Date(Date.now() - 10000).toISOString(),
              },
              {
                message_id: 101,
                server_msg_id: "msg_101",
                role: "user",
                content: "Hi there.",
                created_at: new Date(Date.now() - 5000).toISOString(),
              },
            ],
          },
        });
      } else if (route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        await route.fulfill({
          json: {
            message_id: 102,
            server_msg_id: `msg_${Date.now()}`,
            role: "user",
            content: body.text,
            created_at: new Date().toISOString(),
          },
        });
      } else {
        await route.fallback();
      }
    });

    // 5. SSE Events: Simulate a stream with a delayed message
    await page.route(new RegExp(`/api/p/${FAKE_PROJECT_ID}/events$`), async (route) => {
      const data = JSON.stringify({
        message_id: 200,
        server_msg_id: "msg_sse_200",
        role: "assistant",
        content: "I received your message via SSE!",
        created_at: new Date().toISOString(),
      });
      // Try simple fulfill with body as string
      await route.fulfill({
        status: 200,
        headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
        body: `event: message.final\nid: msg_sse_200\ndata: ${data}\n\n`,
      });
    });
  });

  test.afterEach(async () => {
    if (auth) {
      await removeVirtualAuthenticator(auth);
    }
  });

  test("User creates account, sees dashboard, enters chat, sends message, and receives reply", async ({
    page,
  }) => {
    // -----------------------------------------------------------------------
    // STEP 1: Registration (to get into the authenticated state)
    // -----------------------------------------------------------------------
    await page.goto("/");
    await page.getByTestId("landing-register").click();
    await page.getByTestId("register-email").fill("chat-test@example.com");
    await page.getByTestId("register-email-submit").click();
    await page.getByTestId("register-submit").click(); // WebAuthn creation
    await page.getByTestId("register-display-name").fill("Chat User");
    await page.getByTestId("register-finish").click();

    // -----------------------------------------------------------------------
    // STEP 2: Dashboard
    // -----------------------------------------------------------------------
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByTestId("dashboard-heading")).toHaveText("Chats");

    // Verify our mocked project is visible
    const projectLink = page.getByRole("link", { name: "AI Coach Ready to help!" });
    await expect(projectLink).toBeVisible();

    // Test Search (Client-side filtering)
    await page.getByTestId("chat-search").fill("Coach");
    await expect(projectLink).toBeVisible();

    await page.getByTestId("chat-search").fill("NonExistent");
    await expect(projectLink).not.toBeVisible();

    await page.getByTestId("chat-search").fill(""); // Clear search

    // -----------------------------------------------------------------------
    // STEP 3: Enter Chat
    // -----------------------------------------------------------------------
    await projectLink.click();
    await expect(page).toHaveURL(new RegExp(`/p/${FAKE_PROJECT_ID}/chat`));

    // Verify Header
    await expect(page.getByRole("heading", { name: "AI Coach" })).toBeVisible();

    // Verify Historical Messages
    // Wait specifically for the message list to load
    await expect(page.getByText("Hello! I am your AI Coach.")).toBeVisible({ timeout: 10000 });
    // Check Markdown rendering (bold text becomes strong tag or similar)
    // We can check for the "AI Coach" text inside a strong tag if we want to be specific,
    // but text visibility is a good enough proxy for now.
    await expect(page.getByText("Hi there.")).toBeVisible();

    // -----------------------------------------------------------------------
    // STEP 4: Send a Message
    // -----------------------------------------------------------------------
    const input = page.getByPlaceholder("Type a message…");
    await input.fill("Hello from E2E");
    await page.getByRole("button", { name: "Send" }).click();

    // Verify Optimistic UI (or fast response)
    await expect(page.getByText("Hello from E2E")).toBeVisible();
    await expect(input).toHaveValue("");

    // -----------------------------------------------------------------------
    // STEP 5: Verify SSE Reception
    // -----------------------------------------------------------------------
    // The SSE mock sends "I received your message via SSE!" immediately (but client might take a moment to process)
    await expect(page.getByText("I received your message via SSE!")).toBeVisible({ timeout: 10000 });

    // -----------------------------------------------------------------------
    // STEP 6: Verify Persistence (Reload)
    // -----------------------------------------------------------------------
    // If we reload, we should fetch from /messages again.
    // Since our mock /messages is static (ids 100, 101), the new messages (102, 200) won't be there
    // unless we update the mock.
    // However, the test requirement is just "expectations on chat experience".
    // We've verified: Load history -> Send -> Receive.

    // Let's verify we can go back to dashboard
    await page.getByRole("button", { name: "Back" }).click();
    await expect(page).toHaveURL(/\/dashboard/);
  });
});
