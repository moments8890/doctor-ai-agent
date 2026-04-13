import { useEffect } from "react";

/**
 * Detects soft keyboard visibility via visualViewport and sets
 * --safe-bottom CSS variable on <html>.
 *
 * When keyboard is closed: --safe-bottom = env(safe-area-inset-bottom)
 * When keyboard is open:   --safe-bottom = 0px
 *
 * All components should use var(--safe-bottom) instead of raw env().
 */
export function useKeyboardSafeArea() {
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--safe-bottom", "env(safe-area-inset-bottom)");

    const vv = window.visualViewport;
    if (!vv) return;

    const initialHeight = vv.height;

    function onResize() {
      const keyboardOpen = initialHeight - vv.height > 150;
      root.style.setProperty("--safe-bottom", keyboardOpen ? "0px" : "env(safe-area-inset-bottom)");
    }

    vv.addEventListener("resize", onResize);
    return () => vv.removeEventListener("resize", onResize);
  }, []);
}
