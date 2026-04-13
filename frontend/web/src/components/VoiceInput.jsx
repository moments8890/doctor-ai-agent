/**
 * VoiceInput — keyboard-dictation mode only.
 *
 * All platforms use the same behavior: a mic icon in the input bar that
 * focuses the text input and shows a hint to use the OS keyboard's
 * built-in dictation. No custom ASR, WebSocket, or native recording.
 */
import { Box } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import { TYPE, COLOR, RADIUS } from "../theme";

/** Always false — custom voice recording is disabled; use keyboard dictation. */
export function isVoiceSupported() {
  return false;
}

/** Mic button that focuses the text input and shows a floating dictation hint. */
export function MiniVoiceMicHint({ inputRef, onHint, showHint }) {
  return (
    <Box
      onClick={() => { inputRef?.current?.focus(); onHint?.(); }}
      sx={{ position: "relative", color: COLOR.text4, p: 1, cursor: "pointer", flexShrink: 0, display: "flex", alignItems: "center" }}
    >
      <MicIcon sx={{ fontSize: 22 }} />
      {showHint && (
        <Box sx={{
          position: "absolute", bottom: "calc(100% + 6px)", left: 0,
          display: "flex", alignItems: "center", gap: 1,
          whiteSpace: "nowrap", px: 1.5, py: 0.5,
          bgcolor: COLOR.primaryLight, borderRadius: RADIUS.sm,
          fontSize: TYPE.caption.fontSize, color: COLOR.primary,
          pointerEvents: "none",
        }}>
          {/* Fake keyboard key with mic icon */}
          <Box sx={{
            width: 28, height: 28, borderRadius: "6px",
            bgcolor: COLOR.white, border: `1.5px solid ${COLOR.primary}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: `0 0 6px ${COLOR.primaryLight}`,
            animation: "micPulse 1.5s ease-in-out infinite",
            "@keyframes micPulse": {
              "0%, 100%": { boxShadow: `0 0 4px ${COLOR.primaryLight}` },
              "50%": { boxShadow: `0 0 10px ${COLOR.primary}40` },
            },
          }}>
            <MicIcon sx={{ fontSize: 16, color: COLOR.primary }} />
          </Box>
          点击键盘上此按钮语音输入 ↓
        </Box>
      )}
    </Box>
  );
}

/** @deprecated No-op stub kept for backwards compatibility with ComponentShowcasePage. */
export default function VoiceInput() {
  return null;
}
