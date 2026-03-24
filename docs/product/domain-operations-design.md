# Domain Operations Design

> Date: 2026-03-23
> Status: Reviewed

This document defines the supported operations for each domain in the
doctor-ai-agent system, grouped by entity. It replaces the previous ad-hoc
tool/action model with a clean domain-oriented design.

**Architectural shift**: this design replaces the current LangGraph ReAct
agent (single LLM with autonomous tool-selection across all domains) with
a **routing LLM → intent-specific handler** pattern (Plan and Act). A
lightweight routing LLM classifies intent and extracts entities, then
deterministic code dispatches to a dedicated handler per intent (interview
LLM, diagnosis LLM, compose LLM, etc.). Each handler has focused prompts
and scoped context, rather than one LLM having access to all tools
simultaneously. This improves predictability and allows per-intent prompt
optimization.

**Single intent per turn**: the routing LLM returns one primary intent per
turn. If the doctor's message contains multiple intents (e.g. "查张三病历
然后建个随访任务"), routing extracts the first intent and captures the rest
in a `deferred` field. The compose LLM acknowledges deferred intents in its
response ("已查询张三病历...您还提到要建随访任务，请确认"). This keeps each
turn simple and predictable.

**Future upgrade path**: if real usage shows doctors frequently chain
requests, the routing LLM can return a list of intents for sequential
execution. The dispatch code adds a loop — small diff, no architectural
change. The `create_record` exclusivity rule still applies: if any intent
is `create_record`, it must be the only intent in the turn.

**Routing LLM output format**:
```json
{
  "intent": "query_record",
  "patient_name": "张三",
  "params": {},
  "deferred": "建个随访任务"
}
```

**6 routing intents** (routing LLM classifies into one of these):

```
Intent          │ patient_name │ params
────────────────┼──────────────┼─────────────────────────────────
query_record    │ optional     │ limit (int, default 5)
create_record   │ required     │ gender, age, clinical_text (all optional)
query_task      │ —            │ status (optional: pending|completed)
create_task     │ optional     │ title (required), content, due_at (optional)
query_patient   │ —            │ query (required, NL search string)
general         │ —            │ (none — fallback/chitchat)
```

**`review_record` is NOT a routing intent** — it is a UI-only flow. Doctor
clicks a pending_review record or review task in the UI, frontend calls
the review API directly, no routing LLM involved.

---

## Design Principles

1. **Group by domain, not invocation** — operations are categorized by what
   entity they act on (Patient, Record, Task, Knowledge), not by who calls
   them (doctor agent, UI, WeChat).
2. **LLM only where it adds value** — use LLM for routing intent,
   conducting interviews, summarizing data, and generating suggestions.
   CRUD operations go through the UI directly.
3. **Interview over one-shot** — record creation always goes through the
   interview flow for guided field collection, never one-shot structuring.
4. **Create record is exclusive** — if the routing LLM detects
   `create_record` alongside other intents, it must reject and ask the
   doctor to separate requests. Create record enters interview mode which
   is incompatible with other actions in the same turn. Read-only
   combinations (e.g. query records + create task) are allowed.

---

## 1. Patient

### 1.1 Create Patient

- **Via UI**: doctor creates patient directly from the management UI
  (name, gender, age/year of birth).
- **Indirect**: auto-created when a record is created for a new patient
  name via `resolve(auto_create=True)` in the interview flow.

### 1.2 Query Patient — Point Query

- **Input**: patient name (exact match).
- **Mechanism**: `resolve()` → `find_patient_by_name()`.
- **Used by**: all tools that accept `patient_name` as input.

### 1.3 Query Patient — Range Query

- **Input**: natural language criteria (name substring, gender, age range).
- **Mechanism**: `extract_criteria()` → filter against all patients.
- **Example**: "60岁以上的女性患者"
- **Limitation**: no symptom-based search for now.

### 1.4 Patient Timeline

- **Cross-domain aggregate read**: records + tasks + visits for a patient,
  ordered chronologically.
- **Straddles Patient and Record domains** — listed here as a "patient detail"
  view.

### Not supported via LLM

- Update patient demographics → UI only.
- Delete patient → admin UI only.

---

## 2. Record

### 2.1 Create Record — Always Interview

All record creation paths converge on the **doctor interview LLM** for guided
field collection. No record is ever saved without the doctor reviewing
structured fields through the interview flow.

**Path A: Via chat (free text)**
```
Doctor types "给张三建病历" or "张三，男，45岁，头痛三天伴恶心"
  → routing LLM → intent=create_record, extracts: patient_name, gender, age, partial clinical info
  → enter interview flow (extracted info passed as prefill context)
  → interview LLM skips already-filled fields, asks for remaining
  → doctor confirms → save
```

**Path B: Via UI button**
```
UI sends action_hint=create_record
  → skip routing LLM (intent is known)
  → enter interview flow
  → interview LLM guides through fields
  → doctor confirms → save
```

