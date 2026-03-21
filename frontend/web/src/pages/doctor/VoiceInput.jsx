import { useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import { TYPE, ICON } from "../../theme";

const SpeechRecognition = typeof window !== "undefined"
  ? (window.SpeechRecognition || window.webkitSpeechRecognition)
  : null;

export function isVoiceSupported() {
  return !!SpeechRecognition;
}

export default function VoiceInput({ onResult, onCancel }) {
  const [recording, setRecording] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recognitionRef = useRef(null);
  const timerRef = useRef(null);
  const startYRef = useRef(0);

  function startRecording(clientY) {
    if (!SpeechRecognition) return;
    startYRef.current = clientY;
    setCancelled(false);
    setSeconds(0);
    setRecording(true);

    const recognition = new SpeechRecognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.continuous = false;

    recognition.onresult = (event) => {
      const text = event.results[0]?.[0]?.transcript;
      if (text && !cancelled) onResult(text);
    };
    recognition.onerror = () => { stopTimer(); setRecording(false); onCancel(); };
    recognition.onend = () => { stopTimer(); setRecording(false); };

    recognition.start();
    recognitionRef.current = recognition;
    timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
  }

  function stopTimer() {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }

  function stopRecording() {
    stopTimer();
    if (cancelled) {
      recognitionRef.current?.abort();
      setRecording(false);
      setCancelled(false);
      onCancel();
    } else {
      recognitionRef.current?.stop();
    }
  }

  function handleMove(clientY) {
    if (!recording) return;
    setCancelled(startYRef.current - clientY > 80);
  }

  const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  return (
    <Box
      onTouchStart={(e) => startRecording(e.touches[0].clientY)}
      onTouchEnd={() => stopRecording()}
      onTouchMove={(e) => handleMove(e.touches[0].clientY)}
      onMouseDown={(e) => startRecording(e.clientY)}
      onMouseUp={() => stopRecording()}
      onMouseMove={(e) => { if (recording) handleMove(e.clientY); }}
      sx={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        height: 40, borderRadius: "4px", cursor: "pointer", userSelect: "none",
        bgcolor: recording ? (cancelled ? "#FA5151" : "#07C160") : "#fff",
        border: recording ? "none" : "1px solid #e0e0e0",
        transition: "background-color 0.15s",
      }}
    >
      {recording && !cancelled && (
        <Box sx={{ display: "flex", alignItems: "center", gap: "3px", mr: 1 }}>
          {[0, 1, 2].map((i) => (
            <Box key={i} sx={{
              width: 3, height: 14, borderRadius: 1.5, bgcolor: "#fff",
              animation: "waveBar 0.8s ease-in-out infinite",
              animationDelay: `${i * 0.15}s`,
              "@keyframes waveBar": { "0%, 100%": { transform: "scaleY(0.4)" }, "50%": { transform: "scaleY(1)" } },
            }} />
          ))}
        </Box>
      )}
      <MicIcon sx={{ fontSize: ICON.md, mr: 0.5, color: recording ? "#fff" : "#999" }} />
      <Typography variant="body2" sx={{ fontSize: TYPE.heading.fontSize, color: recording ? "#fff" : "#999", fontWeight: recording ? 600 : 400 }}>
        {recording ? (cancelled ? "松开取消" : `松开发送 ${fmt(seconds)}`) : "按住说话"}
      </Typography>
    </Box>
  );
}
