# Playwright E2E Tests

End-to-end workflow tests for the doctor-ai-agent doctor app. Each spec file
mirrors one workflow plan in `docs/qa/workflows/`.

## Scope

These are **workflow gates** — run before shipping to verify the hero doctor
paths still work. They are **not**:

- Unit tests (see `vitest run` in this package).
- LLM quality checks (see the eval suite in `tests/` at repo root).
- Broad UI design audits (see `/design-review` skill).

If a test here fails, the workflow is broken. If a test here passes, the
workflow is on-path; it does **not** prove the LLM output is medically correct.

## One-time setup

```bash
# From frontend/web/
npm install                    # pulls @playwright/test
npx playwright install chromium   # ~140 MB — downloads browser binary
```

## Pre-flight (run these every session)

The Playwright config intentionally does **not** start servers. The backend
needs `NO_PROXY=*` and a specific startup order, and the frontend sometimes
needs HMR disabled. Start them yourself:

```bash
# Terminal 1 — TEST backend on :8001 with an isolated DB (never share with
# the dev DB on :8000 — see scripts/validate-v2-e2e.sh).
cd /Volumes/ORICO/Code/doctor-ai-agent
NO_PROXY=* no_proxy=* PYTHONPATH=src ENVIRONMENT=development \
  PATIENTS_DB_PATH=/tmp/e2e_test.db \
  .venv/bin/python -m uvicorn main:app --port 8001 --app-dir src

# Terminal 2 — frontend on :5173 (proxy points at :8001 for e2e)
cd frontend/web
npm run dev:stable   # HMR off — prevents flaky reloads during tests
```

Verify both are up:

```bash
curl -s http://127.0.0.1:8001/healthz            # expect 200
curl -sI http://127.0.0.1:5173/login | head -1   # expect 200
```

To start fresh between runs (recommended), wipe the test DB before launching
:8001:

```bash
rm -f /tmp/e2e_test.db
```

## Running tests

```bash
# All workflow specs (sequential)
npm run test:e2e

# One workflow
npx playwright test 01-auth.spec.ts

# Headed mode — watch the browser
npm run test:e2e:headed

# UI mode — interactive runner, great for debugging
npm run test:e2e:ui

# Debug a single test
npx playwright test 01-auth.spec.ts --debug
```

Reports land in `frontend/web/playwright-report/`. Open with
`npx playwright show-report`.

## Test data & fixtures

All specs use the `doctorAuth` fixture in `fixtures/doctor-auth.ts`, which:

1. Calls `POST /api/auth/unified/register/doctor` with a deterministic
   test doctor (phone prefixed with `138E2E`, suffixed with a per-run nonce
   to avoid phone collisions in re-runs).
2. Optionally registers a test patient linked to that doctor.
3. Writes the returned token into `localStorage` before navigating — same
   shape the frontend uses in real login.

If a workflow needs seeded data (knowledge rules, a completed interview,
an existing review suggestion), the spec calls into `fixtures/seed.ts`
helpers that hit the backend API directly. No Playwright click-dancing
to set up state — only to **verify** it.

## Relationship to docs/qa/workflows/

The MD files in `docs/qa/workflows/` are the authoritative description of
each workflow — they document scope, manual steps, validation criteria, and
known issues. The `.spec.ts` files in this directory are the **automated
execution** of those same steps.

When the workflow changes:

1. Update the MD file first (scope + manual steps).
2. Update the matching spec to match.
3. Run the spec to verify.

Never update the spec without updating the MD file — the MD is the spec's
source of truth.