**Path C: From image / file / text**
```
Upload image/PDF/text
  → extract text (Vision LLM or PDF extraction)
  → feed extracted text into interview as prefill context
  → interview LLM shows what it found, asks doctor to confirm/correct/fill gaps
  → doctor confirms → save
```

Both free text and explicit UI actions converge. No chain actions — if the
routing LLM detects `create_record` intent, it routes to interview and
nothing else.

### 2.2 Read Record — LLM-Summarized

Two query modes, both returning LLM-generated summaries (never raw DB records).

**Query without patient name:**
1. Routing LLM → `intent=query_record`, `patient=null`
2. Fetch all doctor's patients + recent records
3. Compose LLM → summarize all-patient overview

**Query with patient name:**
1. Routing LLM → `intent=query_record`, `patient="张三"`
2. Fetch that patient's records
3. Compose LLM → summarize single-patient overview

No symptom-based search for now — name only.

### 2.3 Record Lifecycle — State Machine

```
(interview_active)
  │
  ├─ doctor confirms → completeness check
  │   ├─ diagnosis + treatment + followup all filled → (completed)
  │   └─ any missing → (pending_review) → review pipeline
  │
  ├─ doctor abandons → (deleted, no record saved)
  └─ timeout (10min) → (expired/deleted)

(pending_review)
  │
  ├─ doctor accepts some/all suggestions → (completed)
  └─ doctor rejects all suggestions → (completed, doctor override)
```

A record always reaches "completed" after review, regardless of whether
the doctor accepts or rejects AI suggestions. The doctor has final authority.

### 2.4 Review Record — Diagnosis Pipeline

Triggered conditionally: if diagnosis, treatment_plan, or orders_followup
fields are incomplete after interview, the record enters "pending_review".

**Review pipeline:**
1. Record saved as "pending_review" in DB
2. Gather context (parallel):
   - Doctor knowledge: 诊断规则 + 危险信号 + 治疗方案 categories (see Section 6)
   - Patient's past cases (case history by patient_id)
   - Similar symptom cases (case history by keyword match — plain text)
3. Feed record + all context → diagnosis prompt LLM
4. LLM returns structured output:
   ```json
   {
     "diagnoses": [...],
     "treatment_plan": "...",
     "suggested_tasks": [
       {
         "title": "随访提醒：张三",
         "due_days": 14,
         "reason": "复查血常规"
       }
     ]
   }
   ```
5. Doctor reviews: accept / reject / edit each diagnosis suggestion
6. On confirmation: record → "completed", suggested tasks auto-created
   as `general` type tasks

**Interview and Review are complementary:**
- Interview collects the **clinical facts** (what happened)
- Review suggests the **clinical decisions** (what to do)

### 2.5 Update Record — UI Only

- Direct field edit through the admin UI.
- No LLM in the loop.
- **Append-only versioning**: edits create a new record row with
  `version_of` pointing to the original. The original is never mutated.
  Current version = latest row in the version chain.
- No separate versions table needed — medical_records IS the version
  history.

### 2.6 Delete Record — Admin UI Only

- Soft delete or mark as superseded. Original rows preserved for audit.

### 2.7 Export Record

- PDF per patient (`/api/export/patient/{id}/pdf`)
- PDF per record (`/api/export/record/{id}/pdf`)
- Outpatient report JSON (`/api/export/patient/{id}/outpatient-report`)

Export renders directly from SOAP columns — no separate extraction step
needed. The `medical_record_exports` audit table is killed; export events
are logged to `audit_log` (action=EXPORT, resource_type=record).

---

## 3. Task

### 3.1 Create Task

**Via UI:**
- Doctor fills form directly, no LLM.

**Via chat LLM:**
1. Routing LLM → `intent=create_task`, extracts: title, patient (optional),
   record (optional), due date (optional).
2. Save task to DB. No confirmation gate — tasks are lightweight.

**Auto from record review (diagnosis LLM output):**
- The review/diagnosis LLM includes a `suggested_tasks` field in its
  structured output (see Section 2.4).
- When the doctor confirms the review, suggested tasks are auto-created
  as `general` type tasks with the specified due dates.
- No separate rule engine — task generation is part of the diagnosis
  LLM's single structured response.

### 3.2 Read Task — LLM-Summarized

1. Routing LLM → `intent=query_task` (with or without filter criteria)
2. Fetch all tasks from DB
3. Compose LLM → summarize task overview

### 3.3 Update Task — UI Only

- Status change (pending → completed).
- Due date change.
- No LLM in the loop.

### 3.4 Task Types

Two types only:
- **`general`** — default, covers follow-ups, appointments, reminders, etc.
- **`review`** — auto-created when a record enters "pending_review" status.
  Links to the record. Doctor clicks it → enters the review pipeline.

