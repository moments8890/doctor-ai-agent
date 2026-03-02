# Changelog

## [Unreleased] — 2026-03-01

### Features

- **Editable system prompt via Admin UI** — The structuring LLM prompt is now stored in the `system_prompts` DB table and editable at `/admin → System Prompts` without a server restart. Changes take effect within 60 seconds (TTL cache).
  - `structuring` key — base prompt (seeded from code on first startup)
  - `structuring.extension` key — optional doctor-defined additions appended to the base, allowing specialty-specific rules without replacing the full prompt

- **LLM agent dispatch** — Replaced rule-based intent detection with a pure LLM function-calling agent (`services/agent.py`). Every incoming message goes to the routing LLM which selects a tool (`create_patient`, `add_medical_record`, `query_records`, `list_patients`) and extracts parameters. Handles edge cases and natural language that keyword lists cannot.

- **Two independent LLM roles** — `ROUTING_LLM` (intent dispatch, ~300 tokens/call) and `STRUCTURING_LLM` (medical record JSON, ~800 tokens/call) are configured separately. `ROUTING_LLM` falls back to `STRUCTURING_LLM` if not set.

- **Conversation memory** — Two-layer context per doctor:
  - Rolling in-memory window (up to 10 turns) so pronouns like "他" resolve correctly
  - LLM-compressed persistent summary stored in `doctor_contexts` table, injected as a system message when starting a fresh session

- **Training runner** (`tools/train.py`) — Batch-processes raw clinical case corpora through the full pipeline, with:
  - `--cases 013,018,020` — re-run specific cases without processing the full corpus
  - `--clean` — wipes all `train_*` test data from DB before running for a fresh slate
  - DB verification after each case: confirms patient row and medical record row were actually written with the correct patient name and non-null `chief_complaint`

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
