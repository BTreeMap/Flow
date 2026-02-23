import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./AppShell";

// Mock auth
vi.mock("../../auth", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    displayName: "Test",
    role: "user",
  }),
}));

vi.mock("../../auth/token", () => ({
  getOrMintToken: vi.fn().mockResolvedValue("mock-token"),
}));

// Mock useLayoutMode
let currentMode: "bottom" | "side" = "side";
vi.mock("../../hooks/useLayoutMode", () => ({
  useLayoutMode: () => currentMode,
}));

// Mock install prompt
vi.mock("../../hooks/useInstallPrompt", () => ({
  useInstallPrompt: () => ({
    canPrompt: false,
    installed: false,
    showIOSGuide: false,
    promptInstall: vi.fn(),
    dismiss: vi.fn(),
  }),
}));

function mockFetch(memberships: unknown[]) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ memberships }),
  }) as typeof globalThis.fetch;
}

function renderWithShell(path: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<div>Dashboard Content</div>} />
            <Route path="/settings" element={<div>Settings Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  currentMode = "side";
});

describe("AppShell", () => {
  it("renders nav rail in side mode", () => {
    currentMode = "side";
    mockFetch([]);
    renderWithShell("/dashboard");
    expect(screen.getByTestId("nav-rail")).toBeInTheDocument();
    // Nav items should use same testIds as BottomNav
    expect(screen.getByTestId("nav-chats")).toBeInTheDocument();
    expect(screen.getByTestId("nav-updates")).toBeInTheDocument();
    expect(screen.getByTestId("nav-settings")).toBeInTheDocument();
    // bottom-nav should NOT be present in side mode
    expect(screen.queryByTestId("bottom-nav")).not.toBeInTheDocument();
  });

  it("renders bottom nav in bottom mode", () => {
    currentMode = "bottom";
    renderWithShell("/settings");
    expect(screen.getByTestId("bottom-nav")).toBeInTheDocument();
    expect(screen.getByTestId("nav-settings")).toBeInTheDocument();
    // nav-rail should NOT be present in bottom mode
    expect(screen.queryByTestId("nav-rail")).not.toBeInTheDocument();
  });

  it("shows chat list pane and main content area in side mode on dashboard route", () => {
    currentMode = "side";
    mockFetch([]);
    renderWithShell("/dashboard");
    // Chat list pane is rendered in the shell
    expect(screen.getByTestId("chat-list-pane")).toBeInTheDocument();
  });
});
