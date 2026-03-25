# Web Frontend Simplification — Implementation Plan

> **Status: ✅ DONE** — implementation complete, merged to main.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development
> (if subagents available) or superpowers:executing-plans to implement this plan.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dead code, split bloated files, fix quick commands UX, and
unify draft confirmation to a single point — making the web frontend simpler
and more WeChat-like.

**Architecture:** Approach C — streamlined chat-first. Delete duplicate pages
(ChatPage, ManagePage, manage/ panels, HomeSection). Split api.js into
domain files with barrel re-export. Extract ChatSection sub-components. Remove
polling loops. Make quick commands always visible.

**Tech Stack:** React 19, MUI 7, Zustand 5, Vite 6

**Spec:** `docs/specs/archived/2026-03-15-web-frontend-simplification-design.md`

**Working directory:** `frontend/web/src/` (all paths below are relative to this)

**No tests** — per AGENTS.md temporary testing policy.

---

## Task 1: Delete dead pages and manage panels

**Files:**
- Delete: `pages/ChatPage.jsx`
- Delete: `pages/ManagePage.jsx`
- Delete: `pages/doctor/HomeSection.jsx`
- Delete: `components/manage/PatientPanel.jsx`
- Delete: `components/manage/TaskPanel.jsx`
- Delete: `components/manage/RecordPanel.jsx`
- Delete: `components/manage/LabelPanel.jsx`
- Delete: `components/manage/PromptPanel.jsx`
- Modify: `App.jsx` — remove `/manage` route and ChatPage/ManagePage imports

- [ ] **Step 1: Delete the 8 dead files**

```bash
rm pages/ChatPage.jsx \
   pages/ManagePage.jsx \
   pages/doctor/HomeSection.jsx \
   components/manage/PatientPanel.jsx \
   components/manage/TaskPanel.jsx \
   components/manage/RecordPanel.jsx \
   components/manage/LabelPanel.jsx \
   components/manage/PromptPanel.jsx
rmdir components/manage
```

- [ ] **Step 2: Clean up App.jsx**

Remove the ManagePage import (line 7 area — it's no longer imported since
the `/manage` route already uses `<Navigate>`). No ChatPage import exists
in App.jsx (it was never routed there). Remove the `/manage` redirect route
since the target pages are gone. The catch-all `*` redirect to `/` handles
stale bookmarks.

In `App.jsx`, delete this line:
```jsx
<Route path="/manage" element={<Navigate to="/doctor" replace />} />
```

- [ ] **Step 3: Verify no broken imports remain**

```bash
grep -r "ChatPage\|ManagePage\|HomeSection\|PatientPanel\|TaskPanel\|RecordPanel\|LabelPanel\|PromptPanel" --include="*.jsx" --include="*.js" .
```

Fix any remaining references. Expected: zero matches.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(web): delete dead pages — ChatPage, ManagePage, HomeSection, manage/ panels"
```

---

## Task 2: Split api.js into domain files

**Files:**
- Create: `api/base.js`
- Create: `api/doctor.js`
- Create: `api/admin.js`
- Create: `api/debug.js`
- Create: `api/patient.js`
- Modify: `api.js` → barrel re-export file

- [ ] **Step 1: Create `api/base.js`**

Extract from `api.js` lines 1-104:
- `_API_BASE`, `apiUrl()`, `readError()`
- `_webToken`, `setWebToken()`, `_getToken()`, `request()`
- `_adminToken`, `setAdminToken()`, `onAdminAuthError()`, `adminRequest()`
- `_debugToken`, `setDebugToken()`, `onDebugAuthError()`, `debugRequest()`

Export all public functions. `request`, `adminRequest`, `debugRequest` must
be named exports so domain files can import them.

- [ ] **Step 2: Create `api/doctor.js`**

Import `request` from `./base`. Move these functions from `api.js`:
- `inviteLogin` (line 106)
- `sendChat` (134), `transcribeAudio` (143), `ocrImage` (149), `extractFileForChat` (155)
- `getPatients` (161), `searchPatients` (168), `deletePatient`
- `exportPatientPdf` (173), `exportOutpatientReport` (191)
- `getTemplateStatus`, `uploadTemplate`, `deleteTemplate`
- `getRecords`, `updateRecord`, `deleteRecord`, `getRecordHistory`
- `getTasks`, `patchTask`, `postponeTask`, `createTask`
- `getLabels`, `createLabel`, `deleteLabel`, `assignLabelToPatient`, `removeLabelFromPatient`
- `getDoctorProfile`, `updateDoctorProfile`
- `getWorkingContext`
- `getPendingRecord`, `confirmPendingRecord`, `abandonPendingRecord`
- `confirmPendingRecordById`, `abandonPendingRecordById`
- `getPrompts`, `savePrompts`

Note: `exportPatientPdf` and `exportOutpatientReport` use `_webToken` and
`apiUrl` directly — import these from `./base` (they need to be exported
from base or accessed via a getter).

- [ ] **Step 3: Create `api/admin.js`**

Import `adminRequest` from `./base`. Move:
- `getAdminInviteCodes`, `createAdminInviteCode`, `revokeAdminInviteCode`
- `adminGetTableRows`, `adminGetRowCount`, `adminDeleteRow`, `adminUpdateRow`
- `adminGetConfig`, `adminUpdateConfig`
- `adminGetRoutingKeywords`, `adminAddRoutingKeyword`, `adminDeleteRoutingKeyword`
- `adminExportTableCsv`
- Any other `adminRequest`-based functions

- [ ] **Step 4: Create `api/debug.js`**

Import `debugRequest` from `./base`. Move:
- `debugGetLogs`, `debugGetObservability`, `debugGetRoutingMetrics`
- `debugResetRoutingMetrics`
- Any other `debugRequest`-based functions

- [ ] **Step 5: Create `api/patient.js`**

Import `patientRequest` from `./base`. Move patient portal functions:
- `setPatientToken`, `patientSession`, `getPatientMe`
- `getPatientRecords`, `sendPatientMessage`, `getPatientMessages`

Note: the `patientRequest` helper and `_patientToken` state must also
move — either keep in base.js or co-locate in patient.js. Prefer base.js
for consistency with admin/debug patterns.

- [ ] **Step 6: Replace api.js with barrel re-export**

Replace entire content of `api.js` with:
```javascript
export * from "./api/base";
export * from "./api/doctor";
export * from "./api/admin";
export * from "./api/debug";
export * from "./api/patient";
```

- [ ] **Step 7: Verify no broken imports**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web
npx vite build 2>&1 | head -30
```

