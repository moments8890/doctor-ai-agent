# API Context + Mock Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate duplicate mock pages by making `/debug/doctor/*` render the real DoctorPage with fake API responses via React context.

**Architecture:** Create `useApi()` hook backed by React context. Real routes provide real api.js functions. Mock routes provide mockApi.js (returns MOCK_* data). Add `useAppNavigate()` hook that auto-prefixes `/debug` when in mock mode so navigation stays within the mock route space.

**Tech Stack:** React context, Zustand (existing store), react-router-dom (existing), Vite

**Spec:** `docs/superpowers/specs/2026-03-26-api-context-mock-unification-design.md`

---

### Task 1: Create ApiContext + useApi hook

**Files:**
- Create: `frontend/web/src/api/ApiContext.jsx`

- [ ] **Step 1: Create ApiContext with real API as default**

```jsx
// frontend/web/src/api/ApiContext.jsx
import { createContext, useContext } from "react";
import * as realApi from "../api";

const ApiContext = createContext(null);

/**
 * Provides API functions to descendants. Defaults to real api.js.
 * In mock mode, MockApiProvider overrides with mockApi functions.
 */
export function ApiProvider({ children, value }) {
  const api = value || { ...realApi, isMock: false };
  return <ApiContext.Provider value={api}>{children}</ApiContext.Provider>;
}

/**
 * Hook to access API functions. Must be called inside ApiProvider.
 * Returns all api.js exports + `isMock` boolean.
 */
export function useApi() {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error("useApi must be used within an ApiProvider");
  return ctx;
}
```

- [ ] **Step 2: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build, no output

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/api/ApiContext.jsx
git commit -m "feat: add ApiContext + useApi hook for API dependency injection"
```

---

### Task 2: Create useAppNavigate hook

**Files:**
- Create: `frontend/web/src/hooks/useAppNavigate.js`

- [ ] **Step 1: Create useAppNavigate**

```jsx
// frontend/web/src/hooks/useAppNavigate.js
import { useNavigate } from "react-router-dom";
import { useApi } from "../api/ApiContext";

/**
 * Drop-in replacement for useNavigate that auto-prefixes /debug
 * when running in mock mode. Ensures navigation stays within
 * /debug/doctor/* routes instead of escaping to /doctor/*.
 *
 * Non-string args (e.g. -1 for back) pass through unchanged.
 */
export function useAppNavigate() {
  const navigate = useNavigate();
  const { isMock } = useApi();
  return (to, options) => {
    if (isMock && typeof to === "string" && to.startsWith("/doctor")) {
      navigate("/debug" + to, options);
    } else {
      navigate(to, options);
    }
  };
}
```

- [ ] **Step 2: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/hooks/useAppNavigate.js
git commit -m "feat: add useAppNavigate hook for mock-aware navigation"
```

---

### Task 3: Wrap real app in ApiProvider + add debug routes

**Files:**
- Modify: `frontend/web/src/App.jsx`

- [ ] **Step 1: Add ApiProvider import and wrap doctor routes**

Add import at top of App.jsx:
```jsx
import { ApiProvider } from "./api/ApiContext";
```

Replace the existing doctor route block (lines 118-123):
```jsx
      <Route path="/doctor" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/patients/:patientId" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/review/:recordId" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section/:subpage" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section/:subpage/:subId" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
```

With:
```jsx
      <Route path="/doctor" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/doctor/patients/:patientId" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/doctor/review/:recordId" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section/:subpage" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section/:subpage/:subId" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
```

- [ ] **Step 2: Add debug/doctor routes (placeholder — MockApiProvider comes later)**

Add before the existing `/debug/doctor-pages` route (line 134):
```jsx
      {/* Mock doctor app — same DoctorPage, mock API, auth required in prod */}
      <Route path="/debug/doctor" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/patients/:patientId" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/review/:recordId" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/:section" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/:section/:subpage" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/:section/:subpage/:subId" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />
```

Note: These temporarily use real `ApiProvider`. Task 11 will swap them to `MockApiProvider`. RequireAuth skips auth in dev, requires login in production.

