# Plan B: Chat-Driven Workflows

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ⊕ action panel, PDF import patient creation, daily summary, and voice input to the chat interface.

**Architecture:** Extend the existing ChatSection.jsx with new UI components (ActionPanel, VoiceInput) and leverage the existing backend pipeline (process_turn + extract-file) for PDF import. Daily summary is a frontend-only feature that triggers a chat message on first daily open.

**Tech Stack:** React 19, MUI v7, Capacitor v7 (camera/file plugins), Web Speech API

**Spec:** docs/ux/design-spec.md — "Screen 1: AI助手" section

---

## Feature 1: Action Panel (⊕)

A WeChat-style bottom sheet grid that appears when the user taps the ⊕ button. Four actions: 拍照, 相册, 文档, 患者档案.

### Task 1.1 — Create ActionPanel component

**Files to create:**
- `frontend/web/src/pages/doctor/ActionPanel.jsx`

**Files to modify:**
- `frontend/web/src/pages/doctor/ChatSection.jsx`

**Steps:**

- [ ] Create `ActionPanel.jsx` with a MUI `Slide` or `Box` overlay that renders a 4-column grid of action icons:

```jsx
const ACTIONS = [
  { key: "camera",  label: "拍照",     icon: <CameraAltOutlinedIcon />,       color: "#07C160" },
  { key: "gallery", label: "相册",     icon: <PhotoLibraryOutlinedIcon />,     color: "#5b9bd5" },
  { key: "file",    label: "文档",     icon: <DescriptionOutlinedIcon />,      color: "#e8833a" },
  { key: "patient", label: "患者档案", icon: <PersonSearchOutlinedIcon />,     color: "#9b59b6" },
];
```

- [ ] The panel uses a dark semi-transparent backdrop (`rgba(0,0,0,0.3)`) that dismisses on tap (WeChat convention).
- [ ] Each action is a 56x56 rounded-rect icon box with the action's `color` as background, white icon, and a label below. Grid layout: `display: "grid", gridTemplateColumns: "repeat(4, 1fr)"`, centered horizontally with 16px padding.
- [ ] Component API:

```jsx
export default function ActionPanel({ open, onClose, onAction })
// onAction receives the action key: "camera" | "gallery" | "file" | "patient"
```

- [ ] In `ChatSection.jsx`, add state `const [actionPanelOpen, setActionPanelOpen] = useState(false)`.
- [ ] In `MobileInputBar`, replace the existing `AttachFileOutlinedIcon` button (line 191) with an `AddCircleOutlineIcon` (⊕) that toggles `actionPanelOpen`. Import `AddCircleOutlineIcon` from `@mui/icons-material/AddCircleOutline`.
- [ ] For `DesktopInputBar`, keep the existing attach button but add a small MUI `Menu` dropdown with the same four actions (desktop users rarely use camera/voice).
- [ ] Render `<ActionPanel open={actionPanelOpen} onClose={() => setActionPanelOpen(false)} onAction={handlePanelAction} />` inside the `ChatSection` return block, just before the `<ClearDialog>`.

### Task 1.2 — Wire action handlers in ChatSection

**Files to modify:**
- `frontend/web/src/pages/doctor/ChatSection.jsx`
- `frontend/web/src/pages/doctor/FileUploader.jsx`

**Steps:**

- [ ] Add three additional hidden file inputs in `ChatSection` (alongside the existing `fileInputRef`):

```jsx
const cameraInputRef = useRef(null);
const galleryInputRef = useRef(null);
const fileDocInputRef = useRef(null);
```

```jsx
<input ref={cameraInputRef} type="file" accept="image/*" capture="environment"
  style={{ display: "none" }}
  onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, setMediaError, setMediaProcessing, setInput }); }} />
<input ref={galleryInputRef} type="file" accept="image/*"
  style={{ display: "none" }}
  onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, setMediaError, setMediaProcessing, setInput }); }} />
<input ref={fileDocInputRef} type="file" accept=".pdf,.doc,.docx,application/pdf"
  style={{ display: "none" }}
  onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; handleDocFile(f); }} />
```

- [ ] Add `handlePanelAction` function in `ChatSection`:

```jsx
function handlePanelAction(action) {
  setActionPanelOpen(false);
  switch (action) {
    case "camera":
      cameraInputRef.current?.click();
      break;
    case "gallery":
      galleryInputRef.current?.click();
      break;
    case "file":
      fileDocInputRef.current?.click();
      break;
    case "patient":
      setPatientPickerOpen(true);
      break;
  }
}
```

