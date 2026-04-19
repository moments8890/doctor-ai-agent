/**
 * useOverlayTransition — CSS transition state for overlay subpages.
 *
 * Handles three scenarios:
 *   1. Tab → subpage (PUSH): slide in from right
 *   2. Subpage → tab (POP): slide out to right
 *   3. Subpage → different subpage (PUSH): slide new one in from right
 *
 * Uses react-router's useNavigationType() for direction detection.
 *
 * Usage:
 *   const { overlayStyle, showOverlay, overlayKey } = useOverlayTransition(routeKey);
 *   // routeKey: null when on a tab root, a unique string when on a subpage
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useNavigationType } from "react-router-dom";

const DURATION = 300;

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}

/**
 * @param {string|null} routeKey — null for tab roots, unique key for each subpage route
 * @returns {{ overlayStyle, showOverlay, overlayKey }}
 */
export function useOverlayTransition(routeKey) {
  const navType = useNavigationType();
  const [stage, setStage] = useState(routeKey ? "visible" : "hidden");
  // Track what's currently rendered in the overlay (persists during exit animation)
  const [renderedKey, setRenderedKey] = useState(routeKey);
  const prevKey = useRef(routeKey);
  const timerRef = useRef(null);

  useEffect(() => {
    const prev = prevKey.current;
    prevKey.current = routeKey;

    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const noAnim = prefersReducedMotion();
    const isReplace = navType === "REPLACE";

    if (routeKey && !prev) {
      // Case 1: Tab → subpage (entering overlay)
      setRenderedKey(routeKey);
      if (noAnim || isReplace) {
        setStage("visible");
      } else {
        setStage("enter");
        requestAnimationFrame(() => {
          requestAnimationFrame(() => setStage("visible"));
        });
      }
    } else if (!routeKey && prev) {
      // Case 2: Subpage → tab (leaving overlay)
      // Keep renderedKey so content stays visible during exit animation
      if (noAnim || isReplace) {
        setStage("hidden");
        setRenderedKey(null);
      } else {
        setStage("exit");
        timerRef.current = setTimeout(() => {
          setStage("hidden");
          setRenderedKey(null);
          timerRef.current = null;
        }, DURATION);
      }
    } else if (routeKey && prev && routeKey !== prev) {
      // Case 3: Subpage → different subpage
      setRenderedKey(routeKey);
      if (noAnim || isReplace || navType === "POP") {
        // POP between subpages (back): instant swap (no double-slide)
        setStage("visible");
      } else {
        // PUSH between subpages: slide the new one in
        setStage("enter");
        requestAnimationFrame(() => {
          requestAnimationFrame(() => setStage("visible"));
        });
      }
    }
  }, [routeKey, navType]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const overlayStyle = {
    position: "absolute",
    inset: 0,
    zIndex: 10,
    transform:
      stage === "enter" || stage === "exit"
        ? "translate3d(100%, 0, 0)"
        : "translate3d(0, 0, 0)",
    transition:
      stage === "enter" || stage === "hidden"
        ? "none"
        : `transform ${DURATION}ms cubic-bezier(0.32, 0.72, 0, 1)`,
    willChange: stage === "visible" || stage === "hidden" ? "auto" : "transform",
    visibility: stage === "hidden" ? "hidden" : "visible",
    pointerEvents: stage === "hidden" ? "none" : "auto",
  };

  return {
    stage,
    overlayStyle,
    showOverlay: stage !== "hidden",
    overlayKey: renderedKey,
  };
}

/**
 * useAnimatedBack — drop-in replacement for navigate(-1) in subpages.
 * React-router will report navType=POP, which triggers exit animation.
 */
export function useAnimatedBack() {
  const navigate = useNavigate();
  return useCallback(() => navigate(-1), [navigate]);
}
