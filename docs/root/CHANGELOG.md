# Changelog

## [Unreleased] — 2026-03-01

### Schema Changes

- **`Patient.age` → `Patient.year_of_birth`** — The `patients` table now stores year of birth instead of age, so age is always computed fresh as `current_year - year_of_birth` rather than going stale. On next startup the migration automatically renames the column in-place (no data loss). **Note:** existing rows stored a raw age value; those values will be incorrect as year-of-birth after the rename. Run the following SQL to fix old rows:
  ```sql
  UPDATE patients SET year_of_birth = strftime('%Y','now') - year_of_birth WHERE year_of_birth < 200;
  ```
  `NeuroCaseDB.age` and `IntentResult.age` are intentionally unchanged — they are denormalized/LLM-extracted scalars. The age→year_of_birth conversion happens only at the `create_patient` DB write boundary in `db/crud.py`.

### Bug Fixes

- **Integration test health check** — `conftest.py` now passes `follow_redirects=True` to the httpx server check so a `307 Temporary Redirect` from `/` no longer causes all integration tests to be spuriously skipped.
- **CI: unit job no longer collects integration tests** — added `--ignore=e2e` so skipped integration tests don't pollute unit test output.
- **CI: app readiness curl follows redirects** — added `-L` flag so the startup loop correctly follows the `307 → /chat` redirect.
- **Text pipeline name follow-up is now deterministic** — `POST /api/records/chat` now forces `add_record` when the previous assistant turn asked for patient name and the doctor replies with a name-only message (e.g., `陈明`). This removes routing-model variance that caused intermittent/frequent failures in `test_missing_name_asks_then_saves`, and prevents the name-only turn from polluting structured clinical text.

### Features

- **Patient timeline + risk-driven follow-up automation (v1, In Progress)**:
  - Added patient risk fields on `patients`: `primary_risk_level`, `risk_tags`, `risk_score`, `follow_up_state`, `risk_computed_at`, `risk_rules_version`
  - Added task trigger metadata on `doctor_tasks`: `trigger_source`, `trigger_reason`
  - Added deterministic risk engine: `services/patient_risk.py`
  - Added timeline assembler service: `services/patient_timeline.py`
  - `save_record()` now recomputes risk, and can auto-create idempotent follow-up tasks when `AUTO_FOLLOWUP_TASKS_ENABLED=true`
  - Extended Manage APIs:
    - `GET /api/manage/patients` now returns risk fields and supports `risk`, `follow_up_state`, `stale_risk` filters
    - `GET /api/manage/patients/grouped-risk` returns grouped risk buckets
    - `GET /api/manage/patients/{patient_id}/timeline` returns mixed record/task timeline events
  - Added risk recompute CLI: `scripts/recompute_patient_risk.py`
  - Updated React manage UI with risk badges/filters and a timeline debug panel

- **Patient categorization/grouping (In Progress)** — Structured patient grouping for faster triage and debug workflows:
  - Planned category outputs: `primary_category` + multi-tag grouping (`category_tags`) per patient
  - Deterministic rules engine with explicit precedence and `rules_version` tracking
  - Recompute hooks after patient/record writes, plus batch backfill CLI
  - API filters/grouped views for Manage (`category`, `tag`, stale-category checks)
  - Manage UI grouping/filter controls and visible category badges with debug rationale

- **Neurovascular structured extraction pipeline** — Full end-to-end pipeline for cerebrovascular/stroke cases:
  - `models/neuro_case.py` — Pydantic schema (`NeuroCase`, `ExtractionLog`, `RiskFactors`, `ImagingStudy`, `ImagingFinding`, `LabResult`, `PlanOrder`)
  - `db/models.py` — `NeuroCaseDB` table (promoted scalar columns: `patient_name`, `nihss`, `primary_diagnosis`, etc.) + full JSON blobs; created automatically on next startup via `create_all`
  - `services/neuro_structuring.py` — LLM extraction producing a two-section Markdown response (`## Structured_JSON` + `## Extraction_Log`); parser with raw-JSON fallback for non-compliant models; 60s prompt cache from DB key `structuring.neuro_cvd`
  - `routers/neuro.py` — `POST /api/neuro/from-text` and `GET /api/neuro/cases` REST endpoints
  - `db/init_db.py` — seeds `structuring.neuro_cvd` prompt on first startup (editable at `/admin → System Prompts`)
  - `main.py` — registers neuro router + `NeuroCaseAdmin` view in sqladmin

