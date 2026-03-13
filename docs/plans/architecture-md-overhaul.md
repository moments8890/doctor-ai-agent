# Plan: ARCHITECTURE.md Overhaul

## Context

ARCHITECTURE.md has drifted from the codebase after several rounds of feature work
(compound draft-first unification, test consolidation, ADR 0009 modality normalization).
A joint peer review identified 6 user-reported issues and 10 additional structural/accuracy
problems. This plan fixes all of them in a single pass.

## Issues (combined, by section)

### High — Factual errors

| # | Location | Problem |
|---|----------|---------|
| H1 | :16, :35 | "one patient-scoped transaction per turn" — not true; separate DB sessions for knowledge, patient, pending draft |
| H2 | :43, :218, :338 | Compound create+record described as "directly saves inside create-patient handler" — all 3 channels now route through `shared_handle_add_record` → pending draft |
| H3 | :128-138 (web flow) | Diagram omits fast paths, pending-draft correction, blocked-write cancel, turn-context assembly order |
| H4 | :143-158 (wechat flow) | Diagram omits that WeChat does NOT pass `DoctorTurnContext`, and has structuring fallback on workflow failure |

### Medium — Misleading / incomplete

| # | Location | Problem |
|---|----------|---------|
| M1 | :479 | Lists `add_record + create_task` as planner compound — planner only emits `create_task` for `create_patient` turns; post-save follow-up task is a background side effect |
| M2 | :183 | Says "Image/PDF (`/from-image`, `/from-audio`)" — `/from-audio` is audio not PDF; no `/from-pdf` endpoint; PDF goes through `/extract-file` |
| M3 | :71 | Lists `routers/records_media.py` as live — not mounted in `main.py`; live media endpoints are in `routers/records.py` |
| M4 | :190-390 | Redundant: "Workflow Types and LLM Integration" re-explains same flows from "Doctor Message Flow" and "5-Layer Workflow" |
| M5 | (missing) | No description of error/failure handling per channel |
| M6 | (missing) | No description of pre-workflow fast-path layer |

### Low — Incomplete / minor

| # | Location | Problem |
|---|----------|---------|
| L1 | :554 | WeChat send path described as "WeCom customer-service API" — actually 3 modes: wecom_kf, wecom_app, oa |
| L2 | :656 | ADR 0009 missing from Key ADRs table |
| L3 | :609-623 | Persistence model diagram lists 14 models; codebase has 27 |
| L4 | :568-575 | Session model omits ephemeral fields: candidate_patient_name/gender/age, patient_not_found_name |
| L5 | :112 | `tests/` listed — directory deleted; tests consolidated into `e2e/` |
| L6 | :87-94 | `services/ai/` listing missing intent.py, llm_client.py, provider_registry.py, vision.py, etc. |

## Approach

Single-file edit to `ARCHITECTURE.md`. No structural reorganisation of the doc — just fix
what's wrong and add what's missing. Changes grouped by section:

### Step 1 — Overview block (:1-53)

- **H1**: Replace "one patient-scoped transaction per turn" with honest framing:
  "separate DB sessions per operation within a turn; no single-transaction guarantee yet"
- **H2**: Remove "Still in transition" bullet about compound create+record.
  Update to say compound create+record now routes through `shared_handle_add_record` → pending draft on all channels.
- Keep `update_record` compatibility bullet (still true).

### Step 2 — Directory structure (:56-116)

- **L5**: Replace `tests/` with `e2e/` and update description.
- **M3**: Remove `records_media.py` line (not mounted). Add comment that media endpoints live in `records.py`.
- **L6**: Add missing `services/ai/` modules (intent.py, llm_client.py, llm_resilience.py, provider_registry.py, vision.py, multi_intent.py, neuro_structuring.py, router.py).

### Step 3 — Doctor Message Flow (:120-188)

- **H3**: Update web flow diagram to include: fast paths → pending-draft correction → blocked-write cancel/precheck → assemble DoctorTurnContext → load knowledge → workflow → gate check → handler dispatch.
- **H4**: Update WeChat flow diagram to show: fast paths (task complete, notify, knowledge) → blocked-write precheck → load knowledge → workflow (no turn_context) → gate check → handler dispatch. Add note about structuring fallback on workflow failure.
- **M6**: Add a brief "Pre-workflow fast paths" subsection describing what short-circuits the workflow (greeting, patient count, delete-by-ID, notify control, knowledge add, task completion, pending-draft correction).
- **M2**: Fix modality normalization bullet: `/from-image` (image OCR → import_history), `/from-audio` (audio transcription → import_history). Remove "/from-pdf" claim. Note PDF goes through `/extract-file`.

### Step 4 — Workflow Types and LLM Integration (:190-390)

- **M4**: Collapse redundancy. Keep the workflow map table and the LLM role summary. Remove the 6 detailed workflow subsections (§1–§6) that duplicate info already in the flow diagrams and 5-layer sections. Replace with brief per-row notes in the table where needed.
- **H2**: Update compound create+record row: "Planner detects compound; dispatcher calls `shared_handle_create_patient` then `shared_handle_add_record` → normal pending-draft flow."
- **M5**: Add a "Failure handling" subsection after the workflow map: Web → HTTP 429/503; WeChat → structuring fallback; Voice → HTTP error.

### Step 5 — 5-Layer Intent Workflow (:393-486)

- **M1**: Fix compound planning list. Correct to:
  - `create_patient + add_record`
  - `create_patient + add_record + create_task`
  - `auto_create_patient + add_record` (weak-source patient)
  Remove `add_record + create_task`. Add note that post-save follow-up task creation is a background side effect in `_confirm_pending.py`, not a planner action.

### Step 6 — Session and Context Model (:560-601)

- **L4**: Add ephemeral fields to authoritative state list with "(ephemeral)" annotation:
  `candidate_patient_name`, `candidate_patient_gender`, `candidate_patient_age`, `patient_not_found_name`.

### Step 7 — Persistence Model (:605-635)

- **L3**: Expand entity tree to include missing models. Group into:
  - Core domain (existing)
  - Infrastructure (`RuntimeConfig`, `RuntimeCursor`, `RuntimeToken`, `SchedulerLease`)
  - Communication (`PatientMessage`, `PendingMessage`, `ChatArchive`)
  - Doctor config (`DoctorNotifyPreference`, `InviteCode`)
  - Export (`MedicalRecordExport`)
  - System (`SystemPrompt`, `SystemPromptVersion`)
  Or add a note: "Diagram shows core domain models only; infrastructure and auxiliary models omitted."

### Step 8 — Channel adapters (:539-557)

- **L1**: Update WeChat transport description: "WeChat replies are sent through `_send_customer_service_msg()`, which selects between WeCom KF, WeCom app messaging, or WeChat OA custom-send depending on config."

### Step 9 — Key ADRs table (:654-665)

- **L2**: Add row: `| 0009 | Modality Normalization at Workflow Entry | Complete |`

## Files modified

- `ARCHITECTURE.md` (single file)

## Verification

1. Read through the updated doc end-to-end for internal consistency.
2. Spot-check each fixed claim against the code references cited above.
3. No tests to run — doc-only change.
