// AdminSidebar — left rail with brand, two nav groups, and user-menu trigger.
// Visual contract: docs/specs/2026-04-24-admin-modern-mockup-v3.html — `.sidebar`, `.nav-item`, `.user-row`, `.popover`.
//
// Active item motif: 2px brand-color rail at left:-12px (::before, rendered as
// an absolutely-positioned div since this file uses inline styles).
//
// Role labels in user-menu trigger:
//   viewer → "合作伙伴 · 只读"
//   super  → "管理员"

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { setAdminToken } from "../../../api";
import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "./tokens";
import { isDevMode, toggleDevMode, useAdminRole, useDevMode } from "./devMode";

// Each item carries an optional `href` — when present, clicking the item
// pushes that URL and dispatches a synthetic popstate so the v3 entry
// re-reads the URL (same pattern DoctorList rows use to jump to detail).
const NAV_GROUPS = [
  {
    key: "overview",
    label: "概览",
    items: [
      { key: "dashboard",  label: "仪表盘",      icon: "dashboard",            href: "?v=3&section=overview/dashboard" },
      { key: "doctors",    label: "全体医生",    icon: "stethoscope",          href: "?v=3" },
      { key: "patients",   label: "全体患者",    icon: "groups",               href: "?v=3&section=overview/patients" },
      { key: "chat",       label: "沟通中心",    icon: "forum",                href: "?v=3&section=overview/chat" },
      { key: "ai",         label: "知识库",      icon: "menu_book",            href: "?v=3&section=overview/ai" },
    ],
  },
  {
    key: "ops",
    label: "运营",
    items: [
      { key: "invites",    label: "邀请码",          icon: "key",                     href: "?v=3&section=ops/invites" },
      { key: "pilot",      label: "试点进度",        icon: "deployed_code_history",   href: "?v=3&section=ops/pilot" },
      { key: "report",     label: "合作伙伴报表",    icon: "summarize",               href: "?v=3&section=ops/report" },
      { key: "export",     label: "数据导出",        icon: "download",                href: "?v=3&section=ops/export" },
    ],
  },
];

function navigateTo(href) {
  if (typeof window === "undefined" || !href) return;
  // Push the new URL onto history and dispatch popstate so AdminPageV3's
  // useUrlRoute hook re-reads location.search and re-renders.
  window.history.pushState(null, "", href);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function NavItem({ item, active }) {
  const clickable = !!item.href;
  return (
    <a
      onClick={clickable ? () => navigateTo(item.href) : undefined}
      style={{
        position: "relative",
        height: 36,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0 10px",
        borderRadius: 7,
        fontSize: 13.5,
        color: active ? COLOR.text1 : COLOR.text2,
        background: active ? COLOR.brandTint : "transparent",
        fontWeight: active ? 500 : 400,
        cursor: clickable ? "pointer" : "default",
        marginBottom: 1,
        textDecoration: "none",
      }}
    >
      {/* 2px brand-color left rail — the motif */}
      {active && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: -12,
            top: 6,
            bottom: 6,
            width: 2,
            background: COLOR.brand,
            borderRadius: "0 2px 2px 0",
          }}
        />
      )}
      <span
        className="material-symbols-outlined"
        style={{
          fontSize: 18,
          color: active ? COLOR.brand : COLOR.text3,
          flexShrink: 0,
        }}
      >
        {item.icon}
      </span>
      <span>{item.label}</span>
    </a>
  );
}

// ── User menu ────────────────────────────────────────────────────────────

function PopoverRow({ icon, label, danger, children, onClick, mono }) {
  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (!onClick) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      style={{
        // Touch target ≥ 44 — bumped from mockup's 32 for the desktop too;
        // popover items are click-anywhere safe.
        minHeight: 36,
        padding: "0 10px",
        borderRadius: 5,
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: onClick ? "pointer" : "default",
        color: danger ? COLOR.danger : (mono ? COLOR.text3 : COLOR.text1),
        fontFamily: mono ? FONT_STACK.mono : undefined,
        fontSize: mono ? 11.5 : 12.5,
      }}
    >
      <span
        className="material-symbols-outlined"
        style={{ fontSize: 16, color: danger ? COLOR.danger : (mono ? COLOR.text3 : COLOR.text2) }}
      >
        {icon}
      </span>
      <span style={{ flex: 1 }}>{label}</span>
      {children}
    </div>
  );
}

