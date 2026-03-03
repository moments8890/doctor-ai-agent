# Migration to OpenClaw Skills — v2

## Goal
Migrate the existing Python/FastAPI backend to TypeScript OpenClaw skills and delete Python entirely once Vitest coverage gate (≥90%) is met. All domain logic lives in OpenClaw skills; OpenClaw handles channel routing, session orchestration, and cron jobs. Patient-facing WeChat intake is added as a first-class new feature.

---

## Project Layout

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
    ├── db-core/              # All CRUD (shared lib used by every skill) — custom
    ├── agent-dispatch/       # LLM intent classification (function-calling) — custom
    ├── record-structuring/   # Free text → structured MedicalRecord — custom
    ├── risk-engine/          # Risk scoring + patient categorization (pure) — custom
    ├── task-manager/         # Task CRUD + due-task cron (replaces APScheduler) — custom
    ├── notification/         # WeChat delivery via openclaw-plugin-wecom — OSS adapter
    ├── approval-workflow/    # Pending AI drafts; Lobster gates + custom SQLite/WeChat wiring
    ├── transcription/        # Audio → text via auto-whisper-safe — OSS skill
    ├── doctor-chat/          # Doctor-facing WeChat message handler — custom
    └── patient-intake/       # Patient-facing WeChat handler (NEW) — custom