- [ ] Add `handleDocFile` — extracts text from PDF/Word via existing API, then opens the import choice dialog (Feature 2, Task 2.3). For now, just insert into input:

```jsx
async function handleDocFile(file) {
  if (!file) return;
  setMediaError(null);
  setMediaProcessing(true);
  try {
    const { text } = await extractFileForChat(file);
    if (text) {
      setImportChoice({ text }); // opens ImportChoiceDialog (Task 2.3)
    } else {
      setMediaError("未能从文件中提取文字");
    }
  } catch {
    setMediaError("文件处理失败，请重试");
  } finally {
    setMediaProcessing(false);
  }
}
```

- [ ] Import `extractFileForChat` from `../../api` at the top of `ChatSection.jsx`.
- [ ] Update `FileUploader.jsx` `processFile` to also handle PDF/Word files so the old attach-file input keeps working:

```jsx
import { ocrImage, extractFileForChat } from "../../api";

export async function processFile({ file, setMediaError, setMediaProcessing, setInput }) {
  if (!file) return;
  setMediaError(null);
  setMediaProcessing(true);
  try {
    if (file.type.startsWith("image/")) {
      const { text } = await ocrImage(file);
      if (text) setInput((prev) => (prev ? prev + "\n" + text : text));
    } else if (
      file.type === "application/pdf" ||
      file.name?.toLowerCase().endsWith(".pdf") ||
      file.type?.includes("word") ||
      file.name?.match(/\.docx?$/i)
    ) {
      const { text } = await extractFileForChat(file);
      if (text) setInput((prev) => (prev ? prev + "\n" + text : text));
    } else {
      setMediaError("不支持的文件类型，请上传图片或PDF文档");
    }
  } catch {
    setMediaError("文件处理失败，请重试");
  } finally {
    setMediaProcessing(false);
  }
}
```

### Task 1.3 — Patient picker dialog for "患者档案" action

**Files to create:**
- `frontend/web/src/pages/doctor/PatientPickerDialog.jsx`

**Files to modify:**
- `frontend/web/src/pages/doctor/ChatSection.jsx`

**Steps:**

- [ ] Create `PatientPickerDialog.jsx` — a MUI `Dialog` (fullScreen on mobile via `useMediaQuery`) with:
  - A search `TextField` at top, debounced (300ms), calls `searchPatients(doctorId, q)` from `../../api`.
  - A scrollable `List` of matching patients, each row showing name + gender + age.
  - On patient tap, call `onSelect({ id, name })` and close.
  - Empty state: "输入姓名搜索患者".
  - Loading state: `CircularProgress` centered.

- [ ] Component API:

```jsx
export default function PatientPickerDialog({ open, onClose, doctorId, onSelect })
// onSelect({ id, name }) — called when a patient row is tapped
```

- [ ] In `ChatSection.jsx`:
  - Add state `const [patientPickerOpen, setPatientPickerOpen] = useState(false)`.
  - Render `<PatientPickerDialog>` with `onSelect` wired to send a context message:

```jsx
<PatientPickerDialog
  open={patientPickerOpen}
  onClose={() => setPatientPickerOpen(false)}
  doctorId={doctorId}
  onSelect={(patient) => {
    setPatientPickerOpen(false);
    sendText(`关于患者${patient.name}`);
  }}
/>
```

**Verification:**
1. Tap ⊕ on mobile — panel slides up with 4 icons over dark backdrop.
2. Tap backdrop — panel dismisses.
3. Tap "拍照" — camera file picker opens (with `capture="environment"` on mobile).
4. Tap "相册" — gallery file picker opens for images.
5. Tap "文档" — file picker opens for PDF/Word; extracted text triggers import choice dialog.
6. Tap "患者档案" — patient picker dialog opens; selecting a patient sends "关于患者XXX" to chat.

**Commit:** `feat: add action panel with camera, gallery, file, patient picker`

---

## Feature 2: PDF Import → Patient Creation

User uploads a PDF in chat, AI parses the extracted text to create a patient record. Leverages the existing `extract-file` endpoint and the runtime's `create_patient` / `create_draft` action types.

### Task 2.1 — Create ImportChoiceDialog component

**Files to create:**
- `frontend/web/src/pages/doctor/ImportChoiceDialog.jsx`

