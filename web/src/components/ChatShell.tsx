import { Outlet } from "react-router";
import { NotificationBanner } from "./NotificationBanner";

/**
 * Full-screen shell for immersive views like chat.
 * No top nav, no bottom nav — page handles its own chrome.
 * Uses dynamic viewport height (--vvh) for proper iOS keyboard handling.
 */
export function ChatShell() {
  return (
    <div className="flex flex-col bg-bg overflow-hidden" style={{ height: "var(--vvh, 100vh)" }}>
      <NotificationBanner />
      <Outlet />
    </div>
  );
}
