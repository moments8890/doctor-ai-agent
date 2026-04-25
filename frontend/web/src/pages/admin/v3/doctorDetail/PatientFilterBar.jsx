// PatientFilterBar — admin v3 doctor-detail 患者 tab filter chips.
// Mirrors `<div class="filter-bar">` from the v3 mockup.
//
// Active chip uses neutral fill (bgCanvas + text1) per codex v3 polish — NOT brandTint.
// Counts are rendered in mono numerals beside each label.

import { COLOR, FONT_STACK, RADIUS } from "../tokens";

const CHIPS = [
  { key: "all",    label: "全部",       icon: null },
  { key: "danger", label: "高危",       icon: "priority_high", iconColor: COLOR.danger },
  { key: "warn",   label: "未达标",     icon: null },
  { key: "silent", label: "7天无沟通",  icon: null },
  { key: "postop", label: "术后随访",   icon: null },
];

function Chip({ active, onClick, label, icon, iconColor, count }) {
  return (
    <span
      onClick={onClick}
      style={{
        fontSize: 12.5,
        height: 28,
        padding: "0 11px",
        borderRadius: RADIUS.pill,
        border: `1px solid ${active ? COLOR.text2 : COLOR.borderDefault}`,
        background: active ? COLOR.bgCanvas : COLOR.bgCard,
        color: COLOR.text1,
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        userSelect: "none",
      }}
    >
      {icon && (
        <span
          className="material-symbols-outlined"
          style={{ fontSize: 14, color: iconColor || COLOR.text2 }}
        >
          {icon}
        </span>
      )}
      {label}
      <span
        className="num"
        style={{
          color: active ? COLOR.text2 : COLOR.text3,
          fontVariantNumeric: "tabular-nums",
          fontFamily: FONT_STACK.mono,
          fontSize: 11,
          marginLeft: 2,
        }}
      >
        {count ?? 0}
      </span>
    </span>
  );
}

export default function PatientFilterBar({ filter, onChange, counts }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        padding: "10px 14px",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        background: COLOR.bgCardAlt,
        flexWrap: "wrap",
      }}
    >
      {CHIPS.map((chip) => (
        <Chip
          key={chip.key}
          active={filter === chip.key}
          onClick={() => onChange(chip.key)}
          label={chip.label}
          icon={chip.icon}
          iconColor={chip.iconColor}
          count={counts?.[chip.key]}
        />
      ))}
      <span style={{ flex: 1 }} />
      <span
        style={{
          fontSize: 12.5,
          color: COLOR.text2,
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          height: 28,
          padding: "0 8px",
          cursor: "pointer",
          borderRadius: 6,
          userSelect: "none",
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
          sort
        </span>
        按最近活跃
      </span>
    </div>
  );
}
