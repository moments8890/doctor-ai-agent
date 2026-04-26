# Inline Voice Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let doctors use voice input directly from the web-view (chat + add-knowledge pages) without navigating to a separate native miniapp page, using the backend as a message bus between the web-view and the miniapp.

**Architecture:** Web-view sends start/stop commands to a backend voice session endpoint. The miniapp polls for commands, records audio natively via `wx.getRecorderManager`, uploads to ASR, and posts the transcript back. The web-view polls for the result and fills the text input. All UI stays in the web-view.

**Tech Stack:** FastAPI (backend session), React hooks (web-view), WeChat miniapp native APIs (recorder)

**Spec:** `docs/superpowers/specs/2026-04-16-inline-voice-recording-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/channels/web/voice_jssdk.py` | Add voice session endpoints (`POST/GET /api/voice/session`) |
| Create | `tests/core/test_voice_session.py` | Backend session tests |
| Create | `frontend/web/src/hooks/useVoiceRecording.js` | Voice state machine hook |
| Create | `frontend/web/src/components/VoiceMicButton.jsx` | Reusable mic button component |
| Modify | `frontend/web/src/components/VoiceInput.jsx` | Update `isVoiceSupported()` to check miniapp |
| Modify | `frontend/web/src/utils/miniappBridge.js` | Remove `openAddRuleVoice`, add `isVoiceSupported` |
| Modify | `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx` | Replace voice nav row with `VoiceMicButton` |
| Modify | `frontend/web/src/pages/doctor/IntakePage.jsx` | Replace `MiniVoiceMicHint` with `VoiceMicButton` |
| Modify | `frontend/web/src/pages/doctor/DoctorPage.jsx` | Replace `MiniVoiceMicHint` with `VoiceMicButton` |
| Modify | `frontend/miniprogram/pages/doctor/doctor.js` | Add background voice recorder + polling |

---

### Task 1: Backend Voice Session Endpoint

**Files:**
- Modify: `src/channels/web/voice_jssdk.py`
- Test: `tests/core/test_voice_session.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_voice_session.py`:

```python
"""Tests for voice session relay endpoints."""
import time
import pytest
from unittest.mock import patch

# Import the session store directly for inspection
from channels.web.voice_jssdk import _voice_sessions, _SESSION_TTL


@pytest.fixture(autouse=True)
def clear_sessions():
    _voice_sessions.clear()
    yield
    _voice_sessions.clear()


def test_post_start_creates_session(client):
    resp = client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "start",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_start"
    assert "session_id" in data


def test_get_session_returns_pending_action(client):
    client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "start",
    })
    resp = client.get("/api/voice/session", params={"doctor_id": "doc1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_start"
    assert data["action"] == "start"


def test_post_stop_updates_session(client):
    client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "start",
    })
    resp = client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "stop",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_stop"


def test_post_recording_updates_status(client):
    client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "start",
    })
    resp = client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "recording",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "recording"


def test_post_result_stores_transcript(client):
    client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "start",
    })
    resp = client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "result",
        "text": "患者血压升高",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"

    get_resp = client.get("/api/voice/session", params={"doctor_id": "doc1"})
    assert get_resp.json()["text"] == "患者血压升高"
    assert get_resp.json()["status"] == "done"


def test_post_error_stores_error(client):
    client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "start",
    })
    resp = client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "error",
        "error": "permission_denied",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"

    get_resp = client.get("/api/voice/session", params={"doctor_id": "doc1"})
    assert get_resp.json()["error"] == "permission_denied"


def test_get_nonexistent_returns_idle(client):
    resp = client.get("/api/voice/session", params={"doctor_id": "nobody"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


def test_post_clear_resets_session(client):
    client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "start",
    })
    resp = client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "clear",
    })
    assert resp.status_code == 200
    get_resp = client.get("/api/voice/session", params={"doctor_id": "doc1"})
    assert get_resp.json()["status"] == "idle"


def test_expired_session_returns_idle(client):
    client.post("/api/voice/session", json={
        "doctor_id": "doc1", "action": "start",
    })
    # Manually expire the session
    _voice_sessions["doc1"]["created_at"] = time.time() - _SESSION_TTL - 1
    resp = client.get("/api/voice/session", params={"doctor_id": "doc1"})
    assert resp.json()["status"] == "idle"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_voice_session.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `_voice_sessions` and `_SESSION_TTL` not defined, endpoints not registered.

Note: Tests use a `client` fixture. Check `conftest.py` for the existing test client fixture pattern. If tests need a sync test client, adapt to match the existing pattern (likely `httpx.AsyncClient` with `pytest-asyncio`).

- [ ] **Step 3: Implement voice session endpoints**

Add to `src/channels/web/voice_jssdk.py` after the existing `get_voice_result` endpoint:

```python
# ── Voice session relay (web-view ↔ miniapp via backend) ───────────────────