```

---

## DB Schema (db/schema.ts)

Mirror all existing tables from `db/models.py` exactly using Drizzle. Add three new tables.

### Existing tables (mirrored)
- `system_prompts` — editable LLM prompts
- `doctor_contexts` — persistent compressed memory per doctor
- `patients` — patient profiles with risk + category fields
- `medical_records` — structured clinical records
- `neuro_cases` — neurology case extractions
- `doctor_tasks` — follow-up / emergency / appointment tasks
- `patient_labels` + `patient_label_assignments` — doctor-owned labels

### Design principles
- Keep raw source events immutable (`patient_events` rows are never updated)
- Keep structured clinical facts mutable with timestamp tracking (`medical_records`, patient risk fields)

### New: `patient_events`

```ts
patientEvents = sqliteTable('patient_events', {
  id:              integer('id').primaryKey({ autoIncrement: true }),
  eventId:         text('event_id').notNull().unique(),        // dedup key
  doctorId:        text('doctor_id').notNull(),
  patientId:       integer('patient_id').references(() => patients.id),
  source:          text('source').notNull(),                   // "wechat" | "voice" | "image"
  sourceMessageId: text('source_message_id'),                  // WeChat message dedup
  direction:       text('direction').notNull(),                // "inbound" | "outbound"
  eventType:       text('event_type').notNull(),               // "symptom_report" | "question" | "image_upload" | "reply_sent"
  rawText:         text('raw_text'),
  riskHint:        text('risk_hint'),                          // quick keyword match before full engine
  recordId:        integer('record_id').references(() => medicalRecords.id),
  status:          text('status').notNull().default('raw'),    // "raw" | "structured" | "ignored"
  idempotencyKey:  text('idempotency_key'),
  eventTime:       integer('event_time', { mode: 'timestamp' }).notNull(),
})
```

Indexes: `(doctor_id, event_time DESC)`, `(patient_id, event_time DESC)`, `(source, source_message_id)`.

### New: `doctor_bindings`

```ts
doctorBindings = sqliteTable('doctor_bindings', {
  doctorId:     text('doctor_id').primaryKey(),
  wechatOpenid: text('wechat_openid').notNull().unique(),
})
```

### New: `patient_bindings`

```ts
patientBindings = sqliteTable('patient_bindings', {
  id:           integer('id').primaryKey({ autoIncrement: true }),
  patientId:    integer('patient_id').references(() => patients.id).notNull(),
  doctorId:     text('doctor_id').notNull(),
  wechatOpenid: text('wechat_openid').notNull().unique(),
})
```

---

## Skill Inventory

### 1. `db-core` (shared library)
**From**: `db/crud.py`

- **Input**: typed parameters per function
- **Responsibility**: all CRUD; no LLM calls; used by every other skill
- **Output**: typed DB row objects

Key exports: `createPatient`, `findPatientByName`, `saveRecord` (triggers risk + category + optional follow-up task), `createApprovalItem`, `updateApprovalItem`, `createTask`, `getDueTasks`, `markTaskNotified`, `upsertDoctorContext`, label management.

---

### 2. `agent-dispatch`
**From**: `services/agent.py` + `services/intent.py`

- **Input**: `{ text: string, history?: Message[] }`
- **Responsibility**: Ollama `qwen2.5:14b` function-calling with 7 tools; regex fallback when Ollama unavailable
- **Output**: `IntentResult { intent, patientName?, gender?, age?, isEmergency, extraData, chatReply?, structuredFields? }`

Tools (identical to Python): `create_patient`, `add_medical_record`, `query_records`, `list_patients`, `list_tasks`, `complete_task`, `schedule_appointment`.

---

### 3. `record-structuring`
**From**: `services/structuring.py`

- **Input**: `{ text: string, consultationMode?: boolean }`
- **Responsibility**: LLM extraction → structured `MedicalRecord`; system prompt loaded from `system_prompts` table (60s cache); `consultationMode=true` appends dialogue-aware suffix; preserves STEMI, BNP, EF, EGFR, HER2, ANC, PCI
- **Output**: `MedicalRecord { chiefComplaint, historyOfPresentIllness?, pastMedicalHistory?, physicalExamination?, auxiliaryExaminations?, diagnosis?, treatmentPlan?, followUpPlan? }`

---

### 4. `risk-engine`
**From**: `services/patient_risk.py` + `services/patient_categorization.py`

- **Input**: `{ patientId: number }`
- **Responsibility**: pure computation (no LLM); keyword scoring; follow-up state logic; persist result on patient row; weekly cron for full recompute (new)
- **Output**: `RiskResult { primaryRiskLevel, riskTags, riskScore, followUpState, rulesVersion, computedAt }`

---

### 5. `task-manager`
**From**: `services/tasks.py` + `routers/tasks.py`

- **Input**: `{ doctorId, taskType, title, content?, patientId?, recordId?, dueAt? }`
- **Responsibility**: task CRUD; idempotency guard to avoid duplicate tasks; Chinese follow-up day parsing (`extractFollowUpDays`) ported verbatim; **cron every 1 min** → `checkAndSendDueTasks()` → notify → `markTaskNotified` (replaces APScheduler)
- **Output**: `{ taskId, status, createdAt }`

---

### 6. `notification`
**From**: `services/notification.py` + `services/wechat_notify.py`
**OSS**: [`openclaw-plugin-wecom`](https://github.com/sunnoy/openclaw-plugin-wecom) handles WeChat/WeCom delivery

- **Input**: `{ doctorId: string, message: string }`
- **Responsibility**: route to provider set by `NOTIFICATION_PROVIDER` env var (`log` | `wechat`); for WeChat delivery, delegates to `openclaw-plugin-wecom` (XML callbacks, streaming replies, per-user isolated sessions, four-tier fallback); `log` provider used in dev/test
- **Output**: void (throws on failure)

---

### 7. `approval-workflow`
**From**: `services/approval.py` + `routers/approvals.py`
**OSS**: [Lobster](https://github.com/openclaw/lobster) owns the pause/resume gate; custom code owns persistence + WeChat wiring

- **Input**: `{ itemType, doctorId, payload }` / `{ approvalId, doctorId }`
- **Responsibility**:
  - Lobster gate: pipeline halts at `approve` step → returns `needs_approval` envelope + resume token
  - Custom: persist `approval_items` in SQLite (survives restarts between halt and resume)
  - Custom: doctor lists pending approvals via WeChat message
  - Custom: WeChat reply triggers Lobster resume → side effects fire
  - Custom: **atomic `UPDATE ... WHERE status='pending'`** before side effects (fixes Python race condition)
  - Custom: Zod validation on all LLM payloads (maps parse errors → clean messages, no 500s)
  - Custom: `patient_events` outbound write on approve
- **Output**: `{ approvalId, status }` / `DraftApproved` / `DraftRejected`

---

### 8. `transcription`
**From**: `services/transcription.py`
**OSS**: [`auto-whisper-safe`](https://github.com/openclaw/skills/blob/main/skills/neal-collab/auto-whisper-safe/SKILL.md) — local Whisper, RAM-aware chunking, WeChat audio formats

- **Input**: `{ audioBuffer: Buffer, consultationMode?: boolean }`
- **Responsibility**: delegates to `auto-whisper-safe` with `WHISPER_MODEL=base WHISPER_LANG=zh`; handles `.ogg`/`.m4a`/`.opus` (WeChat voice formats); auto-chunks recordings >10 min; `consultationMode` appended as context hint post-transcription
- **Output**: `{ text: string }`

---

### 9. `doctor-chat`
**From**: `routers/records.py` + `routers/voice.py` + `routers/wechat.py` (doctor path)

- **Input**: WeChat message event (doctor openid)
- **Responsibility**: openid lookup → doctorId; stateful flow check (pending_create_name / interview); `agent-dispatch` → intent execution; reply via WeChat customer service API; session state in OpenClaw session; history compression via `/compact` + `doctor_contexts` table
- **Output**: WeChat customer service reply

---

### 10. `patient-intake` (NEW)
No Python equivalent.

- **Input**: WeChat message event (patient openid)
- **Responsibility**:
  1. openid lookup → `patientId` + `doctorId` (via `patient_bindings`)
  2. write `patient_events` (`direction=inbound`, dedup via `sourceMessageId`)
  3. quick keyword risk hint
  4. `approval-workflow.createApproval(itemType="patient_message")`
  5. notify doctor: `"【患者消息】{name}: {preview}，请审核 #{approvalId}"`
  6. ack patient: `"已收到，医生将尽快回复"`
  7. on doctor approve → reply sent via `patient_bindings.wechatOpenid` + write `patient_events` (`direction=outbound`)
- **Output**: WeChat reply to patient + notification to doctor

---

## Skill I/O Contracts

All skill tools share a base envelope:

```ts
interface SkillEnvelope {
  traceId: string          // for log correlation
  idempotencyKey?: string  // for all side-effect operations
}
```

### `patient-intake` input
```ts
{
  traceId: string
  idempotencyKey?: string  // = sourceMessageId for WeChat
  doctorId: string
  source: 'wechat' | 'voice' | 'image'
  sourceMessageId?: string
  sourceUserId?: string    // WeChat openid
  eventType: 'message' | 'upload' | 'action'
  rawText?: string
  receivedAt: string       // ISO 8601 UTC
}
```

### `record-structuring` output
```ts
{
  recordId: number
  doctorId: string
  patientId: number | null
  structuredFields: {
    chiefComplaint: string | null
    historyOfPresentIllness: string | null
    pastMedicalHistory: string | null
    physicalExamination: string | null
    auxiliaryExaminations: string | null
    diagnosis: string | null
    treatmentPlan: string | null
    followUpPlan: string | null
  }
}
```

### `risk-engine` output
```ts
{
  doctorId: string
  patientId: number
  riskLevel: 'low' | 'medium' | 'high' | 'critical'
  riskScore: number        // 0–100
  riskTags: string[]
  followUpState: 'not_needed' | 'scheduled' | 'due_soon' | 'overdue'
  rulesVersion: string
}
```

### `task-manager` input (create)
```ts
{
  traceId: string
  idempotencyKey?: string
  doctorId: string
  patientId?: number
  recordId?: number
  taskType: 'follow_up' | 'emergency' | 'appointment'
  title: string
  content?: string
  dueAt?: string           // ISO 8601 UTC
}
```

---

## WeChat Channel Routing

```
Incoming POST /wechat
  openid lookup:
  ├── in doctor_bindings  → doctor-chat skill
  ├── in patient_bindings → patient-intake skill
  └── unknown             → onboarding flow
