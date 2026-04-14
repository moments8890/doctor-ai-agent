import { useEffect } from "react";

/**
 * Detects soft keyboard via visualViewport and sets CSS variables on <html>:
 *
 * --safe-bottom: env(safe-area-inset-bottom) when keyboard closed, 0px when open
 * --keyboard-height: 0px when closed, actual keyboard height in px when open
 *
 * Also pins the viewport to the top so the keyboard shrinks the page from
 * the bottom (keeping header in view) instead of pushing content up.
 */
export function useKeyboardSafeArea() {
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--safe-bottom", "env(safe-area-inset-bottom)");
    root.style.setProperty("--keyboard-height", "0px");

    const vv = window.visualViewport;
    if (!vv) return;

    function onResize() {
      // Keyboard height = difference between window height and visual viewport
      const kbHeight = window.innerHeight - vv.height;
      const keyboardOpen = kbHeight > 150;

      root.style.setProperty("--safe-bottom", keyboardOpen ? "0px" : "env(safe-area-inset-bottom)");
      root.style.setProperty("--keyboard-height", keyboardOpen ? `${kbHeight}px` : "0px");

      // Pin scroll to top so keyboard shrinks from bottom, not top
      if (keyboardOpen) {
        window.scrollTo(0, 0);
      }
    }

    function onScroll() {
      // Prevent the page from scrolling up when keyboard is open
      const kbHeight = window.innerHeight - vv.height;
      if (kbHeight > 150 && vv.offsetTop > 0) {
        window.scrollTo(0, 0);
      }
    }

    vv.addEventListener("resize", onResize);
    vv.addEventListener("scroll", onScroll);
    return () => {
      vv.removeEventListener("resize", onResize);
      vv.removeEventListener("scroll", onScroll);
    };
  }, []);
}