- [ ] **Step 3: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/App.jsx
git commit -m "feat: wrap doctor routes in ApiProvider, add /debug/doctor/* routes"
```

---

### Task 4: Migrate HomePage

**Files:**
- Modify: `frontend/web/src/pages/doctor/HomePage.jsx`

- [ ] **Step 1: Replace api import with useApi, useNavigate with useAppNavigate**

Replace imports:
```jsx
// Before:
import { getBriefing } from "../../api";
// After — remove the api import entirely, add:
import { useApi } from "../../api/ApiContext";
```

Replace navigate:
```jsx
// Before:
import { useNavigate } from "react-router-dom";
// After — keep useNavigate import but also add:
import { useAppNavigate } from "../../hooks/useAppNavigate";
```

Note: HomePage passes `useNavigate` to react-router's `useNavigate` only indirectly — it creates navigate via `useNavigate()`. Change:
```jsx
// Before:
const navigate = useNavigate();
// After:
const navigate = useAppNavigate();
```

Then remove `useNavigate` from the react-router import if no longer used directly.

Add `useApi` destructuring at top of component body:
```jsx
const { getBriefing } = useApi();
```

- [ ] **Step 2: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/HomePage.jsx
git commit -m "refactor: migrate HomePage to useApi + useAppNavigate"
```

---

### Task 5: Migrate DoctorPage shell

**Files:**
- Modify: `frontend/web/src/pages/doctor/DoctorPage.jsx`

DoctorPage imports `getTasks` and `getDoctorProfile`/`updateDoctorProfile` from api.js, and uses `useNavigate` in 7 places.

- [ ] **Step 1: Replace api imports with useApi**

Remove api imports and add:
```jsx
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
```

In the component body, destructure:
```jsx
const { getTasks, getDoctorProfile, updateDoctorProfile } = useApi();
```

Replace:
```jsx
const navigate = useNavigate();
```
With:
```jsx
const navigate = useAppNavigate();
```

Remove `useNavigate` from the react-router-dom import if no longer used directly (keep `useParams`).

- [ ] **Step 2: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/DoctorPage.jsx
git commit -m "refactor: migrate DoctorPage to useApi + useAppNavigate"
```

---

### Task 6: Migrate SettingsPage + subpages

**Files:**
- Modify: `frontend/web/src/pages/doctor/SettingsPage.jsx`
- Modify: `frontend/web/src/pages/doctor/subpages/TemplateSubpage.jsx`
- Modify: `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx`

- [ ] **Step 1: Migrate SettingsPage**

Replace:
```jsx
import { getDoctorProfile, updateDoctorProfile, getKnowledgeItems, deleteKnowledgeItem } from "../../api";
```
With:
```jsx
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
```

In `useSettingsState` hook — it receives API functions, so pass them from the parent. OR destructure `useApi()` inside `useSettingsState`. Since hooks can call other hooks, add at top of `useSettingsState`:
```jsx
const { getDoctorProfile, updateDoctorProfile } = useApi();
```

In `KnowledgeSubpageWrapper` function, add:
```jsx
const { getKnowledgeItems, deleteKnowledgeItem } = useApi();
```

Replace `const navigate = useNavigate()` with `const navigate = useAppNavigate()` in SettingsPage and KnowledgeSubpageWrapper.

- [ ] **Step 2: Migrate TemplateSubpage**

Replace its api imports with `useApi()` destructuring for `getTemplateStatus`, `uploadTemplate`, `deleteTemplate`.

- [ ] **Step 3: Migrate AddKnowledgeSubpage**

Replace its api import with `useApi()` destructuring for `addKnowledgeItem`.

- [ ] **Step 4: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/doctor/SettingsPage.jsx frontend/web/src/pages/doctor/subpages/TemplateSubpage.jsx frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx
git commit -m "refactor: migrate SettingsPage + subpages to useApi + useAppNavigate"
```

---

### Task 7: Migrate TasksPage

**Files:**
- Modify: `frontend/web/src/pages/doctor/TasksPage.jsx`

- [ ] **Step 1: Replace imports**

Replace:
```jsx
import { getTasks, patchTask, postponeTask, createTask, getPatients, getTaskRecord } from "../../api";
```
With:
```jsx
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
```

