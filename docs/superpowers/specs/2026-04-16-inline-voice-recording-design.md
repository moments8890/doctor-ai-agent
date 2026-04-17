# Inline Voice Recording — Design Spec

**Date**: 2026-04-16
**Status**: Approved

## Problem

The current voice-to-rule flow navigates the doctor away from the web-view to a
separate native miniapp page (`pages/add-rule/`). This is an extra UI step that
breaks the flow and feels disconnected from the rest of the app. The doctor
leaves the add-knowledge or chat page, enters a bare native page, records, waits
for LLM extraction, then navigates back. The UX should keep the doctor on the
page they're already on.

## Solution

Replace the page-navigation voice flow with an **inline voice recording bridge**
that uses the backend as a message bus between the web-view and the miniapp. The
miniapp records audio invisibly in the background. All UI stays in the web-view.
The result is raw transcription that fills the text input — no LLM extraction
step.

## Architecture

```
Web-view                     Backend                      Miniapp
   |                            |                            |
   | POST /voice/session        |                            |
   |  { action: "start" }  --->| store pending cmd           |
   | <-- { session_id } -------|                             |
   |                            |     (polling every 500ms)  |
   |  show recording UI         | <-- GET /voice/session ----|
   |  (pulsing mic, timer)      | --> { action: "start" } -->|
   |                            |                            |
   |                            |     wx.getRecorderManager  |
   |                            |       .start()             |
   |                            |                            |
   | POST /voice/session        |                            |
   |  { action: "stop" }  ---->| store pending cmd           |
   |                            | <-- GET /voice/session ----|
   |                            | --> { action: "stop" } --->|
   |                            |                            |
   |                            |     .stop()                |
   |                            | <-- upload audio ----------|
   |                            |     ASR (Tencent)          |
   |                            |     store transcript       |
   |                            |                            |
   | GET /voice/session (poll)  |                            |
   | ------------------------->|                             |
   | <-- { status: "done",      |                            |
   |       text: "..." }        |                            |
   |                            |                            |
   | fill text input            |                            |
```

**Key insight**: `wx.miniProgram.postMessage` from web-view to miniapp only
delivers on navigation events (back/share/destroy), not in real-time. The
backend acts as a reliable message bus that both sides poll.

## Components

### 1. Backend — Voice Session Endpoint

**In-memory session store** keyed by `doctor_id`. One active session per doctor.
Auto-expires after 120 seconds.

#### `POST /api/voice/session`

Create or update a voice session.

Request body:
```json
{ "doctor_id": "xxx", "action": "start" | "stop" | "result", "text": "..." }
```

- `start` — web-view signals it wants recording to begin. Sets status to
  `pending_start`.
- `stop` — web-view signals recording should end. Sets status to `pending_stop`.
- `result` — miniapp posts the transcript after ASR completes. Sets status to
  `done` with `text`.

Returns:
```json
{ "session_id": "uuid", "status": "pending_start" | "pending_stop" | "done" }
```

#### `GET /api/voice/session?doctor_id=xxx`

Read current session state. Used by both miniapp (polling for commands) and
web-view (polling for results).

Returns:
```json
{
  "status": "idle" | "pending_start" | "recording" | "pending_stop" | "transcribing" | "done" | "error",
  "action": "start" | "stop" | null,
  "text": "transcribed text..." | null,
  "error": "error message" | null,
  "created_at": 1234567890
}
```

#### Session lifecycle

```
idle --> pending_start --> recording --> pending_stop --> transcribing --> done
  ^                                                                       |
  |_______________________________________________________________________|
  (auto-reset after web-view reads "done", or after 120s expiry)
```

#### Implementation

Simple Python dict in the FastAPI process. No database table — sessions are
ephemeral and single-process is fine for this use case (single doctor per
device). Add a cleanup sweep that removes sessions older than 120s.

```python
_voice_sessions: dict[str, dict] = {}
```

### 2. Backend — Transcribe Endpoint

**`POST /api/voice/transcribe`** already exists. Receives audio file, runs
Tencent 16k_zh_medical ASR, returns `{ transcript: "..." }`.

The miniapp calls this after stopping the recording, then posts the result back
to `/api/voice/session` with `action: "result"`.

### 3. Miniapp — Background Recorder (`doctor.js`)

Modify the existing `pages/doctor/doctor.js` (the web-view host page) to poll
the backend for voice commands.

#### Polling lifecycle

- `onShow()` — start a 500ms `setInterval` that calls
  `GET /api/voice/session?doctor_id=X`.
- `onHide()` — clear the interval. Stop any active recording.
- If polling response has `action: "start"` and not already recording, call
  `wx.getRecorderManager().start()` and POST `{ action: "recording" }` back to
  mark the session as active.
- If polling response has `action: "stop"` and currently recording, call
  `.stop()`. On stop callback, upload audio to `POST /api/voice/transcribe`,
  then POST the transcript to `POST /api/voice/session` with
  `{ action: "result", text }`.

