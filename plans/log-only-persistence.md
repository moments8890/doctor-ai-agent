# Feature: Append-only Persistence + Context Blobs

## Goal
Document the log-only persistence approach that keeps the existing schema while ensuring every change is recorded as an append-only event and conversation context is stored as blobs keyed by doctor+patient.

## Strategy
1. Patients and medical records remain in the current schema, but all updates create new rows or log entries rather than overwriting existing rows.
2. Introduce a `doctor_context_logs` table (doctor_id, patient_id, payload, created_at) to store compressed conversation summaries and history snapshots injected into prompts.
3. Task updates should append to `doctor_task_history` entries while keeping task rows immutable once created; status transitions derive from the latest history row.
4. Business logic reads the latest `doctor_task_history` entry rather than editing the master row, so we can replay or audit past statuses.
5. Maintain the existing LLM tool schema (patient name, diagnosis, etc.) and rely on the new logs purely for auditing and context injection.

## Testing
- Re-run `.venv/bin/python -m pytest tests/integration -v` after implementing updates to confirm the real-world scenarios still pass.
- Focus on the failing cases (`abbrev_heavy`, `short_english_mix`, `neuro_style_brief`); capture the log-only records to verify tokens exist in persisted blobs.
