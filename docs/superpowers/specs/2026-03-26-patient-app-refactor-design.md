# Patient App Refactor — Modular Structure + Mock/Debug

**Date:** 2026-03-26
**Status:** Draft

## Goal

Refactor the monolithic `PatientPage.jsx` (1,137 lines) into a modular file structure matching the doctor app pattern. Add mock/debug mode with pre-seeded realistic data so the patient UI can be developed and demoed without a running backend.

Mobile-only — no desktop layout support needed.

## Architecture

### File Structure

```
pages/patient/
├── PatientPage.jsx          ← shell: auth guard, tab routing, bottom nav
├── ChatTab.jsx              ← AI health chat (home tab)
├── RecordsTab.jsx           ← records list
├── TasksTab.jsx             ← patient tasks with checklist
├── ProfileTab.jsx           ← doctor info, patient info, logout
├── InterviewPage.jsx        ← full-screen pre-assessment interview
├── constants.jsx            ← NAV_TABS, FIELD_LABELS, RECORD_TYPE_LABELS
├── subpages/
│   └── RecordDetail.jsx     ← drilldown view for a single record
└── debug/
    └── MockData.jsx         ← static patient mock data
```

### API Layer

Follow the doctor app's `ApiContext` / `MockApiProvider` pattern:

```
api/
├── PatientApiContext.jsx     ← createContext + PatientApiProvider + usePatientApi()
├── patientMockApi.js         ← mock implementations returning MockData
└── PatientMockApiProvider.jsx ← wraps PatientApiContext with mock functions
```

All patient page components call `usePatientApi()` instead of importing API functions directly. This makes real ↔ mock swappable via provider.

### Routes (App.jsx)

```jsx
// Real patient app
{patientRoutes("/patient", PatientApiProvider)}

// Debug/mock patient app
{patientRoutes("/debug/patient", PatientMockApiProvider)}
```

Helper function mirrors the existing `doctorRoutes()`:
```jsx
const PATIENT_PATH_SUFFIXES = ["", "/:tab", "/:tab/:subpage"];

function patientRoutes(prefix, Provider) {
  return PATIENT_PATH_SUFFIXES.map((suffix) => (
    <Route key={prefix + suffix} path={`${prefix}${suffix}`}
      element={<MobileFrame><Provider><PatientPage /></Provider></MobileFrame>} />
  ));
}
```

Add link to `/debug/patient` on the existing DebugPage.

## Component Design

### PatientPage.jsx (Shell)

Responsibilities:
- Auth guard: check token in localStorage, redirect to `/login` if missing
- In mock mode (`usePatientApi().isMock`): skip auth, use mock patient identity
- Parse `useParams()` for `tab` and `subpage`
- Render active tab component based on `tab` param
- Bottom nav with 4 tabs: 主页, 病历, 任务, 设置
- When interview is active (full-screen), hide bottom nav

Props flow:
- `token`, `patientName`, `doctorName`, `doctorId` derived from auth state
- Passed down to tab components

Bottom nav style: matches doctor app — `#07C160` active color, `#f5f5f5` bgcolor, flex-flow layout (no position:absolute), `env(safe-area-inset-bottom)` padding.

### ChatTab.jsx

Extracted from current `ChatTab` function inside PatientPage.jsx.

- Welcome message with doctor name
- Message polling (10s active, 60s hidden)
- Quick action buttons at top: "新问诊", "我的病历"
- Green user bubbles (right), white AI bubbles (left), DoctorBubble for doctor messages
- Triage enrichment: `diagnosis_confirmation` (green bg), `urgent` (red badge)
- Input bar with send button

API calls via `usePatientApi()`:
- `getMessages(token, lastMsgId)` — polling
- `sendMessage(token, text)` — send + get AI reply

### RecordsTab.jsx

Extracted from current `RecordsTab`.

