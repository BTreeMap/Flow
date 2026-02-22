import { useLayoutMode } from "../../hooks/useLayoutMode";
import { MobileShell } from "../MobileShell";
import { SideRailShell } from "./SideRailShell";

/**
 * Responsive app shell that switches between bottom tab navigation (portrait
 * phones) and side rail navigation (desktop, tablet, landscape phones).
 */
export function AppShell() {
  const mode = useLayoutMode();
  return mode === "bottom" ? <MobileShell /> : <SideRailShell />;
}
