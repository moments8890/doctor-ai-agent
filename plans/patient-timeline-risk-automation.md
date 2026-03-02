# Patient Timeline + Risk-Driven Follow-Up Automation

## Goal
Build a doctor-facing workflow that unifies patient events into a timeline, computes risk and follow-up urgency, and automatically generates actionable tasks with traceable rule reasons.

## Affected files
- `db/models.py`
- `db/crud.py`
- `db/init_db.py`
- `services/patient_categorization.py`
- `services/tasks.py`
- `services/wechat_notify.py`
- `services/patient_timeline.py` (new)
- `services/patient_risk.py` (new)
- `routers/ui.py`
- `routers/tasks.py`
- `routers/wechat.py`
- `frontend/src/pages/ManagePage.jsx`
- `frontend/src/components/*` (new timeline/risk UI components)
- `tests/test_patient_risk.py` (new)
- `tests/test_patient_timeline.py` (new)
- `tests/integration/test_manage_tasks_pipeline.py`
- `tests/integration/test_text_pipeline.py`
- `tools/recompute_patient_risk.py` (new)
- `CHANGELOG.md`
- `ARCHITECTURE.md`

## Steps
1. Define risk and follow-up outcomes
- Finalize core outcomes at patient level: `low`, `medium`, `high`, `critical`.
- Define follow-up states: `not_needed`, `scheduled`, `due_soon`, `overdue`.
- Keep one `primary_risk_level` and multiple `risk_tags` for filtering.

2. Add schema fields for risk/timeline actions
- Extend patient table with:
  - `primary_risk_level`
  - `risk_tags` (JSON/text)
  - `risk_score` (numeric)
  - `risk_computed_at`
  - `risk_rules_version`
- Add task linkage fields:
  - `trigger_source` (`manual`, `risk_engine`, `timeline_rule`)
  - `trigger_reason` (text)
- Add indexes for common list/filter queries.

3. Implement deterministic risk engine
- Add `services/patient_risk.py` with:
  - `compute_patient_risk(patient, latest_record, history) -> RiskResult`
  - explicit rule precedence and stable scoring
  - structured reason payload (`matched_rules`, `source_fields`, `explanation`)
- Reuse patient categorization signals where applicable to avoid duplicated rule logic.

4. Implement timeline assembler service
- Add `services/patient_timeline.py`:
  - normalize records/tasks/notifications into a single event shape
  - sort chronologically, support pagination/windowing
  - annotate timeline events with risk deltas when risk changes

5. Wire trigger points and automation
- Recompute risk after record create/update and relevant patient updates.
- Create/refresh follow-up tasks based on risk + last follow-up plan.
- Enforce idempotency (no duplicate auto tasks for same trigger window).
- Add optional notification hook for high/critical changes.

6. Extend APIs for UI consumption
- Extend patient list API with risk fields and stale flags.
- Add timeline endpoint per patient (e.g. `/api/manage/patients/{id}/timeline`).
- Add grouped summary endpoint by risk/follow-up state.
- Add filters: `risk`, `risk_tags`, `follow_up_state`, `stale_risk`.

7. Update manage UI and debug visibility
- Show risk badge and follow-up state in patient cards/table.
- Add timeline panel in patient details view.
- Add debug section showing rule reasons and compute timestamp.
- Keep current raw-record debug block for low-level troubleshooting.

8. Backfill and operational tooling
- Add `tools/recompute_patient_risk.py` for full/batch recompute.
- Support dry-run mode and summary metrics.
- Document rollout order and rollback toggles.

9. Tests and quality gates
- Unit tests for rule precedence, edge dates, missing fields, conflicting signals.
- Integration tests for:
  - risk recompute on write
  - task auto-creation idempotency
  - timeline API ordering and payload correctness
  - filtering/grouping counts in manage endpoints
- Keep tests deterministic with mocked external I/O.

10. Docs and rollout
- Update `ARCHITECTURE.md` for new services, schema, and endpoint contracts.
- Add `CHANGELOG.md` entry as in-progress feature, then finalized on release.
- Rollout phases:
  - Phase 1: compute/store risk only (no auto-task)
  - Phase 2: enable auto-task creation under feature flag
  - Phase 3: enable notification escalation and dashboard defaults

## Risks / open questions
- Rule quality risk: weak initial thresholds can create noisy or unsafe escalations.
- Data quality risk: missing/ambiguous follow-up text may cause incorrect urgency.
- Operational risk: automatic task generation can spam doctors without strict idempotency.
- Compatibility risk: existing records may not contain fields required for robust scoring.
- Product decision needed: should doctors be allowed to override computed risk, and if yes, for how long?
- Product decision needed: whether notifications are immediate or bundled on schedule.

## Execution plan
1. Foundation (1 PR)
- Add schema fields, indexes, and minimal CRUD/API plumbing for risk metadata.
- Add feature flags: `PATIENT_RISK_ENABLED`, `AUTO_FOLLOWUP_TASKS_ENABLED`.

2. Risk engine (1 PR)
- Implement deterministic risk rules with versioning and reason payload.
- Add unit tests for boundary and precedence behavior.

3. Automation (1 PR)
- Hook recompute triggers on record writes.
- Implement idempotent auto-follow-up task creation and optional notifications.
- Add integration tests for task creation and dedup behavior.

4. Timeline API + UI (1 PR)
- Implement timeline service + endpoint + manage UI timeline panel.
- Expose risk/follow-up filters and grouped summaries in manage view.

5. Backfill + hardening (1 PR)
- Add recompute CLI tooling and metrics.
- Run dry-run, then full backfill in staging-like environment.
- Finalize docs and remove temporary compatibility shims.

## Exit criteria
- Doctors can see per-patient timeline and current risk/follow-up state in manage UI.
- New/updated records trigger deterministic risk recompute.
- High/critical or overdue conditions create exactly one actionable task per trigger window.
- API filters/grouping by risk and follow-up state are stable and tested.
- Unit + integration test suites remain green with required coverage threshold.
