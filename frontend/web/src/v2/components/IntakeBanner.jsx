/**
 * IntakeBanner — sticky banner shown at the top of the patient chat while
 * an intake_session is active.
 *
 * Collapsed: 📝 + label + [ProgressBar] + N/6 + chevron + 取消
 * Expanded:  same row + per-step list (✓/⃝ + plain-language label + value or 待采集)
 *
 * Six steps (chief_complaint + present_illness collapsed into one user-visible
 * "症状情况" step since they're tightly coupled in the intake flow):
 *   1. 症状情况   → chief_complaint AND present_illness both filled
 *   2. 既往史      → past_history
 *   3. 过敏史      → allergy_history
 *   4. 家族史      → family_history
 *   5. 个人史      → personal_history
 *   6. 婚育情况    → marital_reproductive
 *
 * Backend passes ChatResponse.collected (dict). We derive step status here.
 * No turn count display — patients don't think in turns; "已完成 N/6 步" is
 * the actionable signal.
 */

import { useState } from "react";
import { ProgressBar } from "antd-mobile";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import { APP, FONT, ICON, RADIUS } from "../theme";

const STEPS = [
  {
    key: "symptoms",
    label: "症状情况",
    fields: ["chief_complaint", "present_illness"],
    requireAll: true,
  },
  { key: "past_history",         label: "既往史",   fields: ["past_history"] },
  { key: "allergy_history",      label: "过敏史",   fields: ["allergy_history"] },
  { key: "family_history",       label: "家族史",   fields: ["family_history"] },
  { key: "personal_history",     label: "个人史",   fields: ["personal_history"] },
  { key: "marital_reproductive", label: "婚育情况", fields: ["marital_reproductive"] },
];

function isFieldFilled(value) {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

// Carry-forward fields seeded from a prior visit must be patient-confirmed
// before they count as filled — otherwise the banner shows 6/6 while the
// engine keeps asking, and the 提交给医生 button never appears. The server
// surfaces the unconfirmed list explicitly (POST /chat + GET /chat/intake/status
// both return `unconfirmed_carry_forward: [field_name, ...]`).
function computeSteps(collected, unconfirmedSet) {
  const c = collected || {};
  return STEPS.map((step) => {
    const filledFields = step.fields.filter(
      (f) => isFieldFilled(c[f]) && !unconfirmedSet.has(f),
    );
    const filled = step.requireAll
      ? filledFields.length === step.fields.length
      : filledFields.length > 0;
    // Display value: still show the carried text so the patient can see
    // what's there even when unconfirmed (the value is information, but
    // doesn't count toward progress until they confirm it).
    const displayValue = step.fields
      .map((f) => c[f])
      .filter((v) => isFieldFilled(v))
      .join("、");
    return { ...step, filled, displayValue };
  });
}

export default function IntakeBanner({
  collected,
  status,
  onSubmit,
  onCancel,
  unconfirmedCarryForward = [],
}) {
  const [expanded, setExpanded] = useState(false);
  const unconfirmedSet = new Set(unconfirmedCarryForward);
  const steps = computeSteps(collected, unconfirmedSet);
  const filledCount = steps.filter((s) => s.filled).length;
  const total = steps.length;
  const percent = total === 0 ? 0 : Math.round((filledCount / total) * 100);
  const reviewing = status === "reviewing";

  return (
    <div style={styles.wrap}>
      <div style={styles.row}>
        <div style={styles.iconBubble}>
          <EditNoteOutlinedIcon sx={{ fontSize: ICON.sm, color: APP.primary }} />
        </div>
        <div style={styles.labelCol}>
          <div style={styles.title}>
            {reviewing ? "信息已整理，请确认后提交" : "正在采集病史"}
          </div>
          <div style={styles.progressRow}>
            <ProgressBar
              percent={percent}
              style={{
                "--fill-color": APP.primary,
                "--track-color": APP.surface,
                flex: 1,
              }}
            />
            <span style={styles.count}>已完成 {filledCount}/{total} 步</span>
          </div>
        </div>
        <span
          role="button"
          tabIndex={0}
          aria-label={expanded ? "收起" : "展开"}
          onClick={() => setExpanded((e) => !e)}
          style={styles.expandBtn}
        >
          {expanded ? <ExpandLessIcon sx={{ fontSize: ICON.sm }} /> : <ExpandMoreIcon sx={{ fontSize: ICON.sm }} />}
        </span>
        {reviewing && onSubmit && (
          <span
            role="button"
            tabIndex={0}
            aria-label="提交给医生"
            onClick={onSubmit}
            style={styles.submitBtn}
          >
            提交给医生
          </span>
        )}
        {onCancel && (
          <span
            role="button"
            tabIndex={0}
            aria-label="取消问诊"
            onClick={onCancel}
            style={reviewing ? styles.cancelLink : styles.cancel}
          >
            取消
          </span>
        )}
      </div>
      {expanded && (
        <div style={styles.list}>
          {steps.map((step) => (
            <div key={step.key} style={styles.item}>
              {step.filled ? (
                <CheckCircleIcon sx={{ fontSize: ICON.sm, color: APP.primary, flexShrink: 0 }} />
              ) : (
                <RadioButtonUncheckedIcon sx={{ fontSize: ICON.sm, color: APP.text4, flexShrink: 0 }} />
              )}
              <span style={styles.itemLabel}>{step.label}</span>
              <span style={step.filled ? styles.itemValue : styles.itemPending}>
                {step.filled ? step.displayValue : "待采集"}
              </span>
            </div>
          ))}
        </div>
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
    border: `0.5px solid ${APP.primary}`,
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: 10,
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
  labelCol: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    fontSize: FONT.sm,
    fontWeight: 600,
    color: APP.primary,
    marginBottom: 4,
  },
  progressRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  count: {
    fontSize: FONT.xs,
    color: APP.text3,
    flexShrink: 0,
  },
  expandBtn: {
    width: 28,
    height: 28,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: APP.text3,
    cursor: "pointer",
    flexShrink: 0,
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
  submitBtn: {
    fontSize: FONT.sm,
    color: APP.white,
    background: APP.primary,
    padding: "8px 12px",
    borderRadius: RADIUS.md,
    cursor: "pointer",
    userSelect: "none",
    flexShrink: 0,
    fontWeight: 500,
    minHeight: 32,
    display: "inline-flex",
    alignItems: "center",
  },
  cancelLink: {
    fontSize: FONT.sm,
    color: APP.text4,
    padding: "4px 6px",
    cursor: "pointer",
    userSelect: "none",
    flexShrink: 0,
    textDecoration: "underline",
  },
  list: {
    marginTop: 10,
    paddingTop: 10,
    borderTop: `0.5px solid ${APP.primary}`,
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  item: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  itemLabel: {
    fontSize: FONT.sm,
    fontWeight: 500,
    color: APP.text2,
    minWidth: 60,
    flexShrink: 0,
  },
  itemValue: {
    fontSize: FONT.sm,
    color: APP.text1,
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  itemPending: {
    fontSize: FONT.sm,
    color: APP.text4,
    flex: 1,
  },
};