- List view with `ListCard` components
- Each record: `RecordAvatar` (type icon), title (record type label), subtitle (chief complaint), right side (status badge + date)
- `NewItemCard` at top: "新建病历" → navigates to interview
- Tap record → navigate to `/patient/records/:recordId`

API calls:
- `getRecords(token)` — list all records

### RecordDetail.jsx (subpage)

Extracted from current `RecordDetailView`.

- `SubpageHeader` with back button + title
- Summary section: diagnosis status, medications, follow-up, lifestyle
- Full record: expandable structured fields (14 SOAP fields)
- Fallback to raw `content` if no structured data

API calls:
- `getRecordDetail(token, recordId)` — fetch full record

### TasksTab.jsx

Extracted from current `TasksTab`.

- Uses `TaskChecklist` component
- Two sections: pending, completed
- Empty state: "暂无任务" + description

API calls:
- `getTasks(token)` — list tasks
- `completeTask(token, taskId)` — mark done

### ProfileTab.jsx

Extracted from current `ProfileTab`.

- "我的医生" section: doctor name + specialty (via PatientAvatar/ListCard)
- "我的信息" section: patient name, phone
- Logout button (red "退出登录")

API calls:
- `getMe(token)` — patient info + doctor info

### InterviewPage.jsx

Extracted from current interview code inside PatientPage.jsx.

- Full-screen overlay (bottom nav hidden)
- Session-based: sessionId, collected, progress, status
- `SubpageHeader` with "新建病历" title + back
- Progress bar (filled/total)
- Chat-style messages with suggestion chips
- Summary dialog on completion
- Exit dialog: save vs discard

API calls:
- `interviewStart(token)`
- `interviewTurn(token, sessionId, text)`
- `interviewConfirm(token, sessionId)`
- `interviewCancel(token, sessionId)`

### constants.jsx

```jsx
export const NAV_TABS = [
  { key: "chat", label: "主页", icon: ChatOutlinedIcon, title: "AI 健康助手" },
  { key: "records", label: "病历", icon: DescriptionOutlinedIcon, title: "病历" },
  { key: "tasks", label: "任务", icon: AssignmentOutlinedIcon, title: "任务" },
  { key: "profile", label: "设置", icon: SettingsOutlinedIcon, title: "设置" },
];

export const RECORD_TYPE_LABELS = { ... };
export const FIELD_LABELS = { ... };
export const DIAGNOSIS_STATUS_LABELS = { ... };
```

## PatientApiContext

```jsx
// PatientApiContext.jsx
const PatientApiContext = createContext(null);

export function PatientApiProvider({ children }) {
  const value = { ...patientApi, isMock: false };
  return <PatientApiContext.Provider value={value}>{children}</PatientApiContext.Provider>;
}

export function usePatientApi() {
  const ctx = useContext(PatientApiContext);
  if (!ctx) throw new Error("usePatientApi must be used within PatientApiProvider");
  return ctx;
}
```

API functions exposed (matching existing `api.js` patient exports):
- `getMe(token)`
- `getMessages(token, lastMsgId)`
- `sendMessage(token, text)`
- `getRecords(token)`
- `getRecordDetail(token, recordId)`
- `getTasks(token)`
- `completeTask(token, taskId)`
- `interviewStart(token)`
- `interviewTurn(token, sessionId, text)`
- `interviewConfirm(token, sessionId)`
- `interviewCancel(token, sessionId)`

## Mock Data (MockData.jsx)

### Patient & Doctor
```
patient: 陈伟强, male, born 1984, phone 138****5678
doctor: 张医生, 神经外科, doctor_id: mock_doctor
```

### Records (6)
1. **Completed visit** — 头痛3天伴恶心呕吐, full SOAP (14 fields), diagnosis: 高血压性头痛, status: completed
2. **Pending review (interview)** — 头晕反复发作1月, partial fields, status: pending_review
3. **Completed visit** — 血压控制不佳2周, diagnosis: 高血压病3级, with treatment_plan
4. **Completed visit** — 糖尿病复查, diagnosis: 2型糖尿病, with lab results in auxiliary_exam
5. **Imported record** — 外院转入MRI报告, record_type: import, with auxiliary_exam only
6. **Older visit** — 失眠2周, diagnosis: 焦虑相关性失眠, completed 2 months ago

