/**
 * FeedbackSheet — bottom sheet for flagging an AI suggestion.
 *
 * Phase F1 of docs/specs/2026-04-21-ai-feedback-capture-plan.md. Visual
 * reference: docs/specs/2026-04-21-mockups/ai-feedback-capture.html (phone 2).
 *
 * Props
 *   - visible: boolean — controls Popup open state
 *   - suggestion: { content, detail, ... } | null — shown in amber preview
 *   - onCancel(): void
 *   - onSubmit(reasonTag, reasonText): Promise — parent owns the network call
 *
 * The component is stateless w.r.t. which suggestion is being flagged — the
 * parent keeps that in its own state and passes it in. The internal state is
 * the radio selection + textarea content only, reset every time the sheet
 * re-opens (via the `visible → true` effect).
 */
import { useEffect, useState } from "react";
import { Popup, TextArea, Toast } from "antd-mobile";
import { APP, FONT, RADIUS } from "../theme";

const REASONS = [
  { tag: "wrong_diagnosis", label: "诊断错误" },
  { tag: "insufficient_evidence", label: "证据不足" },
  { tag: "against_experience", label: "不符合我的临床经验" },
  { tag: "other", label: "其他" },
];

export default function FeedbackSheet({ visible, suggestion, onCancel, onSubmit }) {
  const [reasonTag, setReasonTag] = useState(null);
  const [reasonText, setReasonText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Reset form every time the sheet opens — doctor flags a different
  // suggestion, we should not carry prior radio/text state.
  useEffect(() => {
    if (visible) {
      setReasonTag(null);
      setReasonText("");
      setSubmitting(false);
    }
  }, [visible]);

  const handleSubmit = async () => {
    if (!reasonTag || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(reasonTag, reasonText.trim());
      Toast.show({ content: "已反馈 · 感谢", duration: 1500 });
    } catch (err) {
      Toast.show({ content: "提交失败，请重试", duration: 1800 });
      setSubmitting(false);
      return;
    }
    // Parent closes the sheet on success; keep submitting=true until the
    // visible prop flips, which triggers the reset effect above.
  };

  const title = suggestion?.edited_text || suggestion?.content || "";
  const detail = suggestion?.detail || "";

  return (
    <Popup
      visible={visible}
      onMaskClick={onCancel}
      onClose={onCancel}
      position="bottom"
      bodyStyle={{
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        padding: "20px 18px 14px",
        maxHeight: "85%",
        overflow: "auto",
      }}
      destroyOnClose
    >
      <div
        style={{
          width: 36,
          height: 4,
          borderRadius: 2,
          background: APP.border,
          margin: "0 auto 14px",
        }}
      />
      <div
        style={{
          fontSize: FONT.md,
          fontWeight: 600,
          color: APP.text1,
          marginBottom: 4,
        }}
      >
        反馈这条 AI 建议
      </div>
      <div
        style={{
          fontSize: FONT.sm,
          color: APP.text3,
          marginBottom: 16,
          lineHeight: 1.5,
        }}
      >
        你的反馈会帮助改进 AI 的推理质量。
      </div>

      {(title || detail) && (
        <div
          style={{
            padding: "10px 12px",
            background: APP.surfaceAlt,
            borderRadius: RADIUS.md,
            fontSize: FONT.sm,
            color: APP.text2,
            marginBottom: 18,
            borderLeft: `3px solid ${APP.warning}`,
            lineHeight: 1.5,
          }}
        >
          {title && <div style={{ color: APP.text1, fontWeight: 600 }}>{title}</div>}
          {detail && (
            <div style={{ color: APP.text4, fontSize: FONT.xs, marginTop: 2 }}>
              {detail}
            </div>
          )}
        </div>
      )}

      {REASONS.map((r) => {
        const selected = reasonTag === r.tag;
        return (
          <div
            key={r.tag}
            onClick={() => setReasonTag(r.tag)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "10px 12px",
              border: `0.5px solid ${selected ? APP.primary : APP.border}`,
              borderRadius: RADIUS.md,
              marginBottom: 8,
              fontSize: FONT.sm,
              cursor: "pointer",
              background: selected ? APP.primaryLight : APP.surface,
              color: APP.text1,
            }}
          >
            <span
              style={{
                width: 16,
                height: 16,
                borderRadius: "50%",
                border: `1.5px solid ${selected ? APP.primary : APP.border}`,
                flexShrink: 0,
                position: "relative",
                background: APP.surface,
              }}
            >
              {selected && (
                <span
                  style={{
                    position: "absolute",
                    inset: 3,
                    background: APP.primary,
                    borderRadius: "50%",
                  }}
                />
              )}
            </span>
            <span>{r.label}</span>
          </div>
        );
      })}

      <TextArea
        placeholder="补充说明（可选）"
        value={reasonText}
        onChange={setReasonText}
        autoSize={{ minRows: 2, maxRows: 5 }}
        maxLength={1000}
        style={{
          marginTop: 6,
          marginBottom: 8,
          fontSize: FONT.sm,
          "--padding-left": "12px",
          "--padding-right": "12px",
        }}
      />
      <div
        style={{
          fontSize: FONT.xs,
          color: APP.text4,
          lineHeight: 1.5,
          marginBottom: 14,
        }}
      >
        请不要输入患者姓名或身份证号 — 只描述 AI 建议本身的问题。
      </div>

      <div style={{ display: "flex", gap: 10 }}>
        <button
          onClick={onCancel}
          disabled={submitting}
          style={{
            flex: 1,
            padding: 11,
            borderRadius: RADIUS.md,
            fontSize: FONT.base,
            fontWeight: 500,
            border: "none",
            cursor: submitting ? "not-allowed" : "pointer",
            background: APP.surfaceAlt,
            color: APP.text2,
          }}
        >
          取消
        </button>
        <button
          onClick={handleSubmit}
          disabled={!reasonTag || submitting}
          style={{
            flex: 1,
            padding: 11,
            borderRadius: RADIUS.md,
            fontSize: FONT.base,
            fontWeight: 500,
            border: "none",
            cursor: !reasonTag || submitting ? "not-allowed" : "pointer",
            background: APP.primary,
            color: APP.white,
            opacity: !reasonTag || submitting ? 0.55 : 1,
          }}
        >
          {submitting ? "提交中…" : "提交"}
        </button>
      </div>
    </Popup>
  );
}
