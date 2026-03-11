# Documentation Index

This repo has several kinds of docs: active plans, dated reviews, product notes,
prompt inventory, and DB notes. This index is the entrypoint for contributors and
AI coding agents.

## Start Here

- [`/AGENTS.md`](../AGENTS.md)
  Repo execution rules, config expectations, testing gates, and push policy.
- [`/README.md`](../README.md)
  Daily development entrypoints such as `./dev.sh start`, `./dev.sh test`, and `./dev.sh e2e`.
- [`docs/TESTING.md`](TESTING.md)
  Current test and evaluation workflow for unit, integration, and chatlog replay.
- [`docs/review/architecture-overview.md`](review/architecture-overview.md)
  Current architecture overview and system map.

## AI and Product Docs

- [`docs/ai/AI提示词文档.md`](ai/AI提示词文档.md)
  Prompt inventory, DB keys, and fallback prompt behavior.
- [`docs/ai/context-and-prompt-contract.md`](ai/context-and-prompt-contract.md)
  Normative contract for AI context assembly, prompt boundaries, and output expectations.
- [`docs/review/03-11/minimal-doctor-assistant-ux-principles.md`](review/03-11/minimal-doctor-assistant-ux-principles.md)
  Current doctor-facing UX contract.
- [`docs/review/03-11/llm-context-architecture-review-and-plan.md`](review/03-11/llm-context-architecture-review-and-plan.md)
  Current LLM context cleanup plan and status.
- [`docs/review/03-11/db-schema-tightening-plan.md`](review/03-11/db-schema-tightening-plan.md)
  Current DB schema-hardening plan and status.
- [`docs/product/ux-review-consolidated.md`](product/ux-review-consolidated.md)
  Product and UX review context.

## Folder Map

- `docs/plans/`
  Active plans and still-actionable backlog docs. This folder should not hold historical review snapshots.
- `docs/review/`
  Dated reviews, reviewed plans, and architecture assessment material.
- `docs/product/`
  Product framing, UX analysis, and feature gap notes.
- `docs/ai/`
  Prompt inventory and future AI contract docs.
- `docs/adr/`
  Architecture decision records for decisions that should stay stable across reviews and plans.
- `docs/db/`
  DB-specific notes and schema review material.
- `docs/process/`
  Contributor workflow docs such as plan lifecycle and review conventions.

## Source of Truth Rules

- Repo workflow rules come from [`/AGENTS.md`](../AGENTS.md).
- Current runtime behavior is defined by code first, then summarized in
  [`docs/review/architecture-overview.md`](review/architecture-overview.md).
- Active implementation intent belongs in `docs/plans/`.
- Once a plan is reviewed or partially completed, move the reviewed version into `docs/review/<date>/`.

## When Adding or Updating Docs

1. Prefer updating an existing authoritative doc over creating a new near-duplicate.
2. Put active work in `docs/plans/`.
3. Put dated reviews and reviewed plans in `docs/review/`.
4. If a doc is historical and no longer actionable, remove it from `docs/plans/`.
5. If a doc is still useful but references stale file paths or old runtime assumptions, rewrite it instead of keeping two competing versions.

## Related Process Docs

- [`docs/TESTING.md`](TESTING.md)
- [`docs/process/plan-lifecycle.md`](process/plan-lifecycle.md)
- [`docs/adr/README.md`](adr/README.md)
