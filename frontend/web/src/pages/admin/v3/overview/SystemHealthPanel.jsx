// SystemHealthPanel — small right-column tile on the 仪表盘 page.
//
// Reads from `/api/admin/overview` `hero.system_health` (24h LLM call log) +
// `secondary.new_knowledge.current` (last 7d new KB items as a coarse
// "knowledge base growth" signal).
//
// Status thresholds (codex v3 polish):
//   error_rate < 0.05 → 运行正常 (brand)
//   error_rate < 0.10 → 注意   (warningBg)
//   else              → 异常   (danger)

import Panel from "../doctorDetail/Panel";
import { COLOR, FONT, FONT_STACK } from "../tokens";

function StatusDot({ color }) {
  return (
    <span
      aria-hidden
      style={{
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
        boxShadow: `0 0 0 3px ${color}22`,
      }}
    />
  );
}

function StatRow({ label, value, unit, mono = true, isLast }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        padding: "9px 0",
        borderBottom: isLast ? "none" : `1px dashed ${COLOR.borderSubtle}`,
      }}
    >
      <span style={{ fontSize: FONT.base, color: COLOR.text2 }}>{label}</span>
      <span
        style={{
          fontSize: FONT.body,
          fontWeight: 500,
          color: COLOR.text1,
          fontFamily: mono ? FONT_STACK.mono : undefined,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
        {unit && (
          <span
            style={{
              fontSize: FONT.sm,
              fontWeight: 400,
              color: COLOR.text3,
              marginLeft: 3,
            }}
          >
            {unit}
          </span>
        )}
      </span>
    </div>
  );
}

function pickStatus(errorRate) {
  if (errorRate == null || !Number.isFinite(errorRate)) {
    return { label: "暂无数据", color: COLOR.text3, rail: undefined };
  }
  if (errorRate < 0.05) {
    return { label: "运行正常", color: COLOR.brand, rail: "brand" };
  }
  if (errorRate < 0.10) {
    return { label: "注意", color: COLOR.warningBg, rail: undefined };
  }
  return { label: "异常", color: COLOR.danger, rail: "danger" };
}

export default function SystemHealthPanel({ hero, secondary }) {
  const h = hero?.system_health || {};
  const knowledge = secondary?.new_knowledge || {};

  const errorRate = h.error_rate;
  const status = pickStatus(errorRate);

  const errorRatePct =
    errorRate != null && Number.isFinite(errorRate)
      ? `${(errorRate * 100).toFixed(1)}`
      : "—";

  return (
    <Panel
      title="系统健康"
      icon="monitor_heart"
      rail={status.rail}
      aside="24h"
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "2px 0 10px",
        }}
      >
        <StatusDot color={status.color} />
        <span
          style={{
            fontSize: FONT.lg,
            fontWeight: 600,
            color: COLOR.text1,
            letterSpacing: "-0.01em",
          }}
        >
          {status.label}
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: FONT.sm,
            color: COLOR.text3,
            fontFamily: FONT_STACK.mono,
          }}
        >
          错误率 {errorRatePct}%
        </span>
      </div>

      <div>
        <StatRow
          label="P95 延迟"
          value={h.p95_latency_ms != null ? Math.round(h.p95_latency_ms) : "—"}
          unit={h.p95_latency_ms != null ? "ms" : null}
        />
        <StatRow
          label="AI 调用 24h"
          value={h.calls_24h != null ? h.calls_24h : "—"}
        />
        <StatRow
          label="错误 24h"
          value={h.errors_24h != null ? h.errors_24h : "—"}
        />
        <StatRow
          label="新增知识 7d"
          value={knowledge.current != null ? knowledge.current : "—"}
          unit={knowledge.current != null ? "条" : null}
          isLast
        />
      </div>
    </Panel>
  );
}
