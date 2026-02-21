import { Outlet } from "react-router";
import { BottomNav } from "./ui/BottomNav";

/**
 * Mobile-first shell: no top nav, full-width content, bottom nav.
 * On desktop (md+), renders with max-width container and hides bottom nav via CSS.
 */
export function MobileShell() {
  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <div className="flex-1 flex flex-col pb-[calc(var(--bottomnav-h)+env(safe-area-inset-bottom,0px))] md:pb-0">
        <Outlet />
      </div>
      <BottomNav />
    </div>
  );
}
