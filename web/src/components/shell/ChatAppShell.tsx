import { useLayoutMode } from "../../hooks/useLayoutMode";
import { ChatShell } from "../ChatShell";
import { ChatShellSide } from "./ChatShellSide";

/**
 * Responsive chat shell:
 * - bottom mode (portrait phone): immersive full-screen chat
 * - side mode (desktop/landscape): split view with rail + chat list + thread
 */
export function ChatAppShell() {
  const mode = useLayoutMode();
  return mode === "bottom" ? <ChatShell /> : <ChatShellSide />;
}
