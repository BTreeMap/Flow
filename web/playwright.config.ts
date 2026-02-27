import { defineConfig } from "@playwright/test";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// In CI the h4ckath0n library is installed from the repo root.
// Locally, the same `uv run` from repo root makes the library available.
const repoRoot = resolve(__dirname, "..");
const apiDir = resolve(__dirname, "../api");

// When PLAYWRIGHT_BASE_URL is set (e.g. http://localhost:8080 for compose-based
// E2E), Playwright hits the external stack directly and does NOT start local
// dev servers. Otherwise, it starts backend + Vite dev server as before.
const externalBaseURL = process.env.PLAYWRIGHT_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: externalBaseURL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
  ...(externalBaseURL
    ? {}
    : {
        webServer: [
          {
            // Use a temp file DB to ensure persistence across requests but clean state on restart
            command: `rm -f /tmp/flow-e2e.db && uv run --directory ${apiDir} --locked python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
            cwd: apiDir,
            url: "http://127.0.0.1:8000/healthz",
            reuseExistingServer: !process.env.CI,
            timeout: 30_000,
            env: {
              PYTHONPATH: apiDir,
              H4CKATH0N_ORIGIN: "http://localhost:5173",
              H4CKATH0N_ADMIN_EMAILS: "chat-test@example.com", // Grant admin access to test user
              H4CKATH0N_DATABASE_URL: "sqlite+aiosqlite:////tmp/flow-e2e.db",
            },
          },
          {
            command: "npx vite --host 127.0.0.1 --port 5173",
            url: "http://127.0.0.1:5173",
            reuseExistingServer: !process.env.CI,
            timeout: 30_000,
          },
        ],
      }),
});