import uuid

_voice_sessions: dict[str, dict] = {}
_SESSION_TTL = 120  # seconds


def _clean_expired_sessions():
    now = time.time()
    expired = [k for k, v in _voice_sessions.items() if now - v["created_at"] > _SESSION_TTL]
    for k in expired:
        del _voice_sessions[k]


class VoiceSessionCommand(BaseModel):
    doctor_id: str
    action: str  # start | stop | recording | result | error | clear
    text: Optional[str] = None
    error: Optional[str] = None


@router.post("/api/voice/session")
async def post_voice_session(body: VoiceSessionCommand):
    """Create or update a voice recording session."""
    _clean_expired_sessions()
    did = body.doctor_id

    if body.action == "clear":
        _voice_sessions.pop(did, None)
        return {"status": "idle"}

    if body.action == "start":
        _voice_sessions[did] = {
            "session_id": uuid.uuid4().hex[:12],
            "status": "pending_start",
            "action": "start",
            "text": None,
            "error": None,
            "created_at": time.time(),
        }
        return {"session_id": _voice_sessions[did]["session_id"], "status": "pending_start"}

    session = _voice_sessions.get(did)
    if not session:
        return {"status": "idle"}

    if body.action == "stop":
        session["status"] = "pending_stop"
        session["action"] = "stop"
    elif body.action == "recording":
        session["status"] = "recording"
        session["action"] = None
    elif body.action == "result":
        session["status"] = "done"
        session["action"] = None
        session["text"] = body.text
    elif body.action == "error":
        session["status"] = "error"
        session["action"] = None
        session["error"] = body.error

    return {"status": session["status"]}


@router.get("/api/voice/session")
async def get_voice_session(doctor_id: str):
    """Read current voice session state. Polled by both miniapp and web-view."""
    _clean_expired_sessions()
    session = _voice_sessions.get(doctor_id)
    if not session:
        return {"status": "idle", "action": None, "text": None, "error": None}

    return {
        "status": session["status"],
        "action": session.get("action"),
        "text": session.get("text"),
        "error": session.get("error"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_voice_session.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/voice_jssdk.py tests/core/test_voice_session.py
git commit -m "feat(voice): add voice session relay endpoints for inline recording"
```

---

### Task 2: `useVoiceRecording` React Hook

**Files:**
- Create: `frontend/web/src/hooks/useVoiceRecording.js`

- [ ] **Step 1: Create the hook**

Create `frontend/web/src/hooks/useVoiceRecording.js`:

```javascript
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
  const [state, setState] = useState("idle"); // idle | recording | transcribing | error
  const [elapsed, setElapsed] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState(null);

  const timerRef = useRef(null);
  const pollRef = useRef(null);
  const pollCountRef = useRef(0);
  const startTsRef = useRef(0);
  const lastToggleRef = useRef(0);

  // Elapsed timer
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
          // Clear the session
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
    // Debounce — ignore taps within 500ms
    const now = Date.now();
    if (now - lastToggleRef.current < 500) return;
    lastToggleRef.current = now;

    if (state === "idle" || state === "error") {
      setError(null);
      setTranscript("");
      try {
        await postSession(doctorId, "start");
        setState("recording");
      } catch {
        setState("error");
        setError("网络异常");
      }
    } else if (state === "recording") {
      try {
        await postSession(doctorId, "stop");
        setState("transcribing");
      } catch {
        setState("error");
        setError("网络异常");
      }
    }
  }, [state, doctorId]);

  const clear = useCallback(() => {
    setState("idle");
    setTranscript("");
    setError(null);
    postSession(doctorId, "clear").catch(() => {});
  }, [doctorId]);

  return { state, elapsed, transcript, error, toggle, clear };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/hooks/useVoiceRecording.js
