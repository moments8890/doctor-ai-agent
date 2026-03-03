# Doctor Approval Workflow

## Why

AI-structured medical records contain clinical data — diagnoses, treatment plans, follow-up schedules — where a silent LLM misinterpretation can have patient-safety consequences. The approval workflow places a human review step between AI output and database commit, giving doctors a chance to inspect, edit, and confirm every AI suggestion before it becomes an official record.

## Modes

| `APPROVAL_MODE_ENABLED` | Behaviour |
|-------------------------|-----------|
| `false` (default) | Direct write: AI output is committed to the database immediately — identical to existing behaviour. |
| `true` | Approval gate: AI output is stored as a **pending** `ApprovalItem`. The record is only committed after the doctor explicitly approves it via the REST API. |

## Lifecycle

```
pending → approved
       → rejected
```

An `ApprovalItem` starts as `pending`. It transitions to `approved` (which triggers the deferred DB write) or `rejected` (no write). Once approved or rejected it cannot be re-processed.

## Flow Diagram

```
Doctor speaks / types a command
          │
          ▼
  LLM dispatch (services/agent.py)
          │ intent = add_record
          ▼
  ┌─ APPROVAL_MODE_ENABLED? ─┐
  │                           │
 YES                          NO
  │                           │
  ▼                           ▼
store ApprovalItem       save_record()
  (status=pending)        cascade risk/tasks
  reply: draft + #id      reply: ✅ saved
  │
  ▼
Doctor: GET /api/approvals
  → review suggested_data (structured MedicalRecord fields)
  │
  ├─ PATCH /api/approvals/{id}/approve  [optional edited_data]
  │      │
  │      ▼
  │  commit_approval()
  │    find/create patient
  │    save_record() → cascade tasks + risk recompute
  │    update ApprovalItem(status=approved, record_id=...)
  │
  └─ PATCH /api/approvals/{id}/reject  [optional reviewer_note]
         │
         ▼
     update ApprovalItem(status=rejected)
     no DB write
```

## Data Model

### `approval_items` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | auto-increment |
| `doctor_id` | VARCHAR(64) | indexed |
| `item_type` | VARCHAR(32) | `"medical_record"` (v1) |
| `patient_id` | INTEGER FK → patients | NULL until approved |
| `record_id` | INTEGER FK → medical_records | NULL until approved |
| `suggested_data` | TEXT (JSON) | AI suggestion payload |
| `source_text` | TEXT | original transcript / user text |
| `status` | VARCHAR(32) | `pending \| approved \| rejected` |
| `reviewer_note` | TEXT | optional doctor comment on review |
| `reviewed_at` | DATETIME | set by `update_approval_item` |
| `created_at` | DATETIME | set on create |

### `suggested_data` JSON shape

```json
{
  "record": {
    "chief_complaint": "...",
    "history_of_present_illness": "...",
    "past_medical_history": "...",
    "physical_examination": "...",
    "auxiliary_examinations": "...",
    "diagnosis": "...",
    "treatment_plan": "...",
    "follow_up_plan": "..."
  },
  "patient_name": "张三",
  "gender": "男",
  "age": 58,
  "existing_patient_id": null
}
```

## API Reference

### `GET /api/approvals`

List approval items for a doctor.

**Query params**

| Param | Required | Description |
|-------|----------|-------------|
| `doctor_id` | ✅ | Doctor identifier |
| `status` | ❌ | Filter: `pending`, `approved`, `rejected`. Omit for all. |

**Response** — `200 OK` → `List[ApprovalItemOut]`

---

### `GET /api/approvals/{id}`

Retrieve a single approval item.

**Query params**: `doctor_id` (required)

**Response** — `200 OK` → `ApprovalItemOut` | `404` if not found or wrong doctor

---

### `PATCH /api/approvals/{id}/approve`

Approve an item and commit it to the database.

**Query params**: `doctor_id` (required)

**Body** (`ApproveRequest`):
```json
{
  "edited_data": { ... },    // optional: override suggested_data fields
  "reviewer_note": "LGTM"   // optional
}
```

**Response** — `200 OK` → `ApprovalItemOut` | `404` | `422` (already processed)

---

### `PATCH /api/approvals/{id}/reject`

Reject an item. No DB write occurs.

**Query params**: `doctor_id` (required)

**Body** (`RejectRequest`):
```json
{
  "reviewer_note": "Transcription error"  // optional
}
```

**Response** — `200 OK` → `ApprovalItemOut` | `404` | `422` (already processed)

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APPROVAL_MODE_ENABLED` | `false` | Set to `true`, `1`, or `yes` to enable the approval gate |

## Backward Compatibility

When `APPROVAL_MODE_ENABLED=false` (the default), the system behaves exactly as before — no `approval_items` rows are created and all existing API responses are unchanged. The `pending_approval_id` field in `ChatResponse` / `VoiceChatResponse` will be `null`.
