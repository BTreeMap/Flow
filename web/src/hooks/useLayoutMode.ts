import { useSyncExternalStore } from "react";

export type LayoutMode = "bottom" | "side";

/**
 * Determines layout mode:
 * - "bottom": portrait on small screens (max-width < 768px AND portrait)
 * - "side": everything else (desktop, tablet, landscape phones)
 */
const QUERY = "(max-width: 767px) and (orientation: portrait)";

function subscribe(cb: () => void) {
  const mql = window.matchMedia(QUERY);
  mql.addEventListener("change", cb);
  return () => mql.removeEventListener("change", cb);
}

function getSnapshot(): LayoutMode {
  return window.matchMedia(QUERY).matches ? "bottom" : "side";
}

function getServerSnapshot(): LayoutMode {
  return "bottom";
}

export function useLayoutMode(): LayoutMode {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