### Tasks (5)
1. **Pending follow-up** — "神经外科复诊", due in 3 days, linked to record
2. **Overdue medication** — "降压药服药提醒", due yesterday, status: notified
3. **Pending checkup** — "复查头颅MRI", due next week
4. **Completed** — "空腹血糖检测", completed 2 days ago
5. **Completed** — "血压监测记录", completed 5 days ago

### Chat Messages (12+)
Realistic multi-turn conversation:
```
patient: "最近头痛又开始了，已经持续3天了"
ai: "了解，请问头痛的位置在哪里？是前额、两侧还是后脑勺？"
patient: "主要是两侧太阳穴，胀痛"
ai: "明白。疼痛程度如何？有没有伴随恶心、呕吐或视物模糊？"
patient: "有点恶心，没有呕吐"
ai: "好的。您最近血压有测过吗？之前的降压药还在按时服用吗？"
patient: "昨天量了一次，150/95"
ai: [triage: diagnosis_confirmation] "根据您描述的症状（双侧太阳穴胀痛3天伴恶心，血压150/95），这可能与血压控制不佳有关。建议：1. 继续按时服用降压药 2. 每天监测血压 3. 如果头痛加重或出现呕吐、视物模糊，请立即就医。张医生会在下次复诊时调整用药方案。"
patient: "好的谢谢"
ai: "不客气！记得按时测血压，有任何不适随时告诉我。"
doctor: [DoctorBubble] "陈伟强您好，看到您最近血压偏高，我已经在任务中安排了复诊，请按时来。"
patient: "好的张医生"
ai: "张医生已收到您的回复。如有其他问题随时问我。"
```

### Interview State (partial)
For showing interview-in-progress:
```
sessionId: "mock-interview-001"
status: "interviewing"
collected: {
  chief_complaint: "头痛反复发作",
  present_illness: "近1月来反复头痛，以双侧太阳穴为主",
}
progress: { filled: 2, total: 7 }
conversation: [4 turns of Q&A]
suggestions: ["有恶心呕吐", "没有其他症状", "有时头晕"]
```

## Behavior in Mock Mode

- Auth is bypassed — PatientPage checks `isMock` and uses mock patient identity
- All API calls return mock data with realistic delays (50-200ms `setTimeout`)
- Chat `sendMessage` returns a canned response: "这是模拟回复。Mock mode 不支持真实对话。"
- Interview turns return next question from a scripted sequence
- Task completion toggles status in mutable mock state (resets on refresh)
- Record list and detail work with full structured data

## What Does NOT Change

- Login page (`/login`) — unchanged, separate from patient app
- Shared components — no modifications, just imported
- Backend API endpoints — untouched
- Doctor app — untouched

## Implementation Order

1. Create `constants.jsx` — extract nav tabs, labels
2. Create `PatientApiContext.jsx` + `usePatientApi()` hook
3. Create `debug/MockData.jsx` — all mock data
4. Create `patientMockApi.js` + `PatientMockApiProvider.jsx`
5. Extract `ProfileTab.jsx` (simplest, no API deps beyond getMe)
6. Extract `TasksTab.jsx`
7. Extract `RecordsTab.jsx` + `subpages/RecordDetail.jsx`
8. Extract `ChatTab.jsx` (most complex, polling logic)
9. Extract `InterviewPage.jsx`
10. Rewrite `PatientPage.jsx` as thin shell
11. Update `App.jsx` — add `patientRoutes()`, debug routes, DebugPage link
12. Verify real mode works (login → all tabs)
13. Verify mock mode works (`/debug/patient` → all tabs with mock data)
