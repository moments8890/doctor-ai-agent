# Patient App Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the monolithic PatientPage.jsx into modular files matching the doctor app pattern, with mock/debug mode and pre-seeded realistic data.

**Architecture:** Split PatientPage.jsx (1,212 lines) into 8 focused files. Add PatientApiContext (mirroring doctor's ApiContext) so all patient pages use `usePatientApi()` hook. Add `/debug/patient` routes backed by PatientMockApiProvider with rich mock data.

**Tech Stack:** React, MUI, React Router, Context API

**Spec:** `docs/superpowers/specs/2026-03-26-patient-app-refactor-design.md`

---

### Task 1: Create constants.jsx

**Files:**
- Create: `frontend/web/src/pages/patient/constants.jsx`

- [ ] **Step 1: Create constants file**

Extract shared constants from PatientPage.jsx (lines 62-108, 85-102, 1062-1067):

```jsx
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";

export const STORAGE_KEY = "patient_portal_token";
export const STORAGE_NAME_KEY = "patient_portal_name";
export const STORAGE_DOCTOR_KEY = "patient_portal_doctor_id";
export const STORAGE_DOCTOR_NAME_KEY = "patient_portal_doctor_name";
export const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";

export const RECORD_TYPE_LABEL = {
  visit: "门诊记录", dictation: "语音记录", import: "导入记录", interview_summary: "预问诊",
};

export const FIELD_LABELS = {
  department: "科别", chief_complaint: "主诉", present_illness: "现病史", past_history: "既往史",
  allergy_history: "过敏史", family_history: "家族史", personal_history: "个人史",
  marital_reproductive: "婚育史", physical_exam: "体格检查", specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查", diagnosis: "初步诊断", treatment_plan: "治疗方案",
  orders_followup: "医嘱及随访",
};

export const FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "personal_history", "marital_reproductive", "family_history",
  "physical_exam", "specialist_exam", "auxiliary_exam", "diagnosis",
  "treatment_plan", "orders_followup",
];

export const NAV_TABS = [
  { key: "chat", label: "主页", icon: <ChatOutlinedIcon />, title: "AI 健康助手" },
  { key: "records", label: "病历", icon: <DescriptionOutlinedIcon />, title: "病历" },
  { key: "tasks", label: "任务", icon: <AssignmentOutlinedIcon />, title: "任务" },
  { key: "profile", label: "设置", icon: <SettingsOutlinedIcon />, title: "设置" },
];

export const DIAGNOSIS_STATUS_LABELS = {
  pending: "诊断中", completed: "待审核", confirmed: "已确认", failed: "诊断失败",
};

export const PAGE_LAYOUT = {
  display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed",
  position: "relative", overflow: "hidden",
};

export function formatDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }); }
  catch { return iso; }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/patient/constants.jsx
git commit -m "refactor(patient): extract constants from PatientPage"
```

---

### Task 2: Create PatientApiContext + PatientMockApiProvider

**Files:**
- Create: `frontend/web/src/api/PatientApiContext.jsx`
- Create: `frontend/web/src/api/PatientMockApiProvider.jsx`
- Create: `frontend/web/src/api/patientMockApi.js` (stub — full implementation in Task 4)

- [ ] **Step 1: Create PatientApiContext**

```jsx
// frontend/web/src/api/PatientApiContext.jsx
import { createContext, useContext } from "react";
import {
  getPatientMe,
  getPatientRecords,
  getPatientRecordDetail,
  getPatientTasks,
  completePatientTask,
  getPatientChatMessages,
  sendPatientChat,
  sendPatientMessage,
  interviewStart,
  interviewTurn,
  interviewConfirm,
  interviewCancel,
} from "../api";

const PatientApiContext = createContext(null);

const DEFAULT_VALUE = {
  getPatientMe,
  getPatientRecords,
  getPatientRecordDetail,
  getPatientTasks,
  completePatientTask,
  getPatientChatMessages,
  sendPatientChat,
  sendPatientMessage,
  interviewStart,
  interviewTurn,
  interviewConfirm,
  interviewCancel,
  isMock: false,
};

export function PatientApiProvider({ children }) {
  return <PatientApiContext.Provider value={DEFAULT_VALUE}>{children}</PatientApiContext.Provider>;
}

export function usePatientApi() {
  const ctx = useContext(PatientApiContext);
  if (!ctx) throw new Error("usePatientApi must be used within PatientApiProvider");
  return ctx;
}

// Re-export context for MockApiProvider
export { PatientApiContext };
```

- [ ] **Step 2: Create stub patientMockApi.js**

```jsx
// frontend/web/src/api/patientMockApi.js
// Full implementation in Task 4 after MockData is created

export async function getPatientMe() { return {}; }
export async function getPatientRecords() { return []; }
export async function getPatientRecordDetail() { return {}; }
export async function getPatientTasks() { return []; }
export async function completePatientTask() { return {}; }
export async function getPatientChatMessages() { return []; }
export async function sendPatientChat() { return {}; }
export async function sendPatientMessage() { return {}; }
export async function interviewStart() { return {}; }
export async function interviewTurn() { return {}; }
export async function interviewConfirm() { return {}; }
export async function interviewCancel() { return {}; }
```

- [ ] **Step 3: Create PatientMockApiProvider**

```jsx
// frontend/web/src/api/PatientMockApiProvider.jsx
import { PatientApiContext } from "./PatientApiContext";
import * as mockApi from "./patientMockApi";

const mockValue = { ...mockApi, isMock: true };

export function PatientMockApiProvider({ children }) {
  return <PatientApiContext.Provider value={mockValue}>{children}</PatientApiContext.Provider>;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/api/PatientApiContext.jsx frontend/web/src/api/PatientMockApiProvider.jsx frontend/web/src/api/patientMockApi.js
git commit -m "feat(patient): add PatientApiContext and mock provider"
```

---

### Task 3: Create MockData.jsx with rich patient data

**Files:**
- Create: `frontend/web/src/pages/patient/debug/MockData.jsx`

- [ ] **Step 1: Create mock data file**

Create `frontend/web/src/pages/patient/debug/MockData.jsx` with these exports:

**MOCK_PATIENT** — the logged-in patient:
```jsx
export const MOCK_PATIENT = {
  patient_name: "陈伟强",
  gender: "male",
  year_of_birth: 1984,
  phone: "138****5678",
  doctor_id: "mock_doctor",
  doctor_name: "张医生",
  doctor_specialty: "神经外科",
};
```

**MOCK_RECORDS** — 6 records, each with full structured data. Include:
1. Completed visit — 头痛3天伴恶心呕吐, 14 SOAP fields, diagnosis: 高血压性头痛, tags: [高血压, 头痛]
2. Pending review interview — 头晕反复发作1月, partial fields (chief_complaint, present_illness, past_history, allergy_history), status: pending_review
3. Completed visit — 血压控制不佳2周, diagnosis: 高血压病3级（高危）, treatment_plan: 调整降压方案
4. Completed visit — 糖尿病复查, diagnosis: 2型糖尿病, auxiliary_exam with lab results
5. Import record — 外院转入MRI报告, record_type: import, only auxiliary_exam filled
6. Older visit — 失眠2周, diagnosis: 焦虑相关性失眠, created_at 2 months ago

Each record should have: `id`, `patient_id: 1`, `patient_name: "陈伟强"`, `doctor_id: "mock_doctor"`, `record_type`, `status`, `content`, `created_at`, `structured` (object with SOAP fields), `tags`, and optionally `diagnosis_status`, `medications`, `followup_plan`, `lifestyle`.

For record 1, include `diagnosis_status: "confirmed"`, `medications: [{name: "氨氯地平", dosage: "5mg", frequency: "每日一次"}]`, `followup_plan: "2周后复诊，复查血压"`, `lifestyle: "低盐饮食，规律作息，避免情绪激动"`.

**MOCK_TASKS** — 5 tasks:
```jsx
export const MOCK_TASKS = [
  { id: 1, title: "神经外科复诊", task_type: "follow_up", status: "pending", due_at: "2026-03-29", patient_name: "陈伟强", record_id: 101, content: "携带近期血压记录" },
  { id: 2, title: "降压药服药提醒", task_type: "medication", status: "notified", due_at: "2026-03-25", patient_name: "陈伟强", content: "氨氯地平5mg，每日一次" },
  { id: 3, title: "复查头颅MRI", task_type: "checkup", status: "pending", due_at: "2026-04-02", patient_name: "陈伟强", content: "空腹，预约放射科" },
  { id: 4, title: "空腹血糖检测", task_type: "checkup", status: "completed", due_at: "2026-03-24", patient_name: "陈伟强", completed_at: "2026-03-24" },
  { id: 5, title: "血压监测记录", task_type: "follow_up", status: "completed", due_at: "2026-03-21", patient_name: "陈伟强", completed_at: "2026-03-21" },
];
```

**MOCK_CHAT_MESSAGES** — 12+ messages in realistic conversation order:
```jsx
export const MOCK_CHAT_MESSAGES = [
  { id: 1, role: "assistant", content: "您好！我是张医生的AI助手。请描述您的症状，我来帮您整理。", created_at: "2026-03-26T09:00:00Z" },
  { id: 2, role: "patient", content: "最近头痛又开始了，已经持续3天了", created_at: "2026-03-26T09:01:00Z" },
  { id: 3, role: "assistant", content: "了解，请问头痛的位置在哪里？是前额、两侧还是后脑勺？有没有伴随其他不适？", created_at: "2026-03-26T09:01:30Z" },
  { id: 4, role: "patient", content: "主要是两侧太阳穴，胀痛", created_at: "2026-03-26T09:02:00Z" },
  { id: 5, role: "assistant", content: "明白。疼痛程度如何？1-10分您打几分？有没有伴随恶心、呕吐或视物模糊？", created_at: "2026-03-26T09:02:30Z" },
  { id: 6, role: "patient", content: "大概6分吧，有点恶心，没有呕吐", created_at: "2026-03-26T09:03:00Z" },
  { id: 7, role: "assistant", content: "好的。您最近血压有测过吗？之前的降压药还在按时服用吗？", created_at: "2026-03-26T09:03:30Z" },
  { id: 8, role: "patient", content: "昨天量了一次，150/95，药一直在吃", created_at: "2026-03-26T09:04:00Z" },
  { id: 9, role: "assistant", content: "根据您描述的症状（双侧太阳穴胀痛3天伴恶心，血压150/95mmHg），这可能与血压控制不佳有关。\n\n建议：\n1. 继续按时服用降压药\n2. 每天早晚各测一次血压并记录\n3. 低盐饮食，避免情绪激动\n4. 如果头痛加重或出现呕吐、视物模糊，请立即就医\n\n张医生会在下次复诊时评估是否需要调整用药方案。", created_at: "2026-03-26T09:05:00Z", triage_category: "diagnosis_confirmation" },
  { id: 10, role: "patient", content: "好的谢谢", created_at: "2026-03-26T09:06:00Z" },
  { id: 11, role: "assistant", content: "不客气！记得按时测血压，有任何不适随时告诉我。", created_at: "2026-03-26T09:06:30Z" },
  { id: 12, role: "doctor", content: "陈伟强您好，看到您最近血压偏高，我已经在任务中安排了复诊和MRI检查，请按时来。", created_at: "2026-03-26T10:00:00Z", doctor_name: "张医生" },
  { id: 13, role: "patient", content: "好的张医生，我会按时来的", created_at: "2026-03-26T10:05:00Z" },
  { id: 14, role: "assistant", content: "张医生已收到您的回复。复诊时间已添加到您的任务列表。如有其他问题随时问我。", created_at: "2026-03-26T10:05:30Z" },
];
```

**MOCK_INTERVIEW_STATE** — partial interview in progress:
```jsx
export const MOCK_INTERVIEW_STATE = {
  session_id: "mock-interview-001",
  status: "interviewing",
  collected: {
    chief_complaint: "头痛反复发作",
    present_illness: "近1月来反复头痛，以双侧太阳穴为主，每次持续2-3小时",
  },
  progress: { filled: 2, total: 7 },
  reply: "收到，主诉和现病史已记录。请问您有什么既往病史吗？比如高血压、糖尿病？",
  suggestions: ["有高血压", "有糖尿病", "没有慢性病", "不太清楚"],
  conversation: [
    { role: "assistant", content: "您好！我来帮您整理病历信息。请先告诉我，您今天最主要的不适是什么？" },
    { role: "user", content: "头痛反复发作，最近一个月了" },
    { role: "assistant", content: "了解。这个头痛是什么样的？在哪个部位？每次持续多久？" },
    { role: "user", content: "两侧太阳穴胀痛，每次大概2到3个小时" },
    { role: "assistant", content: "收到，主诉和现病史已记录。请问您有什么既往病史吗？比如高血压、糖尿病？" },
  ],
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/patient/debug/MockData.jsx
git commit -m "feat(patient): add rich mock data for patient debug mode"
```

---

### Task 4: Implement patientMockApi.js with full mock functions

**Files:**
- Modify: `frontend/web/src/api/patientMockApi.js`

- [ ] **Step 1: Replace stub with full implementation**

Replace the stub `patientMockApi.js` with full implementations. Each function should:
- Import from `../pages/patient/debug/MockData`
- Return data after a short delay (`await new Promise(r => setTimeout(r, 100))`) to simulate network
- Match the real API's return format exactly

Key implementations:
- `getPatientMe(token)` → return `MOCK_PATIENT`
- `getPatientRecords(token)` → return `MOCK_RECORDS` array
- `getPatientRecordDetail(token, recordId)` → find by id in `MOCK_RECORDS`, return the full record with structured fields flattened (chief_complaint, diagnosis, etc. at top level)
- `getPatientTasks(token)` → return `MOCK_TASKS`
- `completePatientTask(token, taskId)` → mutate task status to "completed" in local array, return updated task
- `getPatientChatMessages(token, sinceId)` → if sinceId, filter messages after that id; else return all `MOCK_CHAT_MESSAGES`
- `sendPatientChat(token, text)` → return `{ reply: "这是模拟回复。Mock mode 不支持真实对话。", message_id: Date.now() }`
- `sendPatientMessage(token, text)` → same as sendPatientChat
- `interviewStart(token)` → return `{ session_id: MOCK_INTERVIEW_STATE.session_id, reply: MOCK_INTERVIEW_STATE.conversation[0].content, collected: {}, progress: { filled: 0, total: 7 }, status: "interviewing", resumed: false }`
- `interviewTurn(token, sessionId, text)` → return `{ reply: MOCK_INTERVIEW_STATE.reply, collected: MOCK_INTERVIEW_STATE.collected, progress: MOCK_INTERVIEW_STATE.progress, status: "interviewing", suggestions: MOCK_INTERVIEW_STATE.suggestions, missing_fields: ["past_history", "allergy_history", "family_history", "personal_history", "physical_exam"], complete: false }`
- `interviewConfirm(token, sessionId)` → return `{ message: "病历已保存", record_id: 999 }`
- `interviewCancel(token, sessionId)` → return `{ status: "cancelled" }`

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/api/patientMockApi.js
git commit -m "feat(patient): implement full patient mock API"
```

---

### Task 5: Extract ProfileTab.jsx

**Files:**
- Create: `frontend/web/src/pages/patient/ProfileTab.jsx`

- [ ] **Step 1: Create ProfileTab**

Extract the profile tab inline JSX from PatientPage.jsx lines 1155-1188. Convert to a standalone component that receives props:

```jsx
import { Box, Typography } from "@mui/material";
import ListCard from "../../components/ListCard";
import PatientAvatar from "../../components/PatientAvatar";
import SectionLabel from "../../components/SectionLabel";
import { TYPE, COLOR } from "../../theme";

export default function ProfileTab({ patientName, doctorName, doctorSpecialty, doctorId, onLogout }) {
  return (
    <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
      {doctorName && (
        <>
          <SectionLabel>我的医生</SectionLabel>
          <Box sx={{ bgcolor: COLOR.white }}>
            <ListCard
              avatar={<PatientAvatar name={doctorName} size={42} />}
              title={doctorName}
              subtitle={doctorSpecialty || ""}
            />
          </Box>
        </>
      )}
      <SectionLabel>我的信息</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white }}>
        <ListCard
          avatar={<PatientAvatar name={patientName || "?"} size={42} />}
          title={patientName || "患者"}
          subtitle={doctorId || ""}
        />
      </Box>
      <Box sx={{ mt: 1 }}>
        <Box onClick={onLogout}
          sx={{ bgcolor: COLOR.white, py: 1.5, textAlign: "center", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.danger }}>退出登录</Typography>
        </Box>
      </Box>
    </Box>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/patient/ProfileTab.jsx
git commit -m "refactor(patient): extract ProfileTab from PatientPage"
```

---

### Task 6: Extract TasksTab.jsx

**Files:**
- Create: `frontend/web/src/pages/patient/TasksTab.jsx`

- [ ] **Step 1: Create TasksTab**

Extract lines 760-816 from PatientPage.jsx. Replace direct API imports with `usePatientApi()`:

```jsx
import { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import TaskChecklist from "../../components/TaskChecklist";
import SectionLabel from "../../components/SectionLabel";
import { usePatientApi } from "../../api/PatientApiContext";
import { TYPE, ICON, COLOR } from "../../theme";

export default function TasksTab({ token }) {
  const { getPatientTasks, completePatientTask } = usePatientApi();
  // ... rest of the existing TasksTab logic (state, useEffect, handleComplete, render)
  // Copy lines 761-816 verbatim, replacing direct API calls with destructured functions above
}
```

The component body is a direct copy of the existing `TasksTab` function (lines 760-816), only changing imports to use `usePatientApi()` instead of direct imports from `../../api`.

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/patient/TasksTab.jsx
git commit -m "refactor(patient): extract TasksTab from PatientPage"
```

---

### Task 7: Extract RecordDetail.jsx + RecordsTab.jsx

**Files:**
- Create: `frontend/web/src/pages/patient/subpages/RecordDetail.jsx`
- Create: `frontend/web/src/pages/patient/RecordsTab.jsx`

- [ ] **Step 1: Create RecordDetail subpage**

Extract `RecordDetailView` (lines 466-626) from PatientPage.jsx. Use `usePatientApi()` for API calls. Import constants from `../constants.jsx`:

```jsx
import { useEffect, useState } from "react";
import { Box, Typography, Chip, Stack, LinearProgress } from "@mui/material";
import SubpageHeader from "../../../components/SubpageHeader";
import StatusBadge from "../../../components/StatusBadge";
import SectionLabel from "../../../components/SectionLabel";
import { usePatientApi } from "../../../api/PatientApiContext";
import { FIELD_LABELS, FIELD_ORDER, DIAGNOSIS_STATUS_LABELS, formatDate } from "../constants";
import { TYPE, COLOR } from "../../../theme";

export default function RecordDetail({ recordId, token, onBack }) {
  const { getPatientRecordDetail } = usePatientApi();
  // ... existing RecordDetailView logic, adapted
}
```

Note: the existing RecordDetailView receives the full `record` object and only fetches detail via `getPatientRecordDetail` if needed. Keep this behavior but use `usePatientApi()`.

- [ ] **Step 2: Create RecordsTab**

Extract `RecordsTab` (lines 628-754) from PatientPage.jsx. Replace direct API imports with `usePatientApi()`. Import constants from `./constants.jsx`. For record detail, navigate to `/patient/records/:recordId`:

```jsx
import { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import ListCard from "../../components/ListCard";
import NewItemCard from "../../components/NewItemCard";
import RecordAvatar from "../../components/RecordAvatar";
import StatusBadge from "../../components/StatusBadge";
import { usePatientApi } from "../../api/PatientApiContext";
import { RECORD_TYPE_LABEL, formatDate } from "./constants";
import { TYPE, COLOR } from "../../theme";
import RecordDetail from "./subpages/RecordDetail";

export default function RecordsTab({ token, onNewRecord, urlSubpage }) {
  const { getPatientRecords } = usePatientApi();
  const navigate = useNavigate();
  // ... existing RecordsTab logic
  // When urlSubpage is a numeric recordId, render <RecordDetail>
  // Otherwise render the records list
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/subpages/RecordDetail.jsx frontend/web/src/pages/patient/RecordsTab.jsx
git commit -m "refactor(patient): extract RecordsTab and RecordDetail from PatientPage"
```

---

### Task 8: Extract ChatTab.jsx

**Files:**
- Create: `frontend/web/src/pages/patient/ChatTab.jsx`

- [ ] **Step 1: Create ChatTab**

Extract `QuickActions` (lines 211-242) and `ChatTab` (lines 244-459) from PatientPage.jsx. This is the most complex extraction due to polling logic.

Replace direct API imports with `usePatientApi()`:

```jsx
import { useEffect, useState, useRef, useCallback } from "react";
import { Box, IconButton, Typography, Badge } from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import AddIcon from "@mui/icons-material/Add";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import SubpageHeader from "../../components/SubpageHeader";
import DoctorBubble from "../../components/DoctorBubble";
import AppButton from "../../components/AppButton";
import { usePatientApi } from "../../api/PatientApiContext";
import { TYPE, ICON, COLOR } from "../../theme";
import { LAST_SEEN_CHAT_KEY } from "./constants";

const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

function QuickActions({ onNewInterview, onViewRecords }) {
  // ... existing QuickActions (lines 211-242), verbatim
}

export default function ChatTab({ token, doctorName, onLogout, onNewInterview, onViewRecords, onUnreadCountChange }) {
  const { getPatientChatMessages, sendPatientChat } = usePatientApi();
  // ... existing ChatTab logic (lines 244-459)
  // Replace direct calls to getPatientChatMessages/sendPatientChat with destructured functions
}
```

Key: the existing code references `getPatientChatMessages` and `sendPatientChat` from `../../api` — replace with `usePatientApi()` destructuring.

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/patient/ChatTab.jsx
git commit -m "refactor(patient): extract ChatTab from PatientPage"
```

---

### Task 9: Extract InterviewPage.jsx

**Files:**
- Create: `frontend/web/src/pages/patient/InterviewPage.jsx`

- [ ] **Step 1: Create InterviewPage**

Extract the `InterviewPage` function (lines 822-1056) from PatientPage.jsx. Replace direct API imports with `usePatientApi()`:

```jsx
import { useEffect, useRef, useState } from "react";
import { Box, Typography, IconButton, LinearProgress, CircularProgress } from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import SubpageHeader from "../../components/SubpageHeader";
import SuggestionChips from "../../components/SuggestionChips";
import SheetDialog from "../../components/SheetDialog";
import ConfirmDialog from "../../components/ConfirmDialog";
import AppButton from "../../components/AppButton";
import { usePatientApi } from "../../api/PatientApiContext";
import { TYPE, ICON, COLOR } from "../../theme";

export default function InterviewPage({ token, onBack, onLogout }) {
  const { interviewStart, interviewTurn, interviewConfirm, interviewCancel } = usePatientApi();
  // ... existing InterviewPage logic (lines 822-1056)
  // Replace direct calls with destructured functions
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/patient/InterviewPage.jsx
git commit -m "refactor(patient): extract InterviewPage from PatientPage"
```

---

### Task 10: Rewrite PatientPage.jsx as thin shell

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx`

- [ ] **Step 1: Rewrite PatientPage as shell**

Replace the entire 1,212-line file with a thin shell (~100 lines) that:
1. Handles auth (token check, mock mode bypass)
2. Loads patient identity via `usePatientApi().getPatientMe`
3. Routes to the correct tab component based on URL params
4. Renders bottom nav
5. Renders full-screen InterviewPage when `urlSubpage === "interview"`

```jsx
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Box } from "@mui/material";
import Badge from "@mui/material/Badge";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import SubpageHeader from "../../components/SubpageHeader";
import { usePatientApi } from "../../api/PatientApiContext";
import ChatTab from "./ChatTab";
import RecordsTab from "./RecordsTab";
import TasksTab from "./TasksTab";
import ProfileTab from "./ProfileTab";
import InterviewPage from "./InterviewPage";
import {
  NAV_TABS, PAGE_LAYOUT,
  STORAGE_KEY, STORAGE_NAME_KEY, STORAGE_DOCTOR_KEY, STORAGE_DOCTOR_NAME_KEY,
  LAST_SEEN_CHAT_KEY,
} from "./constants";

const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

export default function PatientPage() {
  const { tab: urlTab, subpage: urlSubpage } = useParams();
  const navigate = useNavigate();
  const api = usePatientApi();

  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
  const [doctorName, setDoctorName] = useState(() => localStorage.getItem(STORAGE_DOCTOR_NAME_KEY) || "");
  const [doctorSpecialty, setDoctorSpecialty] = useState("");
  const [doctorId, setDoctorId] = useState(() => localStorage.getItem(STORAGE_DOCTOR_KEY) || "");
  const [unreadCount, setUnreadCount] = useState(0);

  // Mock mode: bypass auth with mock patient identity
  useEffect(() => {
    if (api.isMock && !token) {
      setToken("mock-patient-token");
      setPatientName("陈伟强");
      setDoctorName("张医生");
      setDoctorSpecialty("神经外科");
      setDoctorId("mock_doctor");
    }
  }, [api.isMock]);

  // Load patient identity
  useEffect(() => {
    if (!token || api.isMock) return;
    api.getPatientMe(token).then(data => {
      if (data.patient_name) setPatientName(data.patient_name);
      setDoctorName(data.doctor_name || "");
      setDoctorSpecialty(data.doctor_specialty || "");
      if (data.doctor_id) setDoctorId(data.doctor_id);
    }).catch(() => {});
  }, [token]);

  const tab = urlTab || "chat";
  const inInterview = urlSubpage === "interview";
  function setTab(t) { navigate(`/patient/${t}`); }
  function startInterview() { navigate("/patient/records/interview"); }
  function exitInterview() { navigate("/patient/records"); }

  // Clear badge when chat tab is active
  useEffect(() => {
    if (tab === "chat") {
      localStorage.setItem(LAST_SEEN_CHAT_KEY, String(Date.now()));
      setUnreadCount(0);
    }
  }, [tab]);

  function handleLogout() {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_NAME_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_NAME_KEY);
    localStorage.removeItem(PATIENT_CHAT_STORAGE_KEY);
    setToken("");
    setPatientName("");
    setDoctorName("");
  }

  // Auth gate (skip in mock mode)
  if (!token && !api.isMock) {
    window.location.href = "/login";
    return null;
  }

  // Full-screen interview
  if (inInterview) {
    return <InterviewPage token={token} onBack={exitInterview} onLogout={handleLogout} />;
  }

  return (
    <Box sx={PAGE_LAYOUT}>
      {!urlSubpage && <SubpageHeader title={NAV_TABS.find(t => t.key === tab)?.title || "AI 健康助手"} />}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
        {tab === "chat" && <ChatTab token={token} doctorName={doctorName} onLogout={handleLogout}
          onNewInterview={startInterview} onViewRecords={() => setTab("records")}
          onUnreadCountChange={setUnreadCount} />}
        {tab === "records" && <RecordsTab token={token} onNewRecord={startInterview} urlSubpage={urlSubpage} />}
        {tab === "tasks" && <TasksTab token={token} />}
        {tab === "profile" && <ProfileTab patientName={patientName} doctorName={doctorName}
          doctorSpecialty={doctorSpecialty} doctorId={doctorId} onLogout={handleLogout} />}
      </Box>
      <BottomNavigation value={tab} onChange={(_, v) => setTab(v)} showLabels
        sx={{ flexShrink: 0, height: 56, borderTop: "1px solid #ddd", bgcolor: "#f5f5f5",
          paddingBottom: "env(safe-area-inset-bottom)" }}>
        {NAV_TABS.map(t => (
          <BottomNavigationAction key={t.key} value={t.key} label={t.label}
            icon={t.key === "chat" && unreadCount > 0 ? <Badge badgeContent={unreadCount} color="error">{t.icon}</Badge> : t.icon}
            sx={{ "&.Mui-selected": { color: "#07C160" } }} />
        ))}
      </BottomNavigation>
    </Box>
  );
}
```

Note: `LoginView` is NOT included — it lives in the shared `/login` route already. PatientPage just redirects to `/login` when no token.

- [ ] **Step 2: Verify no broken imports**

Check that all old imports from the monolithic file are now covered by the new modules. The old PatientPage.jsx had ~25 imports — the new shell should only need ~12.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "refactor(patient): rewrite PatientPage as thin shell with modular tabs"
```

---

### Task 11: Update App.jsx — add patient routes with providers

**Files:**
- Modify: `frontend/web/src/App.jsx`

- [ ] **Step 1: Add patientRoutes helper and debug routes**

Add imports at top of App.jsx:
```jsx
import { PatientApiProvider } from "./api/PatientApiContext";
import { PatientMockApiProvider } from "./api/PatientMockApiProvider";
```

Add `patientRoutes` helper (after existing `doctorRoutes`):
```jsx
const PATIENT_PATH_SUFFIXES = ["", "/:tab", "/:tab/:subpage"];

function patientRoutes(prefix, Provider) {
  return PATIENT_PATH_SUFFIXES.map((suffix) => (
    <Route key={prefix + suffix} path={`${prefix}${suffix}`}
      element={<MobileFrame><Provider><PatientPage /></Provider></MobileFrame>} />
  ));
}
```

Replace the existing 3 patient Route lines:
```jsx
// OLD:
<Route path="/patient" element={<MobileFrame><PatientPage /></MobileFrame>} />
<Route path="/patient/:tab" element={<MobileFrame><PatientPage /></MobileFrame>} />
<Route path="/patient/:tab/:subpage" element={<MobileFrame><PatientPage /></MobileFrame>} />

// NEW:
{patientRoutes("/patient", PatientApiProvider)}
```

Add debug routes (before the debug wildcard):
```jsx
{patientRoutes("/debug/patient", PatientMockApiProvider)}
```

- [ ] **Step 2: Add debug/patient link to DebugPage**

In `frontend/web/src/pages/admin/DebugPage.jsx`, add a navigation link/button for `/debug/patient` alongside the existing doctor debug links.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/App.jsx frontend/web/src/pages/admin/DebugPage.jsx
git commit -m "feat(patient): add patient routes with API providers and debug mode"
```

---

### Task 12: Smoke test — verify real mode and mock mode

**Files:** None (testing only)

- [ ] **Step 1: Test mock mode**

Open `http://localhost:5173/debug/patient` in browser. Verify:
- Chat tab loads with mock messages (12+ messages, doctor bubble visible)
- Records tab shows 6 records with proper avatars and status badges
- Tap a record → RecordDetail shows structured SOAP fields
- Tasks tab shows 3 pending + 2 completed tasks
- Profile tab shows 张医生 (神经外科) and 陈伟强
- Bottom nav highlights active tab in green
- "新建病历" → interview page loads with mock data

- [ ] **Step 2: Test real mode**

Open `http://localhost:5173/patient` in browser. Verify:
- Redirects to `/login` when no token
- After login, all 4 tabs work with real API
- Interview flow works end-to-end
- No console errors

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(patient): smoke test fixes for patient app refactor"
```
