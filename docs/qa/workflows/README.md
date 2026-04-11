# Doctor Workflow QA Plans

Per-workflow QA plans for the doctor-ai-agent doctor app. **Each file is a
ship gate.** Before pushing to production, the affected workflow plans should
pass — both the manual checklist and the matching Playwright spec.

```
docs/qa/workflows/          ← authoritative checklist (this directory)
frontend/web/tests/e2e/     ← matching Playwright spec per workflow
```

The MD file is the source of truth. The spec is the automation.

## Index

| # | Workflow | File | Spec | Touches |
|---|----------|------|------|---------|
| 01 | Auth (login / logout / history safety) | [01-auth.md](01-auth.md) | `01-auth.spec.ts` | `/login`, `SettingsPage` |
| 02 | Doctor onboarding wizard | [02-onboarding.md](02-onboarding.md) | `02-onboarding.spec.ts` | `OnboardingWizard.jsx` |
| 03 | My AI tab overview | [03-my-ai-overview.md](03-my-ai-overview.md) | `03-my-ai-overview.spec.ts` | `MyAIPage.jsx` |
| 04 | Persona rules CRUD | [04-persona-rules.md](04-persona-rules.md) | `04-persona-rules.spec.ts` | `PersonaSubpage.jsx` |
| 05 | Knowledge CRUD (4 sources) | [05-knowledge.md](05-knowledge.md) | `05-knowledge.spec.ts` | `KnowledgeSubpage.jsx`, `AddKnowledgeSubpage.jsx`, `KnowledgeDetailSubpage.jsx` |
| 06 | Patient list + search | [06-patient-list.md](06-patient-list.md) | `06-patient-list.spec.ts` | `PatientsPage.jsx` |
| 07 | Patient detail + records | [07-patient-detail.md](07-patient-detail.md) | `07-patient-detail.spec.ts` | `patients/PatientDetail.jsx` |
| 08 | Review diagnosis (审核 待审核) | [08-review-diagnosis.md](08-review-diagnosis.md) | `08-review-diagnosis.spec.ts` | `ReviewQueuePage.jsx`, `ReviewPage.jsx` |
| 09 | Draft reply send (审核 待回复) | [09-draft-reply.md](09-draft-reply.md) | `09-draft-reply.spec.ts` | `ReviewQueuePage.jsx`, `patients/PatientDetail.jsx` |
| 10 | Tasks browse + complete | [10-tasks.md](10-tasks.md) | `10-tasks.spec.ts` | `TaskPage.jsx`, `TaskDetailSubpage.jsx` |
| 11 | Settings (font / about / logout) | [11-settings.md](11-settings.md) | `11-settings.spec.ts` | `SettingsListSubpage.jsx`, `fontScaleStore.js` |

## Shared pre-flight

Every workflow assumes the same local environment. Run these once before
starting any workflow spec.

### 1. Start backend (NO_PROXY required)

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
NO_PROXY=* no_proxy=* PYTHONPATH=src \
  .venv/bin/python -m uvicorn main:app --port 8000 --app-dir src
```

`NO_PROXY=*` is mandatory — without it all LLM calls fail silently (see
BUG-04 in `docs/qa/hero-path-qa-plan.md`). The `trust_env=False` fix in the
httpx clients makes this redundant in production, but local dev still uses
it as a belt-and-braces guard.

### 2. Start frontend (stable mode)

```bash
cd frontend/web
npm run dev:stable   # VITE_NO_HMR=1 — prevents flaky reloads during tests
```

### 3. Playwright one-time install (first run only)

```bash
cd frontend/web
npm install
npx playwright install chromium
```

### 4. Sanity check

```bash
curl -s http://127.0.0.1:8000/api/health           # {"status":"ok"}
curl -sI http://127.0.0.1:5173/login | head -1     # HTTP/1.1 200 OK
```

### Test account seeding

Each Playwright spec registers its own doctor via the `doctorAuth` fixture —
no manual seeding needed. For manual runs, use this one-liner:

```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/unified/register/doctor \
  -H "Content-Type: application/json" \
  -d '{"name":"测试医生","phone":"13800138001","year_of_birth":1980,"invite_code":"WELCOME"}'
# → save doctor_id + token. Login at http://127.0.0.1:5173/login
#   with 昵称=13800138001, 口令=1980
```

Re-running on a dirty DB will hit "phone already registered" (400) — use
`/api/auth/unified/login` with the same credentials instead.

## When to run what

| Trigger | Run these plans |
|---------|-----------------|
| Any change to login / auth / doctor store | 01, 03 |
| Any change to MyAIPage / doctor home | 03, 04 |
| Any change to persona | 04 |
| Any change to knowledge ingestion / rendering | 05, 08 (citations) |
| Any change to patient list / search | 06 |
| Any change to patient detail / records | 07 |
| Any change to review queue or suggestions | 08, 09 |
| Any change to draft reply / send flow | 09 |
| Any change to task queue | 10 |
| Any change to settings / theme / fontScale | 11 |
| **Before any production ship** | **All 11** — sequentially |

## Adding a new workflow

1. Copy [`_TEMPLATE.md`](_TEMPLATE.md) to `NN-my-workflow.md` and fill in.
2. Create `frontend/web/tests/e2e/NN-my-workflow.spec.ts` from the existing
   spec patterns (import `doctorAuth` fixture, seed via helpers in
   `fixtures/seed.ts`).
3. Add a row to the index table above.
4. Update the "When to run what" table.

## Authoring conventions

- **Scope** states exactly what this plan covers and what is out of scope.
  If you see yourself checking something "while you're here," it belongs in
  a different workflow plan.
- **Steps** are numbered so the Playwright spec can reference them
  (`// step 3.2`).
- **Verify** columns are **assertion-grade** — "text is 'X'" not "looks
  right." If it can't be asserted, it can't be automated.
- **Edge cases** are noted but not always automated — document them even
  when manual-only.
- **Known issues** links back to `hero-path-qa-plan.md` §Known Issues for
  the canonical bug registry — don't fork the bug list here.
