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

import { useEffect } from "react";
import { COLOR, FONT_STACK, FONT } from "./tokens";
import AdminSidebar from "./AdminSidebar";
import AdminTopbar from "./AdminTopbar";

const MOBILE_STYLE_ID = "admin-v3-mobile-styles";

const MOBILE_CSS = `
@media (max-width: 768px) {
  [data-v3-shell] { grid-template-columns: 1fr !important; }
  [data-v3-sidebar] { display: none !important; }
  [data-v3-content] { padding: 14px 12px 60px !important; }
  [data-v3="kpi"] { grid-template-columns: 1fr 1fr !important; }
  [data-v3="row-3-1"], [data-v3="row-2"] { grid-template-columns: 1fr !important; }
  [data-v3="chat-shell"] { grid-template-columns: 1fr !important; height: auto !important; }
  [data-v3="chat-list"] { display: none !important; }
  [data-v3="triptych"] { grid-template-columns: 1fr !important; }
  [data-v3="crumb-here"] { font-size: 18px !important; }
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

export default function AdminShellV3({ section, breadcrumb, children }) {
  useEffect(() => {
    injectMobileStyles();
  }, []);

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
      <AdminSidebar activeSection={section} />
      <main style={{ background: COLOR.bgPage, minWidth: 0 }}>
        <AdminTopbar breadcrumb={breadcrumb} />
        <div data-v3-content style={{ padding: "20px 24px 80px", maxWidth: 1320 }}>
          {children}
        </div>
      </main>
    </div>
  );
}
