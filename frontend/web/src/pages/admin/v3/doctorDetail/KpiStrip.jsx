// KpiStrip — 5-cell metric row beneath the doctor header.
// Visual contract: docs/specs/2026-04-24-admin-modern-mockup-v3.html `.kpi-strip`.
//
// Cells: 患者 / 消息 / AI 采纳率 (info color) / 回复时效 P50 / 逾期任务.
// AI adoption number is COLOR.info (codex v3 polish — green dropped from
// this surface since adoption is contextual, not a celebration).

import { COLOR, FONT, FONT_STACK, RADIUS } from "../tokens";

function Cell({ label, value, unit, valueColor, trend, isLast }) {
  return (
    <div
      style={{
        padding: "14px 16px",
        borderRight: isLast ? "none" : `1px solid ${COLOR.borderSubtle}`,
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <div
        style={{
          fontSize: FONT.xs,
          textTransform: "uppercase",
          letterSpacing: "0.12em",
          color: COLOR.text3,
          fontWeight: 600,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 28,
          lineHeight: "32px",
          fontWeight: 600,
          letterSpacing: "-0.02em",
          color: valueColor || COLOR.text1,
          fontVariantNumeric: "tabular-nums",
          display: "flex",
          alignItems: "baseline",
          gap: 4,
        }}
      >
        {value}
        {unit && (
          <span
            style={{
              fontSize: FONT.base,
              fontWeight: 400,
              color: valueColor || COLOR.text2,
              letterSpacing: 0,
            }}
          >
            {unit}
          </span>
        )}
      </div>
      {trend && (
        <div
          style={{
            fontSize: 11.5,
            display: "flex",
            alignItems: "center",
            gap: 6,
            color:
              trend.dir === "up"
                ? COLOR.brand
                : trend.dir === "down"
                  ? COLOR.danger
                  : COLOR.text3,
            fontFamily: FONT_STACK.mono,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {trend.dir === "up" && (
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
              arrow_upward
            </span>
          )}
          {trend.dir === "down" && (
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
              arrow_downward
            </span>
          )}
          {trend.label}
        </div>
      )}
    </div>
  );
}

function safeNum(v, fallback = "—") {
  if (v === null || v === undefined || v === "") return fallback;
  return v;
}

export default function KpiStrip({ stats }) {
  const s = stats || {};
  const adoptionRate =
    s.ai_adoption != null && Number.isFinite(s.ai_adoption)
      ? Math.round(s.ai_adoption * 100)
      : null;
  const overdue = s.overdue_tasks ?? null;

  const cells = [
    {
      label: "近 7 日 患者",
      value: safeNum(s.patients),
      unit: s.patients != null ? "位" : null,
      trend: null,
    },
    {
      label: "近 7 日 消息",
      value: safeNum(s.messages),
      unit: null,
      trend: null,
    },
    {
      label: "AI 采纳率",
      value: adoptionRate != null ? adoptionRate : "—",
      unit: adoptionRate != null ? "%" : null,
      valueColor: adoptionRate != null ? COLOR.info : COLOR.text3,
      trend: null,
    },
    {
      label: "回复时效 P50",
      value: safeNum(s.response_p50_hours),
      unit: s.response_p50_hours != null ? "小时" : null,
      trend: null,
    },
    {
      label: "逾期任务",
      value: overdue != null ? overdue : "—",
      unit: null,
      valueColor: overdue != null && overdue > 0 ? COLOR.danger : undefined,
      trend: null,
    },
  ];

  return (
    <section
      data-v3="kpi"
      style={{
        marginTop: 12,
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        display: "grid",
        gridTemplateColumns: "repeat(5, 1fr)",
        overflow: "hidden",
        boxShadow: "0 1px 1px rgba(15,23,28,0.04)",
      }}
    >
      {cells.map((c, i) => (
        <Cell key={c.label} {...c} isLast={i === cells.length - 1} />
      ))}
    </section>
  );
}