**Files to modify:**
- `frontend/web/src/pages/doctor/ChatSection.jsx`

**Steps:**

- [ ] Create `ImportChoiceDialog.jsx`:

```jsx
import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from "@mui/material";

export default function ImportChoiceDialog({ open, text, onInsert, onImport, onClose }) {
  if (!text) return null;
  const preview = text.length > 200 ? text.slice(0, 200) + "..." : text;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: 16, fontWeight: 600 }}>已提取文字内容</DialogTitle>
      <DialogContent>
        <Box sx={{ p: 1.5, borderRadius: 1.5, bgcolor: "#f6f8fa", border: "1px solid #e0e0e0", mb: 1 }}>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontSize: 13, color: "#555", lineHeight: 1.8 }}>
            {preview}
          </Typography>
        </Box>
        <Typography variant="caption" color="text.secondary">
          共提取 {text.length} 字
        </Typography>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button variant="outlined" onClick={() => onInsert(text)} sx={{ borderRadius: 2 }}>
          放入输入框
        </Button>
        <Button variant="contained" onClick={() => onImport(text)}
          sx={{ borderRadius: 2, bgcolor: "#07C160", "&:hover": { bgcolor: "#06ad56" } }}>
          导入病历
        </Button>
      </DialogActions>
    </Dialog>
  );
}
```

- [ ] In `ChatSection.jsx`, add state:

```jsx
const [importChoice, setImportChoice] = useState(null); // { text: string } | null
```

- [ ] Render the dialog:

```jsx
<ImportChoiceDialog
  open={!!importChoice}
  text={importChoice?.text}
  onInsert={(text) => { setInput((prev) => prev ? prev + "\n" + text : text); setImportChoice(null); }}
  onImport={(text) => {
    sendText("导入这个患者的病历：\n" + text.slice(0, 4000));
    setImportChoice(null);
  }}
  onClose={() => setImportChoice(null)}
/>
```

- [ ] The `handleDocFile` function (from Task 1.2) already sets `setImportChoice({ text })` when extraction succeeds. Verify the wiring is correct.

### Task 2.2 — Ensure understand prompt handles PDF import intent

**Files to modify:**
- System prompt for understand (managed via `system_prompts` DB table, key `"understand"`) — only if needed

**Steps:**

- [ ] Review the current understand prompt (loaded via `get_prompt_sync("understand")` in `src/services/runtime/understand.py`). Test with a message like:

```
导入这个患者的病历：
姓名：陈梅  性别：女  年龄：62岁
诊断：2型糖尿病  高血压
入院日期：2026-03-10
...
```

- [ ] Verify the LLM classifies this as `create_patient` with `args: { patient_name: "陈梅", gender: "女", age: 62 }`.
- [ ] If classification is unreliable, add this guidance to the understand prompt:

```
当用户说"导入病历"或"导入患者"并附带长文本时：
- 如果文本包含患者姓名/性别/年龄等基本信息，提取这些字段，action_type 设为 "create_patient"
- 如果当前已有选中患者且文本主要是临床内容（主诉、诊断、用药等），action_type 设为 "create_draft"
```

- [ ] No new backend endpoints needed. The end-to-end flow:
  1. Frontend: `POST /api/records/extract-file` → get text
  2. Frontend: user taps "导入病历" → `POST /api/records/chat` with `"导入这个患者的病历：\n{text}"`
  3. Backend: `process_turn()` → `understand()` → `create_patient` or `create_draft`
  4. Backend: `commit_engine._create_patient()` or `_create_draft()` → returns result
  5. Frontend: displays confirmation card (existing `PendingConfirmCard` for drafts, or success message for patient creation)

**Verification:**
1. Tap ⊕ → 文档 → select a PDF containing patient info (e.g., discharge summary).
2. Import choice dialog appears showing extracted text preview.
3. Tap "导入病历" — chat sends "导入这个患者的病历：..." message.
4. AI responds with patient creation confirmation (e.g., "已为您创建患者陈梅").
5. Check patient list — new patient appears.
6. Tap "放入输入框" instead — text is inserted into the input field for manual editing before send.

**Commit:** `feat: PDF import patient creation flow via chat pipeline`

---

## Feature 3: Daily Summary on App Open

Frontend-only feature. On first open each day, auto-send a summary request to the AI. The AI responds with today's appointments, pending tasks, patients needing follow-up.