Fix any import errors. All existing `import { X } from "../api"` or
`import { X } from "../../api"` should work via the barrel file.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "refactor(web): split api.js into domain files — base, doctor, admin, debug, patient"
```

---

## Task 3: Extract ChatSection sub-components

**Files:**
- Create: `pages/doctor/VoiceRecorder.jsx`
- Create: `pages/doctor/FileUploader.jsx`
- Create: `pages/doctor/ViewPayloadCard.jsx`
- Modify: `pages/doctor/ChatSection.jsx`

- [ ] **Step 1: Create `ViewPayloadCard.jsx`**

Move the `ViewPayloadCard` function (currently at lines 70-126 of
ChatSection.jsx) into its own file. It has no state — pure render from
`payload` prop. Import `Typography, Box` from MUI.

```jsx
// pages/doctor/ViewPayloadCard.jsx
import { Box, Typography } from "@mui/material";

export default function ViewPayloadCard({ payload }) {
  // ... existing implementation
}
```

- [ ] **Step 2: Create `VoiceRecorder.jsx`**

Extract the voice recording logic from ChatSection. This includes:
- `recordingActive` state, `mediaStreamRef`, `mediaRecorderRef`
- `startRecording()`, `stopRecording()` functions
- The mic/stop button JSX

Props: `onTranscribed(text)` — callback when transcription succeeds,
`disabled` — when loading.

- [ ] **Step 3: Create `FileUploader.jsx`**

Extract the file upload logic:
- `fileInputRef`
- `handleFileSelect()` function that calls `ocrImage()`
- The attach button JSX + hidden file input

Props: `onFileText(text)` — callback with extracted text,
`disabled` — when loading.

- [ ] **Step 4: Update ChatSection.jsx**

Replace inline voice/file/ViewPayload code with imports:
```jsx
import VoiceRecorder from "./VoiceRecorder";
import FileUploader from "./FileUploader";
import ViewPayloadCard from "./ViewPayloadCard";
```

Wire callbacks:
- `<VoiceRecorder onTranscribed={(t) => setInput(prev => prev + t)} disabled={loading} />`
- `<FileUploader onFileText={(t) => setInput(prev => prev + t)} disabled={loading} />`
- In MsgBubble: `<ViewPayloadCard payload={msg.view_payload} />`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(web): extract VoiceRecorder, FileUploader, ViewPayloadCard from ChatSection"
```

---

## Task 4: Remove duplicate draft confirmation and polling

**Files:**
- Modify: `pages/DoctorPage.jsx`

- [ ] **Step 1: Remove PendingRecordBanner**

In `DoctorPage.jsx`, delete:
- The `PendingRecordBanner` component definition (lines 33-70 area)
- The `pendingRecord` state variable
- The `getPendingRecord` 30-second polling `useEffect`
- The `<PendingRecordBanner>` JSX in the render
- Any imports used only by the banner (`getPendingRecord` from api)
- Related props passing (`onConfirm`, `onAbandon` for the banner)

- [ ] **Step 2: Remove working-context polling**

In `DoctorPage.jsx`, delete:
- The `workingContext` state variable
- The `getWorkingContext` 15-second polling `useEffect`

Replace with:
- `const [currentPatient, setCurrentPatient] = useState(null);`
- Single `useEffect` on mount that calls `getWorkingContext()` once to
  initialise `currentPatient`