Add at top of component body:
```jsx
const { getTasks, patchTask, postponeTask, createTask, getPatients, getTaskRecord } = useApi();
```

Replace `const navigate = useNavigate()` with `const navigate = useAppNavigate()`.

Note: `TaskDetailView` is a separate function component inside TasksPage.jsx that calls `getTaskRecord` in a `useEffect`. It needs its own `const { getTaskRecord } = useApi()` call at the top of its body.

- [ ] **Step 2: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/TasksPage.jsx
git commit -m "refactor: migrate TasksPage to useApi + useAppNavigate"
```

---

### Task 8: Migrate PatientsPage + PatientDetail

**Files:**
- Modify: `frontend/web/src/pages/doctor/PatientsPage.jsx`
- Modify: `frontend/web/src/pages/doctor/patients/PatientDetail.jsx`

- [ ] **Step 1: Migrate PatientsPage**

Replace:
```jsx
import { getPatients, searchPatients, extractFileForChat } from "../../api";
```
With:
```jsx
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
```

Add in component body:
```jsx
const { getPatients, searchPatients, extractFileForChat } = useApi();
```

Replace `const navigate = useNavigate()` with `const navigate = useAppNavigate()`.

Note: `usePatientsState` is a custom hook that uses the API functions. Since it's defined in the same file, pass them via closure or call `useApi()` inside it directly.

- [ ] **Step 2: Migrate PatientDetail**

Replace:
```jsx
import { getRecords, exportPatientPdf, exportOutpatientReport, deletePatient, getPatientChat, replyToPatient } from "../../../api";
```
With:
```jsx
import { useApi } from "../../../api/ApiContext";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
```

Add in component body (or in `usePatientDetailState` hook):
```jsx
const { getRecords, exportPatientPdf, exportOutpatientReport, deletePatient, getPatientChat, replyToPatient } = useApi();
```

Replace `useNavigate()` calls with `useAppNavigate()`.

- [ ] **Step 3: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/doctor/PatientsPage.jsx frontend/web/src/pages/doctor/patients/PatientDetail.jsx
git commit -m "refactor: migrate PatientsPage + PatientDetail to useApi + useAppNavigate"
```

---

### Task 9: Migrate ReviewPage, ChatPage, InterviewPage

**Files:**
- Modify: `frontend/web/src/pages/doctor/ReviewPage.jsx`
- Modify: `frontend/web/src/pages/doctor/ChatPage.jsx`
- Modify: `frontend/web/src/pages/doctor/InterviewPage.jsx`

- [ ] **Step 1: Migrate ReviewPage**

Replace api imports with `useApi()` destructuring for: `getSuggestions`, `decideSuggestion`, `addSuggestion`, `triggerDiagnosis`, `finalizeReview`, `getTaskRecord`.

Replace `useNavigate()` with `useAppNavigate()`. Note: ReviewPage also uses `navigate(-1)` which passes through `useAppNavigate` unchanged (not a string starting with "/doctor").

- [ ] **Step 2: Migrate ChatPage**

Replace api imports with `useApi()` destructuring for: `sendChat`, `ocrImage`, `extractFileForChat`, `clearContext`, `importToInterview`, `textToInterview`.

ChatPage does NOT use `useNavigate` — no `useAppNavigate` change needed.

- [ ] **Step 3: Migrate InterviewPage**

Replace api imports with `useApi()` destructuring for: `doctorInterviewTurn`, `doctorInterviewConfirm`, `doctorInterviewCancel`, `doctorInterviewGetSession`, `confirmCarryForward`, `triggerDiagnosis`, `updateInterviewField`.

Replace `useNavigate()` with `useAppNavigate()`.