- **DB seed tool** (`scripts/seed_db.py`) — LLM-free path to bootstrap a fresh `patients.db` from a portable JSON fixture (`tests/fixtures/seed_data.json`).  Export once, commit the fixture, import anywhere:
  - `--export` — dumps `patients` + `medical_records` to JSON
  - `--import` — loads the fixture into a (new or existing) DB with patient/record deduplication
  - `--reset` — wipes patients + records and resets auto-increment counters
  - `--dry-run` — preview counts without writing anything
  - Combinations: `--reset --import` (clean dev reset), `--reset --no-import` (wipe only)
  - Deduplication keys: `(doctor_id, name)` for patients; `(patient_id, chief_complaint, created_at)` for records — safe to re-run multiple times
  - `system_prompts` and `doctor_contexts` are untouched by reset/import

- **Editable system prompt via Admin UI** — The structuring LLM prompt is now stored in the `system_prompts` DB table and editable at `/admin → System Prompts` without a server restart. Changes take effect within 60 seconds (TTL cache).
  - `structuring` key — base prompt (seeded from code on first startup)
  - `structuring.extension` key — optional doctor-defined additions appended to the base, allowing specialty-specific rules without replacing the full prompt

- **LLM agent dispatch** — Replaced rule-based intent detection with a pure LLM function-calling agent (`services/agent.py`). Every incoming message goes to the routing LLM which selects a tool (`create_patient`, `add_medical_record`, `query_records`, `list_patients`) and extracts parameters. Handles edge cases and natural language that keyword lists cannot.

- **Two independent LLM roles** — `ROUTING_LLM` (intent dispatch, ~300 tokens/call) and `STRUCTURING_LLM` (medical record JSON, ~800 tokens/call) are configured separately. `ROUTING_LLM` falls back to `STRUCTURING_LLM` if not set.

- **Conversation memory** — Two-layer context per doctor:
  - Rolling in-memory window (up to 10 turns) so pronouns like "他" resolve correctly
  - LLM-compressed persistent summary stored in `doctor_contexts` table, injected as a system message when starting a fresh session

- **Human-language E2E runner** (`scripts/run_chatlog_e2e.py`) — Replays real-world doctor chatlogs and verifies API+DB behavior, replacing the older train batch workflow.

### Fixes

- **LLM array/dict fields coerced to strings** — Some models (llama3.2, groq) return `treatment_plan`, `follow_up_plan`, or `auxiliary_examinations` as JSON arrays or objects. These are now joined into a flat string with `；` before Pydantic validation, preventing `ValidationError`.

- **Hallucination prevention in structuring prompt** — Added `【严禁虚构】` rules: no fabricated vitals or lab values, no inferred treatment plans, no expanding terse input with unmentioned clinical details. Fields with no corresponding input must return `null`.

- **Patient name validation** — Server-side guard (`_is_valid_patient_name`) rejects names that contain question phrases (e.g. `这位患者叫什么名字`) — prevents the LLM from storing its own question as a patient name when context is ambiguous.

- **Anonymous patient handling** — Training script now uses `匿名患者` as a placeholder when a case has no patient name (`未报姓名`) and the agent asks for one.

### Documentation

- `ARCHITECTURE.md` — Updated env var names (`ROUTING_LLM`, `STRUCTURING_LLM`), added LLM roles table, added `llama3.2` as an Ollama model option.
- `.env.example` — Reflects new variable names and model choices.
- `debug/iteration_2026-03-01.md` — Root cause analysis and resolution tracking for training failures.

### Training Results

| Corpus | Model | Result |
|--------|-------|--------|
| `cardiology_v1` (20 cases) | llama3.2 | 17/20 (3 field type errors — fixed) |
| `cardiology_v1` (20 cases) | qwen2.5:7b | 20/20 ✅ |
| `cardiology_v2` (37 cases) | llama3.2 | 37/37 API ✅ — 2 DB name mismatches detected by verifier |
| `cardiology_v2` (37 cases) | qwen2.5:7b | pending |

### Recommendation

Use `OLLAMA_MODEL=qwen2.5:7b` for production. `llama3.2` passes API checks but hallucinates Chinese patient names (~2/37 cases), which the DB verifier now catches.
