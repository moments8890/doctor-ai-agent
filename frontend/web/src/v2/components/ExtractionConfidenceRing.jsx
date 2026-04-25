// frontend/web/src/v2/components/ExtractionConfidenceRing.jsx
// Renders N/7 as a ring. Honest about denominator; not a percentage, not a colored severity.
import { APP, FONT } from "../theme";

export default function ExtractionConfidenceRing({ confidence }) {
  const filled = Math.round((confidence ?? 0) * 7);
  const radius = 11;
  const circ = 2 * Math.PI * radius;
  const offset = circ - (filled / 7) * circ;
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <svg width="28" height="28">
        <circle cx="14" cy="14" r={radius} stroke={APP.borderLight} strokeWidth="3" fill="none" />
        <circle cx="14" cy="14" r={radius} stroke={APP.primary} strokeWidth="3" fill="none"
                strokeDasharray={circ} strokeDashoffset={offset}
                transform="rotate(-90 14 14)" />
      </svg>
      <span style={{ fontSize: FONT.xs, color: APP.text4 }}>{filled}/7</span>
    </div>
  );
}
