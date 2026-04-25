// AdminTopbar — sticky 56px header with breadcrumb + search + notification.
// Visual contract: docs/specs/2026-04-24-admin-modern-mockup-v3.html — `.topbar`, `.crumbs`, `.search`, `.icon-btn`.
//
// The breadcrumb's `.here` element is the ONLY >17px sans element in v3:
// 22px / weight 600 / letter-spacing -0.015em.

import { COLOR, FONT, FONT_STACK, RADIUS } from "./tokens";

export default function AdminTopbar({ breadcrumb = [] }) {
  return (
    <header
      style={{
        height: 56,
        padding: "0 20px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        background: "rgba(245, 247, 248, 0.88)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        position: "sticky",
        top: 0,
        zIndex: 5,
        fontFamily: FONT_STACK.sans,
      }}
    >
      {/* Breadcrumb */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 13,
          color: COLOR.text2,
        }}
      >
        {breadcrumb.map((c, i) => {
          const isLast = i === breadcrumb.length - 1;
          return (
            <span key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {i > 0 && <span style={{ color: COLOR.text4 }}>/</span>}
              {c.here ? (
                <span
                  data-v3="crumb-here"
                  style={{
                    color: COLOR.text1,
                    fontWeight: 600,
                    fontSize: 22,
                    letterSpacing: "-0.015em",
                  }}
                >
                  {c.label}
                </span>
              ) : (
                <a style={{ color: COLOR.text2, cursor: "pointer", textDecoration: "none" }}>
                  {c.label}
                </a>
              )}
              {/* no extra separator after last */}
              {!isLast && c.here ? null : null}
            </span>
          );
        })}
      </div>

      {/* Right side */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: COLOR.bgCard,
            border: `1px solid ${COLOR.borderDefault}`,
            borderRadius: RADIUS.md,
            padding: "7px 10px",
            fontSize: 13,
            color: COLOR.text3,
            width: 240,
            height: 36,
          }}
        >
          <span
            className="material-symbols-outlined"
            style={{ fontSize: 16, color: COLOR.text3 }}
          >
            search
          </span>
          <span>搜索患者、消息、知识…</span>
          <span
            style={{
              marginLeft: "auto",
              fontSize: 10.5,
              color: COLOR.text3,
              border: `1px solid ${COLOR.borderDefault}`,
              borderRadius: 4,
              padding: "0 4px",
              fontFamily: FONT_STACK.mono,
              background: COLOR.bgPage,
            }}
          >
            ⌘K
          </span>
        </div>
        <button
          type="button"
          title="通知"
          style={{
            width: 36,
            height: 36,
            borderRadius: RADIUS.md,
            border: "1px solid transparent",
            background: "transparent",
            color: COLOR.text2,
            cursor: "pointer",
            display: "grid",
            placeItems: "center",
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
            notifications
          </span>
        </button>
      </div>
    </header>
  );
}
