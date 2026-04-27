/**
 * ReleaseNotesDialog — "what's new" modal shown after a doctor's first
 * page mount post-release.
 *
 * Wiring lives in MyAIPage via the useReleaseNotes hook; this component
 * is render-only. Uses antd-mobile's Dialog (the project standard for
 * confirmations across the app) so styling, animation, scroll-lock,
 * and z-index layering match every other dialog the doctor sees.
 */
import { Dialog } from "antd-mobile";
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

  const content = (
    <div>
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
          maxHeight: "60vh",
          overflowY: "auto",
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
    </div>
  );

  return (
    <Dialog
      visible={visible}
      content={content}
      closeOnAction
      closeOnMaskClick={false}
      onClose={onDismiss}
      actions={[
        {
          key: "ok",
          text: "知道了",
          bold: true,
          onClick: onDismiss,
        },
      ]}
    />
  );
}
