import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { ChatListPane } from "./ChatListPane";

vi.mock("../../auth/token", () => ({
  getOrMintToken: vi.fn().mockResolvedValue("mock-token"),
}));

function mockFetch(memberships: unknown[]) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ memberships }),
  }) as typeof globalThis.fetch;
}

function renderPane() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1/chat"]}>
        <Routes>
          <Route path="/p/:projectId/chat" element={<ChatListPane embedded />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ChatListPane", () => {
  it("masks system preview text defensively", async () => {
    mockFetch([
      {
        project_id: "p-system",
        display_name: "System Test",
        status: "active",
        conversation_id: 10,
        last_message_preview:
          "[System: User provided feedback 'Needs tweaks' on notification 1]",
        last_message_at: "2025-01-15T10:00:00Z",
      },
    ]);
    renderPane();

    expect(await screen.findByText("System Test")).toBeInTheDocument();
    expect(screen.getByText("Feedback submitted")).toBeInTheDocument();
    expect(screen.queryByText(/\[System:/)).not.toBeInTheDocument();
  });
});
