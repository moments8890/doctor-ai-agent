# Plan and Review Lifecycle

This repo separates active work planning from dated review history.
Use this document to decide where a doc belongs and how it should move over time.

## Folder Responsibilities

### `docs/plans/`

Use for:

- active implementation plans
- still-actionable backlog docs
- deployment or integration plans that are not yet historical

Do not use for:

- dated review snapshots
- completed readiness reports
- post-implementation assessment writeups

### `docs/review/`

Use for:

- dated reviews
- reviewed plans after implementation or triage
- architecture assessment notes
- cross-review findings

Current repo convention uses dated folders such as:

- `docs/review/03-09/`
- `docs/review/03-10/`
- `docs/review/03-11/`

## Minimum Plan Shape

Active plans should usually include:

- `Goal`
- `Affected files`
- `Steps`
- `Risks / open questions`

If the plan is updated after implementation, it may also include:

- `Done`
- `Deferred`
- `Follow-up`

## Lifecycle

### 1. Create

Create a plan in `docs/plans/` when the work is still being scoped or actively executed.

### 2. Execute

As work lands, update the plan so it reflects reality:

- mark completed steps clearly
- call out deferred items explicitly
- remove stale assumptions

### 3. Review

Once the plan has been reviewed, partially completed, or converted into a decision record,
move the reviewed version into `docs/review/<date>/`.

### 4. Close

After closure:

- keep only the reviewed copy if the doc is historical
- keep an active copy in `docs/plans/` only if there is still open implementation work

## Status Language

Use consistent language:

- `Done` for completed items
- `Deferred` for intentionally postponed items
- `Superseded` when replaced by a newer plan or decision
- `Open questions` for unresolved design points

Avoid vague states such as "mostly done" or "probably complete".

## Cleanup Rules

Delete or move docs out of `docs/plans/` when they are:

- review snapshots tied to a past date
- completed readiness checklists
- obsolete recommendations replaced by newer decisions

Rewrite, do not duplicate, when a doc is still useful but:

- references stale file paths
- assumes old runtime behavior
- points to dead commands

## Practical Guidance for AI Contributors

Before creating a new plan:

1. Check whether an active plan already exists for the same workstream.
2. If a reviewed plan already exists in `docs/review/`, update or supersede it instead of creating a conflicting duplicate.
3. If a doc is historical, do not put it back into `docs/plans/`.

When in doubt:

- active future work -> `docs/plans/`
- dated assessment or reviewed plan -> `docs/review/`
