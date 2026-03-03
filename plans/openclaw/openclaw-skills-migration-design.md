# OpenClaw Skills Migration Design

## Goal
Migrate the current Doctor AI system from a Python domain backend to an OpenClaw-native skills architecture, with a safe phased rollout and strict parity gates.

## Scope
This design covers:
- Target architecture in OpenClaw ecosystem
- Skill boundaries and responsibilities
- Data model and contracts
- Phased migration plan from current Python implementation
- Quality gates and rollback strategy

---

## 1. Target Architecture

### 1.1 Repository layout

```text
openclaw-medical/
├── skills/
│   ├── patient-intake/
│   ├── record-structuring/
│   ├── risk-engine/
│   ├── task-manager/
│   ├── approval-queue/
│   ├── notification-dispatch/
│   └── daily-digest/
├── packages/
│   ├── contracts/      # typed DTOs/events shared by all skills
│   ├── db/             # schema, migrations, repositories
│   ├── core/           # domain rules/models independent from transport
│   └── llm/            # Ollama client + prompt contracts
└── apps/
    └── doctor-ui/      # doctor-facing web UI
```

### 1.2 Runtime flow

```text
Patient channel (WeChat/voice/image)
  -> OpenClaw skill orchestration
  -> Domain skills (intake/structuring/risk/tasks/approval)
  -> SQLite (source of truth)
  -> Notification skills (wechat/sms/email)
  -> Doctor UI + daily digest
```

---

## 2. Skill Boundaries

### 2.1 patient-intake
- Input: incoming patient messages from channels
- Responsibility:
  - normalize source payload
  - persist raw event (`patient_events`)
  - infer/resolve patient identity (safe, deterministic)
- Output: `PatientEventCreated`

### 2.2 record-structuring
- Input: `PatientEventCreated`
- Responsibility:
  - run LLM extraction for structured medical fields
  - persist `medical_records`
  - persist extraction trace/audit metadata
- Output: `MedicalRecordCreated`

### 2.3 risk-engine
- Input: `MedicalRecordCreated`
- Responsibility:
  - compute patient risk level/score/tags
  - persist risk snapshot + rationale
- Output: `PatientRiskUpdated`

### 2.4 task-manager
- Input: `PatientRiskUpdated`, follow-up triggers, manual doctor actions
- Responsibility:
  - create/update/complete `doctor_tasks`
  - idempotency guard to avoid duplicate tasks
- Output: `TaskCreated`, `TaskCompleted`, `TaskDue`

### 2.5 approval-queue
- Input: AI-generated draft replies
- Responsibility:
  - persist pending drafts for doctor review
  - approve/reject workflow
- Output: `DraftApproved`, `DraftRejected`

### 2.6 notification-dispatch
- Input: `TaskDue`, `DraftApproved`, digest events
- Responsibility:
  - send to configured channels (wechat/sms/email)
  - retry/backoff
  - persist delivery logs
- Output: `NotificationSent`, `NotificationFailed`

### 2.7 daily-digest
- Trigger: OpenClaw cron
- Responsibility:
  - summarize patient activity and risks for doctor
  - send and archive digest
- Output: `DailyDigestSent`

---

## 3. Data Model (Minimum)

## 3.1 Core tables
- `patients`
- `patient_events` (raw free text/event payloads)
- `medical_records`
- `doctor_tasks`
- `draft_replies`
- `delivery_logs`
- `audit_log`

### 3.2 Recommended additions
- `patient_risk_snapshots`
- `task_attempts` (per-delivery retry trace)

### 3.3 Design principles
- Keep raw source event immutable (`patient_events`)
- Keep structured clinical fact mutable with version/audit
- Every automated action must have rationale in `audit_log`

---

## 4. Contracts and Events

### 4.1 Canonical events (examples)
- `PatientEventCreated`
- `MedicalRecordCreated`
- `PatientRiskUpdated`
- `TaskCreated`
- `TaskDue`
- `DraftApproved`
- `NotificationSent`

### 4.2 Contract requirements
- Stable IDs (`event_id`, `patient_id`, `record_id`, `task_id`)
- Event timestamps in UTC
- Explicit version field (`schema_version`)
- Idempotency key for all side-effect operations

---

## 5. Migration Strategy (Phased)

## Phase 0: Contract freeze
- Extract current Python API/domain payloads into typed contracts
- Build gold test fixtures from existing production-like cases

## Phase 1: Shadow mode (dual-run)
- Skills run in parallel; Python remains source of truth
- Compare outputs:
  - structuring fields
  - risk score/level
  - task creation decisions

## Phase 2: Low-risk cutover
- Cut over `daily-digest` and `notification-dispatch`
- Keep clinical decision path on Python backend

## Phase 3: Task cutover
- Cut over `task-manager`
- Enforce idempotency and duplicate suppression

## Phase 4: Risk + structuring cutover
- Cut over `risk-engine` and `record-structuring`
- Block rollout unless parity thresholds are met

## Phase 5: Intake cutover
- Route channel ingestion directly to `patient-intake`

## Phase 6: Decommission Python domain routes
- Keep read-only fallback window
- Remove old paths after stability period

---

## 6. Quality Gates (Go/No-go)

- Structured record field parity >= 95%
- Risk classification parity >= 99%
- Task generation parity >= 99.5%
- Duplicate notification rate = 0 in canary period
- 100% audit coverage on automated actions

If any gate fails:
- auto rollback to previous phase
- keep writing comparison logs for triage

---

## 7. Rollback and Safety

- Feature flags per skill/domain path
- Dual-write only where idempotent
- Hard rollback switch for notification sends
- Preserve Python path until 2 full release cycles are clean

---

## 8. First Sprint Plan

1. Create `packages/contracts` from existing Python payload shapes
2. Add `patient_events` and `delivery_logs` schema
3. Implement `patient-intake` and `daily-digest` skills
4. Build parity harness reusing existing corpus/tests
5. Add dashboard metrics for parity and failure rates

Deliverables:
- runnable skill skeletons
- migration feature flags
- parity report baseline

---

## 9. Decision Summary

- Long-term direction: OpenClaw-native domain skills
- Short-term strategy: phased migration with strict parity and rollback
- Rationale: preserve current proven logic while reducing rewrite risk

