# Documentation Index

This repo has several kinds of docs: active plans, design specs, product notes,
dated reviews, and operational guides. This index is the entrypoint for
contributors and AI coding agents.

## Start Here

- [`/AGENTS.md`](../AGENTS.md)
  Repo execution rules, config expectations, testing gates, and push policy.
  **Includes documentation standards** — read before creating any new docs.
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

## Folder Map

| Folder | Contents |
|--------|----------|
| `docs/plans/` | Active implementation plans |
| `docs/plans/archived/` | Completed plans retained for traceability |
| `docs/specs/` | Active design specs (brainstorm output, architecture decisions) |
| `docs/specs/archived/` | Completed design specs |
| `docs/product/` | Product strategy, requirements, gap analysis, UX reviews |
| `docs/review/` | Dated code/architecture reviews |
| `docs/qa/` | QA reports, simulation results, UI checkpoint screenshots |
| `docs/ux/` | UX design spec, wireframes, mockups |
| `docs/dev/` | Developer guides (setup, LLM providers, simulation, test strategy) |
| `docs/deploy/` | Deployment & infrastructure guides |
| `docs/release/` | App store submission, compliance materials |
| `docs/debug/` | Debug iteration logs |

## Source of Truth Rules

- Repo workflow rules come from [`/AGENTS.md`](../AGENTS.md).
- Documentation standards (where to put what) are defined in `AGENTS.md` § Documentation Standards.
- Current runtime behavior is defined by code first, then summarized in
  [`docs/review/architecture-overview.md`](review/architecture-overview.md).
- Active implementation intent belongs in `docs/plans/` (not `archived/`).
- Active design specs belong in `docs/specs/` (not `archived/`).
- Once a plan or spec is fully implemented, move it to the corresponding `archived/` folder.

## When Adding or Updating Docs

1. Prefer updating an existing authoritative doc over creating a new near-duplicate.
2. Put active plans in `docs/plans/`, active specs in `docs/specs/`.
3. Put dated reviews in `docs/review/MM-DD/`.
4. If a doc is historical and no longer actionable, move it to `archived/`.
5. If a doc references stale file paths or old architecture, rewrite it — don't keep two competing versions.
6. **Do NOT create docs under `docs/superpowers/`.** This prefix is deprecated.

## Key Product Docs

- [`docs/product/product-strategy-doctor-ai-agent-2026-03-20.md`](product/product-strategy-doctor-ai-agent-2026-03-20.md)
  Product positioning, user persona, AI role definition.
- [`docs/product/requirements-and-gaps.md`](product/requirements-and-gaps.md)
  4-phase feature roadmap with completion status.
- [`docs/product/feature-gap-analysis-2026-03-20.md`](product/feature-gap-analysis-2026-03-20.md)
  Code audit: what exists, what's missing, what's broken.
- [`docs/product/clinical-decision-support-design.md`](product/clinical-decision-support-design.md)
  CDS roadmap with per-feature implementation status.
- [`docs/product/domain-operations-design.md`](product/domain-operations-design.md)
  Domain ops design (Plan-and-Act architecture).
- [`docs/product/ux-review-consolidated.md`](product/ux-review-consolidated.md)
  UX review findings with prioritized action items.
- [`docs/ux/design-spec.md`](ux/design-spec.md)
  UX design specification (wireframes, flows).

## Related Process Docs

- [`docs/TESTING.md`](TESTING.md)
