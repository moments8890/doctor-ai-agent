# ADR 0016 — Patient Pre-Consultation Interview Pipeline

**Status:** Proposed
**Date:** 2026-03-17
**Spec:** `docs/superpowers/specs/2026-03-17-patient-pre-consultation-design.md`

## Context

The system currently operates as a doctor-side tool: doctors dictate clinical
content, the AI structures it into medical records. Patients have no way to
provide clinical information themselves before seeing the doctor.

The stakeholder vision is that patients complete a structured pre-consultation
interview via an AI assistant that acts like a junior doctor — collecting
chief complaint, present illness, past history, and other clinical fields.
The structured output is delivered to the doctor's task queue as a reviewable
record, reducing doctor workload and improving consultation efficiency.

### Requirements

1. Patients self-register and log in via web (phone + year_of_birth)
2. AI conducts a multi-turn clinical interview, collecting 7 structured fields
3. Patient reviews and confirms the summary before submission
4. Doctor receives a task with the structured record for review
5. No clinical diagnosis in v1 — smart note-taking only

### Why a New Pipeline

The existing UEC pipeline (ADR 0012) is designed for single-turn doctor intent
classification. The patient interview requires multi-turn goal-oriented
conversation with session state, progressive field extraction, and completeness
tracking. Forcing this into UEC would mean:

- Every patient message classified through intent recognition (wasteful)
- Resolve phase tries to bind doctor context (irrelevant during interview)
- Commit engine saves records on every turn (premature)

The interview pipeline shares infrastructure (LLM providers, DB models,
notifications, prompt loader, medical record schema) but has its own
conversation loop.

## Decision

### Architecture

```
┌─────────────────────────────────────────────────┐
│              Shared Infrastructure               │
│  LLM providers · DB models · Notifications       │
│  Prompt loader · Medical record schema           │
└──────────┬──────────────────────┬────────────────┘
           │                      │
   ┌───────▼───────┐    ┌────────▼─────────┐
   │  UEC Pipeline  │    │ Interview Pipeline│
   │  (doctor-side) │    │  (patient-side)   │
   │                │    │                   │
   │ understand     │    │ session manager   │
   │ resolve        │    │ interview LLM     │
   │ commit/read    │    │ field extractor   │
   │ compose        │    │ completeness check│
   └───────▲───────┘    └────────▲──────────┘
           │                      │
     Doctor UI/WeChat      Patient Web UI
```

Handoff point: interview pipeline creates `MedicalRecord` + `DoctorTask`.
Doctor interacts with it through the normal UEC pipeline.

### Interview Approach: Hybrid (B3)

Single LLM prompt per turn with full context (conversation history +
collected fields + missing fields). The LLM decides what to ask naturally.
A deterministic completeness checker runs after each turn to identify
gaps and trigger review transition.

Not phase-based (would feel rigid) and not tool-call-based (provider
support varies, harder to test).

### Patient Entry & Auth

- Public URL `/patient` — no doctor-specific URL needed
- Patient selects doctor via search/dropdown (doctors opt in with
  `accepting_patients=true`)
- Registration: name + gender + year_of_birth + phone
- Login: phone + year_of_birth (scoped per doctor)
- If doctor previously created the patient record, registration links
  to it (match by name, validate non-null fields, backfill nulls)

### Session Model

```sql
interview_sessions (
    id              VARCHAR(36) PK
    doctor_id       VARCHAR(64) FK
    patient_id      INTEGER FK
    status          VARCHAR(16)  -- interviewing | reviewing | confirmed | abandoned
    collected       TEXT         -- JSON dict of extracted fields
    conversation    TEXT         -- JSON array [{role, content, timestamp}]
    turn_count      INTEGER
    created_at      DATETIME
    updated_at      DATETIME
)
```

### Interview Turn Flow