### Not supported

- Delete task — tasks are completed, not deleted.
- Update task via LLM — UI only.

### Removed from previous design

- 7 task types (follow_up, emergency, lab_review, referral, imaging, medication,
  appointment) → collapsed to 2 (general, review).
- Rule engine (`task_rules.py`) with keyword scanning and suppression → removed.
- `complete_task` agent tool → removed.
- `create_emergency_task`, `create_appointment_task` as separate functions → removed.

---

## 4. Knowledge

### 4.1 Management — UI Only

All CRUD operations through the admin UI:
- **Create**: `POST /api/manage/knowledge` — doctor enters text manually.
- **Read**: `GET /api/manage/knowledge` — list items.
- **Delete**: `DELETE /api/manage/knowledge/{id}` — remove item.

No chat commands, no agent tools, no auto-learn.

### 4.2 Knowledge Categories — Intent Mapping

The existing UI organizes knowledge by category. Each category maps to
specific LLM intent layers:

```
UI Category (existing)     → Injected into which LLM prompts
───────────────────────────────────────────────────────────
问诊指导 (interview guide)  → interview LLM
诊断规则 (diagnosis rules)  → review/diagnosis LLM
危险信号 (red flags)        → interview LLM + review/diagnosis LLM
治疗方案 (treatment plans)  → review/diagnosis LLM
自定义 (custom)             → all intents (always injected)
```

**危险信号 spans two intents** — injected into both interview (so the
interview LLM asks about red flags) and diagnosis (so the review LLM
checks against them).

**自定义 (custom)** is injected into all intent prompts as general doctor
preferences. Use for cross-cutting rules like "我不开阿片类止痛药".

No new UI categories needed. The mapping is a backend wiring concern:
when building the prompt for a given intent, filter knowledge items by
their category and inject the matching ones.

### 4.3 Knowledge Weight

Doctor knowledge outranks patient context in the prompt stack. If the
doctor's KB says "偏头痛首选曲普坦" but a past case used a different drug,
the doctor's stated preference wins. This is enforced by prompt ordering
(knowledge appears before patient context — see Section 6).

### Removed from previous design

- `search_knowledge` agent tool → removed.
- `parse_add_to_knowledge_command` (chat regex) → removed.
- `maybe_auto_learn_knowledge` (auto-extract from records) → removed.
- Embedding infrastructure (BGE-M3 preloading) — evaluate if still needed
  for other features; if not, remove.

---

## 5. Data Model

### 5.1 Logical Entities

**Doctor-side:**

| Entity | Description |
|--------|-------------|
| Doctor info | Profile, preferences |
| Patient info | Demographics, belongs to doctor |
| Medical records | Belongs to patient + doctor, with status + AI diagnosis |
| Doctor knowledge | Doctor's personal KB, categorized, managed via UI |
| Doctor tasks | General + review type (target=doctor or patient) |
| Doctor chat log | Doctor ↔ AI conversation history |

**Patient-side:**

| Entity | Description |
|--------|-------------|
| Patient chat log | Patient ↔ AI conversation history |
| Patient tasks | Subset of doctor_tasks where target=patient (no separate table) |
| Patient medical records | Read-only view of medical_records (no duplication) |

### 5.2 Database Schema — 14 Tables

Simplified from the current 25 tables. Every table must justify its
existence against the core set: patients, doctors, records, knowledge,
tasks, chat logs. Identity tables are kept clean — channel bindings and
auth concerns are separated.

**Convention**: all fields with a fixed set of values use `(str, Enum)`
— never raw strings with comments. This applies to: `status`, `role`,
`task_type`, `target`, `source_type`, `category`, `mode`, `direction`,
`source`, `record_type`.

**Core data (9 tables):**