- [ ] **Step 4: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/doctor/ReviewPage.jsx frontend/web/src/pages/doctor/ChatPage.jsx frontend/web/src/pages/doctor/InterviewPage.jsx
git commit -m "refactor: migrate ReviewPage, ChatPage, InterviewPage to useApi"
```

---

### Task 10: Build mockApi.js + MockApiProvider

**Files:**
- Create: `frontend/web/src/api/mockApi.js`
- Create: `frontend/web/src/api/MockApiProvider.jsx`

- [ ] **Step 1: Create mockApi.js**

This file mirrors the api.js exports used by doctor pages. It imports MOCK_* data from MockData.jsx and returns it as resolved promises. Write operations mutate module-level arrays.

```jsx
// frontend/web/src/api/mockApi.js
import {
  MOCK_DOCTOR, MOCK_PATIENTS, MOCK_RECORDS, MOCK_TASKS,
  MOCK_SUGGESTIONS, MOCK_BRIEFING, MOCK_CHAT_MESSAGES,
  MOCK_OVERDUE, MOCK_INTERVIEW_STATE, MOCK_CARRY_FORWARD,
  MOCK_PATIENT_MESSAGES, MOCK_KNOWLEDGE_ITEMS, MOCK_FIELD_LABELS,
  MOCK_SETTINGS_TEMPLATES,
} from "../pages/doctor/debug/MockData";

// ── Mutable state (resets on page refresh) ──
let patients = [...MOCK_PATIENTS];
let records = [...MOCK_RECORDS];
let tasks = [...MOCK_TASKS];
let suggestions = [...MOCK_SUGGESTIONS];
let knowledgeItems = [...MOCK_KNOWLEDGE_ITEMS];

// ── Read operations ──

export async function getBriefing() {
  return { stats: MOCK_BRIEFING, cards: MOCK_OVERDUE.map(t => ({ type: "urgent", title: `${t.patient_name} ${t.title}`, context: t.due })) };
}

export async function getPatients() {
  return { items: patients };
}

export async function searchPatients(doctorId, q) {
  const filtered = patients.filter(p => p.name.includes(q));
  return { items: filtered };
}

export async function getRecords({ doctorId, patientId, limit = 100 }) {
  const filtered = patientId ? records.filter(r => r.patient_id === patientId) : records;
  return { items: filtered.slice(0, limit) };
}

export async function getTasks(doctorId, status = null) {
  const filtered = status ? tasks.filter(t => t.status === (status === "completed" ? "done" : status)) : tasks;
  return { items: filtered };
}

export async function getTaskRecord(recordId) {
  return records.find(r => r.id === Number(recordId)) || null;
}

export async function getSuggestions(recordId) {
  return { suggestions: suggestions.filter(s => s.record_id === Number(recordId)) };
}

export async function getKnowledgeItems() {
  return { items: knowledgeItems };
}

export async function getDoctorProfile() {
  return { name: MOCK_DOCTOR.doctorName, specialty: MOCK_DOCTOR.specialty };
}

export async function getTemplateStatus() {
  return { templates: MOCK_SETTINGS_TEMPLATES, hasCustom: false };
}

export async function getPatientChat() {
  return { messages: MOCK_PATIENT_MESSAGES };
}

export async function getPatientTimeline({ patientId }) {
  return { items: records.filter(r => r.patient_id === patientId) };
}

// ── Write operations ──

export async function createTask(doctorId, data) {
  const newTask = { id: Date.now(), doctor_id: doctorId, status: "pending", created_at: new Date().toISOString().slice(0, 10), ...data };
  tasks = [...tasks, newTask];
  return newTask;
}

export async function patchTask(taskId, doctorId, status) {
  tasks = tasks.map(t => t.id === taskId ? { ...t, status } : t);
  return {};
}

export async function postponeTask(taskId, doctorId, dueAt) {
  tasks = tasks.map(t => t.id === taskId ? { ...t, due_at: dueAt } : t);
  return {};
}

export async function decideSuggestion(suggestionId, decision, opts = {}) {
  suggestions = suggestions.map(s => s.id === suggestionId ? { ...s, decision, ...opts } : s);
  return {};
}

export async function addSuggestion(recordId, doctorId, section, content, detail) {
  const newSuggestion = { id: Date.now(), record_id: Number(recordId), section, content, detail: detail || "", decision: null, is_custom: true };
  suggestions = [...suggestions, newSuggestion];
  return newSuggestion;
}

export async function addKnowledgeItem(doctorId, content, category = "custom") {
  const newItem = { id: Date.now(), category, text: content, content, source: "doctor", created_at: new Date().toISOString().slice(0, 10), reference_count: 0 };
  knowledgeItems = [...knowledgeItems, newItem];
  return newItem;
}

