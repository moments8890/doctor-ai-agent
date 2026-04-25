# Design: Post-Visit Patient Portal (ADR 0020 / F3.1)

> Generated: 2026-03-21 | Status: DRAFT

## Overview

Upgrade the existing patient portal from a basic pre-consultation tool into an
AI agent-centric post-visit experience. The AI agent handles triage, proactive
notifications, and structured symptom collection. Patients view diagnoses,
treatment plans, and tasks — all within the existing 4-tab layout.

## Scope

All four ADR 0020 sub-features:

1. **Diagnosis/treatment view** — patient sees confirmed diagnosis + treatment plan
2. **Bidirectional messaging** — doctor replies visible in patient chat, AI mediates
3. **Symptom/side-effect reporting** — AI collects structured details, creates follow-up records
4. **Follow-up uploads** — AI-guided, matched to pending treatment/workup items

## Architecture: Domain Layer Extraction

New domain module `src/domain/patient_lifecycle/` owns all business logic.
Web channel layer stays thin (auth + routing).

```
src/domain/patient_lifecycle/
    __init__.py              # public API
    triage.py                # classify → collect → escalate or answer
    treatment_plan.py        # derive patient-visible plan from confirmed diagnosis
    upload_matcher.py        # match upload to pending workup/treatment items
    task_generation.py       # auto-generate patient tasks from confirmed treatment

src/channels/web/
    patient_portal.py        # existing — add new routes, keep thin
    patient_portal_chat.py   # new — agent-style chat, delegates to triage

src/db/models/
    tasks.py                 # add target, source_type, source_id to DoctorTask
    patient_message.py       # replace direction with source enum
```

### Data Flow

```
Patient message
    → patient_portal_chat.py (HTTP, auth)
    → triage.classify(message, patient_context)
    → informational: answer directly from records/tasks/plan
    → clinical: structured follow-up → interview pipeline (mode: follow_up)
        → MedicalRecordDB (record_type: follow_up) → review queue → notify doctor
    → upload: upload_matcher.match(file, pending_tasks) → confirm → mark done → notify

Doctor confirms diagnosis
    → treatment_plan.derive(diagnosis_result) → patient-visible plan (read view)
    → task_generation.generate(plan) → patient tasks in tasks table
    → notify patient: "张医生已确认您的诊断"
```

## AI Triage System

### Classification

| Category | AI Action | Doctor Notified? |
|----------|-----------|-----------------|
| `informational` | LLM answers using patient context (records/tasks/plan injected) | No |
| `symptom_report` | Hand off to interview pipeline (mode: follow_up) | Yes |
| `side_effect` | Hand off to interview pipeline + flag medication | Yes, with urgency |
| `general_question` | LLM answers if within plan context; if not, summarizes chat and escalates | Only if escalated (with summary) |
| `urgent` | Red flag detection → immediate escalation | Yes, high priority |

### Triage v1 (Moderate)

- **All messages go through LLM triage** — there is no hardcoded routing.
  The LLM classifies the message and generates the appropriate response.
- For `informational` queries: LLM answers with patient context injected
  (treatment plan, tasks, diagnosis, medications). E.g., "我的药怎么吃？"
  → LLM sees the treatment plan and answers "甲钴胺片，每日3次，还剩12天"
- For clinical content (symptoms, side effects): AI hands off to existing
  interview pipeline with `mode: follow_up` and narrower scope
- Follow-up interview collects: symptom, onset, severity, duration, pattern,
  related symptoms, suspected trigger (matched from treatment plan)
- For unrelated new complaints (not matching current treatment plan): still
  collect structured data, create follow-up record, escalate to doctor
- Output: `MedicalRecordDB` with `record_type: follow_up`, enters review queue
- Doctor gets structured triaged report, not raw chat text

### Classification Rules

