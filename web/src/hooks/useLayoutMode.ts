import { useSyncExternalStore } from "react";

export type LayoutMode = "bottom" | "side";

/**
 * Determines layout mode based on the smaller viewport dimension.
 *
 * - "bottom": phones in both portrait and landscape (smaller dimension < 600px)
 * - "side": tablets and desktops (smaller dimension ≥ 600px)
 *
 * Using min(width, height) ensures landscape phones stay in the phone shell
 * rather than incorrectly switching to the side-rail / split-view layout.
 * The 600px threshold corresponds to the common small-tablet breakpoint,
 * which safely excludes all phones (iPhone max short edge ≈ 430px).
 */
const PHONE_QUERY = "(max-width: 599px), ((max-height: 599px) and (max-width: 959px))";

function subscribe(cb: () => void) {
  const mql = window.matchMedia(PHONE_QUERY);
  mql.addEventListener("change", cb);
  return () => mql.removeEventListener("change", cb);
}

function getSnapshot(): LayoutMode {
  return window.matchMedia(PHONE_QUERY).matches ? "bottom" : "side";
}

function getServerSnapshot(): LayoutMode {
  return "bottom";
}

export function useLayoutMode(): LayoutMode {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
