# Post-Visit Patient Portal (ADR 0020) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the patient portal from a basic pre-consultation tool into an AI agent-centric post-visit experience with diagnosis viewing, bidirectional messaging, symptom reporting, and follow-up uploads.

**Architecture:** Domain layer extraction — new `src/domain/patient_lifecycle/` module owns business logic (triage, treatment plan derivation, task generation, upload matching). Web channel stays thin. Existing 4-tab patient layout (主页|病历|任务|设置) kept; each tab upgraded.

**Tech Stack:** Python 3.9 (FastAPI), SQLAlchemy, SQLite, React (MUI 7), Qwen3:32b LLM

**Spec:** `docs/specs/2026-03-21-post-visit-patient-portal-design.md`

**UI Reference:** `docs/specs/2026-03-21-mockups/patient-portal-upgrade.html`

**Design System:** `frontend/web/UI-DESIGN.md` — use TYPE/COLOR/ICON tokens, shared components

---

## Build Order

Phased so each phase is independently deployable and testable:

1. **DB schema changes** (Tasks 1-2) — foundation
2. **Read-only views** (Tasks 3-5) — patient sees diagnosis + treatment plan
3. **Patient tasks** (Tasks 6-8) — auto-generated tasks, task tab
4. **Bidirectional messaging** (Tasks 9-11) — doctor replies, polling
5. **AI triage** (Tasks 12-14) — smart chat, follow-up interviews
6. **Upload matching** (Task 15) — AI-guided uploads linked to tasks

---

### Task 1: DB Schema — Extend `doctor_tasks` for Patient Tasks

**Files:**
- Modify: `src/db/models/tasks.py:31-65`
- Modify: `src/db/engine.py` (create_tables call if needed)

- [ ] **Step 1: Add columns to DoctorTask model**

In `src/db/models/tasks.py`, add three columns after `updated_at` (line 46):

```python
target = Column(String(16), nullable=False, server_default="doctor")
source_type = Column(String(32), nullable=True)
source_id = Column(Integer, nullable=True)
```

- [ ] **Step 2: Add CHECK constraints**

Add to the `__table_args__` tuple (after line 54):

```python
CheckConstraint("target IN ('doctor','patient')", name="ck_doctor_tasks_target"),
CheckConstraint("source_type IS NULL OR source_type IN ('manual','rule','diagnosis_auto')", name="ck_doctor_tasks_source_type"),
```

- [ ] **Step 3: Add index for patient task queries**

```python
Index("ix_tasks_target_patient_status", "target", "patient_id", "status"),
```

- [ ] **Step 4: Run ALTER TABLE for existing DB**

```sql
ALTER TABLE doctor_tasks ADD COLUMN target VARCHAR(16) NOT NULL DEFAULT 'doctor';
ALTER TABLE doctor_tasks ADD COLUMN source_type VARCHAR(32);
ALTER TABLE doctor_tasks ADD COLUMN source_id INTEGER;
```

- [ ] **Step 5: Commit**

```bash
git add src/db/models/tasks.py
git commit -m "feat(p5): add target/source columns to doctor_tasks for patient tasks"
```

---

### Task 2: DB Schema — Extend `patient_messages` for Triage

**Files:**
- Modify: `src/db/models/patient_message.py:17-40`
- Modify: `src/db/crud/patient_message.py` (update `save_patient_message` param)
- Modify: `src/channels/web/patient_portal.py:206` (direction="inbound" → source="patient")

- [ ] **Step 1: Add `source` column alongside `direction` (keep `direction` for backward compat)**

Add new columns after `direction` (line 29). Keep `direction` during migration —
remove it in a later cleanup after all callers are updated:

```python
source = Column(String(16), nullable=False)  # patient/ai/doctor
sender_id = Column(String(64), nullable=True)  # doctor_id when source=doctor
reference_id = Column(Integer, nullable=True)  # FK to medical_records.id
triage_category = Column(String(32), nullable=True)
structured_data = Column(Text, nullable=True)  # JSON
ai_handled = Column(Boolean, nullable=True, server_default="1")
```

