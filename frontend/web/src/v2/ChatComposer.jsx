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
import { TextArea, SafeArea } from "antd-mobile";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { isInMiniapp } from "../utils/miniappBridge";
import { APP, FONT, ICON, RADIUS } from "./theme";

// Toggle a chip's text in/out of the textarea. Single source of truth:
// "selected" means the chip's text currently appears as a standalone token
// in the textarea — not as a substring of another chip. Without the
// boundary check, "没有" being in the value would make the "有" chip
// look selected too (有 ⊂ 没有).
const SEP = "，";
function isChipSelected(value, chipText) {
  if (!value || !chipText) return false;
  if (value === chipText) return true;
  if (value.startsWith(chipText + SEP)) return true;
  if (value.endsWith(SEP + chipText)) return true;
  if (value.includes(SEP + chipText + SEP)) return true;
  return false;
}
function toggleChipInValue(value, chipText) {
  if (!value) return chipText;
  if (!isChipSelected(value, chipText)) return `${value}${SEP}${chipText}`;
  // Remove — peel the surrounding separator if present
  let next = value.replace(`${chipText}${SEP}`, "");
  if (next === value) next = value.replace(`${SEP}${chipText}`, "");
  if (next === value && value === chipText) next = "";
  return next.replace(new RegExp(`^${SEP}+|${SEP}+$`, "g"), "");
}

export default function ChatComposer({
  value = "",
  onChange,
  onSend,
  disabled = false,
  placeholder = "输入消息…",
  doctorId,
  suggestions = [],
  // True when composer sits directly on the viewport bottom (e.g. IntakePage
  // full-screen). False when a TabBar below already handles the home-indicator
  // inset — doubling up leaves dead space above the TabBar.
  safeBottom = true,
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

  const hasContent = !!value?.trim();
  const handleSend = () => {
    if (!hasContent || isDisabled) return;
    onSend?.(value.trim());
  };

  // WeChat mobile convention: Enter inserts a newline. Sending requires
  // tapping the send button. We intentionally do not intercept Enter here.

  return (
    <div style={styles.wrapper}>
      {/* Suggestion chips — single row, overflow clips. Selection is derived
          from the textarea: if the chip's text appears in `value`, it shows
          selected; tapping toggles insertion/removal. */}
      {suggestions.length > 0 && (
        <div style={styles.chips}>
          {suggestions.map((s, i) => {
            const selected = isChipSelected(value, s);
            return (
              <span
                key={i}
                style={selected ? styles.chipSelected : styles.chip}
                onClick={() => onChange?.(toggleChipInValue(value, s))}
              >
                {selected ? "✓ " : ""}{s}
              </span>
            );
          })}
        </div>
      )}

      {/* Input row — WeChat-style: gray bar, white input, 发送 button appears when typing */}
      <div style={styles.inputRow}>
        {showMic && <div style={styles.micWrap}>{micButton}</div>}

        <div style={styles.textAreaWrap}>
          <TextArea
            value={value}
            onChange={(v) => onChange?.(v)}
            placeholder={placeholder}
            disabled={isDisabled}
            rows={1}
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={styles.textarea}
          />
        </div>

        {(() => {
          const active = hasContent && !isDisabled;
          return (
            <div
              role="button"
              aria-label="发送"
              onClick={active ? handleSend : undefined}
              style={{
                ...styles.sendBtn,
                background: active ? APP.primary : APP.border,
                color: active ? APP.white : APP.text4,
                cursor: active ? "pointer" : "not-allowed",
              }}
            >
              <SendRoundedIcon sx={{ fontSize: ICON.sm }} />
            </div>
          );
        })()}
      </div>

      {safeBottom && <SafeArea position="bottom" />}
    </div>
  );
}

// WeChat input-bar palette: #EDEDED container, white input, 4px radius.
// Using APP.surfaceAlt (#f7f7f7) for the bar — close enough to WeChat's
// #EDEDED that it fits our palette without introducing a new token.
const styles = {
  wrapper: {
    background: APP.surfaceAlt,
    borderTop: `0.5px solid ${APP.border}`,
    paddingTop: 8,
    paddingLeft: 8,
    paddingRight: 8,
  },
  chips: {
    display: "flex",
    flexWrap: "nowrap",
    gap: 6,
    marginBottom: 8,
    overflow: "hidden",
  },
  chip: {
    display: "inline-block",
    padding: "4px 10px",
    borderRadius: RADIUS.lg,
    fontSize: FONT.sm,
    cursor: "pointer",
    userSelect: "none",
    background: APP.surface,
    color: APP.text3,
    border: `1px solid ${APP.border}`,
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
  chipSelected: {
    display: "inline-block",
    padding: "4px 10px",
    borderRadius: RADIUS.lg,
    fontSize: FONT.sm,
    cursor: "pointer",
    userSelect: "none",
    background: APP.primaryLight,
    color: APP.primary,
    border: `1px solid ${APP.primary}`,
    fontWeight: 500,
    whiteSpace: "nowrap",
    flexShrink: 0,
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
    background: APP.surface,
    borderRadius: RADIUS.sm,
    padding: "4px 10px",
    display: "flex",
    alignItems: "center",
    border: `0.5px solid ${APP.border}`,
  },
  textarea: {
    "--font-size": FONT.md,
    "--color": APP.text1,
    "--placeholder-color": APP.text4,
    "--min-height": "24px",
    background: "transparent",
    border: "none",
    outline: "none",
    width: "100%",
    lineHeight: "1.4",
  },
  sendBtn: {
    flexShrink: 0,
    width: 44,
    height: 36,
    borderRadius: RADIUS.sm,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    userSelect: "none",
    transition: "background 120ms ease",
  },
};