```
doctors (identity only)
  doctor_id (PK), name, specialty, department, phone,
  year_of_birth, created_at, updated_at

doctor_wechat (channel binding, optional)
  doctor_id (PK, FK→doctors), wechat_user_id, mini_openid,
  created_at
  — Only exists for WeChat-connected doctors.
  — Notification config uses system defaults (env vars):
    NOTIFY_MODE=auto, NOTIFY_SCHEDULE=immediate,
    NOTIFY_INTERVAL_MINUTES=1. Per-doctor overrides deferred.

patients (identity only)
  id (PK), doctor_id (FK→doctors), name, gender — (str, Enum),
  year_of_birth, phone, created_at

patient_auth (portal access, optional)
  patient_id (PK, FK→patients), access_code (hashed),
  access_code_version (int), created_at
  — Only exists for portal-enabled patients.

medical_records
  id (PK), patient_id (FK→patients), doctor_id (FK→doctors),
  version_of (FK→medical_records.id, nullable),
  record_type — (str, Enum: visit|import|interview_summary),
  status — (str, Enum: interview_active|pending_review|completed),
  tags (JSON),
  department,
  — SOAP: Subjective
  chief_complaint, present_illness, past_history,
  allergy_history, personal_history, marital_reproductive,
  family_history,
  — SOAP: Objective
  physical_exam, specialist_exam, auxiliary_exam,
  — SOAP: Assessment
  diagnosis, ai_diagnosis (JSON), doctor_decisions (JSON),
  — SOAP: Plan
  treatment_plan, orders_followup, suggested_tasks (JSON),
  — Outcome (absorbs case_history fields)
  final_diagnosis, treatment_outcome, key_symptoms,
  — Meta
  content (denormalized text summary, computed from SOAP fields),
  created_at, updated_at

  Design decisions:
  — SOAP columns replace structured JSON — queryable, indexable
  — Append-only versioning: edits create new row with version_of
    pointing to the original. Current record = version_of IS NULL
    or latest in the version chain. Kills medical_record_versions.
  — Outcome fields (final_diagnosis, treatment_outcome, key_symptoms)
    absorb case_history table. "Similar symptom cases" = query
    medical_records WHERE chief_complaint LIKE '%头痛%'. Real columns,
    indexable.
  — Diagnosis folded in (was diagnosis_results table)
  — Review queue is just: WHERE status='pending_review'
  — Pending records is just: WHERE status='interview_active'

doctor_tasks
  id (PK), doctor_id (FK→doctors), patient_id (FK→patients),
  record_id (FK→medical_records),
  task_type — (str, Enum: general|review),
  title, content,
  status — (str, Enum: pending|notified|completed|cancelled),
  target — (str, Enum: doctor|patient),
  source_type — (str, Enum: manual|diagnosis_auto),
  due_at, created_at, updated_at
  — Covers both doctor and patient tasks (target column)
  — Types simplified from 8 to 2
  — Single due_at column replaces scheduled_for + remind_at.
    Notification sent 1 day before due_at by default (configurable).

doctor_knowledge_items
  id (PK), doctor_id (FK→doctors), content (text),
  category — (str, Enum: interview_guide|diagnosis_rule|red_flag|
              treatment_protocol|custom),
  created_at, updated_at
  — Categories map to prompt intent layers (Section 4.2)

doctor_chat_log
  id (PK), doctor_id (FK→doctors), session_id (UUID v4),
  patient_id,
  role — (str, Enum: user|assistant),
  content, created_at
  — session_id generated when doctor opens new conversation.
    Session expires after 30 min idle (configurable via
    CHAT_SESSION_TIMEOUT_MINUTES env var).
  — Serves as both LLM context source and UI chat history.

patient_chat_log
  id (PK), patient_id (FK→patients), doctor_id (FK→doctors),
  session_id (UUID v4),
  role — (str, Enum: user|assistant|ai),
  content,
  direction — (str, Enum: inbound|outbound),
  source — (str, Enum: patient|ai|doctor),
  sender_id, triage_category, ai_handled (boolean),
  created_at
  — source/sender_id/ai_handled retained for patient portal UI:
    renders who sent each message (patient, AI auto-reply, or doctor).
  — Same dual purpose: LLM context source + UI chat history reload.
```

**Workflow state (1 table):**

```
interview_sessions
  id (PK, UUID v4), doctor_id (FK→doctors), patient_id (FK→patients),
  status — (str, Enum: interviewing|confirmed|abandoned),
  mode — (str, Enum: patient|doctor),
  collected (JSON), conversation (JSON),
  turn_count, created_at, updated_at
  — Justification: interview is a stateful multi-turn flow tracking
    which of 14 SOAP fields are collected. Reconstructing from chat log
    every turn would be wasteful and error-prone.
```

**System/infra (4 tables):**

```
audit_log
  id (PK), ts, doctor_id, action, resource_type, resource_id,
  ip, trace_id, ok
  — Compliance requirement. Non-negotiable.

invite_codes
  code (PK), doctor_id, doctor_name, active, created_at,
  expires_at, max_uses, used_count
  — Doctor signup gating.

runtime_tokens
  token_key (PK), token_value, expires_at, updated_at
  — WeChat access token cache. Cross-instance reuse.

scheduler_leases
  lease_key (PK), owner_id, lease_until, updated_at
  — Distributed lock for task notification scheduler.
```

### 5.3 Killed Tables — Justification

