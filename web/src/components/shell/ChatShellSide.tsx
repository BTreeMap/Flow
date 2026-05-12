import { Outlet } from "react-router";
import { NavRail } from "./NavRail";
import { ChatListPane } from "../chats/ChatListPane";
import { NotificationBanner } from "../NotificationBanner";

/**
 * Side rail shell specifically for chat routes.
 * Shows: rail | chat list pane | chat thread (main content).
 */
export function ChatShellSide() {
  return (
    <div className="flex h-full bg-bg overflow-hidden">
      <NavRail />
      <div className="w-[360px] shrink-0 border-r border-divider overflow-y-auto bg-surface">
        <ChatListPane embedded />
      </div>
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <NotificationBanner />
        <Outlet />
      </main>
    </div>
  );
}
