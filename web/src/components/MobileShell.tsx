import { Outlet } from "react-router";
import { BottomNav } from "./ui/BottomNav";

/**
 * App shell with bottom nav for primary screens (Chats, Updates, Settings).
 * Bottom nav is always visible; content area accounts for nav height.
 */
export function MobileShell() {
  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <div className="flex-1 flex flex-col pb-[calc(var(--bottomnav-h)+env(safe-area-inset-bottom,0px))]">
        <Outlet />
      </div>
      <BottomNav />
    </div>
  );
}
