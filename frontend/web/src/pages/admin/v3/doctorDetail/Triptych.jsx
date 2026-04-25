// Triptych — 3-column AI 原稿 / 医生发送版 / 修改原因 layout used as the
// 医生处理 block content for `kind="reply_suggestion"` decision cards.
// Mirrors `<div class="triptych">` in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (lines ~1002-1026).
//
// Grid: 1fr 1fr 200px. Last column (修改原因) on bgCardAlt to set it apart
// as commentary, not message content.
//
// Props:
//   aiDraft     — string. AI 原稿.
//   sentVersion — string. 医生发送版.
//   reason      — string | null. 修改原因. Empty string is rendered as a
//                 thin "—" placeholder so the column doesn't collapse.

import { COLOR, RADIUS } from "../tokens";

const colLabelStyle = {
  fontSize: 10.5,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: COLOR.text3,
  fontWeight: 600,
  marginBottom: 5,
};

const cellBaseStyle = {
  padding: "10px 12px",
  borderRight: `1px solid ${COLOR.borderSubtle}`,
};

export default function Triptych({ aiDraft, sentVersion, reason }) {
  return (
    <div
      data-v3="triptych"
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr 200px",
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.md,
        overflow: "hidden",
        fontSize: 12.5,
        lineHeight: 1.55,
      }}
    >
      <div style={cellBaseStyle}>
        <div style={colLabelStyle}>AI 原稿</div>
        <div style={{ color: COLOR.text2 }}>{aiDraft || "—"}</div>
      </div>
      <div style={cellBaseStyle}>
        <div style={colLabelStyle}>医生发送版</div>
        <div style={{ color: COLOR.text1, fontWeight: 500 }}>
          {sentVersion || "—"}
        </div>
      </div>
      <div style={{ ...cellBaseStyle, borderRight: "none", background: COLOR.bgCardAlt }}>
        <div style={colLabelStyle}>修改原因</div>
        <div style={{ color: COLOR.text2 }}>
          {reason ? reason : <span style={{ color: COLOR.text4 }}>—</span>}
        </div>
      </div>
    </div>
  );
}