git commit -m "feat(voice): add useVoiceRecording hook with state machine + polling"
```

---

### Task 3: `VoiceMicButton` Component

**Files:**
- Create: `frontend/web/src/components/VoiceMicButton.jsx`

- [ ] **Step 1: Create the component**

Create `frontend/web/src/components/VoiceMicButton.jsx`:

```jsx
/**
 * VoiceMicButton — inline mic button for voice recording via miniapp bridge.
 *
 * Shows mic icon (idle), pulsing red mic + timer (recording), spinner (transcribing).
 * Only renders when inside WeChat miniapp (voice recording requires native bridge).
 *
 * Props:
 *   doctorId: string — current doctor ID
 *   onTranscript: (text: string) => void — called when transcript is ready
 *   compact: boolean — smaller size for inline use in input bars (default false)
 */
import { useEffect } from "react";
import { Box, CircularProgress } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import StopIcon from "@mui/icons-material/Stop";
import { useVoiceRecording } from "../hooks/useVoiceRecording";
import { isInMiniapp } from "../utils/miniappBridge";
import { COLOR, RADIUS, TYPE } from "../theme";

export default function VoiceMicButton({ doctorId, onTranscript, compact = false }) {
  const { state, elapsed, transcript, error, toggle, clear } = useVoiceRecording(doctorId);

  // Deliver transcript to parent when it arrives
  useEffect(() => {
    if (transcript) {
      onTranscript?.(transcript);
      clear();
    }
  }, [transcript, onTranscript, clear]);

  if (!isInMiniapp()) return null;

  const isRecording = state === "recording";
  const isTranscribing = state === "transcribing";
  const isError = state === "error";
  const isActive = isRecording || isTranscribing;

  if (compact) {
    // Inline mic for input bars — same size as MiniVoiceMicHint
    return (
      <Box
        onClick={toggle}
        sx={{
          position: "relative", p: 1, cursor: "pointer", flexShrink: 0,
          display: "flex", alignItems: "center", gap: 0.5,
          color: isRecording ? COLOR.danger : isTranscribing ? COLOR.primary : COLOR.text4,
        }}
      >
        {isTranscribing ? (
          <CircularProgress size={18} sx={{ color: COLOR.primary }} />
        ) : isRecording ? (
          <StopIcon sx={{ fontSize: 22, animation: "micPulse 1s ease-in-out infinite",
            "@keyframes micPulse": {
              "0%, 100%": { opacity: 1 },
              "50%": { opacity: 0.5 },
            },
          }} />
        ) : (
          <MicIcon sx={{ fontSize: 22 }} />
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
        border: `1px solid ${isActive ? COLOR.danger : COLOR.border}`,
        borderRadius: RADIUS.md, cursor: "pointer",
        bgcolor: isRecording ? "rgba(255,77,79,0.06)" : COLOR.white,
        "&:active": { opacity: 0.7 },
        transition: "all 0.15s ease",
      }}
    >
      {isTranscribing ? (
        <CircularProgress size={20} sx={{ color: COLOR.primary }} />
      ) : isRecording ? (
        <StopIcon sx={{ color: COLOR.danger, animation: "micPulse 1s ease-in-out infinite",
          "@keyframes micPulse": { "0%, 100%": { opacity: 1 }, "50%": { opacity: 0.5 } },
        }} />
      ) : (
        <MicIcon sx={{ color: isError ? COLOR.danger : COLOR.primary }} />
      )}
      <Box sx={{ flex: 1 }}>
        <Box sx={{ fontSize: TYPE.body.fontSize, color: isRecording ? COLOR.danger : COLOR.text1 }}>
          {isRecording ? `录音中 ${elapsed}s — 点击停止` :
           isTranscribing ? "识别中..." :
           isError ? error || "识别失败，点击重试" :
           "语音输入"}
        </Box>
      </Box>
    </Box>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/components/VoiceMicButton.jsx
git commit -m "feat(voice): add VoiceMicButton component for inline recording"
```

---

### Task 4: Update `miniappBridge.js` and `VoiceInput.jsx`

**Files:**
- Modify: `frontend/web/src/utils/miniappBridge.js`
- Modify: `frontend/web/src/components/VoiceInput.jsx`

- [ ] **Step 1: Update miniappBridge.js**

Replace `frontend/web/src/utils/miniappBridge.js` with:

```javascript
// Bridge between the React SPA (running inside WeChat miniapp web-view)
// and native miniapp pages. In a regular browser, these helpers are no-ops.

export function isInMiniapp() {
  return typeof window !== "undefined"
    && window.__wxjs_environment === "miniprogram";
}

/** True when inline voice recording is available (requires miniapp bridge). */
export function isVoiceSupported() {
  return isInMiniapp();
}
```

- [ ] **Step 2: Update VoiceInput.jsx**

In `frontend/web/src/components/VoiceInput.jsx`, update `isVoiceSupported` to delegate to the bridge:

```javascript
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
  // In miniapp, VoiceMicButton replaces this — don't show keyboard hint
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
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/utils/miniappBridge.js frontend/web/src/components/VoiceInput.jsx
git commit -m "refactor(voice): update bridge and VoiceInput for inline recording"
```

---

### Task 5: Integrate VoiceMicButton into AddKnowledgeSubpage

**Files:**
- Modify: `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx`

- [ ] **Step 1: Replace the voice navigation row**

In `AddKnowledgeSubpage.jsx`:

1. Replace import line 9:
```javascript
// OLD:
import { isInMiniapp, openAddRuleVoice } from "../../../utils/miniappBridge";
// NEW:
import { isVoiceSupported } from "../../../utils/miniappBridge";
import VoiceMicButton from "../../../components/VoiceMicButton";
```

2. Remove the `MicIcon` import (line 15) — no longer needed since `VoiceMicButton` handles its own icon.

3. Replace the "语音添加规则" block (lines 386-405) with:
```jsx
      {/* Voice input — only visible inside WeChat miniapp */}
      {isVoiceSupported() && (
        <VoiceMicButton
          doctorId={doctorId}
          onTranscript={(text) => {
            setContent((prev) => prev ? prev + "\n" + text : text);
            setSourceTab("text");
          }}
        />
      )}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx
git commit -m "feat(voice): replace voice nav with inline VoiceMicButton in add-knowledge"
```

---

### Task 6: Integrate VoiceMicButton into Chat Input Bars

**Files:**
- Modify: `frontend/web/src/pages/doctor/IntakePage.jsx`
- Modify: `frontend/web/src/pages/doctor/DoctorPage.jsx`

- [ ] **Step 1: Update IntakePage.jsx**

In `IntakePage.jsx`:

1. Add import:
```javascript
import VoiceMicButton from "../../components/VoiceMicButton";
import { isInMiniapp } from "../../utils/miniappBridge";
```

2. Find the input bar section (around line 442). After `MiniVoiceMicHint`, add `VoiceMicButton`:
```jsx
          <MiniVoiceMicHint inputRef={inputRef} showHint={voiceHint} onHint={() => { setVoiceHint(true); setTimeout(() => setVoiceHint(false), 5000); }} />
          {isInMiniapp() && (
            <VoiceMicButton
              doctorId={doctorId}
              compact
              onTranscript={(text) => setInput((prev) => prev ? prev + " " + text : text)}
            />
          )}
```

Note: `MiniVoiceMicHint` already hides itself in miniapp (from Task 4), so both won't show simultaneously. The `VoiceMicButton compact` renders the inline mic.

- [ ] **Step 2: Update DoctorPage.jsx**

Same pattern. Find the `MiniVoiceMicHint` usage (around line 508) and add after it:
```jsx
          {isInMiniapp() && (
            <VoiceMicButton
              doctorId={doctorId}
              compact
              onTranscript={(text) => setInput((prev) => prev ? prev + " " + text : text)}
            />
          )}
```

Add the imports at the top:
```javascript
import VoiceMicButton from "../../components/VoiceMicButton";
import { isInMiniapp } from "../../utils/miniappBridge";
```

Note: Check if `isInMiniapp` or similar is already imported from `utils/env.js`. If so, reuse the existing import rather than adding a duplicate.

- [ ] **Step 3: Verify build**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/doctor/IntakePage.jsx frontend/web/src/pages/doctor/DoctorPage.jsx
git commit -m "feat(voice): add inline VoiceMicButton to chat input bars"
```

---

### Task 7: Miniapp Background Voice Recorder

**Files:**
- Modify: `frontend/miniprogram/pages/doctor/doctor.js`

This is the critical task — the miniapp side that records audio in the background and relays results through the backend.

- [ ] **Step 1: Add voice recording logic to doctor.js**

Modify `frontend/miniprogram/pages/doctor/doctor.js`. Add recording state and polling:

```javascript
const runtimeConfig = require("../../config.js");

const RECORDER_OPTIONS = {
  duration: 60000,
  sampleRate: 16000,
  numberOfChannels: 1,
  encodeBitRate: 96000,
  format: "mp3",
};

const VOICE_POLL_MS = 500;

Page({
  data: {
    url: "",
    loading: true,
    loadError: false,
    showPermissionPrompt: false,
  },

  // Voice recording state (not in data — no UI rendering needed)
  _voicePollTimer: null,
  _isRecording: false,
  _recorderManager: null,

  onLoad() {
    const app = getApp();
    const token = app.globalData.accessToken;
    const doctorId = app.globalData.doctorId;
    const doctorName = app.globalData.doctorName || "";

    if (!token) {
      wx.redirectTo({ url: "/pages/login/login" });
      return;
    }

    const webBase = app.globalData.apiBase;
    const qs = [
      "token="     + encodeURIComponent(token),
      "doctor_id=" + encodeURIComponent(doctorId),
      "name="      + encodeURIComponent(doctorName),
    ].join("&");

    this.setData({ url: webBase + "/doctor?" + qs });

    // Initialize recorder
    this._recorderManager = wx.getRecorderManager();
    this._recorderManager.onStop((res) => {
      this._isRecording = false;
      this._handleRecordingDone(res.tempFilePath);
    });
    this._recorderManager.onError(() => {
      this._isRecording = false;
      this._postVoiceSession("error", { error: "recording_failed" });
    });

    // Show permission prompt if configured
    if (runtimeConfig.subscribeTemplateId && !wx.getStorageSync("permission_prompted")) {
      this.setData({ showPermissionPrompt: true, loading: false });
    }
  },

  onShow() {
    // Start polling for voice commands from the web-view
    this._startVoicePoll();

    // Legacy: check voice result from add-rule page
    const app = getApp();
    const result = app.globalData.voiceResult;
    const ts = app.globalData.voiceResultTs;
    if (result && ts && Date.now() - ts < 10000) {
      app.globalData.voiceResult = null;
      app.globalData.voiceResultTs = null;
      this._pendingVoiceText = result;
    }
  },

  onHide() {
    this._stopVoicePoll();
    if (this._isRecording) {
      try { this._recorderManager.stop(); } catch (_) {}
      this._isRecording = false;
    }
  },

  onUnload() {
    this._stopVoicePoll();
  },

  // ── Voice polling ──────────────────────────────────────────────────────

  _startVoicePoll() {
    this._stopVoicePoll();
    const app = getApp();
    const doctorId = app.globalData.doctorId;
    const token = app.globalData.accessToken;
    if (!doctorId || !token) return;

    this._voicePollTimer = setInterval(() => {
      this._pollVoiceSession(doctorId, token);
    }, VOICE_POLL_MS);
  },

  _stopVoicePoll() {
    if (this._voicePollTimer) {
      clearInterval(this._voicePollTimer);
      this._voicePollTimer = null;
    }
  },

  _pollVoiceSession(doctorId, token) {
    wx.request({
      url: runtimeConfig.apiBase + "/api/voice/session?doctor_id=" + encodeURIComponent(doctorId),
      header: { "Authorization": "Bearer " + token },
      timeout: 3000,
      success: (res) => {
        if (res.statusCode !== 200) return;
        const data = res.data || {};

        if (data.action === "start" && !this._isRecording) {
          this._startRecording(doctorId, token);
        } else if (data.action === "stop" && this._isRecording) {
          this._recorderManager.stop();
        }
      },
    });
  },

  _startRecording(doctorId, token) {
    wx.authorize({
      scope: "scope.record",
      success: () => {
        this._isRecording = true;
        this._recorderManager.start(RECORDER_OPTIONS);
        // Tell backend we're now recording
        this._postVoiceSession("recording");
      },
      fail: () => {
        this._postVoiceSession("error", { error: "permission_denied" });
      },
    });
  },

  _handleRecordingDone(tempFilePath) {
    const app = getApp();
    const doctorId = app.globalData.doctorId;
    const token = app.globalData.accessToken;

    // Upload to ASR endpoint
    wx.uploadFile({
      url: runtimeConfig.apiBase + "/api/manage/knowledge/voice-extract?doctor_id=" + encodeURIComponent(doctorId),
      filePath: tempFilePath,
      name: "file",
      header: { "Authorization": "Bearer " + token },
      timeout: 15000,
      success: (res) => {
        if (res.statusCode !== 200) {
          this._postVoiceSession("error", { error: "asr_failed" });
          return;
        }
        let body;
        try { body = JSON.parse(res.data); } catch (_) {
          this._postVoiceSession("error", { error: "asr_failed" });
          return;
        }
        // The voice-extract endpoint returns { transcript, candidate, error }
        // We only want the raw transcript, not the LLM extraction
        const text = body.transcript || "";
        if (!text) {
          this._postVoiceSession("error", { error: "audio_unclear" });
          return;
        }
        this._postVoiceSession("result", { text: text });
      },
      fail: () => {
        this._postVoiceSession("error", { error: "network" });
      },
    });
  },

  _postVoiceSession(action, extra) {
    const app = getApp();
    const doctorId = app.globalData.doctorId;
    const token = app.globalData.accessToken;
    wx.request({
      url: runtimeConfig.apiBase + "/api/voice/session",
      method: "POST",
      header: {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
      },
      data: Object.assign({ doctor_id: doctorId, action: action }, extra || {}),
      timeout: 5000,
    });
  },

  // ── Existing handlers (unchanged) ──────────────────────────────────────

  onEnterTap() {
    const tmplId = runtimeConfig.subscribeTemplateId;
    if (tmplId) {
      wx.requestSubscribeMessage({
        tmplIds: [tmplId],
        complete: () => {
          wx.setStorageSync("permission_prompted", "1");
          this.setData({ showPermissionPrompt: false, loading: true });
        },
      });
    } else {
      this.setData({ showPermissionPrompt: false, loading: true });
    }
  },

  onWebViewLoad() {
    this.setData({ loading: false });
  },

  onError(e) {
    console.error("WebView load failed:", e.detail);
    this.setData({ loadError: true, loading: false });
  },

  onRetry() {
    const base = this.data.url.split("?")[0];
    const qs = this.data.url.split("?")[1] || "";
    const bust = "_t=" + Date.now();
    const newUrl = base + "?" + (qs ? qs + "&" : "") + bust;
    this.setData({ url: newUrl, loadError: false, loading: true });
  },

  onMessage(e) {
    const msgs = e.detail.data || [];
    const last = msgs[msgs.length - 1];
    if (!last) return;

    if (last.action === "logout") {
      this._clearAuth();
      wx.redirectTo({ url: "/pages/login/login" });
    }
  },

  onShareAppMessage() {
    return {
      title: "鲸鱼随行 · AI 医疗助手",
      path: "/pages/login/login",
    };
  },

  _clearAuth() {
    const app = getApp();
    app.globalData.accessToken = "";
    app.globalData.doctorId    = "";
    app.globalData.doctorName  = "";
    wx.removeStorageSync("token");
    wx.removeStorageSync("doctorId");
    wx.removeStorageSync("doctorName");
  },
});
```

Note: The miniapp uploads to the existing `/api/manage/knowledge/voice-extract` endpoint which does ASR. We only use the `transcript` field from the response, ignoring the LLM extraction (`candidate`). A cleaner approach would be a dedicated ASR-only endpoint, but reusing the existing one avoids adding backend code. If the LLM extraction call is expensive, consider adding a `transcribe_only=1` query param later.

- [ ] **Step 2: Commit**

```bash
git add frontend/miniprogram/pages/doctor/doctor.js
git commit -m "feat(voice): add background voice recorder polling to miniapp doctor page"
```

---

### Task 8: Verify End-to-End on Device

**Files:** None (manual testing)

- [ ] **Step 1: Restart backend and frontend dev servers**

```bash
# Backend
cd /Volumes/ORICO/Code/doctor-ai-agent && ./dev.sh

# Frontend (separate terminal)
cd frontend/web && npm run dev
```

- [ ] **Step 2: Test in WeChat DevTools simulator**

1. Open miniapp in simulator
2. Navigate to add-knowledge page
3. Verify "语音输入" row appears (not the old "语音添加规则" navigation)
4. Note: Recording won't work in simulator (known limitation) — verify UI states only

- [ ] **Step 3: Test on real device via 真机调试**

1. Click 真机调试 in DevTools toolbar
2. Ensure phone and Mac are on same WiFi
3. Ensure `config.js` has `apiBase` set to `http://<mac-ip>:5173`
4. Navigate to add-knowledge page → tap voice button → speak → verify transcript fills text input
5. Navigate to chat page → tap mic → speak → verify transcript fills chat input
6. Test edge cases: short recording (< 1s), network interruption, permission denial

- [ ] **Step 4: Revert config.js to prod URL**

After testing, restore `frontend/miniprogram/config.js`:
```javascript
apiBase: "https://api.doctoragentai.cn",
```

And restore `frontend/web/vite.config.js`:
```javascript
host: "127.0.0.1",
```
