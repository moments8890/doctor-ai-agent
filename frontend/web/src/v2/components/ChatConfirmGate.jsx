import { Button } from "antd-mobile";
import { APP, FONT, RADIUS } from "../theme";

/**
 * ChatConfirmGate — inline prompt shown when the AI dispatcher decides the
 * patient's intake has accumulated enough signal (chief_complaint +
 * present_illness + duration|severity) and needs the patient's consent to
 * assemble a clinical record for the doctor.
 *
 * Props:
 *   continuity  — bool. true → patient is continuing an existing encounter.
 *   onConfirm   — called when patient taps "整理给医生".
 *   onContinue  — called when patient taps "继续聊".
 */
export default function ChatConfirmGate({ continuity, onConfirm, onContinue }) {
  const prompt = continuity
    ? "继续您之前的就诊记录，整理给医生?"
    : "您刚才提到的情况，要为您整理成一条就诊记录给医生看吗?";

  return (
    <div style={styles.wrap}>
      <p style={styles.text}>{prompt}</p>
      <div style={styles.row}>
        <Button color="primary" size="middle" onClick={onConfirm}>整理给医生</Button>
        <Button size="middle" onClick={onContinue}>继续聊</Button>
      </div>
    </div>
  );
}

const styles = {
  wrap: {
    background: APP.surface,
    borderRadius: RADIUS.md,
    padding: "12px 14px",
    margin: "4px 12px",
    boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
  },
  text: { fontSize: FONT.md, color: APP.text1, margin: 0, marginBottom: 12 },
  row: { display: "flex", gap: 12, justifyContent: "flex-end" },
};