- [ ] **Step 2: Update CHECK constraint**

Replace `ck_patient_messages_direction` with:

```python
CheckConstraint("source IN ('patient','ai','doctor')", name="ck_patient_messages_source"),
```

- [ ] **Step 3: Run ALTER TABLE + backfill**

```sql
ALTER TABLE patient_messages ADD COLUMN source VARCHAR(16);
ALTER TABLE patient_messages ADD COLUMN sender_id VARCHAR(64);
ALTER TABLE patient_messages ADD COLUMN reference_id INTEGER;
ALTER TABLE patient_messages ADD COLUMN triage_category VARCHAR(32);
ALTER TABLE patient_messages ADD COLUMN structured_data TEXT;
ALTER TABLE patient_messages ADD COLUMN ai_handled BOOLEAN DEFAULT 1;
UPDATE patient_messages SET source = CASE WHEN direction = 'inbound' THEN 'patient' ELSE 'ai' END;
-- Then drop direction column or keep for backward compat
```

- [ ] **Step 4: Commit**

```bash
git add src/db/models/patient_message.py
git commit -m "feat(p5): extend patient_messages with source/triage fields"
```

---

### Task 3: Domain — Treatment Plan Derivation

**Files:**
- Create: `src/domain/patient_lifecycle/__init__.py`
- Create: `src/domain/patient_lifecycle/treatment_plan.py`

- [ ] **Step 1: Create module init**

```python
"""Patient lifecycle domain — triage, treatment plans, tasks, uploads."""
from __future__ import annotations
```

- [ ] **Step 2: Implement `derive_treatment_plan()`**

`treatment_plan.py` — reads confirmed `diagnosis_results`, extracts approved
workup/treatment items from `doctor_decisions` JSON. Returns structured dict
with `workup_items`, `treatment_items`, `red_flags`, `diagnosis_name`,
`confirmed_at`, `doctor_name`.

Query: `diagnosis_results WHERE status=confirmed AND record.patient_id=X
ORDER BY confirmed_at DESC LIMIT 1`.

Parse `ai_output` JSON for the raw items, cross-reference with
`doctor_decisions` JSON to filter only approved (confirmed) items.

- [ ] **Step 3: Commit**

```bash
git add src/domain/patient_lifecycle/
git commit -m "feat(p5): treatment plan derivation from confirmed diagnosis"
```

---

### Task 4: API — Patient Treatment Plan & Record Detail

**Files:**
- Modify: `src/channels/web/patient_portal.py:142-174` (GET /api/patient/records)
- Create: `src/channels/web/patient_portal_tasks.py` (new router for task/plan endpoints)

- [ ] **Step 1: Create patient tasks/plan router**

New file `patient_portal_tasks.py` with:
- `GET /api/patient/tasks` — query `doctor_tasks WHERE target='patient' AND patient_id=X`, return as JSON
- `GET /api/patient/records/{record_id}` — existing record data + diagnosis + treatment plan if confirmed diagnosis exists for that record
- Modify existing `GET /api/patient/records` (list endpoint in `patient_portal.py:142-174`) to include `diagnosis_status` field per record (null/pending/confirmed)

- [ ] **Step 2: Register router in patient_portal.py**