- **Ambiguous messages** (mix of informational + clinical): classify as the
  **most clinical** category. "What's my dosage? Also my head hurts" →
  `symptom_report`, not `informational`. When in doubt, escalate.
- **Confidence threshold**: if LLM classification confidence < 0.7, default
  to `general_question` (escalate to doctor).
- **Escalation with summary**: when any message is escalated to doctor, the
  LLM generates a structured summary of the conversation context:
  ```json
  {
    "patient_question": "原始问题",
    "conversation_context": "最近3-5轮对话摘要",
    "patient_status": "当前治疗方案和任务状态",
    "reason_for_escalation": "为什么AI无法处理",
    "suggested_action": "建议医生做什么（可选）"
  }
  ```
  This summary is stored in `structured_data` on the message and shown in
  the doctor's triage summary view. Patient gets: "这个问题需要张医生回复，
  我已通知医生。"

### Escalation Rate Limiting

Prevent patients from flooding doctors with escalations:

- **Per-patient rate limit**: max 3 escalations per 6-hour window. After limit
  reached, AI still records the message (`ai_handled: false`) but does NOT
  notify doctor. Patient gets: "医生将在查看时一并处理您的问题"
- **Batch notifications**: escalations within a 10-minute window are batched
  into a single doctor notification with count ("李明有3条新消息需要您处理").
  Doctor sees all items in the triage summary view.
- **Urgent bypasses rate limit**: `urgent` classification (red flags) always
  notifies immediately, regardless of rate limit or batching.
- Existing patient message rate limit (10/min) still applies at the HTTP layer.
- **Urgent escalation**: uses existing notification system (`infra/notify/`).
  Patient immediately gets safety guidance ("如出现严重症状请立即就医").
  No SLA guarantee — this is advisory, not emergency services. The disclaimer
  "AI建议仅供参考" applies to all patient interactions.

### Path to Active Triage (v2, future)