```
Patient sends message
       │
       ▼
┌──────────────┐
│ Validate     │ — session not abandoned/confirmed
│ session      │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌─────────────────┐
│ Turn limit   │─yes─▶│ Force review    │
│ reached?     │     │ (MAX_TURNS=30)  │
└──────┬───────┘     └────────┬────────┘
       │no                    │
       ▼                      │
┌──────────────┐              │
│ Emergency    │─yes─▶ Return warning   │
│ keywords?    │      (continue allowed)│
└──────┬───────┘              │
       │no                    │
       ▼                      │
┌──────────────┐              │
│ Call         │              │
│ interview    │              │
│ LLM         │              │
└──────┬───────┘              │
       │                      │
       ▼                      │
┌──────────────┐              │
│ Merge        │              │
│ extracted    │              │
│ fields       │              │
└──────┬───────┘              │
       │                      │
       ▼                      │
┌──────────────┐              │
│ Completeness │              │
│ check        │              │
└──────┬───────┘              │
       │                      │
       ├── all filled ────────▶ Transition to "reviewing"
       │                      │
       ▼                      ▼
  Return reply          Return summary
  + collected           + collected
  + progress            + progress
  (status:              (status:
   interviewing)         reviewing)
```

### Field Collection

7 patient-collectable fields:

| Priority | Field | Merge |
|----------|-------|-------|
| Required | chief_complaint | Overwrite |
| Required | present_illness | Append |
| Ask | past_history | Append |
| Ask | allergy_history | Append |
| Ask | family_history | Append |
| Ask | personal_history | Append |
| Optional | marital_reproductive | Append |

Fields skipped (doctor fills): physical_exam, specialist_exam,
auxiliary_exam, diagnosis, treatment_plan, orders_followup, department.

Completeness gate: required fields filled + ask-at-least fields each
have a value (including explicit negatives like "无" or "不详").

### Handoff to Doctor

On patient confirmation:
1. Generate `MedicalRecord` (content + structured + tags,
   record_type="interview_summary", needs_review=true)
2. Create `DoctorTask` (task_type="general",
   title="审阅预问诊：{name}", linked to record)
3. Notify doctor via existing notification system
4. Record appears in patient's "我的病历"

Doctor reviews/edits via normal UEC pipeline (query, update).

### Safety

- Emergency keyword check (deterministic, before LLM call):
  胸痛, 呼吸困难, 意识丧失, 大出血, 抽搐, 剧烈头痛, etc.
  Returns warning but allows continuation if patient confirms stable.
- LLM prompt also instructs: emergency → suggest 120.
- No diagnosis, no prescriptions in v1.
- Rate limits on all interview endpoints.

### Patient UI

- WeChat-style chat, single column, mobile-first
- Live summary badge (tap to expand)
- Exit options: "保存退出" (resume later) or "放弃重来" (abandon)
- Resume active session from patient home page

## End-to-End Workflow

```
                    PATIENT SIDE                          DOCTOR SIDE
                    ──────────                            ───────────

           ┌──────────────────┐
           │ /patient          │
           │ Select doctor     │
           │ Register / Login  │
           └────────┬─────────┘
                    │
           ┌────────▼─────────┐
           │ Patient Home      │
           │ • 开始预问诊       │
           │ • 我的病历         │
           │ • 给医生留言       │
           └────────┬─────────┘
                    │ start interview
           ┌────────▼─────────┐
           │ Interview Chat    │
           │                   │
           │ AI: 有什么不舒服？ │
           │ Patient: 头痛3天  │
           │ AI: 持续性还是     │
           │     间歇性？      │
           │ Patient: 持续的   │
           │ AI: 以前有什么     │
           │     疾病吗？      │
           │ Patient: 高血压   │
           │ ...               │
           │                   │
           │ [摘要 7/7]        │
           └────────┬─────────┘
                    │ all fields collected
           ┌────────▼─────────┐
           │ Review Summary    │
           │                   │
           │ 主诉：头痛3天     │
           │ 现病史：持续性头痛 │
           │ 既往史：高血压     │
           │ ...               │
           │                   │
           │ [确认提交]        │
           └────────┬─────────┘
                    │ confirm
                    │
        ┌───────────▼────────────┐
        │ Create MedicalRecord   │
        │ record_type=           │
        │   "interview_summary"  │
        │ needs_review=true      │
        │                        │
        │ Create DoctorTask      │
        │ "审阅预问诊：王芳"     │
        └───────────┬────────────┘
                    │
           ┌────────▼─────────┐        ┌──────────────────┐
           │ Patient sees:     │        │ Doctor sees:      │
           │ "已提交给张医生"  │        │ 📋 待办任务       │
           │                   │        │ 🔴 审阅预问诊：   │
           │ Record appears in │        │    王芳     刚刚   │
           │ "我的病历"        │        │                   │
           └──────────────────┘        └────────┬─────────┘
                                                │ open task
                                       ┌────────▼─────────┐
                                       │ Review Record     │
                                       │                   │
                                       │ 主诉：头痛3天     │
                                       │ 现病史：...       │
                                       │                   │
                                       │ [编辑] [确认]     │
                                       └────────┬─────────┘
                                                │ UEC pipeline
                                                │ (query/update)
                                       ┌────────▼─────────┐
                                       │ Normal workflow   │
                                       │ Add diagnosis,    │
                                       │ treatment, etc.   │
                                       │ Mark task done    │
                                       └──────────────────┘
```

