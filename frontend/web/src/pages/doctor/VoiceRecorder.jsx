/**
 * Voice recording hook and UI components for chat.
 */
import { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import { transcribeAudio } from "../../api";

export function RecordingBanner({ recordingSeconds }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 0.5, bgcolor: "#fff0f0" }}>
      <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "error.main", animation: "recBlink 1s ease-in-out infinite", "@keyframes recBlink": { "0%,100%": { opacity: 1 }, "50%": { opacity: 0.3 } } }} />
      <Typography variant="caption" color="error" sx={{ fontWeight: 700 }}>
        录音中 {Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2, "0")}
      </Typography>
      <Typography variant="caption" color="text.secondary">· 点击停止</Typography>
    </Box>
  );
}

export function useAudioRecorder(onTranscribed, onError) {
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [processing, setProcessing] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerRef = useRef(null);

  useEffect(() => () => clearInterval(timerRef.current), []);

  async function start() {
    onError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        setProcessing(true);
        try {
          const { text } = await transcribeAudio(blob);
          if (text) onTranscribed(text);
        } catch {
          onError("语音识别失败，请重试");
        } finally {
          setProcessing(false);
        }
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
      setRecordingSeconds(0);
      timerRef.current = setInterval(() => setRecordingSeconds((s) => s + 1), 1000);
    } catch {
      onError("无法访问麦克风，请检查权限");
    }
  }

  function stop() {
    clearInterval(timerRef.current);
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  return { recording, recordingSeconds, processing, start, stop };
}
