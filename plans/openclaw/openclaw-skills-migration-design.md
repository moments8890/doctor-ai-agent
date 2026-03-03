# Migration to OpenClaw Skills — Full Design

## Goal
Migrate the existing Python/FastAPI backend to TypeScript OpenClaw skills. Python is retired after feature parity. All domain logic lives in OpenClaw skills; OpenClaw handles channel routing, session orchestration, and cron jobs. Patient-facing WeChat intake is added as a first-class feature (currently only doctor-facing). `patient_events` table captures all raw inbound messages for audit trail and dispute resolution.

---

## New Project Layout

```
doctor-openclaw/
├── package.json              # Node.js 22+, pnpm
├── tsconfig.json
├── drizzle.config.ts
├── db/
│   ├── schema.ts             # All table definitions (Drizzle)
│   └── index.ts              # DB singleton (better-sqlite3 + Drizzle)
├── shared/
│   ├── ollama.ts             # Ollama OpenAI-compatible client
│   ├── wechat.ts             # WeChat token cache + customer service message
│   └── types.ts              # MedicalRecord, IntentResult, RiskResult, etc.
└── skills/
    ├── db-core/              # All CRUD (shared lib used by every skill)
    ├── agent-dispatch/       # LLM intent classification (function-calling)
    ├── record-structuring/   # Free text → structured MedicalRecord
    ├── risk-engine/          # Risk scoring + patient categorization (pure)
    ├── task-manager/         # Task CRUD + due-task cron (replaces APScheduler)
    ├── notification/         # WeChat push abstraction (log | wechat)
    ├── approval-workflow/    # Pending AI drafts awaiting doctor review
    ├── transcription/        # Audio → text (Whisper local/cloud)
    ├── doctor-chat/          # Doctor-facing WeChat message handler
    └── patient-intake/       # Patient-facing WeChat handler (NEW)
```

---

## DB Schema (db/schema.ts)

Mirror all existing tables from Python `db/models.py` exactly using Drizzle. Add three new tables.

### Existing tables (mirrored)
- `system_prompts` — editable LLM prompts
- `doctor_contexts` — persistent compressed memory per doctor
- `patients` — patient profiles with risk + category fields
- `medical_records` — structured clinical records
- `neuro_cases` — neurology case extractions
- `doctor_tasks` — follow-up / emergency / appointment tasks
- `patient_labels` + `patient_label_assignments` — doctor-owned labels

### New: `patient_events`

```ts
patientEvents = sqliteTable('patient_events', {
  id:        integer('id').primaryKey({ autoIncrement: true }),
  doctorId:  text('doctor_id').notNull(),
  patientId: integer('patient_id').references(() => patients.id),
  source:    text('source').notNull(),     // "wechat" | "voice" | "image"
  direction: text('direction').notNull(),  // "inbound" | "outbound"
  eventType: text('event_type').notNull(), // "symptom_report" | "question" | "image_upload" | "reply_sent"
  rawText:   text('raw_text'),
  riskHint:  text('risk_hint'),            // quick keyword match before full engine
  recordId:  integer('record_id').references(() => medicalRecords.id),
  status:    text('status').notNull().default('raw'), // "raw" | "structured" | "ignored"
  eventTime: integer('event_time', { mode: 'timestamp' }).notNull(),
})
```

### New: `doctor_bindings`

```ts
doctorBindings = sqliteTable('doctor_bindings', {
  doctorId:      text('doctor_id').primaryKey(),
  wechatOpenid:  text('wechat_openid').notNull().unique(),
})
```

### New: `patient_bindings`

```ts
patientBindings = sqliteTable('patient_bindings', {
  id:            integer('id').primaryKey({ autoIncrement: true }),
  patientId:     integer('patient_id').references(() => patients.id).notNull(),
  doctorId:      text('doctor_id').notNull(),
  wechatOpenid:  text('wechat_openid').notNull().unique(),
})
```

---

## Skill Inventory

### 1. `db-core` (shared library)
Ported from `db/crud.py`. Exports all CRUD functions used by every other skill. No LLM calls.

Key functions: `createPatient`, `findPatientByName`, `saveRecord` (triggers risk + category + optional follow-up task), `createApprovalItem`, `updateApprovalItem`, `createTask`, `getDueTasks`, `markTaskNotified`, `upsertDoctorContext`, label management.

### 2. `agent-dispatch` skill
**From**: `services/agent.py` + `services/intent.py`

Tool: `dispatch(text, history[]) → IntentResult`
- Ollama `qwen2.5:14b` via `shared/ollama.ts` (OpenAI-compatible, same function-calling tools)
- 8 tools identical to Python version (create_patient, add_medical_record, query_records, list_patients, list_tasks, complete_task, schedule_appointment)
- Regex fallback when Ollama unavailable

### 3. `record-structuring` skill
**From**: `services/structuring.py`

Tool: `structureRecord(text, consultationMode?) → MedicalRecord`
- System prompt from `system_prompts` table, 60s cache
- Preserves medical abbreviations (STEMI, BNP, EF, EGFR, HER2, ANC, PCI)
- `consultationMode=true` appends dialogue-aware suffix

### 4. `risk-engine` skill
**From**: `services/patient_risk.py` + `services/patient_categorization.py`

Tools: `recomputeRisk(patientId)`, `recomputeCategory(patientId)` — pure computation, no LLM.
Keywords, thresholds, follow-up state logic ported verbatim.
Cron: weekly full risk recompute for all patients (new).

### 5. `task-manager` skill
**From**: `services/tasks.py` + `routers/tasks.py`

Tools: `createFollowUpTask`, `createEmergencyTask`, `createAppointmentTask`, `listTasks`, `completeTask`
**Cron** (replaces APScheduler): every 1 min → `checkAndSendDueTasks()` → notify → `markTaskNotified`
Chinese follow-up day parsing (`extractFollowUpDays`) ported verbatim.

