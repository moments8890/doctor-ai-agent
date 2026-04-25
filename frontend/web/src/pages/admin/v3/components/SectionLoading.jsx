// SectionLoading — admin v3 in-section loading state.
// Same chrome as <EmptyState>, with `icon-circle.loading` (infoTint bg /
// info icon), the `hourglass_top` glyph, and 3 skeleton lines (the middle
// one short) inside an 80%-width container.
// Mockup ref: docs/specs/2026-04-24-admin-modern-mockup-v3.html ~line 2031.

import { COLOR, FONT, RADIUS, SHADOW } from "../tokens";
import SkeletonLine from "./SkeletonLine";

export default function SectionLoading({ title = "正在加载…" }) {
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
          background: COLOR.infoTint,
          color: COLOR.info,
          display: "grid",
          placeItems: "center",
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
          hourglass_top
        </span>
      </div>
      <div
        style={{
          fontSize: FONT.body,
          fontWeight: 600,
          color: COLOR.text1,
        }}
      >
        {title}
      </div>
      <div
        style={{
          width: "80%",
          maxWidth: 280,
          display: "flex",
          flexDirection: "column",
          gap: 6,
          marginTop: 4,
        }}
      >
        <SkeletonLine />
        <SkeletonLine width="60%" />
        <SkeletonLine />
      </div>
    </div>
  );
}