### Task 3.1 — Implement daily summary trigger

**Files to modify:**
- `frontend/web/src/pages/doctor/ChatSection.jsx`

**Steps:**

- [ ] Add a `useDailySummary` hook inside `ChatSection.jsx` (above the default export):

```jsx
function useDailySummary({ doctorId, sendText, messagesLoaded }) {
  const triggeredRef = useRef(false);

  useEffect(() => {
    if (!doctorId || !messagesLoaded || triggeredRef.current) return;

    const today = new Date().toISOString().slice(0, 10); // "2026-03-15"
    const key = `daily_summary_sent:${doctorId}`;
    const lastSent = localStorage.getItem(key);

    if (lastSent === today) return;

    triggeredRef.current = true;
    localStorage.setItem(key, today);

    // Delay so chat UI renders and welcome message is visible first
    const timer = setTimeout(() => {
      sendText("今日工作摘要");
    }, 1200);

    return () => clearTimeout(timer);
  }, [doctorId, messagesLoaded]); // eslint-disable-line react-hooks/exhaustive-deps
}
```

- [ ] The hook needs to know when messages have finished loading from localStorage. Add a `messagesLoaded` flag: in `useChatState`, track whether the initial `useEffect` that reads from `localStorage` has run. The simplest approach — pass `messages.length > 0` as `messagesLoaded` since the welcome message is always present after init.
- [ ] Call the hook in `ChatSection` body:

```jsx
useDailySummary({ doctorId, sendText, messagesLoaded: messages.length > 0 });
```

- [ ] The message "今日工作摘要" goes through `POST /api/records/chat` → `process_turn()`. The understand LLM handles this as either:
  - `action_type: "none"` with a `chat_reply` summarizing work (if the LLM has system prompt context about tasks/patients), or
  - A reasonable conversational response if no task/patient data is available.
- [ ] The daily gate is stored in `localStorage` as `daily_summary_sent:{doctorId}` = `"2026-03-15"`. Same-day refreshes skip the trigger.

### Task 3.2 — Verify summary handling in understand prompt

**Files to modify:**
- System prompt for understand (key `"understand"`) — only if needed

**Steps:**

- [ ] Test the understand prompt with the message "今日工作摘要". Verify it returns a reasonable `chat_reply` or dispatches to `query_records` / `list_patients`.
- [ ] If the AI produces a generic or unhelpful response, add this to the understand prompt:

```
当用户说"今日工作摘要"、"今日摘要"、"今天有什么工作"，返回 action_type "none"，
chat_reply 应包含：今日待复诊患者、待处理任务、近期需要关注的事项。
如果没有具体数据，给出鼓励性的工作开始提示。
```

- [ ] This is a prompt-level change only. No code changes in `understand.py` or `turn.py`.

### Task 3.3 — Add "今日摘要" to quick commands

**Files to modify:**
- `frontend/web/src/pages/doctor/constants.jsx`

**Steps:**

- [ ] In `constants.jsx`, add an entry to `QUICK_COMMANDS` after the "今日任务" entry (index 6):

```jsx
{ label: "今日摘要", icon: "📊", insert: "今日工作摘要" },
```

- [ ] The full array should now have the new entry between "今日任务" and "功能帮助":

```jsx
export const QUICK_COMMANDS = [
  { label: "新建患者", icon: "👤", insert: "新建患者：" },
  { label: "查询患者", icon: "🔍", insert: "查询患者：" },
  { label: "患者列表", icon: "📋", insert: "患者列表" },
  { label: "补充记录", icon: "➕", insert: "补充记录：" },
  { label: "修正上条", icon: "✏️", insert: "刚才写错了，应该是" },
  { label: "导出PDF", icon: "📄", insert: "导出病历PDF：" },
  { label: "今日任务", icon: "📌", insert: "今日任务" },
  { label: "今日摘要", icon: "📊", insert: "今日工作摘要" },   // NEW
  { label: "功能帮助", icon: "💡", insert: "帮助" },
];
```

- [ ] Note: "今日摘要" uses `insert:` (no trailing colon), so tapping it auto-sends via `onAutoSend` in `QuickCommandChips`.

**Verification:**
1. Clear `daily_summary_sent:{doctorId}` from localStorage (DevTools → Application → Local Storage).
2. Refresh the app — after the welcome message renders, "今日工作摘要" auto-sends after ~1.2s delay.
3. AI responds with a summary (content depends on existing data for this doctor).
4. Refresh again — no duplicate summary (localStorage gate blocks re-trigger).
5. Tap "今日摘要" quick command chip — manually sends the same summary request.
6. Next calendar day — summary triggers again automatically.

