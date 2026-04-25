import { Button } from "antd-mobile";
import { APP, FONT, RADIUS } from "../theme";

/**
 * ChatDedupPrompt — inline prompt shown when the AI dispatcher detects that a
 * patient's new message closely matches an existing record, and asks whether
 * to merge, open a new record, or discard.
 *
 * Props:
 *   targetReviewed  — bool. true → the matched record has already been seen by the doctor.
 *   onMerge         — called when patient taps "并入上一次".
 *   onNew           — called when patient taps "新开一条".
 *   onNeither       — called when patient taps "都不要".
 */
export default function ChatDedupPrompt({ targetReviewed, onMerge, onNew, onNeither }) {
  const prompt = targetReviewed
    ? "您之前提到过类似的情况，医生已经看过那条记录。要把刚才的内容并入还是新开一条?"
    : "您之前提到过类似的情况。要把刚才的内容并入上一次记录，还是新开一条?";

  return (
    <div style={styles.wrap}>
      <p style={styles.text}>{prompt}</p>
      <div style={styles.row}>
        <Button color="primary" size="middle" onClick={onMerge}>并入上一次</Button>
        <Button size="middle" onClick={onNew}>新开一条</Button>
        <Button size="middle" onClick={onNeither}>都不要</Button>
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
  row: { display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" },
};
