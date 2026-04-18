/**
 * ChatComposer — chat input bar shared by all v2 chat pages.
 *
 * Features:
 * - antd-mobile TextArea with autoSize (1–4 rows)
 * - Voice mic button (miniapp only, via useVoiceInput)
 * - Suggestion chips
 * - Send button (Enter to send, Shift+Enter for newline)
 * - SafeArea bottom padding for home bar
 */
import { useState } from "react";
import { TextArea, Button, SafeArea } from "antd-mobile";
import { SendOutline } from "antd-mobile-icons";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { isInMiniapp } from "../utils/miniappBridge";
import { APP } from "./theme";

export default function ChatComposer({
  value = "",
  onChange,
  onSend,
  disabled = false,
  placeholder = "输入消息…",
  doctorId,
  suggestions = [],
  selectedSuggestions = [],
  onToggleSuggestion,
}) {
  const showMic = isInMiniapp();

  const { micButton, voiceActive } = useVoiceInput({
    doctorId,
    value,
    setValue: (v) => onChange?.(v),
    separator: " ",
    compact: true,
  });

  const isDisabled = disabled || voiceActive;

  const handleSend = () => {
    const trimmed = value?.trim();
    if (!trimmed || isDisabled) return;
    onSend?.(trimmed);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={styles.wrapper}>
      {/* Suggestion chips */}
      {suggestions.length > 0 && (
        <div style={styles.chips}>
          {suggestions.map((s, i) => {
            const active = selectedSuggestions.includes(s);
            return (
              <span
                key={i}
                style={{
                  ...styles.chip,
                  background: active ? APP.wechatGreen : APP.surfaceAlt,
                  color: active ? "#1a1a1a" : APP.text3,
                  border: `1px solid ${active ? APP.wechatGreen : APP.border}`,
                }}
                onClick={() => onToggleSuggestion?.(s)}
              >
                {s}
              </span>
            );
          })}
        </div>
      )}

      {/* Input row */}
      <div style={styles.inputRow}>
        {showMic && <div style={styles.micWrap}>{micButton}</div>}

        <div style={styles.textAreaWrap}>
          <TextArea
            value={value}
            onChange={(v) => onChange?.(v)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isDisabled}
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={styles.textarea}
          />
        </div>

        <Button
          onClick={handleSend}
          disabled={isDisabled || !value?.trim()}
          style={{
            ...styles.sendBtn,
            background: value?.trim() && !isDisabled ? "#07C160" : APP.border,
            color: value?.trim() && !isDisabled ? "#fff" : APP.text4,
          }}
        >
          <SendOutline fontSize={18} />
        </Button>
      </div>

      <SafeArea position="bottom" />
    </div>
  );
}

const styles = {
  wrapper: {
    background: APP.surface,
    borderTop: `1px solid ${APP.border}`,
    paddingTop: 8,
    paddingLeft: 12,
    paddingRight: 12,
  },
  chips: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    marginBottom: 8,
  },
  chip: {
    display: "inline-block",
    padding: "4px 10px",
    borderRadius: 14,
    fontSize: 13,
    cursor: "pointer",
    userSelect: "none",
    transition: "background 0.15s",
  },
  inputRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
    paddingBottom: 8,
  },
  micWrap: {
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    paddingBottom: 4,
  },
  textAreaWrap: {
    flex: 1,
    background: APP.surfaceAlt,
    borderRadius: 18,
    padding: "6px 12px",
    minHeight: 36,
    display: "flex",
    alignItems: "center",
  },
  textarea: {
    "--font-size": "15px",
    "--color": APP.text1,
    "--placeholder-color": APP.text4,
    background: "transparent",
    border: "none",
    outline: "none",
    width: "100%",
    lineHeight: "1.5",
  },
  sendBtn: {
    flexShrink: 0,
    width: 36,
    height: 36,
    borderRadius: "50%",
    border: "none",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
    transition: "background 0.15s",
    minWidth: 0,
  },
};
