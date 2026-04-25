// AlertsCallout — alerts panel on the 仪表盘 page.
//
// Consumes `/api/admin/overview` `alerts: [{ level, label, detail }]` and
// renders each row with a colored left rail keyed off `level`:
//   "error" → COLOR.danger / dangerTint bg
//   "warn"  → COLOR.warningBg / warningTint bg
//   default → bgCardAlt + subtle border (no rail)

import Panel from "../doctorDetail/Panel";
import EmptyState from "../components/EmptyState";
import { COLOR, FONT, RADIUS } from "../tokens";

const LEVEL_STYLE = {
  error: {
    bg: COLOR.dangerTint,
    rail: COLOR.danger,
    chipBg: COLOR.danger,
    chipFg: "#fff",
  },
  warn: {
    bg: COLOR.warningTint,
    rail: COLOR.warningBg,
    chipBg: COLOR.warningBg,
    chipFg: "#1A1A1A",
  },
};

function Row({ level, label, detail }) {
  const style = LEVEL_STYLE[level] || {
    bg: COLOR.bgCardAlt,
    rail: null,
    chipBg: COLOR.borderDefault,
    chipFg: COLOR.text2,
  };
  return (
    <div
      style={{
        position: "relative",
        padding: "10px 12px 10px 14px",
        borderRadius: RADIUS.md,
        background: style.bg,
        overflow: "hidden",
      }}
    >
      {style.rail && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: 3,
            background: style.rail,
          }}
        />
      )}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontWeight: 600,
          fontSize: FONT.body,
          color: COLOR.text1,
        }}
      >
        {label && (
          <span
            style={{
              fontSize: 9.5,
              fontWeight: 700,
              padding: "1px 7px",
              borderRadius: 999,
              background: style.chipBg,
              color: style.chipFg,
              letterSpacing: "0.06em",
            }}
          >
            {label}
          </span>
        )}
        <span
          style={{
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
        >
          {detail}
        </span>
      </div>
    </div>
  );
}

export default function AlertsCallout({ alerts }) {
  const items = Array.isArray(alerts) ? alerts : [];
  const hasItems = items.length > 0;
  const railLevel = items.some((a) => a.level === "error")
    ? "danger"
    : undefined;

  // Show at most 6 to keep the panel from dwarfing system health beside it.
  const visible = items.slice(0, 6);

  return (
    <Panel
      title="提醒"
      icon="priority_high"
      rail={railLevel}
      aside={hasItems ? `${items.length} 条` : ""}
      bodyPad={hasItems ? 12 : 0}
    >
      {!hasItems ? (
        <div style={{ padding: "10px 12px" }}>
          <EmptyState icon="task_alt" title="暂无提醒" desc="平台运行平稳" />
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
        >
          {visible.map((a, idx) => (
            <Row
              key={`${a.level}-${idx}`}
              level={a.level}
              label={a.label}
              detail={a.detail}
            />
          ))}
        </div>
      )}
    </Panel>
  );
}
