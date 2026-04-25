// SectionError — admin v3 in-section error state.
// Same chrome as <EmptyState>, with `icon-circle.error` (dangerTint bg /
// danger icon), the `error` glyph, fixed "加载失败" title, the supplied
// message as desc, and a 重试 CTA when `onRetry` is provided.
// Mockup ref: docs/specs/2026-04-24-admin-modern-mockup-v3.html ~line 2042.

import { COLOR, FONT, RADIUS, SHADOW } from "../tokens";

export default function SectionError({ message, onRetry }) {
  const desc = message
    ? typeof message === "string"
      ? message
      : String(message)
    : "请稍后重试，或联系系统团队。";
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
          background: COLOR.dangerTint,
          color: COLOR.danger,
          display: "grid",
          placeItems: "center",
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
          error
        </span>
      </div>
      <div
        style={{
          fontSize: FONT.body,
          fontWeight: 600,
          color: COLOR.text1,
        }}
      >
        加载失败
      </div>
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
      {onRetry && (
        <a
          onClick={onRetry}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onRetry?.();
            }
          }}
          style={{
            marginTop: 4,
            fontSize: 12.5,
            color: COLOR.info,
            cursor: "pointer",
            fontWeight: 600,
            padding: "10px 14px",
            minHeight: 44,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          重试 →
        </a>
      )}
    </div>
  );
}
