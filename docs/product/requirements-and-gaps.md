# Product Requirements & Feature Gap Analysis

> Updated: 2026-03-17 | Based on stakeholder conversation + codebase audit
>
> **⚠️ CORRECTIONS (2026-03-27):**
> - ADR 0016 (Patient Interview): **✅ Implemented** — multi-turn interview with session state machine
> - ADR 0017 (Patient Onboarding): **✅ Implemented** — QR token endpoint + unified auth + QRDialog
> - ADR 0018 (Clinical Decision Support): **✅ Implemented** — full diagnosis pipeline + review UI
> - ADR 0022 (Knowledge Base): **✅ Implemented** — manual KB CRUD + document upload + LLM processing + citation
> - Deterministic doctor onboarding: **✅ Implemented** — 我的AI checklist, knowledge proof routing, doctor-side patient preview, review-task and follow-up-task bridges
> - ADR 0019 (External AI): NOT STARTED. ADR 0020 (Bidirectional): PARTIAL. ADR 0021 (Outcome Tracking): NOT STARTED.
> - Phases are **concurrent**, not sequential — Phases 1-3 are substantially on main.
> - File paths in Phase 0 section are stale; see `docs/architecture.md` for current module map.

## Product Vision

A neurology-first AI clinical assistant delivered via WeChat mini-program.
Patients self-serve pre-consultation; doctors receive structured records
with preliminary diagnostic suggestions; the system manages the full
patient lifecycle from intake through follow-up.

```
Patient → AI Interview → Structured Record → Doctor → AI Diagnosis → Decision
(pre-consult)  (voice Q&A)    (主诉/现病史/      (review,   (differential,
                               既往史/...)        modify)    treatment plan)
       ↑                                                          ↓
       └────────── reminders / follow-up / lifecycle ─────────────┘
```

Target user: Private practice / clinic doctors, starting with neurosurgery.
Entry point: WeChat mini-program (patient scans QR to enter).

---

## Phase 0 — Completed (Doctor-Side Foundation)

All features below are working end-to-end on `main`.

| # | Feature | Status | Key Files |
|---|---------|--------|-----------|
| 0.1 | UEC pipeline (understand → resolve → execute → compose) | Done | `services/runtime/` |
| 0.2 | 5 action types (none, query, record, update, task) | Done | `types.py`, `commit_engine.py` |
| 0.3 | Medical record structuring (content + structured + tags) | Done | `services/ai/structuring.py` |
| 0.4 | Record import: photo/PDF → structured record | Done | `services/record_import/` |
| 0.5 | Record export: PDF (single, batch, outpatient standard) | Done | `services/export/` |
| 0.6 | Patient CRUD (auto-create, search, switch) | Done | `resolve.py`, `db/crud/` |
| 0.7 | Task scheduling + rule-based auto-tasks + notifications | Done | `notify/task_rules.py` |
| 0.8 | WeChat doctor channel (text, image, PDF, voice) | Done | `channels/wechat/router.py` |
| 0.9 | Web UI: doctor chat, records, tasks, settings, admin | Done | `channels/web/ui/` |
| 0.10 | Patient portal (web): login, view records, send messages | Done (limited) | `channels/web/patient_portal.py` |
| 0.11 | Patient chat (WeChat): emergency detection, health Q&A | Done (limited) | `channels/wechat/patient_pipeline.py` |

---

## Phase 1 — Patient Pre-Consultation (病人端预问诊)

**Priority: Highest** — stakeholder directive: "建议从病人端做起"

The system currently has no way for patients to input clinical information
themselves. The doctor must manually dictate everything.

### F1.1 — AI-Guided Patient Interview

The AI conducts a structured clinical interview with the patient, acting as
a junior doctor. Conversation is voice-primary (with text fallback).

**Input:** Patient speaks/types symptoms.
**Output:** Structured record with 主诉, 现病史, 既往史, 个人史, 婚育史, 家族史.

