# OpenClaw Skills Migration Spec

## Goal
Provide implementation-ready specs for migrating domain logic to OpenClaw skills:
1. SQL DDL for new tables
2. Skill interface signatures (input/output JSON schemas)
3. Phase rollout checklist with owners and exit criteria

---

## 1) SQL DDL

> Notes
- SQLite-first (compatible with current stack)
- UTC timestamps as ISO strings or DATETIME (current DB style)
- Keep immutable raw event rows for auditability

### 1.1 `patient_events`

```sql
CREATE TABLE IF NOT EXISTS patient_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  schema_version INTEGER NOT NULL DEFAULT 1,

  doctor_id TEXT NOT NULL,
  patient_id INTEGER NULL,

  source_channel TEXT NOT NULL,            -- wechat|voice|image|web
  source_message_id TEXT NULL,
  source_user_id TEXT NULL,

  event_type TEXT NOT NULL,                -- message|upload|action
  raw_text TEXT NULL,
  raw_payload_json TEXT NULL,

  language TEXT NULL,
  received_at DATETIME NOT NULL,
  occurred_at DATETIME NULL,

  trace_id TEXT NULL,
  idempotency_key TEXT NULL,

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS ix_patient_events_doctor_time
  ON patient_events(doctor_id, received_at DESC);

CREATE INDEX IF NOT EXISTS ix_patient_events_patient_time
  ON patient_events(patient_id, received_at DESC);

CREATE INDEX IF NOT EXISTS ix_patient_events_channel_msg
  ON patient_events(source_channel, source_message_id);
```

### 1.2 `delivery_logs`

```sql
CREATE TABLE IF NOT EXISTS delivery_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  delivery_id TEXT NOT NULL UNIQUE,
  schema_version INTEGER NOT NULL DEFAULT 1,

  doctor_id TEXT NOT NULL,
  task_id INTEGER NULL,
  draft_id INTEGER NULL,

  channel TEXT NOT NULL,                   -- wechat|sms|email
  destination TEXT NOT NULL,

  provider TEXT NOT NULL,                  -- wechat_api|twilio|smtp|log
  request_payload_json TEXT NULL,
  response_payload_json TEXT NULL,

  status TEXT NOT NULL,                    -- pending|sent|failed
  error_code TEXT NULL,
  error_message TEXT NULL,

  attempt INTEGER NOT NULL DEFAULT 1,
  sent_at DATETIME NULL,

  trace_id TEXT NULL,
  idempotency_key TEXT NULL,

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (task_id) REFERENCES doctor_tasks(id)
);

CREATE INDEX IF NOT EXISTS ix_delivery_logs_doctor_time
  ON delivery_logs(doctor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_delivery_logs_task
  ON delivery_logs(task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_delivery_logs_status
  ON delivery_logs(status, created_at DESC);
```

### 1.3 `audit_log`

```sql
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  audit_id TEXT NOT NULL UNIQUE,
  schema_version INTEGER NOT NULL DEFAULT 1,

  actor_type TEXT NOT NULL,                -- system|doctor|agent|skill
  actor_id TEXT NOT NULL,

  doctor_id TEXT NULL,
  patient_id INTEGER NULL,
  record_id INTEGER NULL,
  task_id INTEGER NULL,

  action TEXT NOT NULL,                    -- risk_recomputed|task_created|draft_approved|...
  reason TEXT NULL,

  input_ref_json TEXT NULL,                -- references to upstream IDs/events
  decision_json TEXT NULL,                 -- computed result/rationale

  trace_id TEXT NULL,
  idempotency_key TEXT NULL,

  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  FOREIGN KEY (patient_id) REFERENCES patients(id),
  FOREIGN KEY (record_id) REFERENCES medical_records(id),
  FOREIGN KEY (task_id) REFERENCES doctor_tasks(id)
);

CREATE INDEX IF NOT EXISTS ix_audit_log_doctor_time
  ON audit_log(doctor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_audit_log_patient_time
  ON audit_log(patient_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_audit_log_action_time
  ON audit_log(action, created_at DESC);
```

---

## 2) Skill Interface Signatures (JSON Schemas)

> Style
- JSON Schema draft-07
- Explicit `schema_version`
- All side-effect skills require `idempotency_key`

