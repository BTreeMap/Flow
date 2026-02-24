import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { OnboardingNotifications } from "./OnboardingNotifications";
import { usePushNotifications } from "../hooks/usePushNotifications";

vi.mock("../hooks/usePushNotifications", () => ({
  usePushNotifications: vi.fn(),
  isIOS: () => false,
  isStandalone: () => false,
}));

describe("OnboardingNotifications", () => {
  const mockUsePushNotifications = usePushNotifications as unknown as ReturnType<
    typeof vi.fn
  >;

  it("renders enable button when not subscribed", () => {
    mockUsePushNotifications.mockReturnValue({
      permission: "default",
      subscribed: false,
      loading: false,
      error: null,
      success: null,
      pushNotConfigured: false,
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={["/p/123/onboarding/notifications"]}>
        <Routes>
          <Route
            path="/p/:projectId/onboarding/notifications"
            element={<OnboardingNotifications />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Enable Notifications")).toBeInTheDocument();
    expect(screen.getByText("Skip for now")).toBeInTheDocument();
  });

  it("renders continue button when subscribed", () => {
    mockUsePushNotifications.mockReturnValue({
      permission: "granted",
      subscribed: true,
      loading: false,
      error: null,
      success: null,
      pushNotConfigured: false,
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={["/p/123/onboarding/notifications"]}>
        <Routes>
          <Route
            path="/p/:projectId/onboarding/notifications"
            element={<OnboardingNotifications />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Continue to Chat")).toBeInTheDocument();
    expect(screen.queryByText("Skip for now")).not.toBeInTheDocument();
  });

  it("calls subscribe when enable button is clicked", () => {
    const mockSubscribe = vi.fn();
    mockUsePushNotifications.mockReturnValue({
      permission: "default",
      subscribed: false,
      loading: false,
      error: null,
      success: null,
      pushNotConfigured: false,
      subscribe: mockSubscribe,
      unsubscribe: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={["/p/123/onboarding/notifications"]}>
        <Routes>
          <Route
            path="/p/:projectId/onboarding/notifications"
            element={<OnboardingNotifications />}
          />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("Enable Notifications"));
    expect(mockSubscribe).toHaveBeenCalled();
  });
});