| Killed Table | Reason |
|-------------|--------|
| `medical_record_versions` | Replaced by append-only versioning on medical_records (`version_of` FK). Edits create new rows, originals preserved. |
| `medical_record_exports` | Just a PDF generation log. Track in audit_log if needed. |
| `patient_labels` + assignments | Nice-to-have. patients.category_tags JSON is sufficient for MVP. |
| `diagnosis_results` | Folded into medical_records (ai_diagnosis, doctor_decisions, suggested_tasks columns). |
| `case_history` | Absorbed into medical_records SOAP columns (final_diagnosis, treatment_outcome, key_symptoms). "Similar cases" = query medical_records by chief_complaint/key_symptoms — real columns, indexable. |
| `review_queue` | Redundant. medical_records WHERE status='pending_review' IS the queue. |
| `pending_records` | Redundant. Interview sessions replace the pending draft flow. Record creation goes through `interview_sessions` table (multi-turn), not one-shot pending drafts with confirm/abandon. The confirm/abandon regex fast paths in `handle_turn.py` are removed — interview has its own confirm/abandon via the interview API. |
| `pending_messages` | WeChat retry queue. Move to application-level retry, not core data. |
| `system_prompts` + versions | All prompts live on file system (`prompts/*.md`). prompt_loader.py handles caching. No DB needed. |
| `doctor_notify_preferences` | System defaults in env vars. Per-doctor config deferred to post-MVP. |
| `runtime_configs` | Fold into env vars or file-based config. |

### 5.4 Chat Log Design

**Store**: both user input and LLM reply.
**Do not store**: full LLM prompt (system prompt, context injection, knowledge).
The prompt context is reconstructable from current DB state + file system prompts.

**Schema** — incremental messages, not snapshots:

```
doctor_chat_log:
  id | doctor_id | session_id | patient_id | role | content | created_at
```

Loading a session = `SELECT * FROM doctor_chat_log WHERE session_id = ?
ORDER BY created_at`. No duplication. Conversation history for the LLM
is built by reading the last N messages from this table.

### 5.5 Session & Context Management

**Session lifecycle:**
- **Starts**: doctor opens chat / clicks new conversation → UUID v4 generated
- **Persists**: across all messages, regardless of which patient is mentioned
- **Clears**: timeout (30 min idle, configurable via `CHAT_SESSION_TIMEOUT_MINUTES`)
  OR doctor explicitly starts new conversation
- **No auto-clear on patient switch** — no implicit context switching

**Patient resolution**: the routing LLM extracts patient_name from the
current message text. If no name is mentioned, the most recently mentioned
patient in chat history is used (simple last-mention lookup from the rolling
window). No pronoun resolution, no session-level patient tracking.

**Chat history in memory vs DB:**
- Agent memory holds a rolling window of last N turns for the current session
- Messages are persisted to doctor_chat_log async (non-blocking) for backup
- On session end, agent memory is released
- DB is the source of truth for conversation history; agent memory is a
  warm cache for the current session

**Context per intent** — what data is loaded after routing decides the intent:

```
Intent          │ Context loaded from DB
────────────────┼──────────────────────────────────────────
routing         │ (none — only chat history from agent memory)
                │
query patient   │ patients (all for doctor)
                │ records (summary per patient)
                │ tasks (count per patient)
                │
create record   │ patient info (via resolve)
(interview)     │ patient's past records
                │ knowledge: 问诊指导 + 危险信号
                │
query record    │ patient info (via resolve, if name given)
                │ records (for patient or all recent)
                │
review record   │ patient info
                │ patient's past records
                │ similar symptom records (keyword search across all records)
                │ knowledge: 诊断规则 + 危险信号 + 治疗方案
                │
query task      │ tasks (all for doctor, with patient names)
                │
create task     │ patient info (if specified, via resolve)
```

**Two-stage context loading:**
1. **Routing stage**: minimal context (chat history only) — fast, cheap
2. **Execution stage**: full context per intent (DB queries) — loaded only
   after routing decides what's needed

This avoids loading heavy context (records, knowledge) for every message.

---

## 6. Prompt Architecture

### 6-Layer Prompt Composer

All LLM calls use a shared prompt composer (`agent/prompt_composer.py`) that
assembles messages from separate layers. Layers 1-3 are concatenated into
one system message. Layers 4-6 go into the final user message with XML tags.

```
┌─────────────────────────────────┐
│ 1. system/base.md               │  Identity, safety, precedence rules
├─────────────────────────────────┤
│ 2. common/{specialty}.md        │  Specialty knowledge (e.g. neurology)
├─────────────────────────────────┤
│ 3. intent/{intent}.md           │  Action-specific rules + few-shot examples
├─────────────────────────────────┤
│ 4. <doctor_knowledge> XML       │  Per-intent KB slice from DB
├─────────────────────────────────┤
│ 5. <patient_context> XML        │  Records, case history from DB
├─────────────────────────────────┤
│ 6. <doctor_request> XML         │  Actual doctor/patient message
└─────────────────────────────────┘
Layers 1-3 → system message | Layers 4-6 → user message
```

**Message assembly:**
```python
messages = [
    {"role": "system", "content": base + common + intent},
    *conversation_history,
    {"role": "user", "content": "<doctor_knowledge>...</> <patient_context>...</> <doctor_request>...</>"},
]
```