#### Recorder config

Same as existing `add-rule` page:
```javascript
{ duration: 60000, sampleRate: 16000, numberOfChannels: 1,
  encodeBitRate: 96000, format: "mp3" }
```

#### Permission handling

On first `start` command, `wx.authorize({ scope: "scope.record" })`. If denied,
POST `{ action: "result", error: "permission_denied" }` to the session endpoint.

### 4. Web-view — `useVoiceRecording` Hook

```typescript
useVoiceRecording(doctorId: string) => {
  state: "idle" | "recording" | "transcribing" | "error",
  elapsed: number,        // seconds since recording started
  transcript: string,     // filled when done
  error: string | null,
  toggle: () => void,     // tap to start, tap again to stop
  clear: () => void,      // reset state
}
```

#### State machine

```
idle --[toggle]--> recording --[toggle]--> transcribing --[result]--> idle
                                                |
                                                +--> error --[clear]--> idle
```

- **toggle() in idle**: POST `/api/voice/session` with `action: "start"`. Start
  local elapsed timer. Set state to `recording`.
- **toggle() in recording**: POST `/api/voice/session` with `action: "stop"`.
  Set state to `transcribing`. Start polling `GET /api/voice/session` every
  500ms.
- **poll result**: When status is `done`, read `text`, set `transcript`, return
  to `idle`. When status is `error`, set error message, go to `error` state.
- **timeout**: If transcribing for > 15s (30 polls), set error "识别超时".

### 5. Web-view — `VoiceMicButton` Component

Reusable mic button used in two places:

- `AddKnowledgeSubpage` — replaces the "语音添加规则" navigation row
- Chat `InputBar` — replaces the keyboard mic hint banner

Visual states:
- **idle**: mic icon, muted color
- **recording**: pulsing red mic icon + elapsed seconds counter
- **transcribing**: spinner + "识别中..."
- **error**: brief toast, auto-reset to idle

Props:
```typescript
{ doctorId: string, onTranscript: (text: string) => void }
```

When transcript arrives, calls `onTranscript(text)` and the parent fills its
text input. Doctor can edit and submit normally.

Only rendered when `isInMiniapp()` returns true (voice recording requires the
miniapp bridge).

### 6. Web-view — `miniappBridge.js` Changes

- Add `isVoiceSupported()` — returns `isInMiniapp()`.
- Remove `openAddRuleVoice()` — no longer used.

## Integration Points

### AddKnowledgeSubpage

Replace the "语音添加规则" Box (lines 386-405) with:
```jsx
{isVoiceSupported() && (
  <VoiceMicButton doctorId={doctorId} onTranscript={(text) => {
    setContent((prev) => prev ? prev + "\n" + text : text);
    setSourceTab("text");
  }} />
)}
```

Transcript appends to the text input. If the user was on a different source tab,
switch to "手动输入" to show the filled text.

### Chat InputBar

Add `VoiceMicButton` next to the text input (where the keyboard mic hint
currently shows). On transcript, fill the chat input field. Remove the green
"点击键盘上此按钮语音输入" hint banner.

## What Gets Removed

- "语音添加规则" navigation row in AddKnowledgeSubpage
- `openAddRuleVoice()` from `miniappBridge.js`
- Green keyboard mic hint banner in chat InputBar (when in miniapp)
- The `pages/add-rule/` native page files stay in the repo but are no longer
  linked from the web-view

## Edge Cases

- **Doctor switches pages while recording**: `useVoiceRecording` cleanup sends
  stop on unmount. Miniapp `onHide` also stops recording.
- **Network failure during upload**: Miniapp posts `{ action: "result",
  error: "network" }`. Web-view shows toast.
- **Double-tap**: Toggle function is debounced — ignores taps within 500ms of
  the last one.
- **Session expiry**: Backend auto-clears sessions after 120s. Both sides treat
  missing sessions as idle.
- **Concurrent sessions**: One session per doctor. Starting a new session
  overwrites any existing one.
- **Audio too short** (< 1s): Miniapp ignores and posts error "录音太短".
- **Permission denied**: Miniapp posts error, web-view shows "需要录音权限".

## Testing

- **`useVoiceRecording` hook**: Unit tests with mocked fetch. Test all state
  transitions: idle→recording→transcribing→done, timeout, error paths.
- **Backend session endpoint**: Test CRUD operations, expiry, concurrent session
  override.
- **Manual real-device test**: 真机调试 on WeChat DevTools. Verify recording
  works, transcript fills input, both knowledge and chat pages.

## Not In Scope

- Real-time partial transcription (streaming ASR)
- Voice recording outside WeChat miniapp (browser `getUserMedia` unavailable in
  WeChat web-view)
- Deleting `pages/add-rule/` page files
- LLM extraction of rules from speech (doctor edits raw transcript manually)
