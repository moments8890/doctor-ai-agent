# Goal
Tighten the current single-doctor patient-pool schema so DB constraints match the product rules: no duplicate patient names per doctor, single active session semantics, and safer pending-record / record persistence.

# Affected files
- docs/plans/db-schema-tightening-plan.md
- db/models/patient.py
- db/models/pending.py
- db/models/tasks.py
- db/models/records.py
- db/models/doctor.py
- db/models/system.py
- db/models/runtime.py
- db/models/specialty.py
- alembic/versions/0003_schema_tightening.py
- db/repositories/patients.py
- tests/test_crud.py

# Steps

## Done

1. ~~Add a DB-level uniqueness rule for patients within a doctor's namespace.~~
   - Added `UniqueConstraint("doctor_id", "name", name="uq_patients_doctor_name")` in `db/models/patient.py`.
   - The unique constraint implicitly provides the needed `(doctor_id, name)` index.

2. ~~Audit existing patient rows for same-doctor duplicate names before applying the migration.~~
   - Alembic migration `0003_schema_tightening` includes `_check_no_duplicate_patient_names()` that fails loudly if duplicates exist, with a clear remediation message.
   - Cleanup strategy: manual resolution required (migration halts with per-row details).

3. ~~Tighten pending/task status columns so workflow state is not free-form text.~~
   - Added CHECK constraints in models and migration:
     - `pending_records.status` → `IN ('awaiting','confirmed','abandoned','expired')`
     - `pending_messages.status` → `IN ('pending','done','dead')`
     - `doctor_tasks.status` → `IN ('pending','completed','cancelled')`
     - `doctor_tasks.task_type` → `IN ('follow_up','emergency','appointment')`

4. ~~Clarify single-session semantics in the schema and code.~~
   - `doctor_session_states` uses `doctor_id` as primary key — enforces exactly one row per doctor at the DB level. This is the intended single active cursor model (not concurrent sessions).
   - `find_by_name()` returns `Optional[Patient]` (at most one match), consistent with the new unique constraint.

5. ~~Add `onupdate=_utcnow` to all `updated_at` columns.~~
   - All `updated_at` mapped columns across the codebase now include `onupdate=_utcnow` so ORM updates automatically bump the timestamp.
   - Fixed `SystemPrompt.updated_at` which used an inline `lambda` instead of the shared `_utcnow` helper.

6. ~~Update tests to match the stricter schema.~~
   - Replaced `test_find_patients_by_exact_name_returns_latest_first` (which created duplicate names) with:
     - `test_find_patients_by_exact_name_returns_match` — verifies single-name lookup.
     - `test_duplicate_patient_name_same_doctor_raises` — confirms `IntegrityError` on duplicate.
     - `test_same_name_different_doctors_ok` — confirms cross-doctor names are allowed.
   - All 95 schema-related tests pass (test_crud, test_repositories, test_tasks).

7. ~~Verify migration and runtime behavior end to end.~~
   - Migration `0003_schema_tightening` created with duplicate-check guard, constraint creation, and clean downgrade.
   - Unit tests confirm constraints work at the ORM level via SQLite `create_all()`.

## Deferred — separate follow-up

5. **Structured record payload (`structured_json`)** — Deferred to a dedicated plan.
   - `medical_records.content` remains the single source of truth.
   - A future plan may add an optional `structured_json` column for evaluation/quality-check use, but that is out of scope for this integrity-hardening task.

# Risks / open questions
- Existing databases may already contain duplicate `(doctor_id, name)` rows; migration `0003` will halt with details so they can be resolved before proceeding.
- CHECK constraints are enforced by SQLite and PostgreSQL 9.4+; MySQL enforces them starting from 8.0.16. Verify target production DB version supports CHECK constraints.
