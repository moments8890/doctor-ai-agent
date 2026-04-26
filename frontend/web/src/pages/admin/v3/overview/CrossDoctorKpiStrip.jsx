// CrossDoctorKpiStrip — 5-cell platform-wide metric row at the top of the
// 仪表盘 (admin v3 overview/dashboard) page.
//
// Visual contract: matches the doctor-detail KpiStrip exactly (28px / weight
// 600 numbers, 11px uppercase labels, 5-equal columns, dividers, COLOR.info
// for AI 采纳率, COLOR.danger when 待回复消息 > 0). Uses the
// `/api/admin/overview` `hero` block as the data source — that shape is
// different from `stats_7d` so it gets its own component instead of reusing
// KpiStrip.
//
// Cells (left → right):
//   活跃医生 / 注册患者 / 本周问诊 / AI 采纳率 / 待回复消息
//
// `hero.active_doctors.current/total`        — denominator shown as `/N`
// `secondary.new_patients.current`           — 7d new patients (best signal
//                                              for "registered patients" we
//                                              have without a fresh endpoint)
// `hero.intakes.started`                  — intakes 7d
// `hero.ai_acceptance.rate` (0..1)           — × 100 → integer pct
// `hero.unanswered_messages.count`           — red when > 0

import { COLOR, FONT, FONT_STACK, RADIUS } from "../tokens";

function Cell({ label, value, unit, valueColor, hint, isLast }) {
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
      {hint && (
        <div
          style={{
            fontSize: 11.5,
            color: COLOR.text3,
            fontFamily: FONT_STACK.mono,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

function safeNum(v, fallback = "—") {
  if (v === null || v === undefined || v === "") return fallback;
  return v;
}

export default function CrossDoctorKpiStrip({ hero, secondary }) {
  const h = hero || {};
  const s = secondary || {};

  const active = h.active_doctors || {};
  const intakes = h.intakes || {};
  const acceptance = h.ai_acceptance || {};
  const unanswered = h.unanswered_messages || {};
  const newPatients = s.new_patients || {};

  const adoptionRate =
    acceptance.rate != null && Number.isFinite(acceptance.rate)
      ? Math.round(acceptance.rate * 100)
      : null;

  const unansweredCount = unanswered.count;

  const cells = [
    {
      label: "活跃医生",
      value: safeNum(active.current),
      unit: active.total != null ? `/ ${active.total}` : null,
      hint: active.current != null ? "近 7 日活跃" : null,
    },
    {
      label: "新增患者",
      value: safeNum(newPatients.current),
      unit: newPatients.current != null ? "位" : null,
      hint: "近 7 日",
    },
    {
      label: "本周问诊",
      value: safeNum(intakes.started),
      unit: null,
      hint:
        intakes.completed != null
          ? `${intakes.completed} 已完成`
          : null,
    },
    {
      label: "AI 采纳率",
      value: adoptionRate != null ? adoptionRate : "—",
      unit: adoptionRate != null ? "%" : null,
      valueColor: adoptionRate != null ? COLOR.info : COLOR.text3,
    },
    {
      label: "待回复消息",
      value: safeNum(unansweredCount),
      unit: null,
      valueColor:
        unansweredCount != null && unansweredCount > 0
          ? COLOR.danger
          : undefined,
      hint:
        unanswered.oldest_hours != null && unansweredCount > 0
          ? `最久 ${unanswered.oldest_hours}h`
          : null,
    },
  ];

  return (
    <section
      data-v3="cross-kpi"
      style={{
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