Add `router.include_router(patient_tasks_router)` in `patient_portal.py`.

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/patient_portal_tasks.py src/channels/web/patient_portal.py
git commit -m "feat(p5): patient tasks and record detail API endpoints"
```

---

### Task 5: Frontend — 病历 Tab Record Detail with Diagnosis

**Files:**
- Modify: `frontend/web/src/pages/PatientPage.jsx:310-341` (RecordDetailView)
- Modify: `frontend/web/src/api.js` (add getPatientRecordDetail)

- [ ] **Step 1: Add API function**

In `api.js`, add:
```javascript
export async function getPatientRecordDetail(token, recordId) {
  return patientRequest(`/api/patient/records/${recordId}`, token);
}
```

- [ ] **Step 2: Upgrade RecordDetailView**

In `PatientPage.jsx`, modify `RecordDetailView` to:
- Fetch record detail via `getPatientRecordDetail(token, recordId)`
- If response includes `diagnosis` object, render:
  - `ContentCard` with diagnosis name + `StatusBadge` (已确认/待确认)
  - Treatment plan items list with `TYPE.heading` section header
  - Red flag warning card (`COLOR.dangerLight` bg + `COLOR.danger` border-left)
- Use `TYPE`/`COLOR` tokens from `theme.js`

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/PatientPage.jsx frontend/web/src/api.js
git commit -m "feat(p5): record detail shows diagnosis and treatment plan"
```

---

### Task 6: Domain — Patient Task Auto-Generation

**Files:**
- Create: `src/domain/patient_lifecycle/task_generation.py`
- Modify: `src/channels/web/ui/diagnosis_handlers.py` (hook into confirm endpoint)

- [ ] **Step 1: Implement `generate_patient_tasks()`**

`task_generation.py` — given a confirmed `DiagnosisResult`:
1. Extract approved workup items → create tasks with due dates based on urgency
   (急诊: +1d, 紧急: +3d, 常规: +7d)
2. Extract approved treatment items → create medication/follow-up tasks
3. Dedupe: skip items that already have a pending/completed task with same
   `source_id` + `task_type`
4. All tasks: `target='patient'`, `source_type='diagnosis_auto'`,
   `source_id=diagnosis_result.id`

- [ ] **Step 2: Hook into diagnosis confirmation**

In `diagnosis_handlers.py`, after the confirm endpoint saves doctor decisions,
call `generate_patient_tasks(diagnosis_result, session)`.

- [ ] **Step 3: Commit**

```bash
git add src/domain/patient_lifecycle/task_generation.py src/channels/web/ui/diagnosis_handlers.py
git commit -m "feat(p5): auto-generate patient tasks on diagnosis confirmation"
```

---

### Task 7: API — Patient Task Endpoints

**Files:**
- Modify: `src/channels/web/patient_portal_tasks.py`

- [ ] **Step 1: Add task completion endpoint**

`POST /api/patient/tasks/{task_id}/complete` — verify task belongs to patient,
mark status='completed', set `updated_at`. Return updated task.

- [ ] **Step 2: Commit**

```bash
git add src/channels/web/patient_portal_tasks.py
git commit -m "feat(p5): patient task completion endpoint"
```

---

### Task 8: Frontend — 任务 Tab with TaskChecklist

**Files:**
- Create: `frontend/web/src/components/TaskChecklist.jsx`
- Modify: `frontend/web/src/pages/PatientPage.jsx:720-728` (TasksTab placeholder)
- Modify: `frontend/web/src/api.js`

- [ ] **Step 1: Add API functions**

```javascript
export async function getPatientTasks(token) {
  return patientRequest("/api/patient/tasks", token);
}
export async function completePatientTask(token, taskId) {
  return patientRequest(`/api/patient/tasks/${taskId}/complete`, token, { method: "POST" });
}
```

- [ ] **Step 2: Create TaskChecklist component**

`TaskChecklist.jsx` — receives task list, renders:
- Circular checkboxes: pending 20px `1.5px solid COLOR.border`, done `COLOR.success` bg
- Title: `TYPE.action` (15/500) per ListCard pattern
- Due date: `TYPE.caption` (12), overdue `COLOR.danger`
- Upload action: `AppButton variant="ghost" size="sm"` on workup tasks
- Urgency badge: `StatusBadge` with `colorMap: {紧急: COLOR.danger, 常规: COLOR.text4}`

- [ ] **Step 3: Replace TasksTab placeholder**

