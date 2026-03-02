# Architecture Hardening v1

## Goal

Improve reliability, scalability readiness, and operational safety without a major rewrite.

## Scope

- Keep current FastAPI + service-layer structure.
- Harden write paths, background jobs, migrations, and observability.
- Preserve current product behavior while reducing risk.

## Recommendations

1. Separate write-critical path from side effects
- Keep patient/record writes synchronous and minimal.
- Move notifications and non-critical fan-out to background queue/outbox flow.
- Ensure failed notifications never block clinical data persistence.

2. Strengthen service boundaries
- Keep `routers/*` thin (validation + routing only).
- Move branching business logic to `services/*` consistently.
- Add service-level unit tests for all non-trivial decision trees.

3. Define SQLite exit criteria now
- Set concrete trigger points for Postgres migration:
  - concurrent writes crossing defined threshold
  - scheduler/task volume crossing threshold
  - multi-instance deployment requirement
- Prepare migration checklist before reaching those thresholds.

4. Formalize schema migration workflow
- Move from ad-hoc startup DDL evolution to explicit versioned migrations.
- Require migration review in PRs touching `db/models.py`.
- Add rollback notes for each migration where feasible.

5. Add first-class observability
- Introduce structured logs and baseline metrics:
  - intent dispatch failures
  - task notification success/failure
  - categorization recompute errors
  - scheduler lag / job runtime
  - DB query latency hot spots
- Add simple dashboards/alerts for top failure modes.

6. Enforce idempotency for async/background operations
- Make task notification and category recompute safe to retry.
- Add explicit idempotency tests for duplicate/at-least-once execution.
- Document retry semantics and deduplication keys.

7. Keep release/branch policy strict
- Maintain PR-only flow for `main`.
- Keep required status checks and no-bypass enforcement.
- Require branch to be up to date before merge for safer integrations.

## Execution Sequence

1. Observability baseline (logging + key counters)
2. Service-boundary cleanup in high-churn modules (`wechat`, tasks, categorization)
3. Async side-effect hardening (outbox/queue pattern)
4. Migration workflow formalization
5. SQLite-to-Postgres readiness playbook

## Success Criteria

- No clinical write failures caused by notification/task side effects.
- Clear visibility into top operational failures and latency.
- Background jobs can be retried safely without duplicate bad effects.
- Schema changes are reproducible and reviewable.
- Team can migrate off SQLite without emergency refactor.
