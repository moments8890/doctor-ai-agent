// SkeletonLine — single shimmer line for skeleton loading states.
// Matches the `.skel-line` rule in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (~line 1100):
//   height: 8px; gradient bgCanvas → bgCardAlt → bgCanvas at 200% 100%;
//   animation: shimmer 1.4s linear infinite (keyframes injected once).
//
// Props:
//   width — string | number. Defaults to "100%". Pass "60%" for short variant.

import { useEffect } from "react";
import { COLOR, RADIUS } from "../tokens";

const KEYFRAMES_ID = "admin-v3-shimmer-keyframes";

function ensureKeyframes() {
  if (typeof document === "undefined") return;
  if (document.getElementById(KEYFRAMES_ID)) return;
  const style = document.createElement("style");
  style.id = KEYFRAMES_ID;
  style.textContent =
    "@keyframes adminV3Shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }";
  document.head.appendChild(style);
}

export default function SkeletonLine({ width = "100%" }) {
  useEffect(() => {
    ensureKeyframes();
  }, []);
  return (
    <div
      aria-hidden
      style={{
        height: 8,
        width,
        borderRadius: RADIUS.sm,
        background: `linear-gradient(90deg, ${COLOR.bgCanvas}, ${COLOR.bgCardAlt}, ${COLOR.bgCanvas})`,
        backgroundSize: "200% 100%",
        animation: "adminV3Shimmer 1.4s linear infinite",
      }}
    />
  );
}
