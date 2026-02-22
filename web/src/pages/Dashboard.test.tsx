import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router";
import { Dashboard } from "./Dashboard";

// Mock auth
vi.mock("../auth", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    displayName: "Test",
    role: "user",
  }),
}));

vi.mock("../auth/token", () => ({
  getOrMintToken: vi.fn().mockResolvedValue("mock-token"),
}));

// Mock install prompt hook
vi.mock("../hooks/useInstallPrompt", () => ({
  useInstallPrompt: () => ({
    canPrompt: false,
    installed: false,
    showIOSGuide: false,
    promptInstall: vi.fn(),
    dismiss: vi.fn(),
  }),
}));

// Mock layout mode to bottom (mobile) so Dashboard renders full chat list
vi.mock("../hooks/useLayoutMode", () => ({
  useLayoutMode: () => "bottom",
}));

const mockMemberships = [
  {
    project_id: "p1",
    display_name: "Health Study",
    status: "active",
    conversation_id: 1,
    last_message_preview: "How are you feeling today?",
    last_message_at: "2025-01-15T10:00:00Z",
  },
  {
    project_id: "p2",
    display_name: "Exercise Tracker",
    status: "active",
    conversation_id: 2,
    last_message_preview: "Great workout session!",
    last_message_at: "2025-01-14T08:00:00Z",
  },
  {
    project_id: "p3",
    display_name: "Old Project",
    status: "ended",
    conversation_id: 3,
    last_message_preview: null,
    last_message_at: null,
  },
];

function mockFetch(memberships: typeof mockMemberships) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ memberships }),
  }) as typeof globalThis.fetch;
}

function renderDashboard() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("Dashboard chats list", () => {
  it("renders chat rows after loading", async () => {
    mockFetch(mockMemberships);
    renderDashboard();

    expect(
      await screen.findByText("Health Study"),
    ).toBeInTheDocument();
    expect(screen.getByText("Exercise Tracker")).toBeInTheDocument();
    expect(screen.getByText("Old Project")).toBeInTheDocument();
  });

  it("filters chats by search query matching display name", async () => {
    mockFetch(mockMemberships);
    renderDashboard();

    await screen.findByText("Health Study");

    const searchInput = screen.getByTestId("chat-search");
    fireEvent.change(searchInput, { target: { value: "exercise" } });

    expect(screen.getByText("Exercise Tracker")).toBeInTheDocument();
    expect(screen.queryByText("Health Study")).not.toBeInTheDocument();
  });

  it("filters chats by search query matching last message preview", async () => {
    mockFetch(mockMemberships);
    renderDashboard();

    await screen.findByText("Health Study");

    const searchInput = screen.getByTestId("chat-search");
    fireEvent.change(searchInput, { target: { value: "feeling" } });

    expect(screen.getByText("Health Study")).toBeInTheDocument();
    expect(screen.queryByText("Exercise Tracker")).not.toBeInTheDocument();
  });

  it("shows empty state when no memberships", async () => {
    mockFetch([]);
    renderDashboard();

    expect(await screen.findByText("No chats yet")).toBeInTheDocument();
  });
});
