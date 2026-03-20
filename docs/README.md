# Documentation Index

This repo has several kinds of docs: active plans, dated reviews, product notes,
prompt inventory, and DB notes. This index is the entrypoint for contributors and
AI coding agents.

## Start Here

- [`/AGENTS.md`](../AGENTS.md)
  Repo execution rules, config expectations, testing gates, and push policy.
- [`/README.md`](../README.md)
  Daily development entrypoints such as `./cli.py start`, `./cli.py stop`, and `./cli.py bootstrap`.
- [`docs/TESTING.md`](TESTING.md)
  Current validation workflow, including the temporary no-new-unit-tests policy for the MVP phase.
- [`docs/review/architecture-overview.md`](review/architecture-overview.md)
  Current architecture overview and system map.

## Auth and Security

- **Mini-program login**: `POST /api/auth/wechat-mini/login` — exchanges WeChat `js_code` for an openid-linked doctor identity + JWT (`routers/auth.py`).
- **Invite-code web login**: `POST /api/auth/invite/login` — validates invite code, issues JWT, optionally links mini openid (`routers/auth.py`).
- **Patient portal session**: `POST /api/patient/session` — patient authenticates with name + doctor_id + access code; returns 24h JWT with `acv` for revocation (`routers/patient_portal.py`).
- **Access-code rotation**: `POST /api/patient/access-code` (doctor-facing) and `POST /api/mini/patients/{id}/access-code` — generates new 6-digit code, bumps `access_code_version` to invalidate outstanding patient tokens.
- **Admin/debug endpoints**: hidden from OpenAPI schema; require `X-Admin-Token` / `X-Debug-Token` headers; return 503 when unconfigured.
- **Production guards**: startup refuses to start without `WECHAT_ID_HMAC_KEY`, `PATIENT_PORTAL_SECRET`, `MINIPROGRAM_TOKEN_SECRET`, and `CORS_ALLOW_ORIGINS` (`main.py:_enforce_production_guards`).

## AI and Product Docs

- [`docs/ai/AI提示词文档.md`](ai/AI提示词文档.md)
  Prompt inventory, DB keys, and fallback prompt behavior.
- [`docs/ai/context-and-prompt-contract.md`](ai/context-and-prompt-contract.md)
  Normative contract for AI context assembly, prompt boundaries, and output expectations.
- [`docs/plans/adr-0007-blocked-write-continuation-execution-plan.md`](plans/adr-0007-blocked-write-continuation-execution-plan.md)
  Execution plan for ADR 0007: stateful blocked-write continuation and routing/structuring separation.
- [`docs/plans/adr-0009-modality-normalization-execution-plan.md`](plans/adr-0009-modality-normalization-execution-plan.md)
  Execution plan for ADR 0009: voice as normal message after transcription; image/PDF as import after extraction.
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
- `docs/plans/archived/`
  Closed implementation plans retained for traceability after execution.
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
- Active implementation intent belongs in `docs/plans/` and not in `docs/plans/archived/`.
- Once a plan is reviewed or closed, move the historical or retained version into `docs/review/<date>/` or `docs/plans/archived/`.

## When Adding or Updating Docs

1. Prefer updating an existing authoritative doc over creating a new near-duplicate.
2. Put active work in `docs/plans/`.
3. Put dated reviews and reviewed plans in `docs/review/`.
4. If a doc is historical and no longer actionable, move it out of active `docs/plans/` into `docs/plans/archived/` or `docs/review/`.
5. If a doc is still useful but references stale file paths or old runtime assumptions, rewrite it instead of keeping two competing versions.

## Related Process Docs

- [`docs/TESTING.md`](TESTING.md)
- [`docs/process/plan-lifecycle.md`](process/plan-lifecycle.md)
- [`docs/adr/README.md`](adr/README.md)
