// RiskTagRow — pill row for the 触发规则 / 风险 block of a DecisionCard.
// Mirrors `<div class="risk-row">` + `.risk-tag.risk-{high,med,low}` in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (lines ~988-1000).
//
// Codex v3 polish: risk-low was switched from brand-tint to info-tint so
// the row doesn't read as "everything is fine — green light". Brand stays
// reserved for accepted/done outcome states.
//
// Props:
//   risks — Array<{ label: string, level: "high" | "med" | "low" }>.
//
// `level === "high"` gets a leading warning glyph; med/low render label only.

import { COLOR } from "../tokens";

const LEVEL_STYLE = {
  high: {
    background: COLOR.dangerTint,
    border: "1px solid rgba(250,81,81,0.30)",
    color: COLOR.danger,
  },
  med: {
    background: COLOR.warningTint,
    border: "1px solid rgba(176,122,28,0.30)",
    color: COLOR.warning,
  },
  low: {
    background: COLOR.infoTint,
    border: "1px solid rgba(87,107,149,0.25)",
    color: COLOR.info,
  },
};

function RiskTag({ label, level }) {
  const styleByLevel = LEVEL_STYLE[level] || LEVEL_STYLE.low;
  return (
    <span
      style={{
        fontSize: 11.5,
        padding: "3px 9px",
        borderRadius: 999,
        fontWeight: 500,
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        ...styleByLevel,
      }}
    >
      {level === "high" && (
        <span className="material-symbols-outlined" style={{ fontSize: 12 }}>
          warning
        </span>
      )}
      {label}
    </span>
  );
}

export default function RiskTagRow({ risks }) {
  if (!Array.isArray(risks) || risks.length === 0) return null;
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {risks.map((r, i) => (
        <RiskTag key={`${r.label}-${i}`} label={r.label} level={r.level} />
      ))}
    </div>
  );
}
