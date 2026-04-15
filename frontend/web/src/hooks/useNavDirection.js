/**
 * useNavDirection — detects forward/back navigation direction across renders.
 *
 * Returns "forward" | "back" | "none":
 * - "forward" — PUSH nav. PageSkeleton slides the new subpage in from right.
 * - "back"    — POP nav that originated from an intentional in-app back action
 *               (user tapped the ← arrow; handler called markIntentionalBack()
 *               just before navigate(-1)). PageSkeleton slides out to right.
 * - "none"    — First render ever, deep-link, or a POP from browser-back /
 *               swipe-back / hardware-back. We skip our animation because the
 *               browser renders its own visual on iOS (and a double play is
 *               visible). On Android WebView where there is no native visual,
 *               the SubpageHeader's ← arrow still animates correctly because
 *               that path goes through markIntentionalBack().
 *
 * Module-level state is used on purpose: a cross-section push unmounts the
 * old PageSkeleton and mounts a fresh one — per-hook refs would re-initialise
 * and lose the previous idx, so the new PageSkeleton would see no change and
 * report "none". Module state survives that unmount.
 *
 * NOTE on react-router coupling: we read `window.history.state?.idx`, which
 * is an implementation detail of react-router v6+ (a monotonically
 * incrementing id it attaches to each history entry). This is the only known
 * way today to tell PUSH from POP reliably across component boundaries
 * without plumbing. If react-router changes the shape, revisit this hook.
 *
 * StrictMode cache: computation is keyed on location.key so dev's
 * double-invoke doesn't consume the intentional-back flag twice or flip
 * direction between renders.
 */
import { useCallback, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

// Intentional-back flag. Set synchronously in our ← arrow handler and
// consumed by the very next popstate — not by a wall-clock timer. A timer
// leaked the flag when a navigation was blocked/delayed. The popstate
// listener is tight: it fires once, consumes, and the flag is gone before
// the next render computes direction.
//
// Fuse timer is kept as a last-resort safety net (cleared on consume) so a
// blocked nav can't keep the flag set forever.
let intentionalBackPending = false;
let fuseTimer = null;
let popstateListenerAttached = false;
const POPSTATE_FUSE_MS = 2000;

function attachPopstateConsumer() {
  if (popstateListenerAttached || typeof window === "undefined") return;
  popstateListenerAttached = true;
  // Capture phase so we observe before react-router's handler runs — but we
  // don't consume here (useNavDirection does that during the resulting
  // render, keyed on location.key, which gives us StrictMode safety). The
  // popstate handler only exists to clear the fuse early if we want to add
  // more sophisticated behaviour later.
}

/**
 * Call this synchronously right before a programmatic back nav
 * (navigate(-1)) so PageSkeleton can distinguish it from a browser/swipe
 * back and play its slide-out animation.
 */
export function markIntentionalBack() {
  intentionalBackPending = true;
  if (fuseTimer) clearTimeout(fuseTimer);
  // Fuse timer only; consumption is event-driven via useNavDirection reading
  // on the next location change. 2s is plenty for any real navigation and
  // short enough that a cancelled nav won't pollute a later real one.
  fuseTimer = setTimeout(() => { intentionalBackPending = false; }, POPSTATE_FUSE_MS);
}

function consumeIntentionalBack() {
  if (!intentionalBackPending) return false;
  intentionalBackPending = false;
  if (fuseTimer) { clearTimeout(fuseTimer); fuseTimer = null; }
  return true;
}

// Detect iOS (Safari, Chrome-for-iOS, Firefox-for-iOS). iOS browsers render
// their own slide visual during swipe-back, so our animation would double up.
// On every other platform (Android Chrome/WeChat WebView, Firefox Android,
// desktop) there is no native back visual, so we animate ALL POPs so the
// user gets consistent page-push feedback.
//
// Note: Android Chrome v120+ has predictive back for installed PWAs, but that
// only animates the browser chrome, not in-page routing. Our slide is still
// the right visual there.
function detectIOS() {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  if (/iPad|iPhone|iPod/.test(ua)) return true;
  // iPadOS 13+ reports as Mac — disambiguate via touch support.
  return navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1;
}
const IS_IOS = detectIOS();

// Module-level nav state. Survives component unmount/remount so cross-section
// pushes still report "forward" to the new PageSkeleton.
let moduleIdx = null;
let moduleDirection = "none";
let moduleLastKey = null;

function computeDirection(currentIdx, currentKey) {
  // Same navigation (or re-render within one nav) → same direction. This
  // short-circuits StrictMode's second render and any unrelated re-renders.
  if (currentKey === moduleLastKey) return moduleDirection;
  moduleLastKey = currentKey;

  if (moduleIdx === null) {
    moduleDirection = "none";
  } else if (currentIdx > moduleIdx) {
    moduleDirection = "forward";
  } else if (currentIdx < moduleIdx) {
    // iOS: only animate when the back was intentional (our ← arrow). A
    // swipe-back or browser-back is left to the browser's native visual.
    // Non-iOS: there is no native visual, so animate every back so the page
    // push/pop still feels coherent. This covers Android Chrome and WeChat
    // WebView — the target environment for most users here.
    if (IS_IOS) {
      moduleDirection = consumeIntentionalBack() ? "back" : "none";
    } else {
      // Still consume the flag so we don't leak it into a later nav.
      consumeIntentionalBack();
      moduleDirection = "back";
    }
  } else {
    // REPLACE or same idx — treat as not-a-nav.
    moduleDirection = "none";
  }

  moduleIdx = currentIdx;
  return moduleDirection;
}

/**
 * useBackWithAnimation — returns a callback that performs an animated back
 * nav. Use this instead of a bare `navigate(-1)` at any call site where the
 * user tapping something should feel like "go back" visually (settings
 * dialogs, dismiss modals, chat-reply send-then-back flows, etc.).
 *
 * Equivalent to:
 *     markIntentionalBack();
 *     navigate(-1);
 *
 * SubpageHeader already wraps ← with this behaviour; prefer using it for
 * regular back buttons. This hook is for custom back triggers that don't
 * go through SubpageHeader.
 */
export function useBackWithAnimation() {
  const navigate = useNavigate();
  return useCallback((steps = -1) => {
    markIntentionalBack();
    navigate(steps);
  }, [navigate]);
}

export function useNavDirection() {
  const location = useLocation();
  const idx = (typeof window !== "undefined" && window.history.state?.idx) ?? 0;
  const directionRef = useRef("none");

  useEffect(() => { attachPopstateConsumer(); }, []);

  directionRef.current = computeDirection(idx, location.key);

  // Reserved slot for potential post-commit side effects on location change.
  useEffect(() => {}, [location.key]);

  return directionRef.current;
}