**File layout:**
```
prompts/
  system/base.md              ← Layer 1: identity, safety, precedence
  common/neurology.md         ← Layer 2: specialty knowledge
  intent/routing.md           ← Layer 3: routing rules + 9 examples
  intent/interview.md         ← Layer 3: doctor interview + 4 examples
  intent/patient-interview.md ← Layer 3: patient pre-consultation + 3 examples
  intent/diagnosis.md         ← Layer 3: differential diagnosis + 2 examples
  intent/structuring.md       ← Layer 3: text → SOAP + 3 examples
  intent/query.md             ← Layer 3: query summary rules
  intent/create-task.md       ← Layer 3: task creation rules
  intent/general.md           ← Layer 3: fallback/chitchat
```

**Config:** `agent/prompt_config.py` defines `INTENT_LAYERS` — a dict mapping
each `IntentType` to a `LayerConfig` (which layers to include, which KB
categories to load). An assert at import time ensures every IntentType has
a config entry — adding a new intent without a LayerConfig crashes at startup.

**Structured output:** All LLM calls that return structured data use
`instructor` (JSON mode) + Pydantic response models via `agent/llm.py:structured_call()`.
Instructor handles schema enforcement, validation, and retries. Prompts do
NOT contain JSON format specifications — Pydantic models are the single
source of truth for output structure.

### Layer usage by intent (from `prompt_config.py`)

```
Intent             | System | Common | Intent           | Dr Knowledge                  | Patient Ctx
-------------------|--------|--------|------------------|-------------------------------|------------
routing            |   ✓    |        | routing          | custom                        |
create_record      |   ✓    |   ✓    | interview        | interview_guide+red_flag+custom|      ✓
query_record       |   ✓    |        | query            | custom                        |      ✓
query_task         |   ✓    |        | query            | custom                        |
create_task        |   ✓    |        | create-task      | custom                        |
query_patient      |   ✓    |        | query            | custom                        |      ✓
general            |   ✓    |        | general          | custom                        |
patient_interview  |   ✓    |   ✓    | patient-interview| interview_guide+red_flag+custom|      ✓
review/diagnosis   |   ✓    |   ✓    | diagnosis        | diagnosis_rule+red_flag+treatment+custom| ✓
```

---

## 7. Migration Plan — ReAct to Plan and Act

### 7.1 Framework Decision

- **Instructor** (`instructor` package) for structured LLM output via Pydantic
  models. Uses `instructor.Mode.JSON` for Groq/Qwen3 compatibility.
- **Raw `AsyncOpenAI`** for free-text LLM calls (compose/summary).
- **No LangChain** — removed entirely (kept `langchain-huggingface` for embeddings).
- Shared LLM helper: `agent/llm.py` with `structured_call()` and `llm_call()`.
- 6-layer prompt composer: `agent/prompt_composer.py` + `agent/prompt_config.py`.

### 7.2 Files to Delete

| File/Module | Reason |
|-------------|--------|
| `agent/setup.py` — ReAct parts | `create_agent()`, `bind_tools()`, LangChain callback plumbing, `BaseTool` tool listing. Keep provider/model resolution. |
| `agent/tools/doctor.py` — `@tool` decorators + `DOCTOR_TOOLS` export | LangChain tool wrappers removed. Business logic (DB queries, record ops) stays as plain async functions. |
| `agent/tools/patient.py` — `@tool` decorators + `PATIENT_TOOLS` export | Same — strip decorator, keep logic. |
| `agent/prompts/doctor-agent.md` | ReAct-specific prompt (tool descriptions, output format for tool calling). Replaced by `doctor-router.md`. |
| `agent/prompts/patient-agent.md` | Same — replaced by `patient-router.md`. |
| `agent/prompts/agent-doctor.md` | Dead file if exists. |
| `domain/tasks/task_rules.py` | Rule engine for auto-task generation — replaced by diagnosis LLM output. |
| `db/models/` for killed tables | ORM models for: `pending_records`, `pending_messages`, `diagnosis_results`, `case_history`, `review_queue`, `medical_record_versions`, `medical_record_exports`, `patient_labels`, `system_prompts`, `system_prompt_versions`, `doctor_notify_preferences`, `runtime_configs`. |
| `db/crud/` for killed tables | CRUD modules for all killed tables: `pending.py`, `case_history.py`, `diagnosis.py`, `system.py` (prompt parts), etc. |
| LangChain deps in `requirements.txt` | Remove: `langchain`, `langchain-openai`, `langchain-groq`, `langchain-deepseek`, `langchain-ollama`, `langchain-core`. |

### 7.3 Files to Modify

