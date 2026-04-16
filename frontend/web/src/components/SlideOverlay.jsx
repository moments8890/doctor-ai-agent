/**
 * SlideOverlay — WeChat-style push/pop animation for a full-screen overlay.
 *
 * Three code paths depending on direction:
 * - "forward" / "back" → AnimatePresence + motion.div with tween slide.
 * - "none"             → plain div (or null). Bypasses AnimatePresence so a
 *                        disappearing overlay unmounts in the SAME commit
 *                        instead of lingering one frame in the exit phase.
 *                        Covers: first render, deep-link, iOS swipe-back,
 *                        browser-back, prefers-reduced-motion.
 *
 * Props:
 *   show                 — whether the overlay content should be rendered
 *   stackKey             — identity of the current overlay. Changes trigger
 *                          exit+enter transitions between peers.
 *   onAnimationComplete  — fires after every transition end (enter or exit).
 *   sx, zIndex           — cosmetic overrides for the overlay wrapper.
 */
import { createContext, useContext, useRef } from "react";
import { useLocation } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { COLOR } from "../theme";
import { useNavDirection } from "../hooks/useNavDirection";

export const SLIDE_TRANSITION = { type: "tween", duration: 0.3, ease: [0.32, 0.72, 0, 1] };

/**
 * When true, inner SlideOverlays skip their entry animation because an
 * outer cross-section slide is already handling the visual transition.
 */
export const SuppressAnimationContext = createContext(false);

export default function SlideOverlay({
  show,
  stackKey = "overlay",
  children,
  sx,
  zIndex = 2,
  onAnimationComplete,
}) {
  const direction = useNavDirection();
  const reduceMotion = useReducedMotion();
  const suppressAnimation = useContext(SuppressAnimationContext);
  const effectiveDirection = reduceMotion ? "none" : direction;
  const location = useLocation();

  // Track whether we already rendered content for this location.
  // Prevents re-animation when suppress context transitions from true→false
  // (outer cross-section animation completing doesn't re-trigger inner slide).
  // Check BEFORE setting — otherwise first render always thinks it was already shown.
  const shownForKeyRef = useRef(null);
  const alreadyShown = show && shownForKeyRef.current === location.key;
  if (show) shownForKeyRef.current = location.key;
  if (!show) shownForKeyRef.current = null;

  const overlayStyle = {
    position: "absolute", inset: 0, zIndex,
    backgroundColor: COLOR.surface,
    ...sx,
  };

  // No animation: suppressed, direction=none, or already shown for this nav
  if (effectiveDirection === "none" || suppressAnimation || (alreadyShown && effectiveDirection === "forward")) {
    return show ? (
      <div style={overlayStyle} ref={() => onAnimationComplete?.()}>
        {children}
      </div>
    ) : null;
  }

  const initialX = effectiveDirection === "forward" ? "100%" : 0;
  const exitX = effectiveDirection === "back" ? "100%" : "-24%";
  const animateInitial = effectiveDirection === "forward";

  return (
    <AnimatePresence initial={animateInitial} mode="sync">
      {show && (
        <motion.div
          key={stackKey}
          initial={{ x: initialX }}
          animate={{ x: 0 }}
          exit={{ x: exitX }}
          transition={SLIDE_TRANSITION}
          onAnimationComplete={onAnimationComplete}
          style={{
            ...overlayStyle,
            willChange: "transform",
            boxShadow: "-1px 0 0 rgba(0,0,0,0.05), -8px 0 24px rgba(0,0,0,0.10)",
          }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
