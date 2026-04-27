/**
 * IntakeSubmitPopup — patient-side confirm dialog shown when the engine has
 * flipped intake status to "reviewing" and the patient taps 提交给医生 on
 * the IntakeBanner (or the inline 查看并提交 CTA on the wrap-up message).
 *
 * Centered Dialog (was a bottom-sheet Popup). Title + subtitle + field
 * preview + 取消 / 提交给医生 buttons row. Buttons follow CLAUDE.md
 * dialog rule: cancel LEFT (gray), primary RIGHT (green).
 *
 * `loading` disables both actions and swaps the primary button label for
 * a spinner so the patient can't double-submit while the network request
 * is in flight.
 */

import { Dialog, SpinLoading } from "antd-mobile";
import { APP, FONT, RADIUS } from "../theme";
import { FIELD_LABELS, PATIENT_INTAKE_FIELDS } from "../intake/fieldLabels";

export default function IntakeSubmitPopup({
  open,
  collected,
  onSubmit,
  onClose,
  loading,
}) {
  // Only show + count patient-relevant fields. The dialog grew to 60vh
  // so we no longer need the slice(0, 8) cap; show all filled patient
  // fields and let the list scroll if needed.
  const c = collected || {};
  const filledFields = PATIENT_INTAKE_FIELDS
    .map((k) => [k, c[k]])
    .filter(([, v]) => v && String(v).trim());
  const filledCount = filledFields.length;
  const totalCount = PATIENT_INTAKE_FIELDS.length;

  const content = (
    <div style={styles.wrap}>
      <div style={styles.subtitle}>
        已填写 {filledCount} / {totalCount} 项
      </div>

      {filledFields.length > 0 && (
        <div style={styles.fieldList}>
          {filledFields.map(([k, v]) => (
            <div key={k} style={styles.fieldRow}>
              <span style={styles.fieldLabel}>{FIELD_LABELS[k] || k}</span>
              <span style={styles.fieldValue}>
                {String(v).slice(0, 60)}
                {String(v).length > 60 ? "…" : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <Dialog
      visible={open}
      title="提交问诊"
      content={content}
      bodyStyle={{ minHeight: "60vh", display: "flex", flexDirection: "column" }}
      closeOnMaskClick={!loading}
      onClose={loading ? undefined : onClose}
      actions={[
        [
          {
            key: "cancel",
            text: "取消",
            disabled: loading,
            onClick: onClose,
          },
          {
            key: "submit",
            text: loading ? (
              <SpinLoading color="white" style={{ "--size": "18px" }} />
            ) : (
              "提交给医生"
            ),
            bold: true,
            danger: false,
            disabled: loading,
            style: {
              color: APP.white,
              "--background-color": APP.primary,
            },
            onClick: () => onSubmit?.(),
          },
        ],
      ]}
    />
  );
}

const styles = {
  // Tokens mirror doctor IntakePage's popupStyles (IntakePage.jsx:279-377)
  // so the patient submit dialog reads pixel-for-pixel the same as the
  // doctor's complete popup (with `flex: 1 / minHeight: 0` added so the
  // field list grows into the 60vh dialog rather than being capped at
  // 160px like the doctor's bottom-sheet popup).
  wrap: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    paddingBottom: 8,
    flex: 1,
    minHeight: 0,
  },
  // Patient-facing dialog: bumped from FONT.sm (13px) to FONT.base/.md
  // because the audience is 40+ and the doctor's popup uses the smaller
  // sizes for an info-dense view that doctors scan, not patients.
  subtitle: {
    fontSize: FONT.base,
    color: APP.text3,
    textAlign: "center",
  },
  fieldList: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    borderRadius: RADIUS.sm,
    background: APP.surfaceAlt,
    padding: "10px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  fieldRow: {
    display: "flex",
    gap: 10,
    alignItems: "flex-start",
  },
  fieldLabel: {
    fontSize: FONT.base,
    color: APP.text3,
    width: 72,
    flexShrink: 0,
    paddingTop: 1,
    fontWeight: 500,
  },
  fieldValue: {
    fontSize: FONT.md,
    color: APP.text1,
    flex: 1,
    lineHeight: "1.5",
  },
};
