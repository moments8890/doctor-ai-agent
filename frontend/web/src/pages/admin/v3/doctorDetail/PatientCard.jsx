// PatientCard — admin v3 doctor-detail 患者 tab card.
// Mirrors `<div class="pc">` from docs/specs/2026-04-24-admin-modern-mockup-v3.html.
//
// Props:
//   patient: {
//     id, name, meta?,                    // header text
//     risk: "danger" | "warn" | null,     // drives avatar tint + danger rail
//     silentDays?, isPostOp?,             // for the filter, not rendered here
//     spark?: number[],                   // ~9 points, 0..22 range; falls back to flat-line
//     stats?: { messages, records },      // mono numbers in the footer
//     statusTag?: { label, kind: "danger" | "warn" | "ok" | "quiet" },
//   }
//
// The 2px left rail for high-risk cards is rendered as an absolutely-positioned
// inner div to avoid needing a global stylesheet for `::before`.

import { COLOR, FONT, FONT_STACK, RADIUS } from "../tokens";

const TAG_COLOR = {
  danger: { color: COLOR.danger, fontWeight: 600 },
  warn:   { color: COLOR.warning, fontWeight: 500 },
  ok:     { color: COLOR.brand, fontWeight: 400 },
  quiet:  { color: COLOR.text3, fontWeight: 400 },
};

function Sparkline({ points, isDanger }) {
  // points: array of y values (0..22). x is auto-distributed across viewBox 0..240.
  const stroke = isDanger ? COLOR.danger : COLOR.brand;
  const ys = Array.isArray(points) && points.length >= 2
    ? points
    : [11, 11, 11, 11, 11, 11, 11, 11, 11];
  const stable = !points || points.length < 2;
  const finalStroke = stable ? COLOR.text3 : stroke;
  const step = 240 / (ys.length - 1);
  const polyPoints = ys.map((y, i) => `${(i * step).toFixed(1)},${y}`).join(" ");
  return (
    <div
      style={{
        height: 22,
        background: COLOR.bgCardAlt,
        borderRadius: 4,
        position: "relative",
      }}
    >
      <svg
        viewBox="0 0 240 22"
        preserveAspectRatio="none"
        style={{ width: "100%", height: "100%", display: "block" }}
      >
        <polyline points={polyPoints} fill="none" stroke={finalStroke} strokeWidth="1.5" />
      </svg>
    </div>
  );
}

export default function PatientCard({ patient }) {
  const isDanger = patient.risk === "danger";
  const initial = (patient.name || "?").trim().charAt(0);

  return (
    <div
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.md,
        padding: "12px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        cursor: "pointer",
        transition: "120ms",
        position: "relative",
      }}
    >
      {isDanger && (
        <div
          style={{
            content: '""',
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: 2,
            background: COLOR.danger,
            borderRadius: "2px 0 0 2px",
          }}
        />
      )}

      {/* head: avatar + name + meta */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: "50%",
            display: "grid",
            placeItems: "center",
            fontSize: FONT.sm,
            fontWeight: 600,
            background: isDanger ? COLOR.dangerTint : COLOR.brandTint,
            color: isDanger ? COLOR.danger : COLOR.brand,
          }}
        >
          {initial}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: FONT.body, fontWeight: 600, color: COLOR.text1 }}>
            {patient.name}
          </div>
          {patient.meta && (
            <div
              style={{
                fontSize: 11.5,
                color: COLOR.text2,
                marginTop: 1,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {patient.meta}
            </div>
          )}
        </div>
      </div>

      {/* sparkline */}
      <Sparkline points={patient.spark} isDanger={isDanger} />

      {/* stats footer */}
      <div
        style={{
          display: "flex",
          gap: 12,
          fontSize: 11.5,
          color: COLOR.text2,
          borderTop: `1px dashed ${COLOR.borderSubtle}`,
          paddingTop: 6,
          alignItems: "center",
        }}
      >
        <span>
          <b
            style={{
              color: COLOR.text1,
              fontWeight: 600,
              fontVariantNumeric: "tabular-nums",
              fontFamily: FONT_STACK.mono,
            }}
          >
            {patient.stats?.messages ?? 0}
          </b>{" "}
          消息
        </span>
        <span>
          <b
            style={{
              color: COLOR.text1,
              fontWeight: 600,
              fontVariantNumeric: "tabular-nums",
              fontFamily: FONT_STACK.mono,
            }}
          >
            {patient.stats?.records ?? 0}
          </b>{" "}
          病历
        </span>
        {patient.statusTag && (
          <span style={{ marginLeft: "auto", ...TAG_COLOR[patient.statusTag.kind] }}>
            {patient.statusTag.label}
          </span>
        )}
      </div>
    </div>
  );
}