Replace the EmptyState placeholder (lines 720-728) with:
- `SectionLabel` "待完成 · N项" / "已完成 · N项"
- `TaskChecklist` for pending tasks
- `TaskChecklist` for completed tasks (strikethrough)
- Diagnosis context card at bottom (ContentCard + StatusBadge + red flag)
- Keep `EmptyState` for when there are no tasks

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/components/TaskChecklist.jsx frontend/web/src/pages/PatientPage.jsx frontend/web/src/api.js
git commit -m "feat(p5): patient tasks tab with TaskChecklist component"
```

---

### Task 9: Backend — Bidirectional Messaging

**Files:**
- Modify: `src/channels/web/patient_portal.py:177-226` (POST /api/patient/message)
- Create: `src/channels/web/patient_portal_chat.py`
- Modify: `src/channels/web/ui/patient_detail_handlers.py` (add chat panel endpoints)

- [ ] **Step 1: Create patient chat polling endpoint**

`patient_portal_chat.py`:
- `GET /api/patient/chat/messages?since={last_id}` — returns messages newer than
  `last_id`, ordered by `created_at ASC`. Include `source` field so frontend
  can distinguish patient/ai/doctor messages.

- [ ] **Step 2: Add doctor reply endpoint**

Add to existing `src/channels/web/ui/patient_detail_handlers.py` (already
registered in `ui/__init__.py`, so new routes auto-included):
- `GET /api/manage/patients/{patient_id}/chat` — full conversation thread
- `POST /api/manage/patients/{patient_id}/reply` — doctor types reply,
  creates `PatientMessage` with `source='doctor'`, `sender_id=doctor_id`.
  Returns the created message.

- [ ] **Step 3: Register routers**

Include `patient_portal_chat.py` router in `patient_portal.py`.
Include doctor chat endpoints in `ui/__init__.py`.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/patient_portal_chat.py src/channels/web/patient_portal.py src/channels/web/ui/
git commit -m "feat(p5): bidirectional messaging - polling endpoint + doctor reply"
```

---

### Task 10: Frontend — DoctorBubble Component

**Files:**
- Create: `frontend/web/src/components/DoctorBubble.jsx`

- [ ] **Step 1: Create DoctorBubble**

Props: `doctorName`, `content`, `timestamp`

Render:
- Doctor name label: `TYPE.caption` (12), `COLOR.success`, `fontWeight: 500`
- Bubble: `bgcolor: "#fff"`, `border: "0.5px solid ${COLOR.success}"`,
  `borderRadius: "8px"`, `TYPE.body` (14/400), same max-width/padding as
  existing chat bubbles

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/components/DoctorBubble.jsx
git commit -m "feat(p5): DoctorBubble component for doctor replies in chat"
```

---

### Task 11: Frontend — 主页 Tab Chat Upgrade (Messaging)

**Files:**
- Modify: `frontend/web/src/pages/PatientPage.jsx:229-303` (ChatTab)
- Modify: `frontend/web/src/api.js`

- [ ] **Step 1: Add polling API function**

```javascript
export async function getPatientChatMessages(token, sinceId) {
  const params = sinceId ? `?since=${sinceId}` : "";
  return patientRequest(`/api/patient/chat/messages${params}`, token);
}
```

- [ ] **Step 2: Upgrade ChatTab with polling + message types**

Modify `ChatTab` to:
- Poll `getPatientChatMessages` every 10s on active 主页 tab, 60s on other tabs
  (useEffect + setInterval, adjust interval based on current tab)
- Store `lastMessageId` in localStorage for resume
- Render three bubble types based on `source`:
  - `patient` → green bubble (existing style)
  - `ai` → white bubble (existing style)
  - `doctor` → `DoctorBubble` component
- Show unread badge on 主页 tab when messages arrive on other tabs
- Keep existing quick action cards and chat input

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/PatientPage.jsx frontend/web/src/api.js
git commit -m "feat(p5): chat tab with polling, doctor replies, message types"
```

