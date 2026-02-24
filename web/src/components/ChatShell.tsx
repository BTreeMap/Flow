import { Outlet } from "react-router";
import { NotificationBanner } from "./NotificationBanner";

/**
 * Full-screen shell for immersive views like chat.
 * No top nav, no bottom nav — page handles its own chrome.
 */
export function ChatShell() {
  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <NotificationBanner />
      <Outlet />
    </div>
  );
}
