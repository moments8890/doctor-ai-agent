# Next Recommended Steps

1. Enforce PR-only workflow at GitHub level
- Turn off bypass for `main` so direct push cannot happen again.

2. Stabilize task scheduler in production-like environment
- Verify APScheduler lifecycle, duplicate-run protection, and notification retry behavior.

3. Harden categorization rollout
- Add feature flag default/off in production first.
- Run backfill and monitor category quality before enabling UI filtering by default.

4. Add observability dashboards
- Track task notification success/failure.
- Track overdue tasks.
- Track category recompute errors and uncategorized rate.

5. Close datetime technical debt
- Migrate `datetime.utcnow()` calls to timezone-aware UTC (`datetime.now(UTC)`).

6. Add one end-to-end smoke workflow
- Simulate: create patient → save record → task creation → list/complete task → category recompute visible in manage APIs/UI.