export async function deleteKnowledgeItem(doctorId, itemId) {
  knowledgeItems = knowledgeItems.filter(i => i.id !== itemId);
  return {};
}

export async function deletePatient(patientId) {
  patients = patients.filter(p => p.id !== patientId);
  return {};
}

export async function deleteRecord(doctorId, recordId) {
  records = records.filter(r => r.id !== recordId);
  return {};
}

export async function updateRecord(doctorId, recordId, fields) {
  records = records.map(r => r.id === recordId ? { ...r, ...fields } : r);
  return records.find(r => r.id === recordId);
}

export async function updateDoctorProfile(doctorId, data) {
  return { ...data };
}

// ── Complex flows (canned responses) ──

export async function sendChat(payload) {
  return { reply: "这是模拟回复。Mock mode 不支持真实对话。", records: [], tasks: [] };
}

export async function doctorInterviewGetSession(sessionId) {
  return MOCK_INTERVIEW_STATE;
}

export async function doctorInterviewTurn() {
  return { ...MOCK_INTERVIEW_STATE, conversation: [...MOCK_INTERVIEW_STATE.conversation, { role: "assistant", content: "收到。请继续补充信息。" }] };
}

export async function doctorInterviewConfirm() {
  return { record_id: 999, status: "confirmed" };
}

export async function doctorInterviewCancel() {
  return {};
}

export async function confirmCarryForward() {
  return {};
}

export async function updateInterviewField() {
  return {};
}

export async function triggerDiagnosis() {
  return { status: "pending" };
}

export async function finalizeReview() {
  return { status: "reviewed" };
}

export async function clearContext() {
  return {};
}

export async function ocrImage() {
  return { text: "模拟OCR文本：患者张三，男，45岁，主诉头痛3天。" };
}

export async function extractFileForChat() {
  return { text: "模拟文件提取：出院小结内容。" };
}

export async function importToInterview() {
  return { session_id: "mock-import-session", fields: MOCK_INTERVIEW_STATE.collected };
}

export async function textToInterview() {
  return { session_id: "mock-text-session", fields: MOCK_INTERVIEW_STATE.collected };
}

export async function exportPatientPdf() {
  return {};
}

export async function exportOutpatientReport() {
  return {};
}

export async function uploadTemplate() {
  return {};
}

export async function deleteTemplate() {
  return {};
}

export async function replyToPatient() {
  return {};
}

export async function transcribeAudio() {
  return { text: "模拟语音转文字结果" };
}

export async function getWorkingContext() {
  return { messages: MOCK_CHAT_MESSAGES };
}
```

- [ ] **Step 2: Create MockApiProvider**

```jsx
// frontend/web/src/api/MockApiProvider.jsx
import { ApiProvider } from "./ApiContext";
import * as mockApi from "./mockApi";

const mockValue = { ...mockApi, isMock: true };

/**
 * Wraps children in ApiProvider with mock API functions.
 * Does NOT touch useDoctorStore — the real auth state stays intact.
 * In dev: RequireAuth passes through (no auth needed).
 * In prod: user must be logged in first, their real identity stays.
 * Either way, API calls go to mockApi which returns MOCK_* data
 * regardless of the doctorId passed.
 */
export function MockApiProvider({ children }) {
  return <ApiProvider value={mockValue}>{children}</ApiProvider>;
}
```

- [ ] **Step 3: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/api/mockApi.js frontend/web/src/api/MockApiProvider.jsx
git commit -m "feat: add mockApi + MockApiProvider for static-data mock mode"
```

---

### Task 11: Wire up debug routes to MockApiProvider

**Files:**
- Modify: `frontend/web/src/App.jsx`

- [ ] **Step 1: Replace ApiProvider with MockApiProvider on debug routes**

Add import:
```jsx
import { MockApiProvider } from "./api/MockApiProvider";
```