```

[`openclaw-plugin-wecom`](https://github.com/sunnoy/openclaw-plugin-wecom) handles WeChat signature verification, XML callbacks, and per-user session isolation. Replaces `routers/wechat.py` entirely. OpenClaw WebChat ≠ 公众号 webhook.

---

## Migration Phases

### Phase 1 — Foundation
- Init `doctor-openclaw/` (pnpm, tsconfig, drizzle config)
- `db/schema.ts` — all tables + 3 new tables
- `shared/ollama.ts`, `shared/wechat.ts`, `shared/types.ts`
- `skills/db-core` — all CRUD
- `skills/notification`

### Phase 2 — Core domain skills
- `skills/risk-engine` (pure, no LLM — easiest to test)
- `skills/task-manager` + cron
- `skills/record-structuring`
- `skills/agent-dispatch`

### Phase 3 — Workflow skills
- `skills/approval-workflow` (atomic fix + Zod validation)
- `skills/transcription`

### Phase 4 — Channel skills
- WeChat custom channel adapter (公众号 webhook)
- `skills/doctor-chat`
- `skills/patient-intake` + binding tables

### Phase 5 — Validation & cutover
- Port critical Python test cases to Vitest (target ≥90% coverage)
- Coverage gate green → **delete Python backend entirely**

---

## First Sprint Deliverables (Phase 1)

1. `doctor-openclaw/` scaffold — `package.json`, `tsconfig.json`, `drizzle.config.ts`
2. `db/schema.ts` — all 10 existing tables + `patient_events`, `doctor_bindings`, `patient_bindings`
3. `shared/ollama.ts` — OpenAI-compatible client pointed at `http://localhost:11434/v1`
4. `shared/wechat.ts` — token cache + `sendCustomerServiceMsg` (600-char chunking)
5. `shared/types.ts` — `MedicalRecord`, `IntentResult`, `RiskResult`, `CategoryResult`
6. `skills/db-core` — all CRUD functions with Vitest tests
7. `skills/notification` — `log` and `wechat` providers with Vitest tests

