/**
 * ReleaseNotesDialog — "what's new" modal shown after a doctor's first
 * page mount post-release.
 *
 * Wiring lives in MyAIPage via the useReleaseNotes hook; this component
 * is render-only.
 *
 * Implementation note: rolled our own overlay instead of antd-mobile's
 * CenterPopup. The miniprogram WebView centered CenterPopup off-axis
 * (left margin tighter than right) — likely an interaction with the
 * page-stack transformed ancestors. A plain fixed full-viewport flex
 * container is immune.
 */
import { createPortal } from "react-dom";
import { APP, FONT, RADIUS, ICON } from "../theme";

function FeatureCard({ Icon, title, description }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        padding: "12px 14px",
        backgroundColor: APP.surfaceAlt,
        borderRadius: RADIUS.md,
        alignItems: "flex-start",
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: RADIUS.md,
          backgroundColor: APP.primaryLight,
          color: APP.primary,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon sx={{ fontSize: ICON.sm }} />
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{
            fontSize: FONT.base,
            fontWeight: 600,
            color: APP.text1,
            lineHeight: 1.35,
            marginBottom: 2,
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontSize: FONT.sm,
            color: APP.text3,
            lineHeight: 1.55,
          }}
        >
          {description}
        </div>
      </div>
    </div>
  );
}

export default function ReleaseNotesDialog({ release, visible, onDismiss }) {
  if (!release || !visible) return null;
  if (typeof document === "undefined") return null;

  const overlay = (
    <div
      // Full-viewport mask + flex-center so the dialog body lands at
      // viewport center regardless of any transformed ancestor in the
      // app shell. Portaled to document.body to escape page-stack stacking.
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1100,
        backgroundColor: "rgba(0, 0, 0, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 360,
          maxHeight: "85vh",
          overflowY: "auto",
          padding: "22px 20px 20px",
          backgroundColor: APP.surface,
          borderRadius: RADIUS.lg,
          boxSizing: "border-box",
          boxShadow: "0 12px 36px rgba(0,0,0,0.18)",
        }}
      >
        <div
          style={{
            fontSize: FONT.lg,
            fontWeight: 600,
            color: APP.text1,
            marginBottom: 4,
            textAlign: "center",
          }}
        >
          {release.title}
        </div>
        <div
          style={{
            fontSize: FONT.xs,
            color: APP.text4,
            marginBottom: 16,
            textAlign: "center",
          }}
        >
          {release.date}
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 10,
            marginBottom: 18,
          }}
        >
          {release.features.map((f) => (
            <FeatureCard
              key={f.title}
              Icon={f.icon}
              title={f.title}
              description={f.description}
            />
          ))}
        </div>
        <div
          onClick={onDismiss}
          style={{
            width: "100%",
            padding: "12px 0",
            textAlign: "center",
            backgroundColor: APP.primary,
            color: APP.white,
            fontSize: FONT.base,
            fontWeight: 600,
            borderRadius: RADIUS.md,
            cursor: "pointer",
            userSelect: "none",
          }}
        >
          知道了
        </div>
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
}
