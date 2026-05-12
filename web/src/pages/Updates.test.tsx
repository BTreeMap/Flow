import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Updates } from "./Updates";

const mockNavigate = vi.fn();

vi.mock("react-router", async () => {
  const actual = await vi.importActual("react-router");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("../hooks/useInstallPrompt", () => ({
  useInstallPrompt: () => ({
    canPrompt: false,
    promptInstall: vi.fn(),
    showIOSGuide: false,
    installed: false,
  }),
}));

// Mock the api client — factory must not reference outer variables
vi.mock("../api/client", () => ({
  default: {
    GET: vi.fn().mockResolvedValue({
      data: {
        notifications: [
          {
            id: 1,
            title: "Daily Nudge",
            body: "Time to go for a walk!",
            created_at: new Date().toISOString(),
            read_at: null,
            project_id: "paaaa",
            project_display_name: "Study A",
          },
          {
            id: 2,
            title: "Evening Check-in",
            body: "How was your day?",
            created_at: new Date(Date.now() - 3600000).toISOString(),
            read_at: "2023-01-01T00:00:00Z",
            project_id: "pbbbb",
            project_display_name: "Study B",
          },
        ],
      },
      error: undefined,
    }),
    POST: vi.fn().mockResolvedValue({ data: { ok: true }, error: undefined }),
  },
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/updates"]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Updates (unified feed)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders notifications in the feed", async () => {
    renderWithProviders(<Updates />);

    await waitFor(() => {
      expect(screen.getByText("Daily Nudge")).toBeInTheDocument();
    });
    expect(screen.getByText("Evening Check-in")).toBeInTheDocument();
    expect(screen.getByText("Study A")).toBeInTheDocument();
    expect(screen.getByText("Study B")).toBeInTheDocument();
  });

  it("shows unread indicator for unread notifications", async () => {
    renderWithProviders(<Updates />);

    await waitFor(() => {
      expect(screen.getByText("Daily Nudge")).toBeInTheDocument();
    });
    // Unread notification should have bold text
    const nudgeTitle = screen.getByText("Daily Nudge");
    expect(nudgeTitle.className).toContain("font-semibold");
  });

  it("navigates to correct chat on click", async () => {
    renderWithProviders(<Updates />);

    await waitFor(() => {
      expect(screen.getByText("Daily Nudge")).toBeInTheDocument();
    });

    const button = screen.getByText("Daily Nudge").closest("button");
    if (!button) throw new Error("Button not found");
    fireEvent.click(button);

    expect(mockNavigate).toHaveBeenCalledWith("/p/paaaa/chat?nid=1");
  });

  it("shows header", async () => {
    renderWithProviders(<Updates />);
    expect(screen.getByText("Recent Notifications")).toBeInTheDocument();
  });
});