- Pass `onContextUpdate` callback to ChatSection:
  ```jsx
  <ChatSection
    doctorId={doctorId}
    onContextUpdate={({ patientName }) => setCurrentPatient(patientName)}
    ...
  />
  ```

- [ ] **Step 3: Update WorkingContextHeader**

Modify to accept `currentPatient` as a prop instead of reading from
`workingContext`:
```jsx
<WorkingContextHeader currentPatient={currentPatient} />
```

Update `WorkingContextHeader.jsx` to use the prop.

- [ ] **Step 4: Wire onContextUpdate in ChatSection**

In ChatSection's `performSend`, after receiving chat response, call:
```javascript
if (onContextUpdate) {
  onContextUpdate({
    patientName: data.pending_patient_name || data.switch_notification?.match(/【(.+?)】/)?.[1],
  });
}
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "fix(web): single draft confirmation point, remove polling loops"
```

---

## Task 5: Quick commands always visible

**Files:**
- Modify: `pages/doctor/ChatSection.jsx`

- [ ] **Step 1: Replace QuickCommandsPanel**

Find the existing `QuickCommandsPanel` component and its toggle state in
ChatSection.jsx. Delete:
- The toggle button (`KeyboardArrowUp/Down` icon button)
- The `showCommands` state
- The `QuickCommandsPanel` component or its collapsed/expanded rendering

Replace with a simple horizontal chip row rendered directly above the input:

```jsx
import { QUICK_COMMANDS } from "./constants";

// Inside the chat input area, above the TextField:
<Box sx={{
  display: "flex", gap: 0.8, px: 1.5, py: 0.8,
  overflowX: "auto", whiteSpace: "nowrap",
  "&::-webkit-scrollbar": { display: "none" },
}}>
  {QUICK_COMMANDS.map((cmd) => (
    <Box
      key={cmd.label}
      onClick={() => {
        if (cmd.insert.endsWith("：") || cmd.insert.endsWith("，")) {
          setInput(cmd.insert);
          // focus the input
        } else {
          performSend({ text: cmd.insert, /* ...other args */ });
        }
      }}
      sx={{
        px: 1.5, py: 0.5, borderRadius: "16px", cursor: "pointer",
        fontSize: 13, flexShrink: 0, userSelect: "none",
        bgcolor: "#f0f0f0", color: "#333",
        "&:hover": { bgcolor: "#e0e0e0" },
        "&:active": { bgcolor: "#d5d5d5" },
      }}
    >
      {cmd.icon} {cmd.label}
    </Box>
  ))}
</Box>
```

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "feat(web): always-visible quick command chips above chat input"
```

---

## Task 6: WeChat-style UI polish

**Files:**
- Modify: `pages/doctor/ChatSection.jsx`

- [ ] **Step 1: Update chat container background**

Find the outermost Box wrapping the message list. Set:
```jsx
bgcolor: "#ededed"  // WeChat grey
```

- [ ] **Step 2: Update input bar styling**

Find the input bar container. Set:
```jsx
bgcolor: "#f7f7f7"
borderTop: "1px solid #ddd"
```

- [ ] **Step 3: Verify existing elements**

These should already be correct (no changes needed):
- Send button: `#07C160` green circle
- User bubbles: green background
- Assistant bubbles: white background
- Timestamps: subtle grey

If any differ, adjust to match.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "style(web): WeChat-style chat background and input bar"
```

---

## Task 7: Route cleanup in App.jsx

**Files:**
- Modify: `App.jsx`

- [ ] **Step 1: Remove stale imports and routes**

After Task 1 already removed ManagePage, verify App.jsx has no dead imports.
The `/manage` route should already be gone from Task 1. Verify the final
routes match the spec:

```
/login          → LoginPage
/               → redirect to /doctor
/doctor         → DoctorPage (RequireAuth)
/doctor/:section → DoctorPage with section nav
/doctor/patients/:patientId → DoctorPage with patient detail
/admin/login    → AdminLoginPage
/admin          → AdminPage
/admin/:section → AdminPage
/debug          → DebugPage
/debug/:section → DebugPage
/patient        → PatientPage
*               → redirect to /
```

- [ ] **Step 2: Commit (if any changes needed)**

```bash
git add -A && git commit -m "chore(web): clean up routes"
```

---

## Task 8: Final verification

- [ ] **Step 1: Build check**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web
npx vite build 2>&1 | tail -5
```

Expected: build succeeds with no errors.

- [ ] **Step 2: Grep for dead references**

```bash
grep -r "ManagePage\|ChatPage\|HomeSection\|PatientPanel\|TaskPanel\|RecordPanel\|LabelPanel\|PromptPanel\|QuickCommandsPanel" --include="*.jsx" --include="*.js" src/
```

Expected: zero matches.

- [ ] **Step 3: Commit spec + plan**

```bash
git add docs/plans/ docs/specs/ && git commit -m "docs: web frontend simplification spec and plan"
```
