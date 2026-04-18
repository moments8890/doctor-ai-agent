/**
 * useVoiceRecording — state machine for inline voice recording via miniapp bridge.
 *
 * States: idle → recording → transcribing → idle (with transcript)
 * Communication: web-view → backend ← miniapp (backend as message bus)
 */
import { useCallback, useEffect, useRef, useState } from "react";

const POLL_INTERVAL = 500;
const MAX_POLLS = 30; // 15s timeout

async function postSession(doctorId, action, extra = {}) {
  const res = await fetch("/api/voice/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId, action, ...extra }),
  });
  return res.json();
}

async function getSession(doctorId) {
  const res = await fetch(`/api/voice/session?doctor_id=${encodeURIComponent(doctorId)}`);
  return res.json();
}

export function useVoiceRecording(doctorId) {
  const [state, setState] = useState("idle"); // idle | preparing | recording | transcribing | error
  const [elapsed, setElapsed] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [interim, setInterim] = useState("");
  const [error, setError] = useState(null);

  const timerRef = useRef(null);
  const pollRef = useRef(null);
  const pollCountRef = useRef(0);
  const startTsRef = useRef(0);
  const lastToggleRef = useRef(0);

  // Elapsed timer — only while plugin is actually recording, not while preparing
  useEffect(() => {
    if (state === "recording") {
      startTsRef.current = Date.now();
      setElapsed(0);
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTsRef.current) / 1000));
      }, 250);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [state]);

  // Poll during "preparing" to learn when the miniapp has actually started
  // WechatSI. The web UI stays in "准备中…" until the backend reports status
  // "recording" so the user doesn't speak into a mic that isn't live yet.
  useEffect(() => {
    if (state !== "preparing") return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        const data = await getSession(doctorId);
        if (data.status === "recording") {
          setState("recording");
          return;
        }
        // Defensive: if the whole record/stop cycle finished before we
        // ever saw "recording" (rare, but possible with fast stop clicks),
        // deliver the transcript straight from here.
        if (data.status === "done" && data.text) {
          setTranscript(data.text);
          setState("idle");
          postSession(doctorId, "clear").catch(() => {});
          return;
        }
        if (data.status === "error") {
          setState("error");
          setError(data.error || "识别失败");
          postSession(doctorId, "clear").catch(() => {});
          return;
        }
      } catch {
        // ignore transient network errors, keep polling
      }
      setTimeout(tick, 150);
    };
    tick();
    return () => { cancelled = true; };
  }, [state, doctorId]);

  // Poll during "recording" for streaming interim text from WechatSI's
  // onRecognize callback. The miniapp posts each interim snapshot to the
  // command-bus; we pull it here at ~200ms intervals so the web input can
  // render live transcription as the doctor speaks.
  useEffect(() => {
    if (state !== "recording") return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        const data = await getSession(doctorId);
        if (data.status === "recording" && data.text) {
          setInterim(data.text);
        } else if (data.status === "done" && data.text) {
          // Session auto-completed (e.g. 58s duration cap reached before user
          // clicked stop). Deliver the final transcript directly.
          setTranscript(data.text);
          setInterim("");
          setState("idle");
          postSession(doctorId, "clear").catch(() => {});
          return;
        } else if (data.status === "error") {
          setState("error");
          setError(data.error || "识别失败");
          setInterim("");
          postSession(doctorId, "clear").catch(() => {});
          return;
        }
      } catch {
        // transient — keep polling
      }
      setTimeout(tick, 200);
    };
    tick();
    return () => { cancelled = true; };
  }, [state, doctorId]);

  // Clear interim whenever we leave the active voice states so stale text
  // can't leak into a subsequent recording.
  useEffect(() => {
    if (state === "idle" || state === "error") {
      setInterim("");
    }
  }, [state]);

  // Poll for result when transcribing
  useEffect(() => {
    if (state !== "transcribing") return;
    pollCountRef.current = 0;

    pollRef.current = setInterval(async () => {
      pollCountRef.current++;
      if (pollCountRef.current > MAX_POLLS) {
        clearInterval(pollRef.current);
        setState("error");
        setError("识别超时，请重试");
        return;
      }
      try {
        const data = await getSession(doctorId);
        if (data.status === "done" && data.text) {
          clearInterval(pollRef.current);
          setTranscript(data.text);
          setState("idle");
          postSession(doctorId, "clear").catch(() => {});
        } else if (data.status === "error") {
          clearInterval(pollRef.current);
          setState("error");
          setError(data.error || "识别失败");
          postSession(doctorId, "clear").catch(() => {});
        }
      } catch {
        // Network error — keep polling
      }
    }, POLL_INTERVAL);

    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [state, doctorId]);

  // Cleanup on unmount — stop recording if active
  useEffect(() => {
    return () => {
      postSession(doctorId, "clear").catch(() => {});
    };
  }, [doctorId]);

  const toggle = useCallback(async () => {
    // Debounce — ignore taps within 300ms
    const now = Date.now();
    if (now - lastToggleRef.current < 300) return;
    lastToggleRef.current = now;

    if (state === "idle" || state === "error") {
      setError(null);
      setTranscript("");
      try {
        await postSession(doctorId, "start");
        setState("preparing");
      } catch {
        setState("error");
        setError("网络异常");
      }
    } else if (state === "preparing") {
      // User clicked to cancel before the plugin actually engaged. Post "clear"
      // so the session dies cleanly — miniapp will see idle on its next poll and
      // never record. If the miniapp already called plugin.start() in the tiny
      // race window, its onStop/onError will post to a cleared session (no-op
      // on the backend), so nothing lingers. Return web to idle immediately.
      try {
        await postSession(doctorId, "clear");
      } catch {
        // ignore — already cancelled locally
      }
      setState("idle");
      setTranscript("");
      setError(null);
    } else if (state === "recording") {
      try {
        await postSession(doctorId, "stop");
        setState("transcribing");
      } catch {
        setState("error");
        setError("网络异常");
      }
    }
    // state === "transcribing" — deliberately ignore; wait for result
  }, [state, doctorId]);

  const clear = useCallback(() => {
    setState("idle");
    setTranscript("");
    setError(null);
    postSession(doctorId, "clear").catch(() => {});
  }, [doctorId]);

  return { state, elapsed, transcript, interim, error, toggle, clear };
}
