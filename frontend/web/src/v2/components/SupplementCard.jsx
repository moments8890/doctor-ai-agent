/**
 * SupplementCard — displays a patient's supplemental history submission
 * and lets the doctor accept it (merge into existing record), create a
 * new record from it, or ignore it entirely.
 *
 * v2 card pattern: white surface on gray page bg, RADIUS.lg outer.
 * Touch targets ≥ 44 × 44 CSS px (antd-mobile Button default).
 */
import { Button } from "antd-mobile";
import { APP, FONT, RADIUS } from "../theme";

const HISTORY_LABELS = {
  chief_complaint:      "主诉",
  present_illness:      "现病史",
  past_history:         "既往史",
  allergy_history:      "过敏史",
  personal_history:     "个人史",
  marital_reproductive: "婚育史",
  family_history:       "家族史",
};

/** Lightweight relative-time formatter — mirrors ReviewQueuePage.formatRelative */
function formatRelative(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return d.toLocaleDateString("zh-CN");
}

/**
 * @param {object}   supplement    — RecordSupplement object from the API
 * @param {function} onAccept      — called when doctor clicks 接受补充
 * @param {function} onCreateNew   — called when doctor clicks 创建新记录
 * @param {function} onIgnore      — called when doctor clicks 忽略
 * @param {boolean}  busy          — disables all buttons while a mutation is in-flight
 */
export default function SupplementCard({ supplement, onAccept, onCreateNew, onIgnore, busy }) {
  const entries = supplement.field_entries || [];
  const relTime = formatRelative(supplement.created_at);
  const patientName = supplement.patient_name || "患者";

  return (
    <div style={styles.wrap}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.title}>患者补充信息</span>
          <span style={styles.patientName}>{patientName}</span>
        </div>
        {relTime ? <span style={styles.meta}>{relTime}</span> : null}
      </div>

      {/* Field entries */}
      {entries.length > 0 ? (
        <div style={styles.body}>
          {entries.map((e, i) => (
            <div key={i} style={styles.entry}>
              <span style={styles.fieldLabel}>
                {HISTORY_LABELS[e.field_name] || e.field_name}
              </span>
              <p style={styles.fieldText}>{e.text}</p>
            </div>
          ))}
        </div>
      ) : (
        <p style={{ ...styles.fieldText, marginBottom: 14, color: APP.text4 }}>
          （无具体内容）
        </p>
      )}

      {/* Doctor actions */}
      <div style={styles.actions}>
        <Button
          color="primary"
          size="middle"
          disabled={busy}
          onClick={onAccept}
          style={styles.actionBtn}
        >
          接受补充
        </Button>
        <Button
          size="middle"
          disabled={busy}
          onClick={onCreateNew}
          style={styles.actionBtn}
        >
          创建新记录
        </Button>
        <Button
          size="middle"
          disabled={busy}
          onClick={onIgnore}
          style={styles.actionBtn}
        >
          忽略
        </Button>
      </div>
    </div>
  );
}

const styles = {
  wrap: {
    background: APP.surface,
    borderRadius: RADIUS.lg,
    margin: "8px 12px",
    padding: "14px 16px",
    boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    marginBottom: 10,
    gap: 8,
  },
  headerLeft: {
    display: "flex",
    alignItems: "baseline",
    gap: 8,
    minWidth: 0,
    flex: 1,
  },
  title: {
    fontSize: FONT.md,
    fontWeight: 600,
    color: APP.text1,
    flexShrink: 0,
  },
  patientName: {
    fontSize: FONT.sm,
    color: APP.text3,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  meta: {
    fontSize: FONT.xs,
    color: APP.text4,
    flexShrink: 0,
  },
  body: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    marginBottom: 14,
  },
  entry: {
    borderLeft: `3px solid ${APP.border}`,
    paddingLeft: 10,
  },
  fieldLabel: {
    fontSize: FONT.sm,
    color: APP.text4,
    display: "block",
    marginBottom: 2,
  },
  fieldText: {
    fontSize: FONT.base,
    color: APP.text1,
    lineHeight: 1.5,
    margin: 0,
  },
  actions: {
    display: "flex",
    gap: 8,
    justifyContent: "flex-end",
    flexWrap: "wrap",
  },
  actionBtn: {
    minHeight: 44,
  },
};
