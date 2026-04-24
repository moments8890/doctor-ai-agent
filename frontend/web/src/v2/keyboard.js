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

    function setKeyboard(height, vvHeight) {
      const open = height > 0;
      root.style.setProperty("--keyboard-height", `${height}px`);
      // Write --vvh only while the keyboard is up. Page containers read
      // var(--vvh, 100%) — so when keyboard closes and --vvh is removed,
      // they fall back to plain 100%.
      if (open && vvHeight != null) {
        root.style.setProperty("--vvh", `${Math.round(vvHeight)}px`);
      } else {
        root.style.removeProperty("--vvh");
      }

      if (open && !keyboardOpen) {
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
        // Pin layout viewport at top. iOS Safari auto-scrolls the body
        // to bring the focused input into view; combined with a
        // --vvh-sized page that resets layout to 0, the composer ends
        // up orphaned mid-page with a keyboard-height gap below.
        // Keep it at 0 so visualViewport.offsetTop stays 0.
        window.scrollTo(0, 0);
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
      window.wx.onKeyboardHeightChange((res) => {
        // WeChat gives us keyboard height directly; derive vvh from it.
        const vvH = res.height > 0 ? Math.max(0, root.clientHeight - res.height) : null;
        setKeyboard(res.height, vvH);
      });
      return () => {
        document.removeEventListener("touchend", onTouchEnd);
        if (keyboardOpen) {
          document.documentElement.style.overflow = "";
          document.body.style.overflow = "";
        }
      };
    }

    // Strategy 2: visualViewport
    // Use root.clientHeight (layout viewport, stable across keyboard
    // show/hide on iOS 15.4+) as the reference — NOT window.innerHeight,
    // which on modern iOS Safari shrinks with the keyboard and produces
    // diff ~= 0.
    const vv = window.visualViewport;
    let vvActive = false;
    function onVVResize() {
      if (!vv) return;
      const diff = Math.max(0, root.clientHeight - vv.height);
      const kbOpen = diff > 100;
      setKeyboard(kbOpen ? diff : 0, kbOpen ? vv.height : null);
      vvActive = true;
    }
    function onVVScroll() {
      // If the layout viewport scrolls while keyboard is up, pin it back.
      if (keyboardOpen) window.scrollTo(0, 0);
    }
    if (vv) {
      vv.addEventListener("resize", onVVResize);
      vv.addEventListener("scroll", onVVScroll);
    }

    // Strategy 3: focusin/focusout
    function onFocusIn(e) {
      if (isInputEl(e.target) && !vvActive) {
        // Estimated keyboard height 300; vvh fallback = clientH - 300.
        setKeyboard(300, Math.max(0, root.clientHeight - 300));
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
      if (vv) {
        vv.removeEventListener("resize", onVVResize);
        vv.removeEventListener("scroll", onVVScroll);
      }
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
 * Sizes to --vvh (= visualViewport.height) only while keyboard is up.
 * Falls back to 100% otherwise. Paired with: setKeyboard() writes
 * --vvh, pins window.scrollTo(0,0), and sets body overflow:hidden so
 * the layout viewport doesn't auto-scroll out from under the page.
 */
export const keyboardAwareStyle = {
  display: "flex",
  flexDirection: "column",
  height: "var(--vvh, 100%)",
  overflow: "hidden",
};
