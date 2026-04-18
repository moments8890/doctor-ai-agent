/**
 * VoiceInput — keyboard-dictation mode only (fallback when not in miniapp).
 *
 * When inside miniapp, VoiceMicButton handles voice — this component shows
 * the keyboard mic hint only when NOT in miniapp.
 */
import { Box } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import { TYPE, COLOR, RADIUS } from "../theme";
import { isInMiniapp } from "../utils/miniappBridge";

/** True when inline voice recording is available (miniapp bridge). */
export function isVoiceSupported() {
  return isInMiniapp();
}

/** Mic button that focuses the text input and shows a floating dictation hint.
 *  Only shows when NOT in miniapp (miniapp uses VoiceMicButton instead). */
export function MiniVoiceMicHint({ inputRef, onHint, showHint }) {
  if (isInMiniapp()) return null;

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

/** @deprecated No-op stub kept for backwards compatibility. */
export default function VoiceInput() {
  return null;
}
