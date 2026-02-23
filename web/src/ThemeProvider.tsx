import { useEffect } from "react";
import {
  readThemePreference,
  applyEffectiveThemeForPreference,
  subscribeToSystemThemeChanges,
} from "./theme";

/**
 * Side-effect-only provider that keeps the document theme in sync with
 * the stored preference and system-level changes.
 *
 * Must be rendered near the app root so every route benefits.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Re-apply on mount (defensive — main.tsx already does a sync apply)
    applyEffectiveThemeForPreference(readThemePreference());

    // When Settings (or anything) writes a new preference, apply it.
    const onPrefChange = () => {
      applyEffectiveThemeForPreference(readThemePreference());
    };
    window.addEventListener("theme-preference-change", onPrefChange);

    // Track OS-level theme changes when preference is "system".
    const unsubSystem = subscribeToSystemThemeChanges(() => {
      if (readThemePreference() === "system") {
        applyEffectiveThemeForPreference("system");
      }
    });

    return () => {
      window.removeEventListener("theme-preference-change", onPrefChange);
      unsubSystem();
    };
  }, []);

  return <>{children}</>;
}
