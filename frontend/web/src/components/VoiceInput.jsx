import { useRef, useState, useEffect, useCallback } from "react";
import { Box, Typography } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import { TYPE, ICON, COLOR, RADIUS } from "../theme";

const BrowserSpeechRecognition = typeof window !== "undefined"
  ? (window.SpeechRecognition || window.webkitSpeechRecognition)
  : null;

// ── ASR mode detection ──────────────────────────────────────────────
// Connects briefly to /ws/transcribe to check if server-side ASR is available.
// Returns "browser" (use browser SpeechRecognition) or "server" (stream audio via WS).
let _asrModeCache = null;

function getWsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/transcribe`;
}

async function detectAsrMode() {
  if (_asrModeCache) return _asrModeCache;
  try {
    const ws = new WebSocket(getWsUrl());
    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => { ws.close(); resolve("browser"); }, 2000);
      ws.onmessage = (evt) => {
        clearTimeout(timeout);
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === "config" && msg.provider === "browser") {
            resolve("browser");
          } else {
            resolve("server");
          }
        } catch {
          resolve("server");
        }
        ws.close();
      };
      ws.onerror = () => { clearTimeout(timeout); resolve("browser"); };
      ws.onclose = () => { clearTimeout(timeout); };
    });
    _asrModeCache = result;
    return result;
  } catch {
    _asrModeCache = "browser";
    return "browser";
  }
}

export function isVoiceSupported() {
  // Supported if browser API exists OR if server ASR was detected
  return !!BrowserSpeechRecognition || _asrModeCache === "server";
}

export default function VoiceInput({ onResult, onCancel }) {
  const [recording, setRecording] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [asrMode, setAsrMode] = useState(BrowserSpeechRecognition ? "browser" : null);
  const [interimText, setInterimText] = useState("");

  // Refs for browser mode
  const recognitionRef = useRef(null);
  const timerRef = useRef(null);
  const startYRef = useRef(0);

  // Refs for server mode
  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const cancelledRef = useRef(false);

  // ── Detect ASR mode on mount ──
  useEffect(() => {
    detectAsrMode().then((mode) => setAsrMode(mode));
  }, []);

  // Keep cancelledRef in sync
  useEffect(() => {
    cancelledRef.current = cancelled;
  }, [cancelled]);

  // ── Timer helpers ──
  function startTimer() {
    timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
  }

  function stopTimer() {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }

  // ── Browser SpeechRecognition mode ──
  function startBrowserRecording(clientY) {
    if (!BrowserSpeechRecognition) return;
    startYRef.current = clientY;
    setCancelled(false);
    cancelledRef.current = false;
    setSeconds(0);
    setRecording(true);
    setInterimText("");

    const recognition = new BrowserSpeechRecognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.continuous = false;

    recognition.onresult = (event) => {
      const text = event.results[0]?.[0]?.transcript;
      if (text && !cancelledRef.current) onResult(text);
    };
    recognition.onerror = () => { stopTimer(); setRecording(false); onCancel(); };
    recognition.onend = () => { stopTimer(); setRecording(false); };

    recognition.start();
    recognitionRef.current = recognition;
    startTimer();
  }

  function stopBrowserRecording() {
    stopTimer();
    if (cancelledRef.current) {
      recognitionRef.current?.abort();
      setRecording(false);
      setCancelled(false);
      onCancel();
    } else {
      recognitionRef.current?.stop();
    }
  }

  // ── Server WebSocket ASR mode ──
  const startServerRecording = useCallback(async (clientY) => {
    startYRef.current = clientY;
    setCancelled(false);
    cancelledRef.current = false;
    setSeconds(0);
    setRecording(true);
    setInterimText("");

    try {
      // Get mic access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Open WebSocket
      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === "config") return; // skip config message
          if (msg.type === "interim" && msg.text) {
            setInterimText(msg.text);
          }
          if (msg.type === "final" && msg.text) {
            if (!cancelledRef.current) {
              onResult(msg.text);
            }
            cleanup();
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        cleanup();
        onCancel();
      };

      ws.onopen = () => {
        // Start MediaRecorder once WS is ready
        const recorder = new MediaRecorder(stream, {
          mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
            ? "audio/webm;codecs=opus"
            : "audio/webm",
        });
        mediaRecorderRef.current = recorder;

        recorder.ondataavailable = (e) => {
          if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
            ws.send(e.data);
          }
        };

        recorder.start(250); // send chunks every 250ms
      };

      startTimer();
    } catch {
      // Mic access denied or other error — fall back
      setRecording(false);
      onCancel();
    }
  }, [onResult, onCancel]);

  function cleanup() {
    stopTimer();
    setRecording(false);
    setInterimText("");

    // Stop MediaRecorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    mediaRecorderRef.current = null;

    // Stop mic stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }
  }

  function stopServerRecording() {
    if (cancelledRef.current) {
      cleanup();
      setCancelled(false);
      onCancel();
      return;
    }

    // Stop the recorder so remaining data flushes
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }

    // Tell server we're done
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send("stop");
    }

    // Server will respond with {type: "final"} which triggers cleanup via onmessage.
    // Safety timeout in case server doesn't respond:
    stopTimer();
    setTimeout(() => {
      if (wsRef.current) {
        cleanup();
      }
    }, 5000);
  }

  // ── Unified start/stop ──
  function startRecording(clientY) {
    if (asrMode === "server") {
      startServerRecording(clientY);
    } else if (BrowserSpeechRecognition) {
      startBrowserRecording(clientY);
    }
  }

  function stopRecording() {
    if (asrMode === "server") {
      stopServerRecording();
    } else {
      stopBrowserRecording();
    }
  }

  function handleMove(clientY) {
    if (!recording) return;
    const shouldCancel = startYRef.current - clientY > 80;
    setCancelled(shouldCancel);
    cancelledRef.current = shouldCancel;
  }

  const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  // Not ready yet (detecting mode)
  if (!asrMode && !BrowserSpeechRecognition) return null;

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
        height: 40, borderRadius: RADIUS.sm, cursor: "pointer", userSelect: "none",
        bgcolor: recording ? (cancelled ? COLOR.danger : COLOR.primary) : COLOR.white,
        border: recording ? "none" : "1px solid #e0e0e0",
        transition: "background-color 0.15s",
      }}
    >
      {recording && !cancelled && (
        <Box sx={{ display: "flex", alignItems: "center", gap: "3px", mr: 1 }}>
          {[0, 1, 2].map((i) => (
            <Box key={i} sx={{
              width: 3, height: 14, borderRadius: 1.5, bgcolor: COLOR.white,
              animation: "waveBar 0.8s ease-in-out infinite",
              animationDelay: `${i * 0.15}s`,
              "@keyframes waveBar": { "0%, 100%": { transform: "scaleY(0.4)" }, "50%": { transform: "scaleY(1)" } },
            }} />
          ))}
        </Box>
      )}
      <MicIcon sx={{ fontSize: ICON.md, mr: 0.5, color: recording ? COLOR.white : COLOR.text4 }} />
      <Typography variant="body2" sx={{ fontSize: TYPE.heading.fontSize, color: recording ? COLOR.white : COLOR.text4, fontWeight: recording ? 600 : 400 }}>
        {recording
          ? (cancelled
            ? "松开取消"
            : interimText
              ? interimText
              : `松开发送 ${fmt(seconds)}`)
          : "按住说话"}
      </Typography>
    </Box>
  );
}