## New Files

```
src/
  channels/web/patient_ui.py              — patient web routes
  services/patient_interview/__init__.py
  services/patient_interview/session.py   — load, save, abandon
  services/patient_interview/turn.py      — interview_turn() core loop
  services/patient_interview/completeness.py — check + merge
  services/patient_interview/summary.py   — generate record from collected
  prompts/patient-interview.md            — interview LLM prompt
  db/models/interview_session.py          — InterviewSessionDB
```

## Modified Files

```
src/
  channels/web/patient_portal.py  — register-by-phone, login-by-phone, doctor search
  db/models/doctor.py             — accepting_patients, department columns
frontend/src/pages/PatientPage.jsx — patient home + interview chat UI
```

## Schema Changes

```sql
ALTER TABLE doctors ADD COLUMN accepting_patients BOOLEAN DEFAULT false;
ALTER TABLE doctors ADD COLUMN department VARCHAR(64);
CREATE INDEX ix_patients_doctor_phone ON patients(doctor_id, phone);

CREATE TABLE interview_sessions (
    id          VARCHAR(36) PRIMARY KEY,
    doctor_id   VARCHAR(64) NOT NULL REFERENCES doctors(doctor_id),
    patient_id  INTEGER NOT NULL REFERENCES patients(id),
    status      VARCHAR(16) NOT NULL DEFAULT 'interviewing',
    collected   TEXT,
    conversation TEXT,
    turn_count  INTEGER DEFAULT 0,
    created_at  DATETIME NOT NULL,
    updated_at  DATETIME NOT NULL
);
CREATE INDEX ix_interview_patient ON interview_sessions(patient_id, status);
CREATE INDEX ix_interview_doctor ON interview_sessions(doctor_id, status);
```

## API Endpoints

```
POST  /api/patient/register           — self-register
POST  /api/patient/login              — phone + year_of_birth
GET   /api/patient/doctors            — list accepting doctors

POST  /api/patient/interview/start    — create session
POST  /api/patient/interview/turn     — send message → reply
GET   /api/patient/interview/current  — active session state
POST  /api/patient/interview/confirm  — finalize → record + task
POST  /api/patient/interview/cancel   — abandon session
```

## Consequences

### Positive

- Patients provide structured clinical history before seeing doctor
- Doctor receives pre-filled record — reduces dictation time
- Existing UEC pipeline untouched — zero risk to doctor workflow
- Record schema (MedicalRecord, structured field) reused as-is
- Task system handles doctor notification — no new notification code
- Patient gets a persistent portal (login, records, messaging)

### Negative

- New pipeline to maintain alongside UEC
- LLM cost per interview (~10-20 turns × 1 call each)
- Token cost grows with conversation length (full context per turn)
- No voice input in v1 — text only

### Risks

- Interview quality depends on LLM prompt tuning (mitigate: iterate on
  prompt with real patient scenarios)
- Patients may give vague or incomplete answers (mitigate: completeness
  check ensures all fields addressed; "无"/"不详" accepted as valid)
- Conversation context may exceed LLM context window for very long
  interviews (mitigate: MAX_TURNS=30 cap)
