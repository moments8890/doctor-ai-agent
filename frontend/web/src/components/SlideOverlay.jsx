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
 *                          Used by callers that render a fading backdrop and
 *                          need to drop it when the enter animation finishes.
 *   sx, zIndex           — cosmetic overrides for the overlay wrapper.
 */
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { COLOR } from "../theme";
import { useNavDirection } from "../hooks/useNavDirection";

const SLIDE_TRANSITION = { type: "tween", duration: 0.28, ease: [0.32, 0.72, 0, 1] };

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
  const effectiveDirection = reduceMotion ? "none" : direction;

  const overlayStyle = {
    position: "absolute", inset: 0, zIndex,
    backgroundColor: COLOR.surface,
    ...sx,
  };

  if (effectiveDirection === "none") {
    // Unmount synchronously. Still fire the completion callback so callers
    // that rely on it for backdrop cleanup don't get stuck in transitioning.
    return show ? (
      <div style={overlayStyle} ref={() => onAnimationComplete?.()}>
        {children}
      </div>
    ) : null;
  }

  // iOS/WeChat push semantics: on FORWARD, the outgoing page slides left
  // (parallax) while the incoming page slides in from the right. On BACK,
  // the outgoing page slides right off-screen. Without a non-zero exit
  // target, framer-motion optimises the animation away and unmounts the old
  // page immediately — which makes the base briefly visible before the new
  // page arrives.
  const initialX = effectiveDirection === "forward" ? "100%" : 0;
  const exitX = effectiveDirection === "back" ? "100%" : "-30%";
  // `initial` on AnimatePresence only affects children present at FIRST
  // MOUNT of AnimatePresence (deep-link / fresh-mount case). Children added
  // after AnimatePresence is already mounted animate regardless. We set it
  // false to keep deep-link mounts instant; the section-level SlideOverlay
  // (in DoctorPage) handles cross-section slide-ins separately.
  const animateInitial = false;

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
          style={{ ...overlayStyle, willChange: "transform" }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
