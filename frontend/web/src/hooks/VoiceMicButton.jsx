/**
 * VoiceMicButton — inline mic button for voice recording via miniapp bridge.
 *
 * Only renders when inside WeChat miniapp. Streams interim text and delivers
 * final transcript via callbacks; the parent owns the input field and merges
 * the voice content in.
 *
 * Props:
 *   doctorId: string
 *   onTranscript: (text: string) => void — final recognition result
 *   onInterim: (text: string) => void — streaming interim updates (may fire many times)
 *   onVoiceStart: () => void — user clicked mic to begin; parent should snapshot input
 *   onVoiceCancel: () => void — recording aborted; parent should restore snapshot
 *   compact: boolean — compact icon variant for input-bar use
 */
import { useEffect, useRef } from "react";
import { Box, CircularProgress } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import MicNoneIcon from "@mui/icons-material/MicNone";
import StopIcon from "@mui/icons-material/Stop";
import { useVoiceRecording } from "../hooks/useVoiceRecording";
import { isInMiniapp } from "../utils/miniappBridge";
import { COLOR, RADIUS, TYPE } from "../theme";

export default function VoiceMicButton({ doctorId, onTranscript, onInterim, onVoiceStart, onVoiceCancel, compact = false }) {
  const { state, elapsed, transcript, interim, error, toggle, clear } = useVoiceRecording(doctorId);
  const prevStateRef = useRef("idle");

  // Deliver transcript to parent when it arrives
  useEffect(() => {
    if (transcript) {
      onTranscript?.(transcript);
      clear();
    }
  }, [transcript, onTranscript, clear]);

  // Forward interim updates so the parent can stream them into the input box
  useEffect(() => {
    if (interim) onInterim?.(interim);
  }, [interim, onInterim]);

  // Detect lifecycle transitions: idle→preparing = start, active→idle without
  // transcript = cancel. Fire the appropriate callback so the parent can
  // snapshot/restore its input state.
  useEffect(() => {
    const prev = prevStateRef.current;
    prevStateRef.current = state;
    if (prev === "idle" && state === "preparing") {
      onVoiceStart?.();
    } else if ((prev === "preparing" || prev === "recording") && state === "idle" && !transcript) {
      onVoiceCancel?.();
    }
  }, [state, transcript, onVoiceStart, onVoiceCancel]);

  if (!isInMiniapp()) return null;

  const isPreparing = state === "preparing";
  const isRecording = state === "recording";
  const isTranscribing = state === "transcribing";
  const isError = state === "error";

  if (compact) {
    // Just the icon — streaming lands directly in the input box so we don't
    // need an overlay. Each state has a distinct icon so the user can tell
    // preparing (warming up, don't speak) apart from transcribing (done
    // speaking, wait for result).
    let iconEl;
    if (isPreparing) {
      // Hollow mic + slow amber pulse = "mic not yet live, please wait"
      iconEl = (
        <MicNoneIcon sx={{
          fontSize: 22, color: COLOR.warn || "#F59E0B",
          animation: "voicePrepPulse 1.2s ease-in-out infinite",
          "@keyframes voicePrepPulse": {
            "0%, 100%": { opacity: 0.4, transform: "scale(1)" },
            "50%": { opacity: 1, transform: "scale(1.08)" },
          },
        }} />
      );
    } else if (isRecording) {
      iconEl = (
        <StopIcon sx={{
          fontSize: 22, color: COLOR.danger,
          animation: "voicePulse 1s ease-in-out infinite",
          "@keyframes voicePulse": { "0%, 100%": { opacity: 1 }, "50%": { opacity: 0.5 } },
        }} />
      );
    } else if (isTranscribing) {
      iconEl = <CircularProgress size={20} sx={{ color: COLOR.primary }} />;
    } else {
      iconEl = <MicIcon sx={{ fontSize: 22 }} />;
    }
    return (
      <Box
        onClick={toggle}
        sx={{
          position: "relative", p: 1, cursor: "pointer", flexShrink: 0,
          display: "flex", alignItems: "center", gap: 0.5,
          color: isRecording ? COLOR.danger : COLOR.text4,
        }}
      >
        {iconEl}
        {isPreparing && (
          <Box component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.warn || "#F59E0B" }}>
            准备中
          </Box>
        )}
        {isRecording && (
          <Box component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger, fontVariantNumeric: "tabular-nums" }}>
            {elapsed}s
          </Box>
        )}
      </Box>
    );
  }

  // Full-size mic button for add-knowledge page
  return (
    <Box
      onClick={toggle}
      sx={{
        display: "flex", alignItems: "center", gap: 1,
        px: 2, py: 1.5, mx: 2, mt: 1,
        border: `1px solid ${isRecording || isTranscribing ? COLOR.danger : COLOR.border}`,
        borderRadius: RADIUS.md, cursor: "pointer",
        bgcolor: isRecording ? "rgba(255,77,79,0.06)" : COLOR.white,
        "&:active": { opacity: 0.7 },
        transition: "all 0.15s ease",
      }}
    >
      {isTranscribing || isPreparing ? (
        <CircularProgress size={20} sx={{ color: COLOR.primary }} />
      ) : isRecording ? (
        <StopIcon sx={{ color: COLOR.danger, animation: "voicePulse 1s ease-in-out infinite",
          "@keyframes voicePulse": { "0%, 100%": { opacity: 1 }, "50%": { opacity: 0.5 } },
        }} />
      ) : (
        <MicIcon sx={{ color: isError ? COLOR.danger : COLOR.primary }} />
      )}
      <Box sx={{ flex: 1 }}>
        <Box sx={{ fontSize: TYPE.body.fontSize, color: isRecording ? COLOR.danger : COLOR.text1 }}>
          {isPreparing ? "准备中…请稍候" :
           isRecording ? `录音中 ${elapsed}s — 点击停止` :
           isTranscribing ? "识别中..." :
           isError ? error || "识别失败，点击重试" :
           "语音输入"}
        </Box>
      </Box>
    </Box>
  );
}
