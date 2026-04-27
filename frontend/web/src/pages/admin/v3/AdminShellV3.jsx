// AdminShellV3 — outer grid (sidebar + main with sticky topbar).
// Visual contract: docs/specs/2026-04-24-admin-modern-mockup-v3.html — `.app`, `.main`, `.content`.
//
// Mobile strategy (Task 4.3):
// v3 components use inline styles, but `@media (max-width: 768px)` cannot
// be expressed inline. Approach: inject a single <style> element on first
// mount that targets stable `data-v3-*` attributes and class names assigned
// by the relevant components:
//
//   data-v3-shell    → AdminShellV3 root grid → 1fr columns
//   data-v3-sidebar  → AdminSidebar <aside>   → display: none
//   data-v3-content  → AdminShellV3 content   → tighter padding
//   data-v3="kpi"    → KpiStrip <section>     → 2-col grid
//   data-v3="row-3-1"/ "row-2" → Overview/AI grids → single column
//   data-v3="chat-shell" → ChatTab <div>      → single column, auto height
//   data-v3="chat-list"  → ChatList <div>     → display: none
//   data-v3="triptych"   → Triptych <div>     → single column
//   data-v3="crumb-here" → AdminTopbar `.here` → 18px
//
// We picked Option A (data attributes) — cleaner than free-form class
// strings and survives minification. The targeted components below got a
// 1-line attribute add each.

import { useEffect, useState } from "react";
import { COLOR, FONT_STACK, FONT } from "./tokens";
import AdminSidebar from "./AdminSidebar";
import AdminTopbar from "./AdminTopbar";

const MOBILE_STYLE_ID = "admin-v3-mobile-styles";

// The v2 patient/doctor app deliberately runs as a fixed-viewport mobile
// shell — main.jsx imports `antd-mobile/es/global` (which sets html/body
// height:100%) and v2/App.jsx wraps everything in .v2-mobile-outer +
// .v2-mobile-inner with `height: 100%; overflow: hidden`. That makes the
// patient app behave like a native screen (internal scroll containers,
// sticky bottom tab-bar, no document scroll). Admin v3 lives inside the
// SAME bundle but needs the OPPOSITE — normal document scroll for tall
// dashboards. We scope an override to a body class toggled by the shell
// on mount, so the mobile app keeps its native feel intact.
const MOBILE_CSS = `
body.admin-v3-mounted,
body.admin-v3-mounted #root,
body.admin-v3-mounted .v2-mobile-outer,
body.admin-v3-mounted .v2-mobile-inner,
html:has(body.admin-v3-mounted) {
  height: auto !important;
  min-height: 100% !important;
  overflow: visible !important;
}

@media (max-width: 768px) {
  [data-v3-shell] { grid-template-columns: 1fr !important; }
  /* Sidebar becomes a slide-in drawer instead of being hidden — toggled
     by data-v3-mobile-open on the <aside>. Off-screen by default; the
     hamburger in AdminTopbar flips the attribute. */
  [data-v3-sidebar] {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    height: 100dvh !important;
    width: 260px !important;
    max-width: 80vw !important;
    z-index: 30 !important;
    transform: translateX(-100%);
    transition: transform 200ms ease-out;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.18);
  }
  [data-v3-sidebar][data-v3-mobile-open="true"] {
    transform: translateX(0);
  }
  [data-v3="hamburger"] { display: grid !important; }
  [data-v3-content] { padding: 14px 12px 60px !important; }
  [data-v3="kpi"] { grid-template-columns: 1fr 1fr !important; }
  [data-v3="row-3-1"], [data-v3="row-2"] { grid-template-columns: 1fr !important; }
  [data-v3="chat-shell"] { grid-template-columns: 1fr !important; height: auto !important; }
  [data-v3="chat-list"] { display: none !important; }
  [data-v3="triptych"] { grid-template-columns: 1fr !important; }
  [data-v3="crumb-here"] { font-size: 18px !important; }
  /* Wide grid tables (ops InviteCodes, PartnerReport, etc.) — let them
     keep their desktop column widths but horizontal-scroll inside the
     wrapper instead of squeezing each column to ~50px. The min-width on
     direct children preserves readability; touch scroll keeps it native. */
  [data-v3="table-scroll"] {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
  }
  [data-v3="table-scroll"] > * { min-width: 560px; }
}
`;

function injectMobileStyles() {
  if (typeof document === "undefined") return;
  if (document.getElementById(MOBILE_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = MOBILE_STYLE_ID;
  style.textContent = MOBILE_CSS;
  document.head.appendChild(style);
}

export default function AdminShellV3({ section, breadcrumb, showBack = false, children }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    injectMobileStyles();
    document.body.classList.add("admin-v3-mounted");
    return () => document.body.classList.remove("admin-v3-mounted");
  }, []);

  // Auto-close drawer on browser back/forward — popstate is what
  // sidebar nav clicks dispatch too, so this also handles tap-to-navigate.
  useEffect(() => {
    if (!mobileNavOpen) return;
    const close = () => setMobileNavOpen(false);
    window.addEventListener("popstate", close);
    return () => window.removeEventListener("popstate", close);
  }, [mobileNavOpen]);

  return (
    <div
      data-v3-shell
      style={{
        display: "grid",
        gridTemplateColumns: "240px 1fr",
        minHeight: "100vh",
        background: COLOR.bgPage,
        color: COLOR.text1,
        fontFamily: FONT_STACK.sans,
        fontSize: FONT.body,
        lineHeight: 1.55,
        WebkitFontSmoothing: "antialiased",
      }}
    >
      <AdminSidebar
        activeSection={section}
        mobileOpen={mobileNavOpen}
        onAfterNavigate={() => setMobileNavOpen(false)}
      />
      {/* Backdrop — only rendered while the mobile drawer is open. Tap
          anywhere outside the drawer to dismiss. Above content (z:25) but
          below the sidebar drawer (z:30). */}
      {mobileNavOpen && (
        <div
          onClick={() => setMobileNavOpen(false)}
          aria-hidden
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.4)",
            zIndex: 25,
          }}
        />
      )}
      <main style={{ background: COLOR.bgPage, minWidth: 0 }}>
        <AdminTopbar
          breadcrumb={breadcrumb}
          showBack={showBack}
          onMobileNavOpen={() => setMobileNavOpen(true)}
        />
        <div data-v3-content style={{ padding: "20px 24px 80px", maxWidth: 1320 }}>
          {children}
        </div>
      </main>
    </div>
  );
}
