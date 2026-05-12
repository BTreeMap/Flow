import { Outlet } from "react-router";
import { BottomNav } from "./ui/BottomNav";

/**
 * App shell with bottom nav for primary screens (Chats, Updates, Settings).
 * Bottom nav is always visible; content area accounts for nav height.
 * Uses dynamic viewport height (--vvh) to stay correctly sized on iOS
 * when the browser chrome or keyboard changes the visible area.
 */
export function MobileShell() {
  return (
    <div className="flex flex-col bg-bg overflow-hidden" style={{ height: "var(--vvh, 100vh)" }}>
      <div className="flex-1 flex flex-col overflow-y-auto pb-[calc(var(--bottomnav-h)+env(safe-area-inset-bottom,0px))]">
        <Outlet />
      </div>
      <BottomNav />
    </div>
  );
}
