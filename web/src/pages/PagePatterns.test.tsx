import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Notifications } from "./Notifications";
import { Admin } from "./Admin";
import { DemoRealtime } from "./DemoRealtime";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("../api/client", () => ({
  default: {
    GET: (...args: unknown[]) => mockGet(...args),
    POST: (...args: unknown[]) => mockPost(...args),
    PATCH: vi.fn(),
  },
}));

vi.mock("../auth", () => ({
  useAuth: () => ({
    role: "admin",
    userId: "u12345678",
    deviceId: "d12345678",
  }),
  getOrMintToken: vi.fn().mockResolvedValue("token"),
}));

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function expectSharedPageFrame(container: HTMLElement) {
  const header = container.querySelector("header[data-testid]");
  const main = container.querySelector("main");

  expect(header).toHaveClass("sticky", "h-[var(--header-h)]", "border-b");
  expect(main).toHaveClass("mx-auto", "w-full", "px-4", "py-4", "space-y-4");
}

beforeEach(() => {
  vi.clearAllMocks();

  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });

  Object.defineProperty(window.navigator, "serviceWorker", {
    writable: true,
    value: {
      ready: Promise.resolve({
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
        },
      }),
    },
  });

  Object.defineProperty(window, "PushManager", {
    writable: true,
    value: class {},
  });

  mockGet.mockImplementation((path: string) => {
    if (path === "/p/{project_id}/push/vapid-public-key") {
      return Promise.resolve({ data: { public_key: "test" }, error: null });
    }
    if (path === "/admin/projects") {
      return Promise.resolve({ data: { projects: [] }, error: null });
    }
    if (path === "/admin/debug/status") {
      return Promise.resolve({
        data: {
          llm_mode: "mock",
          openai_api_key_configured: true,
          vapid_public_key_configured: true,
          vapid_private_key_configured: true,
          warnings: [],
        },
        error: null,
      });
    }
    return Promise.resolve({ data: {}, error: null });
  });

  mockPost.mockResolvedValue({ data: {}, error: null });
});

describe("page pattern assertions", () => {
  it("notifications page uses compact header, shared frame, and shared CTA button", async () => {
    const { container } = renderWithQuery(
      <MemoryRouter initialEntries={["/p/p123/notifications"]}>
        <Routes>
          <Route path="/p/:projectId/notifications" element={<Notifications />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("notifications-heading")).toBeInTheDocument();
    expectSharedPageFrame(container);
    expect(container.querySelector("main")).toHaveClass("max-w-3xl");
    expect(screen.getByRole("button", { name: /enable notifications/i })).toHaveClass(
      "rounded-2xl",
      "bg-primary",
    );
  });

  it("admin page uses compact header, shared frame, and shared primary CTAs", async () => {
    const { container } = renderWithQuery(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("admin-heading")).toBeInTheDocument();
    expectSharedPageFrame(container);
    expect(container.querySelector("main")).toHaveClass("max-w-5xl");
    expect(screen.getByRole("button", { name: /run test/i })).toHaveClass(
      "rounded-2xl",
      "bg-primary",
    );
    expect(screen.getByText(/loading…/i)).toBeInTheDocument();
  });

  it("realtime demo uses compact header, shared frame, and shared Button/Input styles", async () => {
    const { container } = renderWithQuery(
      <MemoryRouter>
        <DemoRealtime />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("realtime-heading")).toBeInTheDocument();
    expectSharedPageFrame(container);
    expect(container.querySelector("main")).toHaveClass("max-w-5xl");
    expect(screen.getByTestId("ws-input")).toHaveClass("rounded-xl", "border", "bg-surface");
    expect(screen.getByTestId("ws-connect")).toHaveClass("rounded-2xl", "bg-primary");
    expect(screen.getByTestId("ws-disconnect")).toHaveClass("rounded-2xl", "bg-danger");
  });
});
