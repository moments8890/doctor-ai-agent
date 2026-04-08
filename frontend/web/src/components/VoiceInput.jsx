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
  // In miniprogram, use JSSDK mode (wx.startRecord)
  if (IS_MINIPROGRAM) {
    _asrModeCache = "jssdk";
    return "jssdk";
  }
  try {
    const ws = new WebSocket(getWsUrl());
    const result = await new Promise((resolve) => {
      const timeout = setTimeout(() => { ws.close(); resolve("browser"); }, 2000);
      ws.onmessage = (evt) => {
        clearTimeout(timeout);
        try {
          const msg = JSON.parse(evt.data);
          resolve(msg.type === "config" && msg.provider === "browser" ? "browser" : "server");
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
  if (IS_MINIPROGRAM) return true; // JSSDK recording always available
  return !!BrowserSpeechRecognition || _asrModeCache === "server";
}

// ── JSSDK wx.config (one-time) ──────────────────────────────────────
let _jssdkConfigured = false;
let _jssdkConfiguring = false;

async function ensureJssdkConfig() {
  if (_jssdkConfigured || _jssdkConfiguring) return _jssdkConfigured;
  if (typeof wx === "undefined") return false;
  _jssdkConfiguring = true;
  try {
    const resp = await fetch("/api/wechat/jssdk-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: window.location.href.split("#")[0] }),
    });
    if (!resp.ok) throw new Error(`JSSDK config failed: ${resp.status}`);
    const cfg = await resp.json();
    await new Promise((resolve, reject) => {
      wx.config({ // eslint-disable-line no-undef
        debug: false,
        appId: cfg.appId,
        timestamp: cfg.timestamp,
        nonceStr: cfg.nonceStr,
        signature: cfg.signature,
        jsApiList: ["startRecord", "stopRecord", "uploadVoice", "onVoiceRecordEnd"],
      });
      wx.ready(() => { _jssdkConfigured = true; resolve(); }); // eslint-disable-line no-undef
      wx.error((err) => { console.error("[JSSDK] config error", err); reject(err); }); // eslint-disable-line no-undef
    });
    return true;
  } catch (e) {
    console.error("[JSSDK] config failed", e);
    return false;
  } finally {
    _jssdkConfiguring = false;
  }
}


export default function VoiceInput({ onResult, onCancel }) {
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [asrMode, setAsrMode] = useState(
    IS_MINIPROGRAM ? "jssdk" : (BrowserSpeechRecognition ? "browser" : null)
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
    if (IS_MINIPROGRAM) ensureJssdkConfig();
  }, []);

  useEffect(() => { cancelledRef.current = cancelled; }, [cancelled]);

  // ── Timer helpers ──
  function startTimer() {
    timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
  }
  function stopTimer() {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }

  // ── JSSDK mode (WeChat miniprogram web-view) ──
  function startJssdkRecording(clientY) {
    if (typeof wx === "undefined") return;
    startYRef.current = clientY;
    setCancelled(false);
    cancelledRef.current = false;
    setSeconds(0);
    setRecording(true);
    setInterimText("");

    wx.startRecord(); // eslint-disable-line no-undef
    // Auto-stop at 60s limit
    wx.onVoiceRecordEnd({ // eslint-disable-line no-undef
      complete: (res) => {
        if (!cancelledRef.current) {
          _handleJssdkUpload(res.localId);
        } else {
          setRecording(false);
          setCancelled(false);
        }
      },
    });
    startTimer();
  }

  function stopJssdkRecording() {
    if (typeof wx === "undefined") return;
    stopTimer();

    if (cancelledRef.current) {
      wx.stopRecord(); // eslint-disable-line no-undef
      setRecording(false);
      setCancelled(false);
      setInterimText("");
      onCancel();
      return;
    }

    if (seconds < 1) {
      wx.stopRecord(); // eslint-disable-line no-undef
      setRecording(false);
      setInterimText("");
      return;
    }

    setRecording(false);
    setProcessing(true);

    wx.stopRecord({ // eslint-disable-line no-undef
      success: (res) => _handleJssdkUpload(res.localId),
      fail: () => { setProcessing(false); },
    });
  }

  function _handleJssdkUpload(localId) {
    wx.uploadVoice({ // eslint-disable-line no-undef
      localId,
      isShowProgressTips: 0,
      success: async (res) => {
        try {
          const resp = await fetch("/api/voice/wx-transcribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ serverId: res.serverId }),
          });
          if (resp.ok) {
            const data = await resp.json();
            if (data.text) onResult(data.text);
          }
        } catch (e) {
          console.error("[JSSDK] transcribe error", e);
        } finally {
          setProcessing(false);
          setInterimText("");
        }
      },
      fail: () => { setProcessing(false); setInterimText(""); },
    });
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
    if (asrMode === "jssdk") startJssdkRecording(clientY);
    else if (asrMode === "server") startServerRecording(clientY);
    else if (BrowserSpeechRecognition) startBrowserRecording(clientY);
  }

  function stopRecording() {
    if (asrMode === "jssdk") stopJssdkRecording();
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
        height: 40, borderRadius: RADIUS.sm,
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
      onTouchStart={(e) => { e.preventDefault(); startRecording(e.touches[0].clientY); }}
      onTouchEnd={() => stopRecording()}
      onTouchMove={(e) => handleMove(e.touches[0].clientY)}
      onMouseDown={(e) => startRecording(e.clientY)}
      onMouseUp={() => stopRecording()}
      onMouseMove={(e) => { if (recording) handleMove(e.clientY); }}
      onContextMenu={(e) => e.preventDefault()}
      sx={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        height: 40, borderRadius: RADIUS.sm, cursor: "pointer", userSelect: "none",
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
          : "按住说话"}
      </Typography>
    </Box>
  );
}
