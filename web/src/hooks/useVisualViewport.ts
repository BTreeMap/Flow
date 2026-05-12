import { useEffect } from "react";

/**
 * Keeps a CSS custom property `--vvh` synced with the visual viewport height.
 *
 * On iOS Safari when the virtual keyboard opens, `window.innerHeight` stays
 * the same but `window.visualViewport.height` shrinks. By writing the live
 * value to a CSS variable on `<html>`, layout containers can use
 * `height: calc(var(--vvh, 1vh) * 100)` to stay correctly sized around the
 * keyboard.
 *
 * Also sets `--vvh-offset` which is `window.innerHeight - visualViewport.height`,
 * i.e. the keyboard height + any browser chrome delta. This is useful for
 * positioning fixed/sticky elements above the keyboard.
 *
 * Falls back to `window.innerHeight` when `visualViewport` is not available.
 */
export function useVisualViewport() {
  useEffect(() => {
    const vv = window.visualViewport;

    function update() {
      const h = vv ? vv.height : window.innerHeight;
      const offset = window.innerHeight - h;
      document.documentElement.style.setProperty("--vvh", `${h}px`);
      document.documentElement.style.setProperty(
        "--vvh-offset",
        `${Math.max(0, offset)}px`,
      );
    }

    update();

    if (vv) {
      vv.addEventListener("resize", update);
      vv.addEventListener("scroll", update);
    }
    window.addEventListener("resize", update);

    return () => {
      if (vv) {
        vv.removeEventListener("resize", update);
        vv.removeEventListener("scroll", update);
      }
      window.removeEventListener("resize", update);
    };
  }, []);
}
