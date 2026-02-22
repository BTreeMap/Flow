import { Outlet, useLocation } from "react-router";
import { NavRail } from "./NavRail";
import { ChatListPane } from "../chats/ChatListPane";

/**
 * Desktop / landscape shell with side rail navigation.
 * For chat routes, shows a three-column layout: rail | chat list | main.
 * For other routes, shows rail | main.
 */
export function SideRailShell() {
  const { pathname } = useLocation();
  const isChatRoute = pathname.match(/^\/p\/[^/]+\/chat/);
  const isDashboard = pathname === "/dashboard";

  // Show chat list pane for chat routes and dashboard
  const showListPane = isChatRoute || isDashboard;

  return (
    <div className="flex h-screen bg-bg overflow-hidden">
      <NavRail />
      {showListPane && (
        <div className="w-[360px] shrink-0 border-r border-divider overflow-y-auto bg-surface">
          <ChatListPane embedded />
        </div>
      )}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {isDashboard ? (
          <div className="flex-1 flex items-center justify-center bg-surface-2">
            <div className="text-center text-text-muted">
              <p className="text-[15px]">Select a chat to start messaging</p>
            </div>
          </div>
        ) : (
          <Outlet />
        )}
      </main>
    </div>
  );
}