| File/Module | Change |
|-------------|--------|
| `agent/setup.py` | Replace `get_agent()` with routing LLM client factory using `AsyncOpenAI`. Keep provider/model resolution logic. |
| `agent/session.py` | Replace LangChain `HumanMessage`/`AIMessage` with plain dicts. Replace `.ainvoke()` with router → dispatcher → handler flow. |
| `agent/handle_turn.py` | Call new router/dispatcher instead of LangChain agent. This is the main orchestration entry point. |
| `agent/tools/doctor.py` | Strip `@tool` decorators. Keep all business logic as plain `async def` functions. Remove Pydantic tool input schemas (routing LLM handles param extraction). |
| `agent/tools/patient.py` | Same — plain async handlers. |
| `agent/actions.py` | Becomes the router's allowed intent enum (already has `ActionType`). |
| `domain/patients/interview_turn.py` | Imports `HumanMessage`/`SystemMessage` from langchain-core — replace with plain dicts. |
| `agent/archive.py` | References `ChatArchive` model — update to use `doctor_chat_log` table. |
| `requirements.txt` | Drop LangChain agent packages. Keep `langchain-huggingface` only if embedding model still needed. |

### 7.4 Files to Create

| File/Module | Purpose |
|-------------|---------|
| `agent/router.py` | One LLM call → structured JSON `{intent, patient_name, params, deferred}`. Uses `AsyncOpenAI` + `response_format={"type": "json_object"}`. ~50 lines. |
| `agent/dispatcher.py` | Validates router output, maps intent → handler function, executes. Simple dict dispatch. |
| `agent/types.py` | Pydantic models: `RoutingResult`, `HandlerResult`, `TurnContext`. |
| `agent/handlers/` | One handler per intent: `query_record.py`, `create_record.py`, `create_task.py`, `query_task.py`, `query_patient.py`, `general.py`. Each loads per-intent context + knowledge, calls intent-specific LLM, returns result. `review_record` is NOT a handler — it's a UI-only API endpoint (see Section 2.4). |
| `agent/prompts/routing.md` | Routing LLM prompt — intent classification + entity extraction. Replaces `doctor-agent.md`. |
| `agent/prompts/compose.md` | Response synthesis prompt for query intents. |

### 7.5 What Stays Unchanged

| Module | Why |
|--------|-----|
| `agent/tools/resolve.py` | Patient name → ID resolution. Pure utility, no LangChain dependency. |
| `agent/tools/truncate.py` | Output truncation. Pure utility. |
| `agent/identity.py` | Context var for current doctor_id. |
| `agent/archive.py` | Chat archival logic. |
| `agent/prompts/doctor-interview.md` | Interview LLM prompt — already intent-specific. |
| `agent/prompts/patient-interview.md` | Patient interview prompt — already intent-specific. |
| `agent/prompts/diagnosis.md` | Diagnosis LLM prompt — already intent-specific. |
| `agent/prompts/structuring.md` | Used by import paths (image/file → text extraction). |
| `infra/llm/*` | Client pooling, retry, fallback, provider routing. Becomes the foundation. |
| `domain/*` | All domain logic (records, patients, tasks, knowledge). Untouched. |
| `db/*` | All DB models and CRUD. Untouched (schema changes are separate). |
| `channels/*` | Web and WeChat handlers. Only change: call new `handle_turn` entry point. |

### 7.6 Architecture Comparison

```
BEFORE (ReAct):
  message → LangChain agent → LLM picks tool → tool executes
          → LLM reads result → may call another tool → LLM composes reply
  (3-5 LLM calls, unpredictable, all tools in one prompt)

AFTER (Plan and Act):
  message → router LLM → {intent, entities} → dispatcher → handler
          → handler loads context + knowledge → intent LLM → response
  (2 LLM calls, predictable, per-intent prompts)
```

### 7.7 Migration Phases

#### Phase 1: Agent Pipeline — COMPLETE (2026-03-23)

Plan: `docs/superpowers/plans/2026-03-23-plan-and-act-agent-pipeline.md`

Delivered:
- `agent/types.py` — IntentType (6 values), RoutingResult, HandlerResult, TurnContext
- `agent/router.py` — routing LLM → structured JSON classification
- `agent/dispatcher.py` — intent → handler registry with deferred acknowledgment
- `agent/handlers/` — 6 handlers (general, query_record, create_record,
  create_task, query_task, query_patient)
- `agent/handle_turn.py` — rewritten: route → dispatch → respond
- `agent/session.py` — rewritten: plain dict history, no LangChain
- `agent/prompts/routing.md`, `compose.md` — new prompt files
- 26 tests (unit + integration), all passing

Known breakages to fix in Phase 3:
- `channels/wechat/router.py` — imports removed `_CONFIRM_RE`, `_ABANDON_RE`
- `agent/tools/doctor.py` — uses removed `get_agent_history`
- `main.py` + `patient_detail_handlers.py` — import removed `_agents`
- `tests/core/test_action_dispatch.py` — tests old ReAct behavior

