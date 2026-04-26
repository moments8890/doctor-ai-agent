# E2E QA Test Guide

## Overview

Playwright E2E tests verify the doctor app's critical workflows before shipping.
Each spec file in `frontend/web/tests/e2e/` mirrors a numbered workflow.

Tests produce **videos** (`.webm`) and **screenshots** (`.png`) in
`frontend/web/test-results/` for human review. Each result folder includes a
`README.txt` describing the test steps visible in the video.

## Quick Start

```bash
# 1. Start backend (terminal 1)
cd /Volumes/ORICO/Code/doctor-ai-agent
NO_PROXY=* no_proxy=* PYTHONPATH=src \
  .venv/bin/python -m uvicorn main:app --port 8000 --app-dir src

# 2. Start frontend (terminal 2)
cd frontend/web && npm run dev

# 3. Run tests (terminal 3)
cd frontend/web && npx playwright test
```

Verify servers are up first:
```bash
curl -s http://127.0.0.1:8000/healthz          # backend health
curl -sI http://127.0.0.1:5173/login | head -1  # frontend
```

## Test Suites

| Spec | Workflow | What it covers |
|------|----------|----------------|
| `00-seed-smoke` | Pre-flight | Backend reachable, fixtures work, API contracts valid |
| `01-auth` | Auth | Login, invalid creds, logout, session persistence |
| `02-onboarding` | Wizard | Step 1-3 walkthrough, skip, knowledge add flow |
| `03-my-ai-overview` | My AI tab | Populated view, empty state, CTA navigation |
| `04-persona-rules` | Persona | Rule CRUD, field sections |
| `05-knowledge` | Knowledge | Text/URL/file add, search, detail view |
| `06-patient-list` | Patient list | Card content, search, empty state |
| `07-patient-detail` | Patient detail | Timeline, records, chat shortcut |
| `08-review-diagnosis` | Review | Diagnosis review, suggestions, citations |
| `09-draft-reply` | Drafts | Draft edit, send confirmation |
| `10-tasks` | Tasks | Task tabs, followups |
| `11-settings` | Settings | Account, tools, navigation |
| `12-new-record` | New record | Create record, patient name |
| `13-18` | Persona phase | Pending items, onboarding, teach, template, QR, teaching loop |
| `20-24` | Patient portal | Patient auth, chat, records, tasks, onboarding |

## Video Output

Tests record videos with `slowMo: 600` so each action is visible.

- **Always recorded**: `video: "on"` and `screenshot: "on"` in playwright.config.ts
- **Location**: `frontend/web/test-results/<test-name>/video.webm`
- **README**: Each folder has `README.txt` describing what you see in the video
- **View in VS Code**: Install "Video Preview" extension, then open `.webm` files

## Ship Gate — Pre-Push Checklist

Before pushing code, run the E2E suite as a quality gate:

```bash
cd frontend/web
rm -rf test-results
npx playwright test 00-seed-smoke.spec.ts 01-auth.spec.ts \
  02-onboarding.spec.ts 03-my-ai-overview.spec.ts
```

**Gate criteria:**
- All non-skipped tests must pass
- Review videos in `test-results/` for visual regressions
- Skipped tests (marked `test.skip`) are known issues, not regressions

For a full gate (all workflows):
```bash
npx playwright test
```

## Writing New Tests

### Selector Rules (CRITICAL)

The app uses custom components that don't render standard HTML elements:

| Component | Renders as | Use in tests | Never use |
|-----------|-----------|--------------|-----------|
| `AppButton` | `<Box>` (div) | `getByText("label")` | `getByRole("button")` |
| `ConfirmDialog` buttons | `AppButton` (div) | `locator("[role=dialog]").getByText("label", { exact: true })` | `getByRole("button")` |
| `BottomNavigationAction` | MUI button | `locator(".MuiBottomNavigationAction-label")` | `getByText()` (matches page content too) |

### Strict Mode

Playwright runs in strict mode — a locator matching multiple elements fails.
Common pitfalls:

- `getByText("添加")` matches "添加" AND "添加知识" → use `{ exact: true }`
- `getByText("我的AI")` matches nav + page title + CTA → use `.first()` or scope with `.locator()`
- `getByText("跳过")` in dialog matches title + message + button → scope to `[role=dialog]`

### Fixtures

- `doctorPage` — pre-authenticated doctor page (login + onboarding bypass)
- `doctor` — registered test doctor with unique phone
- `patient` — registered test patient linked to doctor
- `request` — Playwright API request context for seeding data

### Seed Helpers (`fixtures/seed.ts`)

```typescript
addKnowledgeText(request, doctor, content)           // category defaults to "custom"
addPersonaRule(request, doctor, field, text)          // field: reply_style|closing|structure|avoid|edits
completePatientIntake(request, patient, messages)  // returns { recordId }
sendPatientMessage(request, patient, text)
sendDoctorReply(request, doctor, patientId, text)
```

**Gotcha**: `addKnowledgeText` takes `(request, doctor, content, category)`.
The `category` must be a valid enum: `custom`, `diagnosis`, `followup`, `medication`.
Don't pass a Chinese title as category.

### Fresh Doctor State

Registration auto-seeds 3 knowledge items via `preseed_service`. A "fresh"
doctor is never truly empty — persona is empty but knowledge has 3 items.

### Known Skips

| Test | Reason | Ticket |
|------|--------|--------|
| 01-auth §4 BUG-07 | Browser-back after logout doesn't redirect | Needs SPA auth guard |
| 02-onboarding §3 | Step 2 confirm — hardcoded but can be enabled | Low priority |

## Generating README.txt Files

After running tests, generate step descriptions for human review:

```bash
# For each test result directory, create README.txt with:
# - Test name and status
# - What the test verifies
# - Numbered steps visible in the video
```

Claude Code should auto-generate these after each test run when preparing
videos for human review. See the existing README.txt files in test-results/
for the format.