---

### Task 12: Domain — AI Triage System

**Files:**
- Create: `src/domain/patient_lifecycle/triage.py`
- Test: `tests/integration/test_patient_triage.py` (safety-critical)

- [ ] **Step 1: Implement triage classifier**

`triage.py`:
- `classify(message, patient_context) → TriageResult` — LLM call with patient
  context (treatment plan, tasks, medications, recent messages, diagnosis).
  Returns `category` (informational/symptom_report/side_effect/general_question/urgent)
  and `confidence`.
- If confidence < 0.7 → default to `general_question` (escalate)
- Ambiguous messages → classify as most clinical category

- [ ] **Step 2: Implement triage handlers**

- `handle_informational(message, context)` → LLM generates answer using patient
  context, returns response text. `ai_handled=True`.
- `handle_escalation(message, context, category)` → LLM generates conversation
  summary JSON (patient_question, conversation_context, patient_status,
  reason_for_escalation, suggested_action). Creates `PatientMessage` with
  `ai_handled=False`. Checks rate limit (3 per 6h window). Batches
  notifications (10-min window).
- `handle_urgent(message, context)` → immediate notification, safety guidance
  to patient. Bypasses rate limit.

- [ ] **Step 3: Implement follow-up handoff**

For `symptom_report`/`side_effect`: create interview session with
`mode='follow_up'`, pre-fill patient context. Reuse existing interview pipeline.

Also update `src/channels/web/patient_interview_routes.py` to handle
`mode='follow_up'` — narrower scope (symptom, onset, severity, duration,
trigger) instead of full 7-field collection. Check if `record_type: 'follow_up'`
needs to be added to the medical_records model's allowed values.

- [ ] **Step 4: Write integration test for triage classification**

`tests/integration/test_patient_triage.py` — test that clinical messages
are not classified as informational (safety-critical).

- [ ] **Step 5: Commit**

```bash
git add src/domain/patient_lifecycle/triage.py tests/integration/test_patient_triage.py
git commit -m "feat(p5): AI triage system with classification and escalation"
```

---

### Task 13: Backend — Agent-Style Chat Endpoint

**Files:**
- Modify: `src/channels/web/patient_portal_chat.py`

- [ ] **Step 1: Add POST /api/patient/chat endpoint**

Replaces `POST /api/patient/message` as the primary chat endpoint:
1. Receive patient message text
2. Call `triage.classify(message, patient_context)`
3. Route to appropriate handler (informational → respond, clinical → follow-up
   interview, urgent → escalate)
4. Persist all messages (patient input + AI response) to `patient_messages`
   with appropriate `source` and `triage_category`
5. Return AI response to patient

Keep old `/api/patient/message` for backward compatibility but have it delegate
to the new triage flow.

- [ ] **Step 2: Commit**

```bash
git add src/channels/web/patient_portal_chat.py
git commit -m "feat(p5): agent-style chat endpoint with triage routing"
```

---

### Task 14: Frontend — 主页 Tab Triage Features

**Files:**
- Modify: `frontend/web/src/pages/PatientPage.jsx:229-303` (ChatTab)

- [ ] **Step 1: Add triage UI elements**

Upgrade ChatTab to handle triage-enriched responses:
- Inline `DiagnosisCard` (ContentCard + StatusBadge + AppButton) for
  proactive diagnosis notifications
- Triage escalation summary cards (warningLight bg + warning border-left)
  showing "已通知张医生" with structured symptom data
- `SuggestionChips` for structured triage collection (when AI asks follow-up
  questions, backend can return suggestion options)