### 6. `notification` skill
**From**: `services/notification.py` + `services/wechat_notify.py`

Tool: `notify(doctorId, message)`
- Provider: `NOTIFICATION_PROVIDER` env var (`log` | `wechat`)
- WeChat: token cache (60s buffer) + customer service message + 600-char chunking

### 7. `approval-workflow` skill
**From**: `services/approval.py` + `routers/approvals.py`

Tools: `createApproval`, `commitApproval`, `rejectApproval`, `listApprovals`

**Fixes vs Python:**
- `commitApproval`: atomic `UPDATE ... WHERE status='pending'` before side effects (eliminates race condition)
- Zod schema validation on all LLM outputs; maps parse errors → clean error messages (eliminates 500s)

### 8. `transcription` skill
**From**: `services/transcription.py`

Tool: `transcribe(audioBuffer, consultationMode?) → string`
- Primary: shell exec to `whisper-cpp` or Python `faster-whisper` subprocess
- Fallback: OpenAI Whisper API
- Language forced to `zh`

### 9. `doctor-chat` skill
**From**: `routers/records.py` + `routers/voice.py` + `routers/wechat.py` (doctor path)

WeChat channel handler for **doctor** openid messages. Orchestrates:
```
message → openid lookup → doctorId
  → stateful flow check (pending_create_name / interview)
  → agent-dispatch → IntentResult
  → execute intent (same logic as Python records/wechat routers)
  → reply via WeChat customer service API
```
Session state per doctorId stored in OpenClaw session.
Conversation history compression via OpenClaw `/compact` + `doctor_contexts` table.

### 10. `patient-intake` skill (NEW)
No Python equivalent. Patient-facing WeChat handler.

```
Patient message → openid lookup → patientId + doctorId
  → write patient_events (direction=inbound)
  → quick risk hint (keyword match)
  → approval-workflow.createApproval (item_type="patient_message")
  → notify doctor: "【患者消息】{name}: {preview}，请审核 #{approvalId}"
  → ack patient: "已收到，医生将尽快回复"

Doctor approves → reply sent to patient via patient_bindings.wechatOpenid
  → write patient_events (direction=outbound)
```

---

## WeChat Channel Routing

```
Incoming POST /wechat
  openid lookup:
  ├── in doctor_bindings  → doctor-chat skill
  ├── in patient_bindings → patient-intake skill
  └── unknown             → onboarding (doctor or patient?)
```

OpenClaw's built-in "WebChat" is a web widget, not 公众号 webhook. A custom channel adapter in TypeScript handles WeChat signature verification, XML parsing, and routes to the appropriate skill. This replaces `routers/wechat.py` entirely.

---

## Migration Phases

### Phase 1 — Foundation
- Init `doctor-openclaw/` (pnpm, tsconfig, drizzle config)
- `db/schema.ts` — all tables + 3 new tables
- `shared/ollama.ts`, `shared/wechat.ts`, `shared/types.ts`
- `skills/db-core` — all CRUD
- `skills/notification`

### Phase 2 — Core domain skills
- `skills/risk-engine` (pure, easiest to test)
- `skills/task-manager` + cron
- `skills/record-structuring`
- `skills/agent-dispatch`

### Phase 3 — Workflow skills
- `skills/approval-workflow` (with atomic fix + Zod validation)
- `skills/transcription`

### Phase 4 — Channel skills
- WeChat custom channel adapter (公众号 webhook)
- `skills/doctor-chat`
- `skills/patient-intake` + binding tables

### Phase 5 — Validation & cutover
- Port critical Python test cases to Vitest (target ≥90% coverage)
- Vitest green + coverage gate met → delete Python backend entirely

---

## Key Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| ORM | Drizzle + better-sqlite3 | SQL-first, type-safe, works with existing SQLite file, no migration runtime |
| Ollama client | `openai` npm package | Already OpenAI-compatible; same function-calling API as Python |
| Cron | OpenClaw built-in | Replaces APScheduler, 1-min interval |
| Context compression | OpenClaw `/compact` + `doctor_contexts` | Replaces Python rolling-window logic |
| WeChat channel | Custom adapter (TypeScript) | OpenClaw WebChat ≠ 公众号 webhook |
| Testing | Vitest | TypeScript-native, fast, similar to pytest |
| Race condition fix | Atomic `WHERE status='pending'` UPDATE | Fixes approval-workflow double-commit bug |
| Payload validation | Zod on all LLM outputs | Maps parse errors → 422-style messages, no 500s |

---

## Comparison with Event-Driven Approach

The alternative approach (separate `packages/contracts` monorepo, event types like `PatientEventCreated`, shadow dual-run phases) is designed for a safe incremental production cutover. In a dev context where Python is being retired entirely, those concerns don't apply. The relevant trade-offs are:

| Aspect | This plan (flat skills) | Event-driven monorepo |
|---|---|---|
| Setup complexity | Low | High |
| New tables | 3 (`patient_events`, `*_bindings`) | 5+ (`delivery_logs`, `audit_log`, etc.) |
| Timeline | Faster | Slower |

Shadow mode, rollback flags, and parity gates are omitted — Python is deleted once Vitest coverage gates are met.

---

## Verification

```bash
# Phase 1 check
pnpm test                           # Vitest unit tests

# Phase 4 smoke (doctor chat)
openclaw start
# Send WeChat message as doctor → verify intent dispatch → record saved

# Phase 4 smoke (patient intake)
# Send WeChat message as patient → verify patient_events row + doctor notified

# Phase 5 exit criteria
pnpm test --coverage                # overall ≥90% coverage
# Coverage gate green → delete Python backend
```
