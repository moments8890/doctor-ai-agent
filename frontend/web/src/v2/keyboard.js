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

    // --- Visible-viewport height as CSS var (approach b, per codex) ---
    // Single source of truth for "visible area above the keyboard". Chat
    // shells size themselves with `height: var(--vvh, 100dvh)`. Don't
    // subtract --keyboard-height on top — that mixes coordinate systems
    // and double-counts on WKWebView / WeChat.
    function updateVvh() {
      const vv = window.visualViewport;
      const h = vv ? vv.height : window.innerHeight;
      root.style.setProperty("--vvh", `${Math.round(h)}px`);
    }
    updateVvh();
    const vvForVvh = window.visualViewport;
    if (vvForVvh) {
      vvForVvh.addEventListener("resize", updateVvh);
      vvForVvh.addEventListener("scroll", updateVvh);
    } else {
      window.addEventListener("resize", updateVvh);
    }

    function setKeyboard(height) {
      const open = height > 0;
      root.style.setProperty("--keyboard-height", `${height}px`);

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
        if (vvForVvh) {
          vvForVvh.removeEventListener("resize", updateVvh);
          vvForVvh.removeEventListener("scroll", updateVvh);
        } else {
          window.removeEventListener("resize", updateVvh);
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
      if (vvForVvh) {
        vvForVvh.removeEventListener("resize", updateVvh);
        vvForVvh.removeEventListener("scroll", updateVvh);
      } else {
        window.removeEventListener("resize", updateVvh);
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
 * Sizes to --vvh (= visualViewport.height, set by useKeyboard) so the
 * shell matches the visible area above the keyboard. Falls back to
 * 100dvh on platforms without visualViewport (or before the hook
 * mounts). Do NOT switch back to `calc(100% - var(--keyboard-height))`
 * — that mixes layout-viewport math with keyboard math and
 * double-counts on iOS/WKWebView.
 *
 * The message list inside should be the ONLY scroll container
 * (flex: 1 + overflow-y: auto). The composer stays in normal flow as
 * flex: 0 0 auto at the bottom.
 */
export const keyboardAwareStyle = {
  display: "flex",
  flexDirection: "column",
  // Fills a flex-column parent (embedded chat inside PatientDetail) via
  // flex: 1. In a block/absolute parent (standalone chat as the top-level
  // page in DoctorPage's overlay), flex properties are ignored and
  // height: var(--vvh) takes effect.
  flex: 1,
  minHeight: 0,
  height: "var(--vvh, 100dvh)",
  overflow: "hidden",
};