Interview flow:
1. Collect demographics (name, gender, age, phone — minimal)
2. "你有什么不舒服？" → chief complaint
3. Follow-up questions based on symptoms → present illness
   - Onset, duration, severity, aggravating/relieving factors
   - Associated symptoms (guided by specialty knowledge base)
4. Systematic history: past medical, surgical, allergies, medications
5. Personal history (smoking, alcohol), family history
6. Patient reviews generated summary → confirms → submits to doctor

**ADR needed:** Yes — ADR 0016: Patient Pre-Consultation Interview Pipeline
- Interview state machine (multi-turn, session-based)
- How structured output maps to existing MedicalRecord schema
- Voice input handling (STT provider, latency, error recovery)
- Patient identity binding (no doctor_id at this stage)
- Privacy: patient data isolation before doctor accepts

### F1.2 — Patient Entry via QR / Mini-Program

Patients enter by scanning a doctor-specific QR code. No manual patient
creation by doctor needed.

**ADR needed:** Yes — ADR 0017: Patient Onboarding & Identity
- QR code generation per doctor
- Patient self-registration (name, phone, basic demographics)
- Identity binding: link WeChat OpenID to patient record
- Access model: patient belongs to doctor who generated the QR

### F1.3 — Patient Input Modes

Patients can provide information via:
1. **Voice** (primary) — STT → text → AI processing
2. **Text** — direct typing
3. **Photo** — upload existing medical records, lab results
4. **File** — PDF reports, prior discharge summaries

Photo/file import partially exists (vision_import.py) but is doctor-only.
Needs to be exposed to the patient interface.

**ADR needed:** No — extend existing import infrastructure to patient context.

---

## Phase 2 — AI Diagnostic Assistance (智能诊疗)

**Priority: High** — stakeholder: "希望能够有初步的诊断、鉴别诊断以及进一步治疗的建议"

Currently the system structures records but adds zero clinical intelligence.

### F2.1 — Preliminary Diagnosis & Differential

Given chief complaint + present illness + history, generate:
- Preliminary diagnosis (1-3 most likely)
- Differential diagnosis (3-5 alternatives to consider)
- Confidence indicators

Doctor reviews, selects/modifies, makes final decision.

**ADR needed:** Yes — ADR 0018: Clinical Decision Support Pipeline
- LLM prompt design for diagnostic reasoning
- Structured output format (diagnosis list with reasoning)
- Integration point in pipeline (post-structuring, pre-compose)
- Safety guardrails (disclaimers, never auto-confirm diagnoses)
- Specialty-specific vs general-purpose prompts

### F2.2 — Recommended Workup

Based on preliminary diagnosis, suggest:
- Laboratory tests
- Imaging studies
- Specialist referrals
- Procedures

**ADR needed:** Same ADR 0018 — part of the diagnostic output.

### F2.3 — Treatment Suggestions

Based on confirmed diagnosis, suggest:
- Medications (with dosing)
- Non-pharmacological interventions
- Follow-up plan

Doctor selects from suggestions or writes their own.

**ADR needed:** Same ADR 0018.

### F2.4 — External Model Integration

Stakeholder mentioned: "有很多成熟的公司做这一块工作了，但不知道如何导入".

Options:
- Bridge to external diagnostic APIs (e.g., 华佗GPT-style services)
- Use specialized medical LLMs (MedPaLM, HuatuoGPT, etc.)
- Fine-tuned models on neurology-specific datasets

**ADR needed:** Yes — ADR 0019: External Clinical AI Integration
- API contract for external diagnostic services
- Data format translation (our schema ↔ external schema)
- Fallback when external service is unavailable
- PHI/privacy considerations for external API calls

---

## Phase 3 — Doctor-Patient Communication Loop (医患闭环)

**Priority: Medium** — depends on Phase 1 and 2

### F3.1 — Post-Visit Patient Portal

