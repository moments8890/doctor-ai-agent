# Patient Categorization and Grouping Plan

## 1. Define grouping outcomes and scope

- Align on first set of categories:
  - Clinical status: `new`, `active_followup`, `stable`, `high_risk`
  - Operational status: `needs_record_update`, `recent_visit`, `no_recent_visit`
  - Metadata groups: doctor, age band, gender
- Decide output style:
  - Single primary category per patient for dashboard sorting
  - Multiple tags per patient for filtering
- Define refresh policy:
  - Recompute on write (new/updated record)
  - Nightly full recompute for consistency backfill

## 2. Specify category rules in a versioned ruleset

- Create deterministic rule definitions with explicit precedence.
- Add rule versioning so category changes are traceable (`rules_version`).
- Keep rules declarative (config/module), not scattered in route handlers.
- Example rule inputs:
  - Last record timestamp
  - Presence of diagnosis keywords
  - Follow-up plan presence
  - Record count in recent window

## 3. Data model changes

- Add patient-level fields:
  - `primary_category` (string)
  - `category_tags` (json/text array)
  - `category_computed_at` (datetime)
  - `category_rules_version` (string/int)
- Optional audit table:
  - `patient_category_history` with old/new values + reason
- Add indexes for common filters:
  - `(doctor_id, primary_category)`
  - `(doctor_id, category_computed_at)`

## 4. Categorization service implementation

- Add `services/patient_categorization.py`.
- Expose functions:
  - `categorize_patient(patient, latest_record, history) -> CategoryResult`
  - `recompute_patient_category(patient_id)`
  - `recompute_all_categories(doctor_id=None, batch_size=...)`
- Return structured reason metadata for debugging:
  - matched rules
  - source fields used
  - confidence/priority

## 5. Trigger points and recompute pipeline

- Trigger recompute after:
  - patient created
  - record inserted/updated
  - follow-up fields changed
- Add batch CLI:
  - `scripts/recompute_patient_categories.py`
- Add idempotent background job option for scale.

## 6. API surface updates

- Extend patient list endpoint to include category fields.
- Add query params:
  - `category=...`
  - `tags=...`
  - `stale_category=true|false`
- Add optional grouped response endpoint:
  - `/api/manage/patients/grouped` returning `{group, count, items}`.

## 7. UI updates for manage view

- Add group/filter controls:
  - primary category select
  - tag chips
  - stale categorization toggle
- Add visible category badges in patient cards.
- Add debug drawer/panel:
  - show categorization reasons + computed timestamp.

## 8. Validation and test strategy

- Unit tests for rule engine:
  - boundary dates
  - conflicting rules and precedence
  - empty/missing fields
- Integration tests:
  - category recompute after record write
  - API filtering/group counts
- Regression fixtures:
  - known patient scenarios mapped to expected categories

## 9. Rollout and safety

- Phase 1: compute but do not filter UI by default.
- Phase 2: enable filters and grouped view.
- Phase 3: retire old ad-hoc filtering paths.
- Add feature flag:
  - `PATIENT_CATEGORIZATION_ENABLED=true/false`
- Add observability:
  - recompute success/failure counts
  - uncategorized rate
  - stale category rate

## 10. Documentation

- Add `ARCHITECTURE.md` section for category model and rule precedence.
- Add `TESTING.md` scenarios for category correctness.
- Add admin/ops notes for backfill and rule version migrations.

## Execution Plan

### Phase 0: Alignment and rule freeze

- Confirm category definitions, precedence, and thresholds.
- Finalize `rules_version` strategy (e.g., `v1`, `v1.1`).
- Lock acceptance criteria for first release.

Done when:
- Category matrix and precedence table are approved.
- Rule inputs and thresholds are documented in code-facing format.

### Phase 1: Schema and persistence foundations

- Add patient category columns and indexes.
- Add optional `patient_category_history` table (if enabled for v1).
- Add migration/backfill-safe defaults.

Done when:
- Migrations run cleanly on existing DB.
- Read/write queries for patient list remain performant.

### Phase 2: Rule engine and service layer

- Implement deterministic categorization engine.
- Return structured `CategoryResult` including reasons and priority.
- Add service functions for single and bulk recompute.

Done when:
- Unit tests cover precedence, boundary dates, and null/missing data.
- Recompute behavior is idempotent for repeated calls.

### Phase 3: Recompute triggers and batch tooling

- Hook recompute into patient/record write paths.
- Add CLI backfill/recompute tool with `--dry-run`, batching, and doctor scoping.
- Add optional background worker pathway for scale.

Done when:
- Category is updated automatically after relevant writes.
- Full recompute succeeds for a large doctor cohort without failures.

### Phase 4: API and UI delivery

- Extend patient APIs with category fields and filter params.
- Add grouped endpoint for summary views.
- Implement Manage UI filters, badges, and debug details panel.

Done when:
- API contract tests pass for filtering and grouped responses.
- UI can filter by category/tag and surface recompute/debug metadata.

### Phase 5: Rollout, guardrails, and observability

- Roll out behind `PATIENT_CATEGORIZATION_ENABLED`.
- Track metrics: recompute success/failure, uncategorized rate, stale rate.
- Enable by default after monitoring confidence.

Done when:
- Feature is stable in production traffic with acceptable error rates.
- No critical regressions in patient listing or record write paths.

## PR Breakdown

1. Schema + migration + indexes
2. Categorization service + unit tests
3. Write-path hooks + batch CLI
4. API filters/grouped endpoints + integration tests
5. Manage UI filters/badges/debug panel
6. Feature flag + observability wiring

## Suggested Milestone Gates

- Gate A: Schema merged and deploy verified
- Gate B: Engine correctness verified in test fixtures
- Gate C: End-to-end recompute verified in staging
- Gate D: UI + API filtering verified by clinicians
- Gate E: Feature flag enabled for all doctors
