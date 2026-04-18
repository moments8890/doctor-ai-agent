import { useEffect } from "react";

const SAFE_BOTTOM_DEFAULT = "max(env(safe-area-inset-bottom, 0px), 20px)";

if (import.meta.env.DEV) {
  window.__debugKeyboard = (open) => {
    const root = document.documentElement;
    root.style.setProperty("--safe-bottom", open ? "0px" : SAFE_BOTTOM_DEFAULT);
    root.style.setProperty("--keyboard-height", open ? "300px" : "0px");
    console.log(`[keyboard] ${open ? "OPEN" : "CLOSED"}`);
  };
}

/**
 * Keyboard-aware layout. Sets CSS vars on <html>:
 *   --safe-bottom: home bar padding (0px when keyboard open)
 *   --keyboard-height: keyboard height in px (0px when closed)
 *
 * Also globally intercepts input focus events to prevent the browser/WebView
 * from auto-scrolling the page when the keyboard opens (which pushes headers
 * off-screen). Uses focus({ preventScroll: true }) on touchend and locks
 * body scroll while the keyboard is open.
 *
 * Detection priority:
 *   1. wx.onKeyboardHeightChange (WeChat WebView — most reliable)
 *   2. visualViewport resize (Safari, Chrome)
 *   3. focusin/focusout (fallback boolean detection)
 */
export function useKeyboardSafeArea() {
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--safe-bottom", SAFE_BOTTOM_DEFAULT);
    root.style.setProperty("--keyboard-height", "0px");

    let keyboardOpen = false;

    function setKeyboard(height) {
      const open = height > 0;
      root.style.setProperty("--safe-bottom", open ? "0px" : SAFE_BOTTOM_DEFAULT);
      root.style.setProperty("--keyboard-height", `${height}px`);

      // Lock body scroll when keyboard is open to prevent page-level shift
      if (open && !keyboardOpen) {
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
      } else if (!open && keyboardOpen) {
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
      }
      keyboardOpen = open;
    }

    // --- Global preventScroll focus interception ---
    // When a user taps an input, the browser's default focus behavior scrolls
    // the page to make the element visible. In WeChat WebView this pushes
    // headers off-screen. Intercepting touchend and calling
    // focus({ preventScroll: true }) prevents that entirely.
    const INPUT_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);
    function isInputEl(el) {
      return el && (INPUT_TAGS.has(el.tagName) || el.isContentEditable);
    }

    function onTouchEnd(e) {
      const target = e.target;
      // Find the actual input element (may be the target or a parent)
      const inputEl = isInputEl(target) ? target
        : target.closest?.("input, textarea, select, [contenteditable]");
      if (!inputEl) return;
      if (document.activeElement === inputEl) return; // already focused
      e.preventDefault();
      inputEl.focus({ preventScroll: true });
    }
    document.addEventListener("touchend", onTouchEnd, { passive: false });

    // Strategy 1: WeChat API (best in miniprogram WebView)
    if (window.wx?.onKeyboardHeightChange) {
      window.wx.onKeyboardHeightChange((res) => setKeyboard(res.height));
      return () => {
        document.removeEventListener("touchend", onTouchEnd);
        if (keyboardOpen) {
          document.documentElement.style.overflow = "";
          document.body.style.overflow = "";
        }
      };
    }

    // Strategy 2: visualViewport (Safari 15+, Chrome)
    const vv = window.visualViewport;
    let vvActive = false;
    function onVVResize() {
      if (!vv) return;
      const diff = window.innerHeight - vv.height;
      const height = diff > 100 ? diff : 0;
      setKeyboard(height);
      vvActive = true;
    }
    if (vv) {
      vv.addEventListener("resize", onVVResize);
    }

    // Strategy 3: focusin/focusout fallback (no height info, just boolean)
    function onFocusIn(e) {
      if (isInputEl(e.target) && !vvActive) {
        setKeyboard(300); // estimated
      }
    }
    function onFocusOut(e) {
      if (isInputEl(e.target) && !vvActive) {
        setTimeout(() => {
          if (!isInputEl(document.activeElement)) setKeyboard(0);
        }, 100);
      }
    }
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);

    return () => {
      document.removeEventListener("touchend", onTouchEnd);
      if (vv) vv.removeEventListener("resize", onVVResize);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
      if (keyboardOpen) {
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
      }
    };
  }, []);
}

/**
 * SX props for full-page containers that need to shrink when the keyboard opens
 * (chat pages, interview pages). Apply via: <Box sx={KEYBOARD_AWARE_CONTAINER}>
 *
 * Uses --keyboard-height (set by useKeyboardSafeArea) to reduce the container
 * height so the flex chat content area absorbs the keyboard, keeping headers
 * and input bars in place.
 */
export const KEYBOARD_AWARE_CONTAINER = {
  display: "flex",
  flexDirection: "column",
  height: "calc(100% - var(--keyboard-height, 0px))",
  overflow: "hidden",
  transition: "height 0.25s cubic-bezier(0.33,1,0.68,1)",
};