- Buttons route to 任务 tab ("查看治疗方案") or 病历 tab ("查看病历")

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/PatientPage.jsx
git commit -m "feat(p5): triage UI - diagnosis cards, escalation summaries, suggestion chips"
```

---

### Task 15: Domain — Upload Matcher

**Files:**
- Create: `src/domain/patient_lifecycle/upload_matcher.py`
- Modify: `src/channels/web/patient_portal.py:244-273` (POST /api/patient/upload)

- [ ] **Step 1: Implement upload matcher**

`upload_matcher.py`:
- `match_upload(extracted_content, pending_tasks) → MatchResult` — LLM matches
  extracted content (from Vision LLM, already built) against pending workup tasks
- Returns: `matched_task_id`, `confidence`, `suggested_confirmation_text`
- If no match or ambiguous → return pending task list for patient selection

- [ ] **Step 2: Modify upload endpoint**

Extend `POST /api/patient/upload` to:
1. Run existing Vision LLM extraction (already built)
2. Call `upload_matcher.match(extracted, pending_tasks)`
3. If confident match → return confirmation prompt
4. Add `POST /api/patient/upload-result` — patient confirms match →
   mark task completed → notify doctor

- [ ] **Step 3: Commit**

```bash
git add src/domain/patient_lifecycle/upload_matcher.py src/channels/web/patient_portal.py
git commit -m "feat(p5): AI-guided upload matching to pending tasks"
```

---

### Task 16: Doctor Side — Patient Chat Panel

**Files:**
- Modify: `frontend/web/src/pages/doctor/PatientDetail.jsx`
- Modify: `frontend/web/src/api.js`

- [ ] **Step 1: Add doctor API functions**

```javascript
export async function getPatientChat(patientId) {
  return apiFetch(`/api/manage/patients/${patientId}/chat`);
}
export async function replyToPatient(patientId, text) {
  return apiFetch(`/api/manage/patients/${patientId}/reply`, {
    method: "POST", body: JSON.stringify({ text }),
  });
}
```

- [ ] **Step 2: Add chat panel to PatientDetail**

In `PatientDetail.jsx`, add a chat section:
- Default: triage summary view (only escalated items with badges)
- Expandable: full conversation thread
- Reply input at bottom with `AppButton variant="primary"`
- Message types: patient (green bubble), AI (white), doctor (DoctorBubble)
- Unread indicator on patient list when actionable message exists

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/PatientDetail.jsx frontend/web/src/api.js
git commit -m "feat(p5): doctor-side patient chat panel with triage summary"
```

---

### Task 17: Notification Integration

**Files:**
- Modify: `src/domain/patient_lifecycle/triage.py`
- Modify: `src/domain/tasks/notifications.py` (extend for patient-side)

- [ ] **Step 1: Hook triage escalation into notification system**

Wire `handle_escalation()` and `handle_urgent()` to existing `infra/notify/`
system. Implement:
- Escalation rate limiting (3 per 6h per patient, tracked in-memory or DB)
- Batch notifications (10-min window, aggregate count)
- Urgent bypasses both limits

- [ ] **Step 2: Add patient notification on diagnosis confirmation**

When doctor confirms diagnosis → notify patient: "张医生已确认您的诊断"
(proactive message saved as `PatientMessage` with `source='ai'`).

- [ ] **Step 3: Commit**

```bash
git add src/domain/patient_lifecycle/triage.py src/domain/tasks/notifications.py
git commit -m "feat(p5): notification integration with rate limiting and batching"
```

---

## Notes

- **Testing policy**: integration tests only for safety-critical modules (triage
  classification in Task 12). Other modules follow project convention — no unit
  tests unless explicitly asked.
- **No Alembic**: use `ALTER TABLE` for schema changes, document in commit messages.
- **UI-DESIGN.md**: all frontend work uses `TYPE`/`COLOR`/`ICON` tokens from
  `theme.js`. Shared components from `frontend/web/src/components/`.
- **LLM calls**: use `dispatch()` from `services/ai/agent.py`. Mock target for
  tests: `services.ai.agent.dispatch`.
- **Active nav color**: fix `#07C160` → `COLOR.success` (#52C772) in
  `BottomNavigation` during Task 8 or 11.