**Commit:** `feat: daily summary auto-trigger on first app open each day`

---

## Feature 4: Voice Input Toggle

Mic icon toggles between text input and "按住说话" (press-to-talk) button. Uses Web Speech API for browser, with a hook point for Capacitor speech-to-text in future native builds.

### Task 4.1 — Create VoiceInput component

**Files to create:**
- `frontend/web/src/pages/doctor/VoiceInput.jsx`

**Steps:**

- [ ] Create `VoiceInput.jsx`. The component renders a full-width "按住说话" button that replaces the text input when voice mode is active.

```jsx
import { useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";

// Feature-detect Web Speech API
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
    recognition.onerror = () => {
      stopTimer();
      setRecording(false);
      onCancel();
    };
    recognition.onend = () => {
      stopTimer();
      setRecording(false);
    };

    recognition.start();
    recognitionRef.current = recognition;

    timerRef.current = setInterval(() => {
      setSeconds((s) => s + 1);
    }, 1000);
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
      // onresult / onend will fire and handle the rest
    }
  }

  function handleMove(clientY) {
    if (!recording) return;
    const delta = startYRef.current - clientY;
    setCancelled(delta > 80);
  }

  const formatTime = (s) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  };

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
        height: 40, borderRadius: "20px", cursor: "pointer", userSelect: "none",
        bgcolor: recording ? (cancelled ? "#FA5151" : "#07C160") : "#fff",
        border: recording ? "none" : "1px solid #ddd",
        transition: "background-color 0.15s",
        ...(recording && !cancelled && {
          animation: "voicePulse 1.4s ease-in-out infinite",
          "@keyframes voicePulse": {
            "0%":   { boxShadow: "0 0 0 0 rgba(7,193,96,0.4)" },
            "70%":  { boxShadow: "0 0 0 12px rgba(7,193,96,0)" },
            "100%": { boxShadow: "0 0 0 0 rgba(7,193,96,0)" },
          },
        }),
      }}
    >
      <MicIcon sx={{
        fontSize: 18, mr: 0.5,
        color: recording ? "#fff" : "#999",
      }} />
      <Typography variant="body2" sx={{
        fontSize: 14,
        color: recording ? "#fff" : "#999",
        fontWeight: recording ? 600 : 400,
      }}>
        {recording
          ? (cancelled ? "松开取消" : `松开发送 ${formatTime(seconds)}`)
          : "按住说话"}
      </Typography>
    </Box>
  );
}
```

- [ ] Export `isVoiceSupported()` so the parent can conditionally show the mic toggle.
- [ ] The press-and-hold UX works via touch events (mobile) and mouse events (desktop fallback).
- [ ] Drag-up-to-cancel: if touch moves 80+ px upward from start position, button turns red and shows "松开取消". Releasing in this state calls `onCancel()` instead of `onResult()`.

### Task 4.2 — Integrate VoiceInput into ChatSection input bar

**Files to modify:**
- `frontend/web/src/pages/doctor/ChatSection.jsx`

**Steps:**

- [ ] Import the new component at the top of `ChatSection.jsx`:

```jsx
import VoiceInput, { isVoiceSupported } from "./VoiceInput";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import KeyboardOutlinedIcon from "@mui/icons-material/KeyboardOutlined";
```

- [ ] Add state in `ChatSection`:

```jsx
const [voiceMode, setVoiceMode] = useState(false);
const voiceSupported = isVoiceSupported();
```

- [ ] Pass `voiceMode`, `setVoiceMode`, and `voiceSupported` into `MobileInputBar` via `sharedBarProps`:

```jsx
const sharedBarProps = {
  // ... existing props ...
  voiceMode, setVoiceMode, voiceSupported,
  onVoiceResult: (text) => { setVoiceMode(false); sendText(text); },
};
```

- [ ] Modify `MobileInputBar` to add the mic toggle and swap input modes. The updated input row layout:

```
[ MicToggle ] [ VoiceInput OR TextField ] [ ⊕ Button ] [ SendButton (hidden in voice mode) ]
```

