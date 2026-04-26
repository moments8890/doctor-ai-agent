/**
 * IntakeBanner — sticky banner shown at the top of the patient chat while
 * an intake_session is active.
 *
 * Visual: tinted card "📝 正在采集病史 第N次问诊  [取消]" sitting on top of
 * the chat list. Uses v2 design tokens (APP, FONT, RADIUS, ICON).
 *
 * Cancel behaviour: the patient-side chat endpoint does not yet return a
 * session_id, so we cannot reliably call /api/patient/intake/cancel from
 * here. For now, "取消" hides the banner client-side via onCancel and the
 * caller decides whether to no-op or to attempt a backend cancel when a
 * session id becomes available. See PatientPage TODO.
 */

import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import { APP, FONT, ICON, RADIUS } from "../theme";

export default function IntakeBanner({ turnCount, onCancel }) {
  const label = turnCount > 0 ? `正在采集病史 · 第 ${turnCount} 轮问诊` : "正在采集病史";
  return (
    <div style={styles.wrap}>
      <div style={styles.iconBubble}>
        <EditNoteOutlinedIcon sx={{ fontSize: ICON.sm, color: APP.primary }} />
      </div>
      <div style={styles.label}>{label}</div>
      {onCancel && (
        <span
          role="button"
          tabIndex={0}
          aria-label="取消问诊"
          onClick={onCancel}
          style={styles.cancel}
        >
          取消
        </span>
      )}
    </div>
  );
}

const styles = {
  wrap: {
    margin: "8px 12px 0",
    padding: "10px 12px",
    background: APP.primaryLight,
    borderRadius: RADIUS.md,
    display: "flex",
    alignItems: "center",
    gap: 10,
    border: `0.5px solid ${APP.primary}`,
  },
  iconBubble: {
    width: 28,
    height: 28,
    borderRadius: RADIUS.md,
    background: APP.surface,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  label: {
    flex: 1,
    fontSize: FONT.sm,
    fontWeight: 600,
    color: APP.primary,
    minWidth: 0,
  },
  cancel: {
    fontSize: FONT.sm,
    color: APP.text3,
    padding: "4px 10px",
    borderRadius: RADIUS.sm,
    cursor: "pointer",
    userSelect: "none",
    flexShrink: 0,
  },
};
