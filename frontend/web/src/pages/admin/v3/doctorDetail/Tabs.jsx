// Tabs — 4 tabs above the doctor detail content panels.
// Visual contract: docs/specs/2026-04-24-admin-modern-mockup-v3.html `.tabs`.
//
// Active tab gets borderBottom 2px brand + brand-color icon + brand-tint badge.
// Counts come from `related[key]?.count`.

import { COLOR, FONT, FONT_STACK } from "../tokens";

const TAB_DEFS = [
  { key: "overview", label: "总览",     icon: "overview",              countKey: null },
  { key: "patients", label: "患者",     icon: "groups",                countKey: "patients" },
  { key: "chat",     label: "沟通",     icon: "forum",                 countKey: "messages" },
  { key: "ai",       label: "AI 与知识", icon: "network_intelligence", countKey: "suggestions" },
];

function TabItem({ tab, active, onClick, count }) {
  return (
    <div
      role="tab"
      aria-selected={active}
      onClick={onClick}
      style={{
        height: 40,
        padding: "0 14px",
        fontSize: 13.5,
        color: active ? COLOR.text1 : COLOR.text2,
        cursor: "pointer",
        borderBottom: `2px solid ${active ? COLOR.brand : "transparent"}`,
        marginBottom: -1,
        display: "flex",
        alignItems: "center",
        gap: 7,
        fontWeight: active ? 500 : 400,
        transition: "100ms",
        userSelect: "none",
      }}
    >
      <span
        className="material-symbols-outlined"
        style={{
          fontSize: 17,
          color: active ? COLOR.brand : COLOR.text3,
        }}
      >
        {tab.icon}
      </span>
      <span>{tab.label}</span>
      {count != null && (
        <span
          style={{
            fontSize: 10.5,
            fontFamily: FONT_STACK.mono,
            background: active ? COLOR.brandTint : COLOR.bgCanvas,
            color: active ? COLOR.brand : COLOR.text2,
            padding: "1px 7px",
            borderRadius: 999,
          }}
        >
          {count}
        </span>
      )}
    </div>
  );
}

export default function Tabs({ value, onChange, related }) {
  return (
    <nav
      role="tablist"
      style={{
        marginTop: 22,
        display: "flex",
        gap: 2,
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        fontFamily: FONT_STACK.sans,
        fontSize: FONT.body,
      }}
    >
      {TAB_DEFS.map((tab) => {
        const count = tab.countKey ? related?.[tab.countKey]?.count ?? null : null;
        return (
          <TabItem
            key={tab.key}
            tab={tab}
            active={value === tab.key}
            count={count}
            onClick={() => onChange(tab.key)}
          />
        );
      })}
    </nav>
  );
}

export { TAB_DEFS };