```jsx
function MobileInputBar({ ..., voiceMode, setVoiceMode, voiceSupported, onVoiceResult, ... }) {
  return (
    <Box sx={{ borderTop: "1px solid #d9d9d9", backgroundColor: "#f5f5f5" }}>
      {/* ... failedText, mediaError, isProcessing banners unchanged ... */}
      <Stack direction="row" alignItems="center" sx={{ px: 1, py: 0.8, gap: 0.5 }}>
        {voiceSupported && (
          <IconButton size="small" onClick={() => setVoiceMode(!voiceMode)}
            sx={{ color: voiceMode ? "#07C160" : "#666", p: 1.1 }}>
            {voiceMode ? <KeyboardOutlinedIcon /> : <MicNoneOutlinedIcon />}
          </IconButton>
        )}
        {voiceMode ? (
          <VoiceInput
            onResult={onVoiceResult}
            onCancel={() => {}}
          />
        ) : (
          <TextField multiline minRows={1} maxRows={4} fullWidth size="small"
            placeholder={t("chat.placeholder")} value={input}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
            disabled={isProcessing}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: "20px", backgroundColor: "#fff", fontSize: "0.9rem", "& fieldset": { borderColor: "#ddd" } } }} />
        )}
        <IconButton size="small" onClick={onFileClick} disabled={isProcessing} sx={{ color: "#666", p: 1.1 }}>
          <AddCircleOutlineIcon />
        </IconButton>
        {!voiceMode && (
          <IconButton onClick={onSend} disabled={loading || !input.trim()}
            sx={{ bgcolor: "#07C160", color: "#fff", p: 1.2, borderRadius: "50%", "&:hover": { bgcolor: "#06ad56" }, flexShrink: 0, minWidth: 44, minHeight: 44 }}>
            <SendOutlinedIcon fontSize="small" />
          </IconButton>
        )}
      </Stack>
    </Box>
  );
}
```

- [ ] For `DesktopInputBar`, add a mic icon button next to the send button. On click, start Web Speech API in "listen until silence" mode (not press-and-hold), transcribe, and insert text into the `TextField` for review before sending:

```jsx
{voiceSupported && (
  <Tooltip title="语音输入">
    <span>
      <IconButton size="small" onClick={handleDesktopVoice}
        disabled={isProcessing} sx={{ color: "text.secondary" }}>
        <MicNoneOutlinedIcon fontSize="small" />
      </IconButton>
    </span>
  </Tooltip>
)}
```

- [ ] `handleDesktopVoice` creates a one-shot `SpeechRecognition` instance, listens, and on result inserts text into `input` state (does NOT auto-send — desktop users prefer to review).

### Task 4.3 — Voice recording visual feedback polish

**Files to modify:**
- `frontend/web/src/pages/doctor/VoiceInput.jsx`

**Steps:**

- [ ] Add animated waveform bars inside the button during recording (3 vertical bars with staggered bounce animation):

```jsx
{recording && !cancelled && (
  <Box sx={{ display: "flex", alignItems: "center", gap: "3px", ml: 1 }}>
    {[0, 1, 2].map((i) => (
      <Box key={i} sx={{
        width: 3, height: 14, borderRadius: 1.5, bgcolor: "#fff",
        animation: "waveBar 0.8s ease-in-out infinite",
        animationDelay: `${i * 0.15}s`,
        "@keyframes waveBar": {
          "0%, 100%": { transform: "scaleY(0.4)" },
          "50%": { transform: "scaleY(1)" },
        },
      }} />
    ))}
  </Box>
)}
```

- [ ] When in cancel zone, the waveform bars are hidden and replaced by an "X" icon.
- [ ] Ensure the recording timer `mm:ss` is visible and legible against both the green (recording) and red (cancel) backgrounds.

**Verification:**
1. Tap mic icon in mobile input bar — text field is replaced by "按住说话" button; mic icon changes to keyboard icon.
2. Tap keyboard icon — switches back to normal text input.
3. Press and hold "按住说话" — button turns green, pulse animation plays, timer counts up, waveform bars animate.
4. Release — Web Speech API transcribes, transcribed text is auto-sent as a chat message, input bar reverts to text mode.
5. Press and hold, drag finger upward 80+ px — button turns red, shows "松开取消". Release — nothing is sent.
6. On desktop, click mic button — browser asks for microphone permission, listens for speech, inserts transcribed text into the text field (does not auto-send).
7. On a browser without Web Speech API support — mic button is not rendered (graceful degradation via `isVoiceSupported()`).