After consultation, patient can:
- View diagnosis and treatment plan
- Ask follow-up questions (AI-mediated, escalated to doctor if needed)
- Report symptoms or side effects
- Upload new test results

Current patient portal only supports record viewing and basic messaging.

**ADR needed:** Yes — ADR 0020: Bidirectional Doctor-Patient Communication
- Message routing: patient → AI triage → doctor (if needed)
- Which messages need doctor attention vs AI-answerable
- Notification preferences for both sides

### F3.2 — Treatment Plan Visibility

Doctor creates a structured treatment plan; patient sees it as an
actionable checklist:
- Medications (with schedule)
- Lifestyle modifications
- Upcoming appointments
- Warning signs to watch for

**ADR needed:** No — extend existing task system with patient-visible flag.

### F3.3 — Bilateral Reminders

Both doctor and patient receive reminders for:
- Follow-up appointments
- Medication adjustments
- Lab/imaging result review
- Treatment milestones

Current task system sends doctor-only reminders via WeChat.
Needs extension to patient side.

**ADR needed:** No — extend existing notification infrastructure.

---

## Phase 4 — Full Lifecycle Management (全生命周期管理)

**Priority: Lower** — builds on all previous phases

### F4.1 — Treatment Plan Execution Tracking

Track patient adherence to treatment plan:
- Medication compliance
- Appointment attendance
- Outcome measurements over time

**ADR needed:** Yes — ADR 0021: Patient Outcome Tracking
- Data model for longitudinal tracking
- Patient self-reported outcomes
- Doctor-entered clinical outcomes

### F4.2 — Neurology Knowledge Base

Specialty-specific clinical knowledge:
- Disease-symptom mappings for neurological conditions
- Guided question trees per symptom (headache, weakness, numbness, seizure, etc.)
- "几百几千个问题" to cover the specialty
- Expand to other specialties after neuro validation

**ADR needed:** Yes — ADR 0022: Specialty Knowledge Base Architecture
- Knowledge representation (graph? rules? embeddings?)
- How it drives the patient interview (F1.1)
- How it feeds diagnostic suggestions (F2.1)
- Extensibility model for adding new specialties

### F4.3 — Multi-Specialty Expansion

After neurology is validated, replicate to:
- Cardiology, endocrinology, etc.
- Each specialty = new knowledge base + question trees
- Shared infrastructure, specialty-specific content

**ADR needed:** No — F4.2's architecture should handle this by design.

---

## ADR Roadmap

| ADR | Feature | Phase | Dependency |
|-----|---------|-------|------------|
| 0016 | Patient Pre-Consultation Interview Pipeline | 1 | None |
| 0017 | Patient Onboarding & Identity | 1 | None |
| 0018 | Clinical Decision Support Pipeline | 2 | F1.1 (needs structured input) |
| 0019 | External Clinical AI Integration | 2 | ADR 0018 |
| 0020 | Bidirectional Doctor-Patient Communication | 3 | F1.2, F2.1 |
| 0021 | Patient Outcome Tracking | 4 | F3.1, F3.2 |
| 0022 | Specialty Knowledge Base Architecture | 4 | F1.1, F2.1 |

**Suggested implementation order:**
1. ADR 0016 + 0017 (patient entry + interview) — unblocks everything
2. ADR 0018 (diagnostic support) — highest value-add
3. ADR 0022 (knowledge base) — drives quality of 0016 and 0018
4. ADR 0019, 0020, 0021 — incremental additions

---

## Reference

- Stakeholder conversation: 2026-03-17
- 卫医政发〔2010〕11号 《病历书写基本规范》: https://www.nhc.gov.cn/wjw/gfxwj/200205/8348500efb5b490c8db6519e818e96e3.shtml
- Comparable product: 华佗GPT (hospital-facing pre-consultation system)
- Our differentiator: doctor-owned, not hospital-owned; WeChat-native; private practice focused
