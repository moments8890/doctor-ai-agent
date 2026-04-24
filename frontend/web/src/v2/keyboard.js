/**
 * WeChat WebView keyboard handler.
 *
 * antd-mobile SafeArea handles only env(safe-area-inset-bottom) — the home
 * bar indicator. This hook handles the keyboard itself:
 *   1. wx.onKeyboardHeightChange (WeChat API)
 *   2. visualViewport resize fallback
 *   3. focusin/focusout fallback
 *   4. touchend + focus({ preventScroll: true }) — prevent auto-scroll
 *   5. Body scroll lock when keyboard is open
 *   6. keyboardresize custom event for chat scroll-to-bottom
 */
import { useEffect, useCallback } from "react";

export function useKeyboard() {
  useEffect(() => {
    const root = document.documentElement;
    let keyboardOpen = false;

    // Authoritative "visible area above the keyboard" in px. Works on Mobile
    // Safari AND WKWebView regardless of whether 100vh shrinks with the
    // keyboard — page shells read var(--app-height) instead of computing
    // 100% minus keyboard-height (which double-shrinks on WKWebView).
    function syncAppHeight() {
      const vv = window.visualViewport;
      const h = (vv && vv.height) || window.innerHeight;
      root.style.setProperty("--app-height", `${h}px`);
    }
    syncAppHeight();
    const vvForApp = window.visualViewport;
    if (vvForApp) {
      vvForApp.addEventListener("resize", syncAppHeight);
      vvForApp.addEventListener("scroll", syncAppHeight);
    } else {
      window.addEventListener("resize", syncAppHeight);
    }

    function setKeyboard(height) {
      const open = height > 0;
      root.style.setProperty("--keyboard-height", `${height}px`);
      // Collapse home-bar inset while the keyboard covers it. Consumers read
      // var(--safe-bottom, env(safe-area-inset-bottom, 0px)).
      root.style.setProperty(
        "--safe-bottom",
        open ? "0px" : "env(safe-area-inset-bottom, 0px)"
      );

      if (open && !keyboardOpen) {
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
      } else if (!open && keyboardOpen) {
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
      }
      keyboardOpen = open;
      setTimeout(() => window.dispatchEvent(new Event("keyboardresize")), 280);
    }

    // Global preventScroll focus interception
    const INPUT_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);
    function isInputEl(el) {
      return el && (INPUT_TAGS.has(el.tagName) || el.isContentEditable);
    }
    function onTouchEnd(e) {
      const target = e.target;
      const inputEl = isInputEl(target) ? target
        : target.closest?.("input, textarea, select, [contenteditable]");
      if (!inputEl) return;
      if (document.activeElement === inputEl) return;
      e.preventDefault();
      inputEl.focus({ preventScroll: true });
    }
    document.addEventListener("touchend", onTouchEnd, { passive: false });

    // Strategy 1: WeChat API
    if (window.wx?.onKeyboardHeightChange) {
      window.wx.onKeyboardHeightChange((res) => setKeyboard(res.height));
      return () => {
        document.removeEventListener("touchend", onTouchEnd);
        if (vvForApp) {
          vvForApp.removeEventListener("resize", syncAppHeight);
          vvForApp.removeEventListener("scroll", syncAppHeight);
        } else {
          window.removeEventListener("resize", syncAppHeight);
        }
        if (keyboardOpen) {
          document.documentElement.style.overflow = "";
          document.body.style.overflow = "";
        }
      };
    }

    // Strategy 2: visualViewport
    const vv = window.visualViewport;
    let vvActive = false;
    function onVVResize() {
      if (!vv) return;
      const diff = window.innerHeight - vv.height;
      setKeyboard(diff > 100 ? diff : 0);
      vvActive = true;
    }
    if (vv) vv.addEventListener("resize", onVVResize);

    // Strategy 3: focusin/focusout
    function onFocusIn(e) {
      if (isInputEl(e.target) && !vvActive) setKeyboard(300);
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
      if (vvForApp) {
        vvForApp.removeEventListener("resize", syncAppHeight);
        vvForApp.removeEventListener("scroll", syncAppHeight);
      } else {
        window.removeEventListener("resize", syncAppHeight);
      }
      if (keyboardOpen) {
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
      }
    };
  }, []);
}

/**
 * Scroll a ref into view when the keyboard opens/closes.
 * Usage: useScrollOnKeyboard(bottomRef)
 */
export function useScrollOnKeyboard(ref) {
  const scroll = useCallback(() => {
    ref.current?.scrollIntoView({ behavior: "smooth" });
  }, [ref]);

  useEffect(() => {
    window.addEventListener("keyboardresize", scroll);
    return () => window.removeEventListener("keyboardresize", scroll);
  }, [scroll]);
}

/**
 * CSS for keyboard-aware containers (chat pages).
 * Apply as inline style on the outermost flex container.
 *
 * Uses --app-height (set by useKeyboard from visualViewport) as the source of
 * truth for "visible area above the keyboard". Falls back to 100% so pages
 * render correctly before the effect runs. Do NOT revert to
 * `calc(100% - var(--keyboard-height))` — that double-shrinks on WKWebView
 * where 100vh/100% already tracks the keyboard.
 */
export const keyboardAwareStyle = {
  display: "flex",
  flexDirection: "column",
  height: "var(--app-height, 100%)",
  overflow: "hidden",
  transition: "height 0.25s cubic-bezier(0.33,1,0.68,1)",
};
