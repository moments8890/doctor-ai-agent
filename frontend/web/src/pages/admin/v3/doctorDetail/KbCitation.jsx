// KbCitation — single citation row inside the 依据 block of a DecisionCard.
// Mirrors `<div class="kb-item">` in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (lines ~973-986).
//
// Visual contract (codex v3 polish): info-tint bg with 2px info left bar
// — NOT cream/ochre. Two-column grid: mono [KB-N] + bold title + dim quote.
//
// Props:
//   num    — number | string. Rendered as "[KB-${num}]".
//   title  — string.
//   quote  — string. Optional.
//
// Usage: <KbCitation num={12} title="高血压调药梯度" quote="先加量再加药" />

import { COLOR, FONT, FONT_STACK, RADIUS } from "../tokens";

export default function KbCitation({ num, title, quote }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: 10,
        padding: "8px 10px",
        background: COLOR.infoTint,
        borderLeft: `2px solid ${COLOR.info}`,
        borderRadius: RADIUS.sm - 2 || 4,
        fontSize: 12.5,
      }}
    >
      <div
        style={{
          fontFamily: FONT_STACK.mono,
          fontSize: FONT.xs,
          color: COLOR.info,
          fontWeight: 600,
        }}
      >
        [KB-{num}]
      </div>
      <div>
        <div style={{ color: COLOR.text1, fontWeight: 500 }}>{title}</div>
        {quote && (
          <div
            style={{
              color: COLOR.text2,
              marginTop: 2,
              fontSize: FONT.sm,
              lineHeight: 1.5,
            }}
          >
            {quote}
          </div>
        )}
      </div>
    </div>
  );
}
