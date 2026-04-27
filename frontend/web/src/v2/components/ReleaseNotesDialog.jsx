/**
 * ReleaseNotesDialog — "what's new" modal shown after a doctor's first
 * page mount post-release.
 *
 * Wiring lives in MyAIPage via the useReleaseNotes hook; this component
 * is render-only.
 */
import { CenterPopup } from "antd-mobile";
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
  if (!release) return null;
  return (
    <CenterPopup
      visible={visible}
      onClose={onDismiss}
      closeOnMaskClick={false}
      // Portal to body so the popup escapes any transformed page-stack
      // ancestor (translate3d on stack entries creates a containing block
      // for position:fixed and can shift the popup off-center).
      getContainer={() => document.body}
      bodyStyle={{
        padding: "22px 20px 20px",
        maxHeight: "85vh",
        overflowY: "auto",
        width: "min(86vw, 360px)",
        boxSizing: "border-box",
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
    </CenterPopup>
  );
}
