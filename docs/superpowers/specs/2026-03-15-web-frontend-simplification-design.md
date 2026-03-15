# Web Frontend Simplification

## Context

The web frontend has duplicated surfaces (ChatPage + ChatSection, ManagePage +
DoctorPage sections, two draft confirmation points), a bloated single-file API
layer (642 lines, 150+ exports), and hidden quick commands. This spec
streamlines the doctor-facing web app without changing the chat-first
architecture.

## Scope

Approach C from brainstorming: cleanup + targeted UX fixes. No page structure
redesign. Admin and debug pages are untouched except for API file split.

## 1. Delete Dead Code

Remove files that duplicate functionality already in DoctorPage:

| File | Lines | Replaced by |
|------|-------|-------------|
| `pages/ChatPage.jsx` | 253 | `pages/doctor/ChatSection.jsx` |
| `pages/ManagePage.jsx` | 407 | DoctorPage sections |
| `pages/doctor/HomeSection.jsx` | 260 | Dead — not wired in nav |
| `components/manage/PatientPanel.jsx` | 186 | `pages/doctor/PatientsSection.jsx` |
| `components/manage/TaskPanel.jsx` | 373 | `pages/doctor/TasksSection.jsx` |
| `components/manage/RecordPanel.jsx` | 281 | `pages/doctor/PatientsSection.jsx` |
| `components/manage/LabelPanel.jsx` | 138 | `pages/doctor/PatientsSection.jsx` |
| `components/manage/PromptPanel.jsx` | 52 | `pages/doctor/SettingsSection.jsx` |

Remove routes:
- `/manage` route from `App.jsx`
- Any standalone `/chat` route if present

Delete the empty `components/manage/` directory after removing files.

## 2. Split api.js into Domain Files

Current: single `api.js` (642 lines) with all exports.

Target structure:

```
src/api/
  base.js        — request(), token management, error handling (~80 lines)
  doctor.js      — chat, patients, records, tasks, labels, profile, templates, inviteLogin (~250 lines)
  admin.js       — admin tables, config, invite codes, routing keywords (~150 lines)
  debug.js       — logs, observability, metrics (~100 lines)
  patient.js     — patient portal session, records, messages (~60 lines)
```

`base.js` exports:
- `request(url, opts)` — shared fetch wrapper with timeout + error handling
- `setWebToken(token)` / `_getToken()` — doctor auth
- `adminRequest(url, opts)` / `setAdminToken(token)` / `onAdminAuthError(cb)`
- `debugRequest(url, opts)` / `setDebugToken(token)` / `onDebugAuthError(cb)`
- `patientRequest(url, opts)` — patient portal auth

`inviteLogin()` goes in `doctor.js` — it uses base `request()` and is called
from `LoginPage` which is part of the doctor auth flow.

Old `api.js` becomes a re-export barrel file for backward compatibility:
```javascript
export * from "./api/base";
export * from "./api/doctor";
export * from "./api/admin";
export * from "./api/debug";
export * from "./api/patient";
```

This avoids breaking existing imports across all pages while enabling
tree-shaking in the future. The barrel must include `base.js` because
`App.jsx`, `LoginPage.jsx`, `AdminPage.jsx`, `AdminLoginPage.jsx`, and
`DebugPage.jsx` all import token setters and auth error handlers from the
top-level `api` path.

## 3. Split ChatSection.jsx

Current ChatSection (~535 lines) handles chat, voice, file upload, view
payload rendering, quick commands, and pending draft management.

Extract into focused components:

| New file | Responsibility | Approximate lines |
|----------|---------------|-------------------|
| `ChatSection.jsx` | Message list, input bar, quick command chips, send logic | ~280 |
| `VoiceRecorder.jsx` | Mic button, MediaRecorder, audio blob → `transcribeAudio()` | ~80 |
| `FileUploader.jsx` | Attach button, file input ref, image → `ocrImage()` | ~50 |
| `ViewPayloadCard.jsx` | Render records_list, patients_list, task_created cards | ~70 |

