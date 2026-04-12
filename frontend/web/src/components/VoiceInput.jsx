import { useRef, useState, useEffect, useCallback } from "react";
import { Box, Typography, CircularProgress } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import { TYPE, ICON, COLOR, RADIUS } from "../theme";

const BrowserSpeechRecognition = typeof window !== "undefined"
  ? (window.SpeechRecognition || window.webkitSpeechRecognition)
  : null;

const IS_MINIPROGRAM = typeof window !== "undefined" && window.__wxjs_environment === "miniprogram";

// ── ASR mode detection ──────────────────────────────────────────────
let _asrModeCache = null;

function getWsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/transcribe`;
}

async function detectAsrMode() {
  if (_asrModeCache) return _asrModeCache;

  console.log("[Voice] detectAsrMode start", { IS_MINIPROGRAM, hasSpeechRecognition: !!BrowserSpeechRecognition });

  // In miniprogram web-view, getUserMedia is usually blocked.
  // Fall back to native recording page (wx.getRecorderManager → upload).
  if (IS_MINIPROGRAM) {
    const hasMediaDevices = !!(navigator.mediaDevices?.getUserMedia);
    console.log("[Voice] miniprogram: hasMediaDevices =", hasMediaDevices);
    if (!hasMediaDevices) {
      console.log("[Voice] → miniprogram mode (no mediaDevices)");
      _asrModeCache = "miniprogram";
      return "miniprogram";
    }
    // Test if getUserMedia actually works (some web-views have the API but block it)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      console.log("[Voice] getUserMedia succeeded in miniprogram");
    } catch (e) {
      console.log("[Voice] getUserMedia failed:", e.message, "→ miniprogram mode");
      _asrModeCache = "miniprogram";
      return "miniprogram";
    }
  }

  // Probe WebSocket for server-side ASR
  try {
    const wsUrl = getWsUrl();
    console.log("[Voice] probing WebSocket:", wsUrl);
    const ws = new WebSocket(wsUrl);
    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => { ws.close(); console.log("[Voice] WS timeout → browser"); resolve("browser"); }, 2000);
      ws.onmessage = (evt) => {
        clearTimeout(timeout);
        try {
          const msg = JSON.parse(evt.data);
          const mode = msg.type === "config" && msg.provider === "browser" ? "browser" : "server";
          console.log("[Voice] WS config:", msg, "→", mode);
          resolve(mode);
        } catch {
          resolve("server");
        }
        ws.close();
      };
      ws.onerror = (e) => { clearTimeout(timeout); console.log("[Voice] WS error → browser", e); resolve("browser"); };
      ws.onclose = () => { clearTimeout(timeout); };
    });
    console.log("[Voice] final mode:", result);
    _asrModeCache = result;
    return result;
  } catch (e) {
    console.log("[Voice] WS probe failed:", e, "→ browser");
    _asrModeCache = "browser";
    return "browser";
  }
}

export function isVoiceSupported() {
  if (IS_MINIPROGRAM) return true; // Server-side ASR via MediaRecorder works in WeChat WebView
  return !!BrowserSpeechRecognition || _asrModeCache === "server";
}

export default function VoiceInput({ onResult, onCancel }) {
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [asrMode, setAsrMode] = useState(
    BrowserSpeechRecognition && !IS_MINIPROGRAM ? "browser" : null
  );
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

  useEffect(() => { cancelledRef.current = cancelled; }, [cancelled]);

  // ── Timer helpers ──
  function startTimer() {
    timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
  }
  function stopTimer() {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }

  // ── Miniprogram file-capture mode ──
  // Uses <input type="file" capture> to trigger system audio recorder.
  // No page navigation — stays inline.
  const fileInputRef = useRef(null);

  function startMiniRecording() {
    console.log("[Voice] miniprogram: triggering file capture");
    if (fileInputRef.current) fileInputRef.current.click();
  }

  async function handleAudioFile(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // reset for next use
    if (!file) return;
    console.log("[Voice] captured audio:", file.name, file.size, "bytes");
    setProcessing(true);
    const form = new FormData();
    form.append("file", file, file.name || "recording.m4a");
    try {
      const resp = await fetch("/api/transcribe", { method: "POST", body: form });
      const data = await resp.json();
      if (resp.ok && data.text) {
        onResult(data.text);
      } else {
        console.log("[Voice] transcribe failed:", data);
      }
    } catch (err) {
      console.log("[Voice] upload error:", err);
    } finally {
      setProcessing(false);
    }
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
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.continuous = true;

    recognition.onresult = (event) => {
      let final = "";
      let interim = "";
      for (let i = 0; i < event.results.length; i++) {
        const text = event.results[i][0]?.transcript || "";
        if (event.results[i].isFinal) final += text;
        else interim += text;
      }
      if (final && !cancelledRef.current) onResult(final);
      if (interim) setInterimText(interim);
    };
    recognition.onerror = (e) => {
      if (e.error === "no-speech") return;
      stopTimer(); setRecording(false);
    };
    recognition.onend = () => {
      if (recognitionRef.current && !cancelledRef.current) {
        try { recognitionRef.current.start(); } catch { /* already stopped */ }
      }
    };

    recognition.start();
    recognitionRef.current = recognition;
    startTimer();
  }

  function stopBrowserRecording() {
    stopTimer();
    const ref = recognitionRef.current;
    recognitionRef.current = null;
    if (cancelledRef.current) {
      ref?.abort();
      setRecording(false);
      setCancelled(false);
      setInterimText("");
      onCancel();
    } else {
      ref?.stop();
      setRecording(false);
      setInterimText("");
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
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === "config") return;
          if (msg.type === "interim" && msg.text) setInterimText(msg.text);
          if (msg.type === "final") {
            if (msg.text && !cancelledRef.current) onResult(msg.text);
            cleanup();
          }
        } catch { /* ignore */ }
      };

      ws.onerror = () => cleanup();

      ws.onopen = () => {
        const recorder = new MediaRecorder(stream, {
          mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
            ? "audio/webm;codecs=opus" : "audio/webm",
        });
        mediaRecorderRef.current = recorder;
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) ws.send(e.data);
        };
        recorder.start(250);
      };

      startTimer();
    } catch {
      setRecording(false);
      onCancel();
    }
  }, [onResult, onCancel]);

  function cleanup() {
    stopTimer();
    setRecording(false);
    setProcessing(false);
    setInterimText("");
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") mediaRecorderRef.current.stop();
    mediaRecorderRef.current = null;
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
    if (wsRef.current) { if (wsRef.current.readyState === WebSocket.OPEN) wsRef.current.close(); wsRef.current = null; }
  }

  function stopServerRecording() {
    if (cancelledRef.current) { cleanup(); setCancelled(false); onCancel(); return; }
    if (seconds < 1) { cleanup(); return; }
    setRecording(false);
    setProcessing(true);
    stopTimer();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") mediaRecorderRef.current.stop();
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) wsRef.current.send("stop");
    setTimeout(() => { if (wsRef.current) cleanup(); }, 30000);
  }

  // ── Unified start/stop ──
  function startRecording(clientY) {
    console.log("[Voice] startRecording, asrMode =", asrMode);
    if (asrMode === "miniprogram") startMiniRecording();
    else if (asrMode === "server") startServerRecording(clientY);
    else if (BrowserSpeechRecognition) startBrowserRecording(clientY);
    else console.log("[Voice] no recording method available");
  }

  function stopRecording() {
    if (asrMode === "miniprogram") return; // handled by native page
    else if (asrMode === "server") stopServerRecording();
    else stopBrowserRecording();
  }

  function handleMove(clientY) {
    if (!recording) return;
    const shouldCancel = startYRef.current - clientY > 150;
    setCancelled(shouldCancel);
    cancelledRef.current = shouldCancel;
  }

  const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  // Not ready yet (detecting mode)
  if (!asrMode && !BrowserSpeechRecognition) return null;

  // Processing state
  if (processing) {
    return (
      <Box sx={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        height: 36, borderRadius: RADIUS.sm,
        bgcolor: COLOR.surface, border: `1px solid ${COLOR.border}`,
      }}>
        <CircularProgress size={16} sx={{ color: COLOR.primary, mr: 1 }} />
        <Typography variant="body2" sx={{ fontSize: TYPE.heading.fontSize, color: COLOR.text3 }}>
          识别中...
        </Typography>
      </Box>
    );
  }

  return (
    <Box
      onTouchStart={(e) => { if (asrMode !== "miniprogram") { e.preventDefault(); e.stopPropagation(); startRecording(e.touches[0].clientY); } }}
      onTouchEnd={(e) => { if (asrMode !== "miniprogram") { e.preventDefault(); e.stopPropagation(); stopRecording(); } }}
      onTouchMove={(e) => { if (asrMode !== "miniprogram") { e.preventDefault(); handleMove(e.touches[0].clientY); } }}
      onClick={() => { if (asrMode === "miniprogram") startRecording(); }}
      onMouseDown={(e) => { if (e.button === 0) startRecording(e.clientY); }}
      onMouseUp={(e) => { if (e.button === 0) stopRecording(); }}
      onMouseMove={(e) => { if (recording) handleMove(e.clientY); }}
      onContextMenu={(e) => e.preventDefault()}
      sx={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        height: 36, borderRadius: RADIUS.sm, cursor: "pointer", userSelect: "none",
        bgcolor: recording ? (cancelled ? COLOR.danger : COLOR.primary) : COLOR.white,
        border: recording ? "none" : `1px solid ${COLOR.border}`,
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
          : asrMode === "miniprogram" ? "点击录音" : "按住说话"}
      </Typography>
      {/* Hidden file input for miniprogram audio capture */}
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*"
        capture="microphone"
        style={{ display: "none" }}
        onChange={handleAudioFile}
      />
    </Box>
  );
}
