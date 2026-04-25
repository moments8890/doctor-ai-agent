// Panel — reusable card wrapper for v3 admin surfaces.
// Mirrors `<div class="panel">…<div class="panel-head">…<div class="panel-body">`
// from docs/specs/2026-04-24-admin-modern-mockup-v3.html.
//
// Props:
//   title    — string (renders inside .panel-title with optional leading icon)
//   icon     — Material Symbols Outlined icon name (string), optional
//   aside    — string or node (right side of head, mono small caption)
//   rail     — "danger" | "info" | "brand" | undefined → 2px left rail accent
//   bodyPad  — override panel-body padding (default 16px). Pass 0 to opt out.
//   children — panel body content
//
// Note: the rail is rendered as a positioned <span> child rather than ::before
// because v3 components are inline-styled (no stylesheets at the call site).
//
// Reference impl: AiAdoptionPanel / AlertList / TimelinePanel (Task 2.2).

import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";

const RAIL_COLOR = {
  danger: COLOR.danger,
  info: COLOR.info,
  brand: COLOR.brand,
};

export default function Panel({
  title,
  icon,
  aside,
  rail,
  bodyPad,
  children,
  style,
}) {
  const railColor = rail ? RAIL_COLOR[rail] : null;
  const bodyPadding =
    bodyPad === 0 || bodyPad === "0"
      ? 0
      : bodyPad != null
        ? bodyPad
        : 16;

  return (
    <section
      style={{
        position: "relative",
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        boxShadow: SHADOW.s1,
        overflow: "hidden",
        ...style,
      }}
    >
      {railColor && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: 2,
            background: railColor,
          }}
        />
      )}

      <div
        style={{
          height: 44,
          padding: "0 16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: `1px solid ${COLOR.borderSubtle}`,
        }}
      >
        <div
          style={{
            fontSize: FONT.body,
            fontWeight: 600,
            letterSpacing: "-0.005em",
            color: COLOR.text1,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {icon && (
            <span
              className="material-symbols-outlined"
              style={{
                fontSize: FONT.lg,
                color: rail === "danger" ? COLOR.danger : COLOR.text3,
              }}
            >
              {icon}
            </span>
          )}
          {title}
        </div>
        {aside != null && aside !== "" && (
          <div
            style={{
              fontSize: FONT.sm,
              color: COLOR.text2,
              fontFamily: FONT_STACK.mono,
            }}
          >
            {aside}
          </div>
        )}
      </div>

      <div style={{ padding: bodyPadding }}>{children}</div>
    </section>
  );
}