AI provides basic guidance for non-urgent cases ("common side effect, usually
resolves in 2-3 days") with disclaimer. Urgent/red-flag still immediately escalated.

### Patient Context Injected into Triage LLM

- Current treatment plan items (from confirmed diagnosis)
- Pending tasks
- Recent messages (last 10)
- Active medications (from treatment plan)
- Original diagnosis summary

## Treatment Plan

No new table. Treatment plan is a **read view** over confirmed `diagnosis_results`.

When doctor confirms diagnosis:
1. `derive_treatment_plan(diagnosis_result)` extracts approved items from
   `doctor_decisions` JSON
2. Returns structured response:
   - Approved workup items → "检查项目"
   - Approved treatment items → "治疗方案"
   - Red flags → "注意事项"
3. Query: `diagnosis_results WHERE status=confirmed AND record.patient_id=X
   ORDER BY confirmed_at DESC` — **most recent confirmed diagnosis wins**.
   Multiple confirmed diagnoses show as a list in 病历 tab; treatment plan
   and tasks derive from the latest one only.

## Patient Tasks

Mirror the doctor task system. Same `doctor_tasks` table (model: `DoctorTask` in
`src/db/models/tasks.py`) with a new `target` column. Patient tasks still have
`doctor_id` — it references the doctor whose diagnosis generated the task.

### DB Changes to `doctor_tasks` Table

```python
target          # enum: doctor/patient (default: doctor), CHECK constraint
source_type     # enum: manual/rule/diagnosis_auto (default: manual), CHECK constraint
source_id       # nullable FK to diagnosis_result that generated it
```

`doctor_id` remains NOT NULL for patient tasks — it's the prescribing doctor.

### Auto-Generation

Triggered on diagnosis confirmation. Maps approved items to tasks:

| Item Type | Task | Due Date |
|-----------|------|----------|
| Workup (urgency: 急诊) | "完成{test_name}" | +1 day |
| Workup (urgency: 紧急) | "完成{test_name}" | +3 days |
| Workup (urgency: 常规) | "完成{test_name}" | +7 days |
| Treatment (with duration) | "按时服用{drug}" | +duration |
| Treatment (follow-up) | "预约复诊" | +follow_up_interval |

### Upload Completion

When `upload_matcher` links an upload to a workup task:
1. Validate file: supported types (JPEG, PNG, PDF), max 10MB, basic content check
2. LLM matches upload content against pending items
3. If confident match → ask patient to confirm ("这是颈椎MRI的结果吗？")
4. If no match or ambiguous → ask patient to select from pending items list
5. If one file matches multiple tasks → ask patient to clarify which task
6. Task marked `completed` only after patient confirms
7. Doctor notified with upload reference
8. Upload uses existing `patientUpload` endpoint (Vision LLM extraction already built)

### Task Lifecycle Rules

- **Dedupe on reconfirmation**: if diagnosis is re-confirmed, do not duplicate
  existing tasks — skip items that already have a pending or completed task
- **No auto-revocation**: if diagnosis changes, existing tasks remain (doctor
  manually manages). v1 does not auto-delete tasks.
- **No recurrence**: medication tasks have a single due date (end of duration),
  not daily reminders. Recurrence is v2.

## Bidirectional Messaging

### Patient Side (主页 tab)

Three message sources, visually distinct:

| Source | Style |
|--------|-------|
| Patient | Green bubble (#95EC69), right-aligned |
| AI agent | White bubble (#fff), left-aligned |
| Doctor | White bubble + 0.5px COLOR.success border + doctor name label |

AI proactive messages pushed on events:
- Diagnosis confirmed → DiagnosisCard with "查看治疗方案" button
- Task approaching due → reminder
- Doctor replies → DoctorBubble in conversation

### Doctor Side (PatientDetail view)

Chat panel with **two views**:
1. **Triage summary view** (default): only shows escalated items — structured
   follow-up records, upload notifications, urgent alerts. Each with triage
   badge and structured data. This is what the doctor sees first.
2. **Full thread view** (expandable): complete conversation including AI-handled
   informational exchanges. Available for context when doctor needs to
   understand the full conversation history.

Reply input at bottom — doctor types, appears as DoctorBubble in patient chat.
AI handles most messages; doctor intervenes when needed.

### DB Changes to `patient_messages` Table

```python
source          # enum: patient/ai/doctor (replaces direction: inbound/outbound)
sender_id       # nullable string — doctor_id when source=doctor, null otherwise
reference_id    # nullable FK to MedicalRecord if triage created one
triage_category # enum: informational/symptom_report/side_effect/general_question/urgent
structured_data # JSON: collected symptom details, matched medication, severity
ai_handled      # bool: fully handled by AI without doctor involvement
```

Migration: `ALTER TABLE` + backfill. All existing `inbound` → `patient`, all
existing `outbound` → `ai` (doctor direct replies don't exist yet, so all
outbound messages are AI-generated).

### Interview Session Changes

```python
mode            # add "follow_up" to existing "patient"/"doctor" values
```

## Notifications

Doctor notified only on **escalated** actionable events:
- AI-escalated symptom/side-effect report (triage created follow-up record)
- Patient uploads results (new)
- Patient completes a treatment plan item (new)
- Urgent red flag detection (high priority alert)

NOT notified on:
- Informational queries handled by AI (records, plan, task status)
- General questions answered by AI
- Passive views (viewing diagnosis, checking treatment plan)

This means the AI triage acts as a **filter** — doctors only see what needs
their attention, not every patient message.

## Message Transport (v1)

**Polling-based** — no WebSocket/SSE for v1:
- Patient app polls `GET /api/patient/chat/messages?since={last_id}` every 10s
  when 主页 tab is active, every 60s on other tabs
- Response includes all new messages (AI, doctor) since `last_id`
- `last_id` stored in localStorage for resume across sessions
- Unread count badge on 主页 tab icon when new messages arrive on other tabs

**WebSocket/SSE is deferred** — not in scope for v1. Polling is adequate
since patient interactions are minutes-scale, not seconds-scale.

## Frontend

### Navigation: Keep Existing 4-Tab Layout

Reuse the existing `NAV_TABS` array and `BottomNavigation` in `PatientPage.jsx`:

```jsx
const NAV_TABS = [
  { key: "chat", label: "主页", icon: <ChatOutlinedIcon />, title: "AI 健康助手" },
  { key: "records", label: "病历", icon: <DescriptionOutlinedIcon />, title: "病历" },
  { key: "tasks", label: "任务", icon: <AssignmentOutlinedIcon />, title: "任务" },
  { key: "profile", label: "设置", icon: <SettingsOutlinedIcon />, title: "设置" },
];
```

No tab structure changes. Same `BottomNavigation` with `showLabels`, same
`SubpageHeader` per tab. Upgrade each tab's content with ADR 0020 features.
Active tab color should use `COLOR.success` (#52C772) per UI-DESIGN.md
(currently hardcoded as `#07C160` — fix during implementation).

### Visual Reference

Mockups: [docs/specs/2026-03-21-mockups/](2026-03-21-mockups/)

- `patient-portal-upgrade.html` — final 4-tab upgrade mockup
- `agent-style-comparison.html` — traditional portal vs AI agent-centric
- `nav-comparison.html` — competitor navigation research

### 主页 Tab Upgrades

Keep existing quick action cards (新问诊 + 我的病历) + chat input bar.

Add:
- AI proactive messages with inline `DiagnosisCard` (wraps `ContentCard` +
  `StatusBadge` + `AppButton`)
- `DoctorBubble` for doctor direct replies (white + `0.5px solid COLOR.success`
  border + doctor name label `caption(12) COLOR.success`)
- `SuggestionChips` for structured triage collection (pill chips 16px radius)
- Triage escalation summary cards (`warningLight` bg + `warning` border-left)
- Chat bubbles unchanged: user `#95EC69`, AI `#fff`, `TYPE.body` (14/400)

### 病历 Tab Upgrades

Keep existing `NewItemCard` + `ListCard` record list.

Add:
- Tap record → subpage shows diagnosis + treatment plan (if confirmed diagnosis
  exists for that record)
- Treatment plan view: `ContentCard` with `TYPE.heading` (14/600) section title,
  `TYPE.body` (14/400) items, red flag warning (`dangerLight` bg + `danger` border)
- Follow-up reports appear as new `ListCard` rows with warning-colored avatar
- `StatusBadge` for diagnosis status (`colorMap: {已确认: COLOR.success}`)

### 任务 Tab Upgrades

Replace `EmptyState` with `TaskChecklist`:
- Circular checkboxes: pending 20px `1.5px solid COLOR.border`, done `COLOR.success` bg
- Title: `TYPE.action` (15/500) per `ListCard` pattern
- Due date: `TYPE.caption` (12), overdue `COLOR.danger`
- Upload action: `AppButton variant="ghost" size="sm"`
- Urgency badge: `StatusBadge` with `colorMap: {紧急: COLOR.danger, 常规: COLOR.text4}`
- `SectionLabel` for "待完成" / "已完成" groups
- Diagnosis context card at bottom: `ContentCard` + `StatusBadge` + red flag warning

### 设置 Tab

No changes.

### Component Inventory

**Reused (12 existing):**

| Component | Usage |
|-----------|-------|
| `AppButton` | primary, ghost, sm — action buttons throughout |
| `BarButton` | top bar actions |
| `ContentCard` | diagnosis card, treatment plan, task groups |
| `StatusBadge` | 已确认, 紧急, record type badges |
| `SectionLabel` | group headers (待完成, 已完成, 最近诊断) |
| `ListCard` | record rows, task rows |
| `NewItemCard` | 新建病历 entry |
| `EmptyState` | no-data states |
| `ActionButtonPair` | dialog confirm/cancel |
| `AskAIBar` | floating "问 AI" on 病历/任务 tabs |
| `SuggestionChips` | triage quick replies |
| `RecordFields` | record detail view |

**New (2 components):**

| Component | Design |
|-----------|--------|
| `DoctorBubble` | name: `TYPE.caption`(12) `COLOR.success`. Bubble: `#fff`, `0.5px solid COLOR.success`, `TYPE.body`(14/400), 8px radius. Same max-width/padding as existing chat bubbles. |
| `TaskChecklist` | Circle: 20px, pending `COLOR.border`, done `COLOR.success` bg. Wraps `ListCard` layout. Upload: `AppButton ghost sm`. Urgency: `StatusBadge`. |

`DiagnosisCard` was removed as a separate component — it's just a `ContentCard` +
`StatusBadge` + `AppButton` composition, no abstraction needed.

### Design Tokens (from UI-DESIGN.md)

All values from `theme.js` `TYPE`, `COLOR`, `ICON` exports.

Typography: `TYPE.title`(16/600), `TYPE.action`(15/400), `TYPE.heading`(14/600),
`TYPE.body`(14/400), `TYPE.secondary`(13/400), `TYPE.caption`(12/400),
`TYPE.micro`(11/500). Bottom nav labels: 10px.

Colors: `COLOR.success`(#52C772) for confirmed/active states. `COLOR.danger`(#D65745)
for urgency/overdue. `COLOR.warning`(#F59E0B) for triage alerts. `COLOR.primary`(#1B6EF3)
for links. Chat: `wechat.userBubble`(#95EC69), `wechat.aiBubble`(#fff).
Buttons: `#07C160` (AppButton/BarButton).

Spacing: 4px base. Cards 6px radius. Buttons 4px radius. Dialogs 8px radius.
Pill chips 16px radius.

## API Endpoints

### New Endpoints

```
POST   /api/patient/chat              # agent-style chat (replaces /api/patient/message)
GET    /api/patient/chat/messages      # poll for new messages (?since=last_id)
GET    /api/patient/tasks              # patient tasks (target=patient)
POST   /api/patient/tasks/:id/complete # mark task done
POST   /api/patient/upload-result      # AI-guided upload with task matching
```

Treatment plan is accessed via `GET /api/patient/records/:id` (existing endpoint,
extended to include diagnosis + treatment when confirmed). No separate treatment
plan endpoint — single source of truth.

### Modified Endpoints

```
GET    /api/patient/records            # add diagnosis_status field
GET    /api/patient/records/:id        # add diagnosis + treatment plan if confirmed
```

### Doctor-Side New Endpoints

```
GET    /api/manage/patients/:id/chat   # full conversation thread for patient
POST   /api/manage/patients/:id/reply  # doctor direct reply to patient
```

## Dependencies

- ADR 0016 (patient interview pipeline) — reused for follow-up mode
- ADR 0018 (diagnosis pipeline) — treatment plan derived from confirmed results
- Existing task system (`task_rules.py`) — extended for patient tasks

## Constraints

- Python 3.9 compatible (`from __future__ import annotations`)
- No Alembic migrations — `ALTER TABLE` + `create_tables()`
- LLM: Qwen3:32b (dev/prod), Qwen3.5:9b (local)
- Clinical safety: AI suggestions advisory only, doctor has final authority
- Follow UI-DESIGN.md for all frontend work (TYPE/COLOR/ICON tokens, shared components)

## Out of Scope

- Real-time push (WebSocket/SSE) — deferred, polling is sufficient for v1
- Patient-side push notifications (WeChat template messages) — future
- Treatment plan editing by doctor before publishing — future (auto-derive only)
- Active triage (AI provides basic guidance) — v2
- QR code entry (ADR 0017) — separate spec
- Outcome tracking (ADR 0021) — depends on this spec
