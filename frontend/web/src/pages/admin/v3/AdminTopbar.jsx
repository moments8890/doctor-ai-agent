// AdminTopbar — sticky 56px header with optional back arrow + breadcrumb.
// Visual contract: docs/specs/2026-04-24-admin-modern-mockup-v3.html — `.topbar`, `.crumbs`, `.search`, `.icon-btn`.
//
// The breadcrumb's `.here` element is the ONLY >17px sans element in v3:
// 22px / weight 600 / letter-spacing -0.015em.
//
// Back navigation:
// - Each non-`.here` breadcrumb item should carry an `href` so clicking it
//   navigates up. The topbar renders a `←` arrow on the left whenever any
//   breadcrumb item carries an href — that arrow targets the LAST href
//   (i.e., the immediate parent), giving operators a one-tap "go up" that
//   matches WeChat / iOS conventions.
// - Items without href render as plain text (top-level "医生" / "概览"
//   labels that have no parent target).

import { COLOR, FONT, FONT_STACK, RADIUS } from "./tokens";

function navigateToHref(href) {
  if (!href || typeof window === "undefined") return;
  // hrefs are stored as `?...` query strings relative to the current
  // pathname. Resolve against window.location.pathname so the same
  // breadcrumb works whether the page sits at /admin or /admin/.
  const target = href.startsWith("?")
    ? `${window.location.pathname}${href}`
    : href;
  window.history.pushState(null, "", target);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export default function AdminTopbar({ breadcrumb = [] }) {
  // Pick the LAST breadcrumb item with an href as the parent target — that's
  // the immediate ancestor. e.g. patient detail's breadcrumb is
  // `医生 / <doctor> / <patient,here>`; parent = the doctor item.
  const parent = [...breadcrumb].reverse().find((c) => c.href);

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
      {/* Breadcrumb (with optional back arrow) */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 13,
          color: COLOR.text2,
        }}
      >
        {parent && (
          <button
            type="button"
            onClick={() => navigateToHref(parent.href)}
            title={`返回 ${parent.label}`}
            aria-label={`返回 ${parent.label}`}
            style={{
              width: 32,
              height: 32,
              marginRight: 4,
              borderRadius: RADIUS.md,
              border: `1px solid ${COLOR.borderDefault}`,
              background: COLOR.bgCard,
              color: COLOR.text1,
              cursor: "pointer",
              display: "grid",
              placeItems: "center",
              transition: "background 100ms",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = COLOR.bgCardAlt)}
            onMouseLeave={(e) => (e.currentTarget.style.background = COLOR.bgCard)}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              arrow_back
            </span>
          </button>
        )}
        {breadcrumb.map((c, i) => {
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
              ) : c.href ? (
                <a
                  onClick={() => navigateToHref(c.href)}
                  style={{
                    color: COLOR.text2,
                    cursor: "pointer",
                    textDecoration: "none",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = COLOR.text1)}
                  onMouseLeave={(e) => (e.currentTarget.style.color = COLOR.text2)}
                >
                  {c.label}
                </a>
              ) : (
                <span style={{ color: COLOR.text2 }}>{c.label}</span>
              )}
            </span>
          );
        })}
      </div>

      {/* Right side intentionally empty — the search box and notification
          button were placeholders for features that haven't shipped yet,
          and unwired clickable-looking elements train operators to ignore
          the topbar. They'll come back when there's a real search index
          and a real notification feed behind them. */}
    </header>
  );
}