**Commit:** `feat: voice input toggle with press-to-talk and Web Speech API`

---

## Implementation Order and Dependencies

```
Feature 3 (Daily Summary)  — no dependencies, smallest scope
Feature 1 (Action Panel)   — no dependencies, foundation for Feature 2
Feature 2 (PDF Import)     — depends on Feature 1 Task 1.2 (file action handler + handleDocFile)
Feature 4 (Voice Input)    — no dependencies, can parallel with others
```

**Recommended execution sequence:**
1. **Feature 3** (Daily Summary) — 3 small tasks, quick win, can ship independently.
2. **Feature 1** (Action Panel) — builds the ⊕ foundation that Feature 2 relies on.
3. **Feature 2** (PDF Import) — uses the file handler from Feature 1.
4. **Feature 4** (Voice Input) — most complex UI component, fully independent.

---

## Files Summary

### New files (4)

| File | Purpose |
|------|---------|
| `frontend/web/src/pages/doctor/ActionPanel.jsx` | WeChat-style ⊕ bottom sheet with 4 action icons |
| `frontend/web/src/pages/doctor/PatientPickerDialog.jsx` | Search and select patient dialog for "患者档案" action |
| `frontend/web/src/pages/doctor/ImportChoiceDialog.jsx` | Choice dialog after PDF extraction: insert vs. import as patient |
| `frontend/web/src/pages/doctor/VoiceInput.jsx` | Press-to-talk recording component with Web Speech API |

### Modified files (3)

| File | Changes |
|------|---------|
| `frontend/web/src/pages/doctor/ChatSection.jsx` | ⊕ button replacing attach icon, `handlePanelAction`, voice mode toggle, `useDailySummary` hook, import choice state, patient picker state, three new file input refs |
| `frontend/web/src/pages/doctor/FileUploader.jsx` | Add PDF/Word handling via `extractFileForChat` alongside existing image OCR |
| `frontend/web/src/pages/doctor/constants.jsx` | Add "今日摘要" entry to `QUICK_COMMANDS` |

### Backend: no code changes required

All four features work through existing endpoints:
- `POST /api/records/chat` — chat pipeline (`process_turn`)
- `POST /api/records/extract-file` — PDF/Word text extraction (in `src/channels/web/chat.py`)
- `POST /api/records/ocr` — image OCR
- `GET /api/manage/patients/search` — patient search for picker

The only backend change is a potential prompt update to the `understand` system prompt (stored in DB, key `"understand"`) to improve PDF import intent classification. This is a data change, not a code change.

---

## Risks / Open Questions

1. **Web Speech API browser support** — Not available in all browsers (Firefox on some platforms, some WebView configurations). Mitigation: `isVoiceSupported()` feature detection hides the mic button entirely when unsupported. No broken UX.

2. **Capacitor native plugins** — The plan uses web-standard `<input type="file">` with `capture` attribute as a fallback for camera/gallery. Full native camera integration via `@capacitor/camera` and native speech via `@capacitor-community/speech-recognition` are deferred to the native build phase. The web fallback is functional on mobile browsers.

3. **PDF text extraction quality** — The existing `extract_text_from_pdf_smart` handles standard PDFs well but may produce poor results for scanned PDFs (image-only pages). The vision OCR pipeline could be chained as a fallback, but this is out of scope for this plan.

4. **Understand prompt accuracy for PDF imports** — The LLM may not reliably extract patient demographics from all PDF formats. The instruction prefix "导入这个患者的病历" provides strong context. If accuracy is poor in practice, a dedicated two-step extraction (first extract demographics with a specialized prompt, then create patient) could be added in a follow-up iteration.

5. **Daily summary content quality** — Depends on the LLM having enough context about today's tasks and patients. For doctors with no data yet, the summary will be generic. Acceptable for MVP; a future iteration could implement a deterministic fast path in `turn.py` that queries tasks/patients directly and formats a summary without an LLM call.

6. **Voice accuracy in noisy environments** — Web Speech API accuracy degrades in clinical settings with ambient noise. For higher accuracy, the backend's Whisper-based transcription (`POST /api/voice/chat`) could be used instead, at the cost of a network round-trip during recording. This optimization is deferred.

7. **Mobile input bar layout complexity** — Adding mic toggle + voice button + ⊕ button + send button in a single row on small screens may feel cramped. Test on 320px-width devices (iPhone SE) and adjust icon sizes / spacing if needed.