Replace the 6 `/debug/doctor/*` routes added in Task 3 — change `<ApiProvider>` to `<MockApiProvider>`:
```jsx
      {/* Mock doctor app — same DoctorPage, mock API, auth required in prod */}
      <Route path="/debug/doctor" element={<MobileFrame><RequireAuth><MockApiProvider><DoctorPage /></MockApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/patients/:patientId" element={<MobileFrame><RequireAuth><MockApiProvider><DoctorPage /></MockApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/review/:recordId" element={<MobileFrame><RequireAuth><MockApiProvider><DoctorPage /></MockApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/:section" element={<MobileFrame><RequireAuth><MockApiProvider><DoctorPage /></MockApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/:section/:subpage" element={<MobileFrame><RequireAuth><MockApiProvider><DoctorPage /></MockApiProvider></RequireAuth></MobileFrame>} />
      <Route path="/debug/doctor/:section/:subpage/:subId" element={<MobileFrame><RequireAuth><MockApiProvider><DoctorPage /></MockApiProvider></RequireAuth></MobileFrame>} />
```

- [ ] **Step 2: Update legacy /debug/doctor-pages to redirect**

Replace the existing MockPages route:
```jsx
      <Route path="/debug/doctor-pages" element={<MockPages />} />
```
With:
```jsx
      <Route path="/debug/doctor-pages" element={<Navigate to="/debug/doctor" replace />} />
```

Remove the MockPages import from App.jsx:
```jsx
// DELETE this line:
import MockPages from "./pages/doctor/debug/MockPages";
```

- [ ] **Step 3: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 4: Smoke test**

Run the dev server and verify:
1. `/debug/doctor` loads the home page with mock briefing data
2. Clicking "患者" navigates to `/debug/doctor/patients`
3. Clicking a patient navigates to `/debug/doctor/patients/:id`
4. `/doctor` still requires auth (or auto-logs in via DEV_MODE)

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/App.jsx
git commit -m "feat: wire /debug/doctor/* routes to MockApiProvider"
```

---

### Task 12: Delete dead mock code

**Files:**
- Delete contents of: `frontend/web/src/pages/doctor/debug/MockPages.jsx`
- Keep: `frontend/web/src/pages/doctor/debug/MockData.jsx` (consumed by mockApi.js)

- [ ] **Step 1: Replace MockPages.jsx with redirect stub**

Replace the entire file contents with:
```jsx
/**
 * @route /debug/doctor-pages
 * Legacy entry point — redirects to /debug/doctor.
 * The actual mock rendering is handled by MockApiProvider + DoctorPage
 * mounted at /debug/doctor/* in App.jsx.
 */
import { Navigate } from "react-router-dom";
export default function MockPages() {
  return <Navigate to="/debug/doctor" replace />;
}
```

- [ ] **Step 2: Build check**

Run: `cd frontend/web && npx vite build --logLevel error`
Expected: Clean build

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/debug/MockPages.jsx
git commit -m "refactor: replace MockPages with redirect, delete 730 lines of duplicate UI"
```

---

### Task 13: Evaluate and clean up bridging subpages

**Files:**
- Evaluate: `frontend/web/src/pages/doctor/subpages/HomeSubpage.jsx`
- Evaluate: `frontend/web/src/pages/doctor/subpages/TaskDetailSubpage.jsx`
- Evaluate: `frontend/web/src/pages/doctor/subpages/ReviewSubpage.jsx`
- Evaluate: `frontend/web/src/pages/doctor/subpages/SettingsListSubpage.jsx`

- [ ] **Step 1: Evaluate each bridging subpage**

For each subpage, check: does the real page still import and use it? If yes, keep it (it's a useful presentational layer). If only MockPages used it, delete it.

Currently after Refactor B:
- `HomeSubpage` — used by `HomePage.jsx` → **keep** (clean separation of presentation from API)
- `TaskDetailSubpage` — used by `TasksPage.jsx` TaskDetailView → **keep**
- `ReviewSubpage` — used by `ReviewPage.jsx` → **keep** (separates suggestion UI from polling)
- `SettingsListSubpage` — used by `SettingsPage.jsx` → **keep** (separates layout from dialogs)

All four are still used by real pages. No deletion needed.

- [ ] **Step 2: Commit (if any changes made)**

```bash
git commit -m "chore: evaluate bridging subpages — all retained for real page use"
```