ChatSection imports and composes the extracted components. Each component
receives callbacks as props (e.g., `onTranscribed(text)` inserts into input,
`onFileText(text)` inserts into input).

`PendingConfirmCard` stays in ChatSection (small, tightly coupled to message
rendering).

Note: `extractFileForChat()` is used by `PatientsSection.jsx` for PDF import,
not by ChatSection. FileUploader here handles only in-chat image OCR.

## 4. Remove Duplicate Draft Confirmation

**Delete from DoctorPage.jsx:**
- `PendingRecordBanner` component (lines 33-70)
- `pendingRecord` state
- `getPendingRecord` 30-second polling useEffect (lines 182-186)
- All props/callbacks passing pending state to the banner

**Keep:**
- `PendingConfirmCard` inside chat message bubbles (single confirmation point)
- Confirm/abandon API calls from within chat bubble callbacks

The chat bubble card shows patient name, expiry countdown, and
confirm/abandon buttons. This is the only place the doctor confirms drafts
on web.

## 5. Remove Working-Context Polling

**Delete from DoctorPage.jsx:**
- `getWorkingContext` 15-second polling useEffect
- `workingContext` state

**Replace with:**
- DoctorPage maintains `currentPatient` state, initialised from a single
  `getWorkingContext()` call on mount (the API function stays in `doctor.js`).
- ChatSection receives an `onContextUpdate({ patientName, pendingPatientName })`
  callback. After each `sendChat()` response, ChatSection calls it with the
  patient info from the response (`switch_notification`, `pending_patient_name`).
- `WorkingContextHeader` reads `currentPatient` from DoctorPage props. No
  polling — updated reactively from chat responses.

## 6. Quick Commands Always Visible

**Delete:**
- `QuickCommandsPanel` collapsible component
- Toggle button + expanded/collapsed state

**Replace with:**
- Horizontal row of colored chips rendered directly above the chat input
- Always visible, no toggle
- Commands that end with a colon (e.g., `"新建患者："`) → **insert into input**
  so the doctor can append a name. Commands without a colon → **auto-send**.
- On mobile: horizontally scrollable row

Keep the existing `QUICK_COMMANDS` constant from `constants.jsx` (8 commands).
The chip display uses `cmd.label` as text, `cmd.icon` as prefix, and
`cmd.insert` as the action payload. Behavior:
- If `cmd.insert` ends with `：` → insert into input, focus
- Otherwise → auto-send immediately

| Label | Insert text | Behavior |
|-------|------------|----------|
| 新建患者 | `新建患者：` | Insert (needs name) |
| 查询患者 | `查询患者：` | Insert (needs name) |
| 患者列表 | `患者列表` | Auto-send |
| 补充记录 | `补充记录：` | Insert (needs content) |
| 修正上条 | `刚才写错了，应该是` | Insert (needs correction) |
| 导出PDF | `导出病历PDF：` | Insert (needs name) |
| 今日任务 | `今日任务` | Auto-send |
| 功能帮助 | `帮助` | Auto-send |

## 7. WeChat-Style UI Polish

The chat interface already uses green/white bubbles. Polish to align more
closely with WeChat aesthetics:

- Chat background: `#ededed` (WeChat grey)
- Input bar background: `#f7f7f7` with top border
- Send button: `#07C160` circle (already done)
- Message bubbles: keep existing green (user) / white (assistant) with
  current border-radius
- Timestamps: subtle grey below bubbles (already done)
- Quick command chips: soft pastel backgrounds with matching text color

No structural changes to MsgBubble, MsgAvatar, or SystemMessage components.

## 8. Route Cleanup

After deleting dead pages, `App.jsx` routes simplify to:

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
```

No `/manage` or `/chat` routes.

## Out of Scope

- Admin page redesign (kept as-is, only API split)
- Debug page redesign (kept as-is, only API split)
- Patient portal changes
- Backend API changes
- Mobile app (Capacitor) changes
- i18n additions
