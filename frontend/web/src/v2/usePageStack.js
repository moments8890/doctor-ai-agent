/**
 * usePageStack — maintains a stack of overlay pages with CSS slide transitions.
 *
 * Pages pushed onto the stack stay mounted (preserving state, scroll position,
 * fetched data) until they are popped. Only the topmost page is visible.
 *
 * IMPORTANT: Do NOT hide the base content (NavBar, tabs, TabBar) when the stack
 * has entries. The base must remain visible so it's ready when the stack empties.
 * Stack entries use opaque backgrounds to cover the base visually.
 *
 * Uses react-router's useNavigationType() for push/pop detection.
 *
 * Usage:
 *   const { stackEntries, overlayActive } = usePageStack(routeKey, renderContent);
 *   // stackEntries: [{ key, content, style }] — render all of them, only top is visible
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useNavigationType } from "react-router-dom";
import { APP } from "./theme";

const DURATION = 300;
const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}

/**
 * @param {string|null} routeKey — null for tab root, unique string per subpage
 * @param {(key: string) => React.ReactNode} renderContent — called once per key to create content
 * @returns {{ stackEntries: Array<{key, content, style}>, overlayActive: boolean }}
 */
export function usePageStack(routeKey, renderContent) {
  const navType = useNavigationType();
  const prevKey = useRef(routeKey);
  const timerRef = useRef(null);

  // Stack of { key, content } — bottom to top
  const [stack, setStack] = useState(() =>
    routeKey ? [{ key: routeKey, content: renderContent(routeKey) }] : []
  );
  // Animation state for the topmost entry: "idle" | "entering" | "exiting"
  const [topAnim, setTopAnim] = useState("idle");
  // Key being animated out (kept until animation completes)
  const [exitingKey, setExitingKey] = useState(null);

  useEffect(() => {
    const prev = prevKey.current;
    prevKey.current = routeKey;

    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    // TEMP: force no-animation for intake overlay to debug iPhone blank
    // page. If this resolves the bug, the root cause is animation-related
    // (rAF, transform, transition). Remove once diagnosed.
    const noAnim = prefersReducedMotion() || routeKey === "intake";
    const isReplace = navType === "REPLACE";

    if (routeKey && !prev) {
      const entry = { key: routeKey, content: renderContent(routeKey) };
      setStack([entry]);
      if (noAnim || isReplace) {
        setTopAnim("idle");
      } else {
        setTopAnim("entering");
        // Chained rAF triggers the slide-in smoothly. On iOS Safari, chained
        // rAF can be dropped when layout changes between them, leaving topAnim
        // stuck at "entering" and the page stuck off-screen at
        // translate3d(100%,0,0) → blank page. setTimeout fallback guarantees
        // topAnim flips to "idle" even if rAF never fires.
        let fired = false;
        const flip = () => {
          if (fired) return;
          fired = true;
          setTopAnim("idle");
        };
        requestAnimationFrame(() => requestAnimationFrame(flip));
        setTimeout(flip, 50);
      }
    } else if (!routeKey && prev) {
      // Subpage → tab: pop everything

      if (noAnim || isReplace) {
        setStack([]);
        setTopAnim("idle");
      } else {
        setTopAnim("exiting");
        setExitingKey(prev);
        timerRef.current = setTimeout(() => {
          setStack([]);
          setTopAnim("idle");
          setExitingKey(null);
          timerRef.current = null;
        }, DURATION);
      }
    } else if (routeKey && prev && routeKey !== prev) {
      if (navType === "POP") {
        // Back: pop the top entry, reveal the one underneath
        const stackSnap = stack;
        const idx = stackSnap.findIndex((e) => e.key === routeKey);
        if (idx >= 0) {
          // Going back to an existing stack entry — animate out top, remove above it

          if (noAnim) {
            setStack(stackSnap.slice(0, idx + 1));
          } else {
            setTopAnim("exiting");
            setExitingKey(prev);
            timerRef.current = setTimeout(() => {
              setStack((curr) => {
                const i = curr.findIndex((e) => e.key === routeKey);
                return i >= 0 ? curr.slice(0, i + 1) : curr;
              });
              setTopAnim("idle");
              setExitingKey(null);
              timerRef.current = null;
            }, DURATION);
          }
        } else {
          // Not in stack (cross-section back or browser history) — animate exit,
          // then replace with new content

          if (noAnim) {
            setStack([{ key: routeKey, content: renderContent(routeKey) }]);
          } else {
            setTopAnim("exiting");
            setExitingKey(prev);
            timerRef.current = setTimeout(() => {
              setStack([{ key: routeKey, content: renderContent(routeKey) }]);
              setTopAnim("idle");
              setExitingKey(null);
              timerRef.current = null;
            }, DURATION);
          }
        }
      } else {
        // Push: add new entry on top

        const entry = { key: routeKey, content: renderContent(routeKey) };
        setStack((s) => [...s, entry]);
        if (noAnim || isReplace) {
          setTopAnim("idle");
        } else {
          setTopAnim("entering");
          // setTimeout fallback — see note in the first-push branch above.
          let fired = false;
          const flip = () => {
            if (fired) return;
            fired = true;
            setTopAnim("idle");
          };
          requestAnimationFrame(() => requestAnimationFrame(flip));
          setTimeout(flip, 50);
        }
      }
    }
  }, [routeKey, navType, renderContent]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  // Build styled entries for rendering
  const stackEntries = stack.map((entry, idx) => {
    const isTop = idx === stack.length - 1;
    const isExiting = entry.key === exitingKey;

    let transform = "translate3d(0, 0, 0)";
    let transition = "none";
    let visibility = "visible";
    let pointerEvents = "auto";

    if (isTop || isExiting) {
      if (topAnim === "entering" && isTop) {
        transform = "translate3d(100%, 0, 0)";
      } else if (topAnim === "exiting" && isExiting) {
        transform = "translate3d(100%, 0, 0)";
        transition = `transform ${DURATION}ms ${EASE}`;
      } else if (topAnim === "idle" && isTop) {
        transition = `transform ${DURATION}ms ${EASE}`;
      }
    }

    if (!isTop && !isExiting) {
      const isSecondFromTop = idx === stack.length - 2;
      if (isSecondFromTop) {
        // Always keep second-from-top visible. The top entry (higher z-index)
        // covers it when fully slid in. During enter/exit animations it
        // provides the "previous page" behind the sliding page.
        // This avoids any timing dependency between topAnim state and
        // CSS transition duration.
        pointerEvents = "none";
      } else {
        visibility = "hidden";
        pointerEvents = "none";
      }
    }

    return {
      key: entry.key,
      content: entry.content,
      style: {
        position: "absolute",
        inset: 0,
        zIndex: 10 + idx,
        transform,
        transition,
        visibility,
        pointerEvents,
        overflow: "hidden",
        background: APP.scrim,
        willChange: topAnim !== "idle" && (isTop || isExiting) ? "transform" : "auto",
      },
    };
  });

  return {
    stackEntries,
    overlayActive: stack.length > 0 || exitingKey !== null,
    overlayCovers: stack.length > 0 && topAnim === "idle",
  };
}

/**
 * useAnimatedBack — drop-in replacement for navigate(-1).
 */
export function useAnimatedBack() {
  const navigate = useNavigate();
  return useCallback(() => navigate(-1), [navigate]);
}