function Switch({ on, onClick }) {
  // 26x14 pill matching `.switch` in the mockup. Click handler stops
  // propagation so the surrounding row's onClick doesn't double-fire.
  return (
    <span
      role="switch"
      aria-checked={on ? "true" : "false"}
      tabIndex={0}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          e.stopPropagation();
          onClick?.();
        }
      }}
      style={{
        width: 26,
        height: 14,
        background: on ? COLOR.brand : COLOR.text4,
        borderRadius: 7,
        position: "relative",
        flexShrink: 0,
        marginLeft: "auto",
        cursor: "pointer",
        display: "inline-block",
        transition: "background 200ms",
      }}
    >
      <span
        aria-hidden
        style={{
          position: "absolute",
          width: 10,
          height: 10,
          background: "#fff",
          borderRadius: "50%",
          top: 2,
          left: on ? 14 : 2,
          transition: "left 200ms",
        }}
      />
    </span>
  );
}

function UserMenu({ role }) {
  const [open, setOpen] = useState(false);
  const dev = useDevMode();
  const wrapRef = useRef(null);
  const navigate = useNavigate();

  // Click-outside closes the popover.
  useEffect(() => {
    if (!open) return undefined;
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const roleLabel = role === "viewer" ? "合作伙伴 · 只读" : "管理员";
  const showDevRow = role !== "viewer";

  function handleLogout() {
    localStorage.removeItem("adminToken");
    setAdminToken("");
    setOpen(false);
    navigate("/admin/login");
  }

  return (
    <div
      ref={wrapRef}
      style={{
        marginTop: "auto",
        padding: "8px 4px 0",
        borderTop: `1px solid ${COLOR.borderSubtle}`,
      }}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          height: 44,
          padding: "0 8px",
          borderRadius: 7,
          cursor: "pointer",
          position: "relative",
          background: open ? COLOR.bgPage : "transparent",
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: COLOR.info,
            color: "#fff",
            display: "grid",
            placeItems: "center",
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
            person
          </span>
        </div>
        <div
          style={{
            fontSize: 13,
            fontWeight: 500,
            color: COLOR.text1,
            lineHeight: 1.2,
          }}
        >
          {roleLabel}
        </div>
        <span
          className="material-symbols-outlined"
          style={{
            marginLeft: "auto",
            color: COLOR.text4,
            fontSize: 18,
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform 150ms",
          }}
        >
          expand_less
        </span>

        {open && (
          <div
            // Stop click propagation inside the popover; row clicks have
            // their own handlers and shouldn't bubble back to the trigger.
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "absolute",
              bottom: "calc(100% + 6px)",
              left: 0,
              right: 0,
              background: COLOR.bgCard,
              border: `1px solid ${COLOR.borderDefault}`,
              borderRadius: RADIUS.md,
              boxShadow: SHADOW.s2,
              padding: 6,
              fontSize: 12.5,
              zIndex: 10,
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            <PopoverRow icon="person" label="账号设置" onClick={() => setOpen(false)} />
            <PopoverRow icon="help" label="帮助 / 反馈" onClick={() => setOpen(false)} />
            {showDevRow && (
              <PopoverRow icon="terminal" label="raw_db_view (internal)" mono onClick={toggleDevMode}>
                <Switch on={dev} onClick={toggleDevMode} />
              </PopoverRow>
            )}
            <PopoverRow icon="logout" label="退出" danger onClick={handleLogout} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function AdminSidebar({ activeSection }) {
  const role = useAdminRole();

  return (
    <aside
      data-v3-sidebar
      style={{
        borderRight: `1px solid ${COLOR.borderSubtle}`,
        background: COLOR.bgCard,
        padding: "16px 12px 12px",
        position: "sticky",
        top: 0,
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        fontFamily: FONT_STACK.sans,
      }}
    >
      {/* Brand */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "4px 8px 14px",
          borderBottom: `1px solid ${COLOR.borderSubtle}`,
          marginBottom: 12,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 7,
            background: COLOR.brand,
            color: "#fff",
            display: "grid",
            placeItems: "center",
            fontWeight: 600,
            fontSize: 13,
          }}
        >
          鲸
        </div>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
          <span style={{ fontSize: FONT.body, fontWeight: 600, color: COLOR.text1 }}>
            鲸鱼随行
          </span>
          <span
            style={{
              fontSize: 10,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: COLOR.text3,
              fontWeight: 500,
            }}
          >
            Admin
          </span>
        </div>
      </div>

      {/* Nav groups */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {NAV_GROUPS.map((group) => (
          <div key={group.label} style={{ marginBottom: 12 }}>
            <div
              style={{
                fontSize: 10.5,
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: COLOR.text3,
                padding: "4px 10px 6px",
                fontWeight: 600,
              }}
            >
              {group.label}
            </div>
            {group.items.map((item) => (
              <NavItem
                key={item.key}
                item={item}
                active={item.key === activeSection}
              />
            ))}
          </div>
        ))}
      </div>

      <UserMenu role={role} />
    </aside>
  );
}

// Re-export so callers (e.g. e2e helpers) can read the current dev-mode
// flag without importing devMode.js directly.
export { isDevMode };