### 2.1 Shared envelope

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SkillEnvelope",
  "type": "object",
  "required": ["schema_version", "trace_id", "timestamp_utc"],
  "properties": {
    "schema_version": { "type": "integer", "minimum": 1 },
    "trace_id": { "type": "string", "minLength": 1 },
    "timestamp_utc": { "type": "string", "format": "date-time" },
    "idempotency_key": { "type": "string" }
  },
  "additionalProperties": true
}
```

### 2.2 `patient-intake`

Input:
```json
{
  "type": "object",
  "required": ["schema_version", "trace_id", "doctor_id", "source_channel", "event_type", "received_at"],
  "properties": {
    "schema_version": { "type": "integer" },
    "trace_id": { "type": "string" },
    "idempotency_key": { "type": "string" },
    "doctor_id": { "type": "string" },
    "patient_hint": { "type": "string" },
    "source_channel": { "type": "string", "enum": ["wechat", "voice", "image", "web"] },
    "source_message_id": { "type": "string" },
    "source_user_id": { "type": "string" },
    "event_type": { "type": "string", "enum": ["message", "upload", "action"] },
    "raw_text": { "type": "string" },
    "raw_payload": { "type": "object" },
    "received_at": { "type": "string", "format": "date-time" },
    "occurred_at": { "type": "string", "format": "date-time" }
  }
}
```

Output:
```json
{
  "type": "object",
  "required": ["event_id", "doctor_id", "created_at"],
  "properties": {
    "event_id": { "type": "string" },
    "doctor_id": { "type": "string" },
    "patient_id": { "type": ["integer", "null"] },
    "created_at": { "type": "string", "format": "date-time" }
  }
}
```

### 2.3 `record-structuring`

Input:
```json
{
  "type": "object",
  "required": ["schema_version", "trace_id", "doctor_id", "event_id"],
  "properties": {
    "schema_version": { "type": "integer" },
    "trace_id": { "type": "string" },
    "idempotency_key": { "type": "string" },
    "doctor_id": { "type": "string" },
    "patient_id": { "type": ["integer", "null"] },
    "event_id": { "type": "string" },
    "raw_text": { "type": "string" }
  }
}
```

Output:
```json
{
  "type": "object",
  "required": ["record_id", "doctor_id", "structured_fields"],
  "properties": {
    "record_id": { "type": "integer" },
    "doctor_id": { "type": "string" },
    "patient_id": { "type": ["integer", "null"] },
    "structured_fields": {
      "type": "object",
      "properties": {
        "chief_complaint": { "type": ["string", "null"] },
        "history_of_present_illness": { "type": ["string", "null"] },
        "past_medical_history": { "type": ["string", "null"] },
        "physical_examination": { "type": ["string", "null"] },
        "auxiliary_examinations": { "type": ["string", "null"] },
        "diagnosis": { "type": ["string", "null"] },
        "treatment_plan": { "type": ["string", "null"] },
        "follow_up_plan": { "type": ["string", "null"] }
      }
    },
    "extraction_trace": { "type": "object" }
  }
}
```

### 2.4 `risk-engine`

Input:
```json
{
  "type": "object",
  "required": ["schema_version", "trace_id", "doctor_id", "patient_id", "record_id"],
  "properties": {
    "schema_version": { "type": "integer" },
    "trace_id": { "type": "string" },
    "idempotency_key": { "type": "string" },
    "doctor_id": { "type": "string" },
    "patient_id": { "type": "integer" },
    "record_id": { "type": "integer" }
  }
}
```

Output:
```json
{
  "type": "object",
  "required": ["doctor_id", "patient_id", "risk_level", "risk_score"],
  "properties": {
    "doctor_id": { "type": "string" },
    "patient_id": { "type": "integer" },
    "risk_level": { "type": "string", "enum": ["low", "medium", "high"] },
    "risk_score": { "type": "integer", "minimum": 0, "maximum": 100 },
    "risk_tags": { "type": "array", "items": { "type": "string" } },
    "rationale": { "type": "object" }
  }
}
```

### 2.5 `task-manager`

Input:
```json
{
  "type": "object",
  "required": ["schema_version", "trace_id", "doctor_id", "task_type", "title"],
  "properties": {
    "schema_version": { "type": "integer" },
    "trace_id": { "type": "string" },
    "idempotency_key": { "type": "string" },
    "doctor_id": { "type": "string" },
    "patient_id": { "type": ["integer", "null"] },
    "record_id": { "type": ["integer", "null"] },
    "task_type": { "type": "string", "enum": ["follow_up", "emergency", "appointment"] },
    "title": { "type": "string" },
    "content": { "type": ["string", "null"] },
    "due_at": { "type": ["string", "null"], "format": "date-time" }
  }
}
```

Output:
```json
{
  "type": "object",
  "required": ["task_id", "status"],
  "properties": {
    "task_id": { "type": "integer" },
    "status": { "type": "string", "enum": ["pending", "completed", "cancelled"] },
    "created_at": { "type": "string", "format": "date-time" }
  }
}
```

### 2.6 `daily-digest`

Input:
```json
{
  "type": "object",
  "required": ["schema_version", "trace_id", "doctor_id", "date", "timezone"],
  "properties": {
    "schema_version": { "type": "integer" },
    "trace_id": { "type": "string" },
    "doctor_id": { "type": "string" },
    "date": { "type": "string", "format": "date" },
    "timezone": { "type": "string" },
    "max_items": { "type": "integer", "minimum": 3, "maximum": 30 }
  }
}
```

Output:
```json
{
  "type": "object",
  "required": ["doctor_id", "digest_text", "sections"],
  "properties": {
    "doctor_id": { "type": "string" },
    "digest_text": { "type": "string" },
    "sections": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["title", "items"],
        "properties": {
          "title": { "type": "string" },
          "items": { "type": "array", "items": { "type": "string" } }
        }
      }
    }
  }
}
```

---

## 3) Rollout Checklist (Owners + Exit Criteria)

## Phase 0 — Contract Freeze
Owner: Platform + Domain lead

- [ ] Extract canonical DTOs from current Python routes/services
- [ ] Build fixture set from real/integration cases
- [ ] Freeze `schema_version=1` for initial migration

Exit criteria:
- [ ] Contract review approved
- [ ] Fixture coverage >= 90% of common flows

## Phase 1 — Shadow Run
Owner: Skills team

- [ ] Run skills in read/compare mode only
- [ ] Persist parity diffs (structuring/risk/tasks)
- [ ] Build parity dashboard

Exit criteria:
- [ ] Structuring field parity >= 95%
- [ ] Risk parity >= 99%
- [ ] No critical safety mismatch unresolved

## Phase 2 — Low-risk Cutover
Owner: Integrations + Ops

- [ ] Cut over `daily-digest`
- [ ] Cut over `notification-dispatch`
- [ ] Keep clinical decisions on Python backend

Exit criteria:
- [ ] Delivery success rate >= 99%
- [ ] Duplicate sends = 0 in 14-day canary

## Phase 3 — Task Manager Cutover
Owner: Domain backend + Skills team

- [ ] Cut over task create/update/complete path
- [ ] Enable idempotency keys on all task side effects

Exit criteria:
- [ ] Task parity >= 99.5%
- [ ] No duplicate pending tasks for same trigger

## Phase 4 — Structuring + Risk Cutover
Owner: Clinical AI lead

- [ ] Cut over `record-structuring`
- [ ] Cut over `risk-engine`
- [ ] Enable audit logs for every decision

Exit criteria:
- [ ] Clinical sign-off on sampled cases
- [ ] Error budget within agreed SLO for 2 release cycles

## Phase 5 — Intake Cutover
Owner: Channel integrations

- [ ] Route channel ingress to `patient-intake`
- [ ] Keep Python ingestion as fallback for rollback window

Exit criteria:
- [ ] End-to-end flow success >= 99%
- [ ] Rollback drill completed successfully

## Phase 6 — Python Decommission
Owner: Tech lead

- [ ] Remove deprecated domain routes
- [ ] Archive parity tooling and migration flags
- [ ] Update architecture docs/runbooks

Exit criteria:
- [ ] 2 clean release cycles post-cutover
- [ ] Incident rate not worse than baseline

---

## 4) Operational SLO/Guardrails

- P95 intake-to-task latency <= 5s (non-LLM path)
- LLM structuring timeout budget <= 20s (configurable)
- Notification retry policy: exponential backoff + max attempts
- Mandatory audit row for all automated writes
- Hard fail-safe: if risk engine fails, default to conservative queue-for-review

---

## 5) Immediate Next Steps

1. Add DB migration files for the 3 tables above
2. Implement JSON schema validation middleware for skill I/O
3. Stand up Phase 1 shadow pipeline and parity report job
4. Define rollback runbook and ownership rota