#### Phase 2: DB Schema Migration — COMPLETE (2026-03-23)

Delivered:
- `doctor_wechat` and `patient_auth` tables created
- 20 SOAP columns added to `medical_records` (department, 7 subjective,
  3 objective, 3 assessment, 3 plan, 3 outcome fields)
- `version_of` FK for append-only versioning
- `RecordStatus` enum (interview_active, pending_review, completed)
- `doctor_chat_log` and `patient_chat_log` tables created
- `TaskType` simplified to (general, review)
- `scheduled_for` and `remind_at` removed from tasks
- All references to old task types and removed columns fixed

#### Phase 3: Cleanup — COMPLETE (2026-03-23)

Delivered:
- All Phase 1 import breakages fixed (wechat, main, tools, tests)
- `@tool` decorators stripped from tools/doctor.py and tools/patient.py
- LangChain messages replaced with raw AsyncOpenAI in interview_turn.py
- Deleted: `agent/setup.py`, old ReAct prompts, `task_rules.py`
- LangChain packages removed from requirements.txt (kept langchain-huggingface)
- Auto-followup task creation removed (replaced by diagnosis LLM output)

#### Phase 4: Instructor + Structured Output — COMPLETE (2026-03-23)

Delivered:
- `instructor` package for Pydantic-based structured LLM output
- `instructor.Mode.JSON` for Groq/Qwen3 compatibility (tool-calling unsupported)
- Response models: `RoutingResult`, `InterviewLLMResponse`, `DiagnosisLLMResponse`,
  `StructuringLLMResponse`
- `agent/llm.py:structured_call()` — shared helper with tracing + logging
- All interview, diagnosis, structuring LLM calls migrated

#### Phase 5: 6-Layer Prompt Composer — COMPLETE (2026-03-23)

Delivered:
- `agent/prompt_config.py` — `LayerConfig` dataclass + `INTENT_LAYERS` matrix
  with import-time assert for completeness
- `agent/prompt_composer.py` — `compose_messages()` with XML tags
  (`<doctor_knowledge>`, `<patient_context>`, `<doctor_request>`)
- Prompt files restructured: `system/base.md`, `common/neurology.md`,
  `intent/*.md` (11 intent fragments)
- All handlers wired to composer: router, query_record, query_task,
  interview (doctor + patient), diagnosis
- Dead code removed: `_build_system_prompt()`, `_get_prompt()`, skill loader

#### Phase 6: Frontend + Interview Confirm — COMPLETE (2026-03-23)

Delivered:
- `handle_turn` returns `HandlerResult` (reply + data) instead of string
- Chat endpoint passes `view_payload` with `session_id` to frontend
- Frontend detects `session_id` → navigates to interview UI
- Interview UI loads existing session via `GET /session/{id}` (conversation history)
- Interview confirm saves SOAP fields directly to `medical_records`
  (no structuring LLM, no pending_records)
- Tasks page: graceful handling of deleted review-queue endpoint

#### Phase 7: Prompt Rewrite — COMPLETE (2026-03-23)

Delivered:
- Doctor-interview: 4 few-shot examples (multi-field extraction + SOAP checklist)
- Diagnosis: full case example (differentials + workup + treatment)
- Routing: output format section removed (instructor handles schema)
- Dead code: `_build_system_prompt`, `_get_prompt`, `get_diagnosis_skill` removed
- Prompt inventory updated (`tmp-prompt-inventory.md`)

#### Deferred (previously planned, now DONE)

- ~~Delete old DB model files for killed tables~~ — DONE (Phase 3)
- ~~Update ARCHITECTURE.md~~ — DONE (Phase 3)
- ~~Fix old tests referencing TaskType.follow_up~~ — DONE (Phase 3)
- ~~Remove old columns from doctors/patients~~ — DONE (Phase 3)

#### Remaining (low priority)

- Vision-import: migrate to `structured_call` (uses manual JSON parse)
- Old root prompt files: kept for admin UI backward compatibility
- Triage inline prompts: 3 prompts in `triage.py` not yet migrated
- Upload matcher: inline prompt not yet migrated

---

## Summary: LLM vs UI Operations

| Operation | LLM | UI |
|-----------|-----|----|
| Create record | Interview LLM (all paths) | — |
| Read record | Query → LLM summary | List view |
| Review record | Diagnosis LLM pipeline | Accept/reject suggestions |
| Update record | — | Direct field edit |
| Delete record | — | Admin only |
| Create task | Routing → extract → save | Form |
| Create task (auto) | Diagnosis LLM output → auto-create | — |
| Read task | Query → LLM summary | List view |
| Update task | — | Status/due change |
| Create patient | Indirect (via record) | — |
| Query patient | Point/range query | List/search |
| Knowledge CRUD | — | Full CRUD (categorized) |
| Knowledge consumption | Interview + diagnosis prompt context | — |
