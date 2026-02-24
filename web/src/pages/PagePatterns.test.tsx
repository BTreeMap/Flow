import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(Date, "now").mockReturnValue(new Date("2026-03-03T21:14:00.000Z").valueOf());

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

afterEach(() => {
  vi.restoreAllMocks();
});

describe("page pattern snapshots", () => {
  it("notifications page uses compact header + card sections", async () => {
    const { container } = renderWithQuery(
      <MemoryRouter initialEntries={["/p/p123/notifications"]}>
        <Routes>
          <Route path="/p/:projectId/notifications" element={<Notifications />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("notifications-heading")).toBeInTheDocument();
    expect(container.firstChild).toMatchSnapshot();
  });

  it("admin page uses compact header + spacing tokens", async () => {
    const { container } = renderWithQuery(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("admin-heading")).toBeInTheDocument();
    expect(container.firstChild).toMatchSnapshot();
  });

  it("realtime demo uses shared button and input primitives", async () => {
    const { container } = renderWithQuery(
      <MemoryRouter>
        <DemoRealtime />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("realtime-heading")).toBeInTheDocument();
    expect(container.firstChild).toMatchSnapshot();
  });
});
