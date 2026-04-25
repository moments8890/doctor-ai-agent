// EmptyState — admin v3 empty-state card.
// Mirrors `.state-card` + `.icon-circle.empty` in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (~line 1076).
//
// Layout: 44px round icon circle (bgCanvas bg, text3 icon) + 14px/600 title +
// 12.5px desc + optional CTA (info color, 12.5px/600).
//
// Props:
//   icon  — Material Symbols icon name (default "inbox").
//   title — string | node.
//   desc  — string | node. Optional.
//   cta   — string. Optional CTA label (renders an arrow appended).
//   onCta — () => void. Required when `cta` is set.

import { COLOR, FONT, RADIUS, SHADOW } from "../tokens";

export default function EmptyState({ icon = "inbox", title, desc, cta, onCta }) {
  return (
    <div
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        padding: "28px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        alignItems: "center",
        textAlign: "center",
        minHeight: 180,
        justifyContent: "center",
        boxShadow: SHADOW.s1,
      }}
    >
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: "50%",
          background: COLOR.bgCanvas,
          color: COLOR.text3,
          display: "grid",
          placeItems: "center",
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
          {icon}
        </span>
      </div>
      {title && (
        <div
          style={{
            fontSize: FONT.body,
            fontWeight: 600,
            color: COLOR.text1,
          }}
        >
          {title}
        </div>
      )}
      {desc && (
        <div
          style={{
            fontSize: 12.5,
            color: COLOR.text2,
            maxWidth: 240,
            lineHeight: 1.5,
          }}
        >
          {desc}
        </div>
      )}
      {cta && (
        <a
          onClick={onCta}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onCta?.();
            }
          }}
          style={{
            marginTop: 4,
            fontSize: 12.5,
            color: COLOR.info,
            cursor: "pointer",
            fontWeight: 600,
            // Touch target ≥ 44×44 — provide invisible padding without
            // disrupting the centered text alignment.
            padding: "10px 14px",
            minHeight: 44,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {cta} →
        </a>
      )}
    </div>
  );
}