---

## OSS Skills Leveraged

| Skill | OSS component | What we own |
|---|---|---|
| `transcription` | [`auto-whisper-safe`](https://github.com/openclaw/skills/blob/main/skills/neal-collab/auto-whisper-safe/SKILL.md) — local Whisper, RAM-aware, WeChat audio formats | `WHISPER_LANG=zh` config; `consultationMode` hint |
| `approval-workflow` | [Lobster](https://github.com/openclaw/lobster) — pipeline halt/resume gates | SQLite persistence, WeChat wiring, atomic commit, Zod validation |
| `notification` + WeChat channel | [`openclaw-plugin-wecom`](https://github.com/sunnoy/openclaw-plugin-wecom) — WeCom XML callbacks, per-user sessions | `log` provider, routing logic, openid lookup |
| `db-core`, `agent-dispatch`, `record-structuring`, `risk-engine`, `task-manager`, `doctor-chat`, `patient-intake` | — | Fully custom (medical domain, no OSS equivalent exists) |

---

## Key Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| ORM | Drizzle + better-sqlite3 | SQL-first, type-safe, works with existing SQLite file, no migration runtime |
| Ollama client | `openai` npm package | Already OpenAI-compatible; same function-calling API as Python |
| Cron | OpenClaw built-in | Replaces APScheduler, 1-min interval |
| Context compression | OpenClaw `/compact` + `doctor_contexts` | Replaces Python rolling-window logic |
| WeChat channel | `openclaw-plugin-wecom` | Handles 公众号 XML callbacks + per-user session isolation out of the box |
| Transcription | `auto-whisper-safe` + `WHISPER_LANG=zh` | Local, RAM-safe, handles `.ogg`/`.m4a`/`.opus` WeChat voice formats |
| Approval gate | Lobster (pause/resume) + custom SQLite/WeChat wiring | Lobster owns halt; we own persistence and reply routing |
| Testing | Vitest | TypeScript-native, fast, similar to pytest |
| Race condition fix | Atomic `WHERE status='pending'` UPDATE | Fixes approval-workflow double-commit bug |
| Payload validation | Zod on all LLM outputs | Maps parse errors → clean messages, eliminates 500s |
| WeChat dedup | `event_id` UNIQUE + `source_message_id` index | Prevents duplicate `patient_events` rows on WeChat retry |
| Task idempotency | `idempotency_key` on all side-effect calls | Prevents duplicate task creation |

---

## Verification

```bash
# Phase 1 check
pnpm test                # Vitest unit tests (db-core + notification)

# Phase 4 smoke — doctor chat
openclaw start
# Send WeChat message as doctor → verify intent dispatch → record saved

# Phase 4 smoke — patient intake
# Send WeChat message as patient → verify patient_events row created + doctor notified

# Phase 5 exit criteria
pnpm test --coverage     # overall ≥90% → delete Python backend
```
