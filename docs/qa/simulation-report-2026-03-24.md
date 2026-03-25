# Doctor QA Simulation Report — 2026-03-24

**Tester**: Claude (automated via gstack browse)
**Persona**: Dr. Chen (陈医生), new doctor registration via invite code
**Target**: `http://localhost:5173` (Vite dev + uvicorn backend, deepseek provider)
**Commit**: `96798a2` (Plan-and-Act architecture, SOAP schema)

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| P0 (blocker) | 1 | Task creation broken — type mismatch |
| P1 (major) | 3 | Working context 500, chat routing error, patient name not linked |
| P2 (minor) | 3 | Default specialty, no onboarding, patient list stale during interview |
| **Total** | **7** | |

**Overall**: Core flows (registration, patient creation via interview, record SOAP
collection, settings) work well. The Plan-and-Act interview flow is impressive — AI
correctly parses multi-turn input into structured SOAP fields. Main issues are in task
creation and chat routing, both likely caused by the recent architecture migration.

---

## Bugs

### BUG-1: Task creation fails — task_type enum mismatch (P0)

- **Section**: Tasks → New Task
- **Steps**:
  1. Navigate to `/doctor/tasks/new`
  2. Fill form with default type "随访" (follow_up)
  3. Click "创建"
- **Expected**: Task created successfully
- **Actual**: Error: `task_type must be one of {'review', 'general'}`
- **Root cause**: Frontend offers 4 task types (follow_up, medication, checkup, general)
  but backend `TaskType` enum only allows `general` and `review`. The CHECK constraint
  `ck_doctor_tasks_task_type` rejects anything else.
- **Fix**: Either expand backend `TaskType` enum to include the full set, or limit
  frontend dropdown to `general`/`review`.

### BUG-2: Chat "今日摘要" triggers routing error (P1)

- **Section**: Chat
- **Steps**:
  1. Navigate to `/doctor/chat`
  2. "今日摘要" chip auto-sends on page load
- **Expected**: AI returns daily summary
- **Actual**: Error: `请求失败：Input should be 'query_record', 'create_record',
  'query_task', 'create_task', 'query_patient' or 'general'`
- **Root cause**: The "今日摘要" action sends an intent type that the Plan-and-Act
  router doesn't recognize. The old router likely handled this as a special case.
- **Fix**: Map "today_summary" to the appropriate action type in the router, or handle
  as `general`.

### BUG-3: Working context endpoint returns 500 (P1)

- **Section**: Cross-cutting (header polling)
- **Steps**: Automatic — `GET /api/manage/working-context` called every ~15s
- **Expected**: Returns current patient context, pending drafts
- **Actual**: HTTP 500
- **Impact**: WorkingContextHeader never shows pending drafts or current patient.
  Silent background error polluting logs.
- **Fix**: Investigate server-side error in the working-context handler.

### BUG-4: Record created without patient name linkage (P1)

- **Section**: Chat → Query
- **Steps**:
  1. Create patient "王小明" via interview flow
  2. In chat, ask "查询王小明的病历"
- **Expected**: Returns 王小明's record with patient name
- **Actual**: AI says "当前病历未记录患者姓名" — the record exists but patient_name
  isn't stored in the record or the query can't match by name
- **Root cause**: The interview flow creates the record but may not link the patient_id
  correctly, or the query handler doesn't join patient table.

### BUG-5: Specialty auto-assigned without user input (P2)

- **Section**: Settings
- **Steps**:
  1. Register without selecting specialty
  2. Go to Settings
- **Expected**: Specialty field empty or "未设置"
- **Actual**: Shows "神经外科" (neurosurgery)
- **Root cause**: Likely a default value in the registration API or invite code mapping.

### BUG-6: No onboarding for new doctor (P2)

- **Section**: Home (Briefing)
- **Steps**: First login after registration
- **Expected**: Some guidance (welcome message, "get started" flow, tour)
- **Actual**: Empty dashboard with all-zero stats, no hints
- **Impact**: New doctors may not know where to start.

### BUG-7: Patient list doesn't refresh during interview (P2)

- **Section**: Patients → New Patient (interview mode)
- **Steps**:
  1. Click "新建患者" → opens interview chat
  2. Complete the interview and generate record
- **Expected**: Left sidebar patient list updates in real-time
- **Actual**: Shows "0位患者" until navigation away and back
- **Root cause**: Patient list query not re-triggered after patient/record creation in
  the interview subview.

---

## What Works Well

1. **Registration flow**: Clean, fast, invite-code gated. Redirects to dashboard
   immediately.
2. **SOAP interview collection**: The AI-driven interview flow is excellent — correctly
   parses multi-turn natural language into structured SOAP fields (chief complaint,
   present illness, past history, allergy, family history, personal history, physical
   exam, diagnosis, treatment plan). Progress counter (7/13) and suggestion chips guide
   the doctor.
3. **Patient detail page**: Good information hierarchy — demographics header, record tabs
   (全部/病历/检验/问诊), action buttons (PDF export, outpatient report, labels).
4. **Settings page**: Well-organized with account, tools, and general sections. Knowledge
   base categories match the enum.
5. **Mobile responsive**: Clean layout, bottom nav adapts correctly, content stacks
   properly.
6. **Empty states**: Friendly messages with actionable hints (e.g., "点击新建患者或在
   聊天中创建").

---

## Console / Network Errors

| URL | Status | Context |
|-----|--------|---------|
| `GET /api/manage/working-context` | 500 | Polling every 15s, always fails |
| `POST /api/tasks` | 422 | Task type validation failure |
| `POST /api/records/chat` | 422 | "今日摘要" routing failure |

---

## Fix Status

| Bug | Status | Fix |
|-----|--------|-----|
| BUG-1 (P0) | **FIXED** | Expanded `TaskType` enum + CHECK + `_VALID_TASK_TYPES` to include follow_up, medication, checkup |
| BUG-2 (P1) | **FIXED** | Added `daily_summary` intent type + dedicated handler + `action_hint` bypass in router |
| BUG-3 (P1) | **CLOSED** | Not reproducible — transient startup timing issue |
| BUG-4 (P1) | **FIXED** | `query_record` handler now returns SOAP fields + patient name context to LLM |
| BUG-5 (P2) | **FIXED** | Removed hardcoded "神经外科" default in `LoginPage.jsx` registration call |
| BUG-6 (P2) | **FIXED** | Added onboarding welcome card in `BriefingSection.jsx` when all stats are 0 |
| BUG-7 (P2) | **CLOSED** | Expected behavior — patient not persisted until interview confirm |

---

## Test Environment

- macOS Darwin 25.3.0
- Python 3.13.3 (local), Python 3.10 (production)
- Browser: Chromium via gstack headless browse
- Frontend: Vite dev server (port 5173)
- Backend: uvicorn (port 8000), DeepSeek LLM provider
- DB: SQLite (local dev)
