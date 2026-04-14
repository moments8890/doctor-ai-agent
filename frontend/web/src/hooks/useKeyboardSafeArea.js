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

    function setKeyboard(height) {
      const open = height > 0;
      root.style.setProperty("--safe-bottom", open ? "0px" : SAFE_BOTTOM_DEFAULT);
      root.style.setProperty("--keyboard-height", `${height}px`);
    }

    // Strategy 1: WeChat API (best in miniprogram WebView)
    if (window.wx?.onKeyboardHeightChange) {
      window.wx.onKeyboardHeightChange((res) => setKeyboard(res.height));
      return; // wx API handles everything, no fallbacks needed
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
    const INPUT_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);
    function isInput(el) {
      return el && (INPUT_TAGS.has(el.tagName) || el.isContentEditable);
    }
    function onFocusIn(e) {
      if (isInput(e.target) && !vvActive) {
        setKeyboard(300); // estimated
      }
    }
    function onFocusOut(e) {
      if (isInput(e.target) && !vvActive) {
        setTimeout(() => {
          if (!isInput(document.activeElement)) setKeyboard(0);
        }, 100);
      }
    }
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);

    return () => {
      if (vv) vv.removeEventListener("resize", onVVResize);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
    };
  }, []);
}
