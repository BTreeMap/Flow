import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { Settings } from "./Settings";

// ── mock api client (typed openapi-fetch) ─────────────────────────
const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock("../api/client", () => ({
  default: {
    GET: (...args: unknown[]) => mockGet(...args),
    POST: (...args: unknown[]) => mockPost(...args),
  },
}));

// ── mock apiFetch (raw fetch wrapper used for mutations) ──────────
const mockApiFetch = vi.fn();
vi.mock("../auth", () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
  useAuth: () => ({
    isAuthenticated: true,
    role: "user",
    logout: vi.fn(),
  }),
}));

// ── mock webauthn helpers ─────────────────────────────────────────
vi.mock("../auth/webauthn", () => ({
  toCreateOptions: vi.fn(),
  serializeCreateResponse: vi.fn(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });
}

const samplePasskeys = [
  {
    id: "k00000000000000000000000000000001",
    name: "My Laptop",
    created_at: "2025-01-01T00:00:00Z",
    last_used_at: null,
    revoked_at: null,
  },
  {
    id: "k00000000000000000000000000000002",
    name: null,
    created_at: "2025-02-01T00:00:00Z",
    last_used_at: "2025-02-15T00:00:00Z",
    revoked_at: "2025-03-01T00:00:00Z",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockImplementation((path: unknown) => {
    if (path === "/auth/passkeys") {
      return Promise.resolve({ data: { passkeys: [] } });
    }
    if (path === "/auth/sessions") {
      return Promise.resolve({ data: { sessions: [] } });
    }
    return Promise.resolve({ data: {} });
  });
  mockPost.mockResolvedValue({ data: { ok: true } });
  mockApiFetch.mockResolvedValue({ ok: true, data: {} });
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("Settings – passkey name display", () => {
  it("renders passkey name when present", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: samplePasskeys } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ data: { sessions: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    render(<Settings />, { wrapper });
    expect(await screen.findByText("My Laptop")).toBeInTheDocument();
  });

  it("renders fallback for null name", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: samplePasskeys } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ data: { sessions: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    render(<Settings />, { wrapper });
    expect(await screen.findByText("Unnamed passkey")).toBeInTheDocument();
  });

  it("shows edit button only on non-revoked passkeys", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: samplePasskeys } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ data: { sessions: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    render(<Settings />, { wrapper });
    await screen.findByText("My Laptop");
    const editButtons = screen.getAllByTestId("passkey-edit-btn");
    // Only the first (non-revoked) passkey gets an edit button
    expect(editButtons).toHaveLength(1);
  });
});

describe("Settings – passkey rename", () => {
  it("opens inline edit form when edit button is clicked", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: [samplePasskeys[0]] } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ data: { sessions: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    render(<Settings />, { wrapper });
    await screen.findByText("My Laptop");
    fireEvent.click(screen.getByTestId("passkey-edit-btn"));
    expect(screen.getByTestId("passkey-name-input")).toBeInTheDocument();
    expect(screen.getByTestId("passkey-name-save")).toBeInTheDocument();
    expect(screen.getByTestId("passkey-name-cancel")).toBeInTheDocument();
  });

  it("cancels edit on cancel button click", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: [samplePasskeys[0]] } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ data: { sessions: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    render(<Settings />, { wrapper });
    await screen.findByText("My Laptop");
    fireEvent.click(screen.getByTestId("passkey-edit-btn"));
    fireEvent.click(screen.getByTestId("passkey-name-cancel"));
    expect(screen.queryByTestId("passkey-name-input")).not.toBeInTheDocument();
  });

  it("saves name on save button click", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: [samplePasskeys[0]] } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ data: { sessions: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    mockApiFetch.mockResolvedValue({
      ok: true,
      data: { id: samplePasskeys[0]!.id, name: "Work Key" },
    });
    render(<Settings />, { wrapper });
    await screen.findByText("My Laptop");
    fireEvent.click(screen.getByTestId("passkey-edit-btn"));
    const input = screen.getByTestId("passkey-name-input");
    fireEvent.change(input, { target: { value: "Work Key" } });
    fireEvent.click(screen.getByTestId("passkey-name-save"));
    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        `/auth/passkeys/${samplePasskeys[0]!.id}`,
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ name: "Work Key" }),
        }),
      ),
    );
  });

  it("shows validation error for too-long name", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: [samplePasskeys[0]] } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ data: { sessions: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    render(<Settings />, { wrapper });
    await screen.findByText("My Laptop");
    fireEvent.click(screen.getByTestId("passkey-edit-btn"));
    const input = screen.getByTestId("passkey-name-input");
    fireEvent.change(input, { target: { value: "x".repeat(65) } });
    fireEvent.click(screen.getByTestId("passkey-name-save"));
    expect(await screen.findByTestId("passkey-rename-error")).toHaveTextContent(
      "64 characters",
    );
  });

  it("shows API error on failed rename", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: [samplePasskeys[0]] } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ data: { sessions: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    mockApiFetch.mockResolvedValue({
      ok: false,
      data: { detail: "Something went wrong" },
    });
    render(<Settings />, { wrapper });
    await screen.findByText("My Laptop");
    fireEvent.click(screen.getByTestId("passkey-edit-btn"));
    fireEvent.click(screen.getByTestId("passkey-name-save"));
    expect(await screen.findByTestId("passkey-rename-error")).toHaveTextContent(
      "Something went wrong",
    );
  });
});

describe("Settings – sessions", () => {
  it("renders current and revocable sessions", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: [] } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({
          data: {
            sessions: [
              {
                device_id: "d_current",
                label: "My Laptop",
                created_at: "2025-01-01T00:00:00Z",
                revoked_at: null,
                is_current: true,
              },
              {
                device_id: "d_other",
                label: "Phone",
                created_at: "2025-01-02T00:00:00Z",
                revoked_at: null,
                is_current: false,
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    render(<Settings />, { wrapper });
    expect(await screen.findByText("My Laptop")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Phone")).toBeInTheDocument();
    expect(screen.getAllByText("Revoke")).toHaveLength(1);
  });

  it("shows sessions error and avoids empty-state on request failure", async () => {
    mockGet.mockImplementation((path: unknown) => {
      if (path === "/auth/passkeys") {
        return Promise.resolve({ data: { passkeys: [] } });
      }
      if (path === "/auth/sessions") {
        return Promise.resolve({ error: { detail: "boom" } });
      }
      return Promise.resolve({ data: {} });
    });
    render(<Settings />, { wrapper });
    expect(
      await screen.findByText("Failed to load sessions"),
    ).toBeInTheDocument();
    expect(screen.queryByText("No sessions found.")).not.toBeInTheDocument();
    // Error alert should be present with stable data-testid
    expect(screen.getByTestId("sessions-error")).toBeInTheDocument();
  });
});

describe("Settings – theme preference", () => {
  it("defaults to system when no preference is saved", async () => {
    mockMatchMedia(false);
    render(<Settings />, { wrapper });

    expect(await screen.findByRole("radio", { name: "System" })).toBeChecked();
  });

  it("selecting dark persists preference and applies dark theme", async () => {
    mockMatchMedia(false);
    render(<Settings />, { wrapper });

    fireEvent.click(await screen.findByRole("radio", { name: "Dark" }));
    expect(localStorage.getItem("theme-preference")).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("selecting system applies effective theme from matchMedia", async () => {
    mockMatchMedia(false);
    localStorage.setItem("theme-preference", "dark");
    render(<Settings />, { wrapper });

    fireEvent.click(await screen.findByRole("radio", { name: "System" }));
    expect(localStorage.getItem("theme-preference")).toBe("system");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
