# Pre-Release QA Checklist

Run this before every production deploy. Takes ~60 minutes for a normal release,
longer if any section fails and needs investigation.

**Save your report to:** `docs/qa/reports/qa-report-YYYY-MM-DD.md`
**Reference:** see `README.md` for the full test plan index.

---

## Step 0 — Automated Tests

Run before opening the browser. Don't skip.

```bash
# Backend tests
cd /Volumes/ORICO/Code/doctor-ai-agent
.venv/bin/python -m pytest tests/ -x -q --rootdir=.

# Frontend tests
cd frontend/web && npx vitest run
```

**Gate:** all tests must pass before proceeding. Fix failures first.

---

## Step 1 — Start Servers

```bash
# Backend — NO_PROXY required (BUG-04: silent LLM failure without it)
cd /Volumes/ORICO/Code/doctor-ai-agent
NO_PROXY=* no_proxy=* PYTHONPATH=src .venv/bin/python -m uvicorn main:app --port 8000 --app-dir src

# Frontend
cd frontend/web && npm run dev

# Verify both are up
curl -s http://127.0.0.1:8000/api/auth/unified/doctors | head -1
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5173
```

---

## Step 2 — Register Test Accounts

Run once per fresh DB. Skip if accounts exist.

```bash
# Doctor
curl -s -X POST http://127.0.0.1:8000/api/auth/unified/register/doctor \
  -H "Content-Type: application/json" \
  -d '{"name":"测试医生","phone":"13800138001","year_of_birth":1980,"invite_code":"WELCOME"}'
# Save doctor_id from response

# Patient (replace <doctor_id>)
curl -s -X POST http://127.0.0.1:8000/api/auth/unified/register/patient \
  -H "Content-Type: application/json" \
  -d '{"name":"测试患者","phone":"13900139001","year_of_birth":1990,"doctor_id":"<doctor_id>","gender":"male"}'
```

**Login:** `http://127.0.0.1:5173/login`
- Doctor: 昵称 = `13800138001`, 口令 = `1980`
- Patient: 昵称 = `13900139001`, 口令 = `1990`

---

## Step 3 — Hero Path Run + AI Thinks Like Me

Run both plans. Hero path first, then AI loop.

**3a. Hero path** — work through `hero-path-qa-plan.md` in order:

| Section | Area | Result | Notes |
|---------|------|--------|-------|
| 1 | App Load & Login | ☐ Pass ☐ Fail | |
| 2 | 我的AI Tab | ☐ Pass ☐ Fail | |
| 3 | 患者 Tab — Patient List | ☐ Pass ☐ Fail | |
| 4 | 患者 Tab — Patient Detail | ☐ Pass ☐ Fail | |
| 5 | 审核 — Review Queue | ☐ Pass ☐ Fail | |
| 6 | 审核 — 待回复 | ☐ Pass ☐ Fail | |
| 7 | Patient Portal Interview | ☐ Pass ☐ Fail | |
| 8 | Navigation & UI | ☐ Pass ☐ Fail | |
| 9 | Regression Checks | ☐ Pass ☐ Fail | |

**3b. AI thinks like me** — work through `ai-thinks-like-me-qa-plan.md` in order:

| Section | Area | Result | Notes |
|---------|------|--------|-------|
| 1 | Knowledge ingestion (4 sources) | ☐ Pass ☐ Fail | |
| 2 | Citation in diagnosis | ☐ Pass ☐ Fail | |
| 3 | Teaching loop | ☐ Pass ☐ Fail | |
| 4 | Round-trip validation | ☐ Pass ☐ Fail | **Ship gate** |
| 5 | Persona learning (basic) | ☐ Pass ☐ Fail | |
| 6 | Citation guardrails | ☐ Pass ☐ Fail | |

**Ship gate for 3b:** §4.4 (new teaching rule cited in next diagnosis) must pass.

---

Known-open bugs (don't fail on these unless you expect them to be fixed):

| Bug | Expected | Action if now passing |
|-----|---------|----------------------|
| BUG-01 | Dates still show -1天前 | Mark as fixed; update Known Issues |
| BUG-02 | Greeting shows 医生医生 | Mark as fixed |
| BUG-03 | Headless only; real device unverified | Test on device |
| BUG-05 | Edit buttons reversed | Mark as fixed |
| BUG-06 | NL search returns empty | Mark as fixed |
| BUG-07 | Back after logout shows settings | Mark as fixed |

---

## Step 4 — Spot Checks (run based on what changed)

Check git diff for changed areas and run targeted manual checks:

```bash
git diff origin/main --name-only | head -30
```

| If changed files include... | Spot check |
|-----------------------------|-----------|
| `src/domain/patient_lifecycle/` or interview pages | Re-run §7 (Patient Portal) of hero-path |
| `knowledge` in any path | Re-run §2 (我的AI) + §5 (Review Queue) of hero-path |
| `draft_handlers.py` or draft reply pages | Re-run §6 (待回复) of hero-path |
| Core pipeline (agent, prompts, intents) | Re-run full hero-path §1–9 |
| No specific match | Hero path §9 regressions only |

---

## Step 5 — Ship Decision

| Condition | Decision |
|-----------|----------|
| All Step 3 sections Pass; no new P0/P1 bugs | **SHIP** |
| Step 3 has 1–2 Fail on known open bugs (BUG-01/02/05/06/07) | **SHIP** with bug note in release |
| Step 3 has any new P0/P1 not on the known list | **BLOCK** — fix first |
| Step 0 (automated tests) failed | **BLOCK** — fix first |
| BUG-03 reproduced on real device | **BLOCK** — fix first |
| BUG-04 (proxy) triggered — LLM calls silent-failing | **BLOCK** — permanent code fix needed |

---

## Step 6 — Save Report

Copy this template to `docs/qa/reports/qa-report-YYYY-MM-DD.md`:

```markdown
# QA Report — YYYY-MM-DD

**Release:** vX.Y.Z (or commit SHA)
**QA engineer:** [name]
**Duration:** ~XX min
**Verdict:** SHIP / BLOCK

## Step 0 — Automated Tests
- Backend pytest: PASS / FAIL (N failed)
- Frontend vitest: PASS / FAIL (N failed)

## Step 3 — Hero Path

| Section | Result | Notes |
|---------|--------|-------|
| 1 App Load | | |
| 2 我的AI | | |
| 3 Patient List | | |
| 4 Patient Detail | | |
| 5 Review Queue | | |
| 6 待回复 | | |
| 7 Patient Portal | | |
| 8 Navigation | | |
| 9 Regressions | | |

## Step 4 — Targeted E2E
[which ran, results]

## New Bugs Found
[none / list]

## Known Bugs Status
| Bug | Status |
|-----|--------|
| BUG-01 (dates) | Still open / Fixed |
| BUG-02 (greeting) | Still open / Fixed |
| BUG-03 (send headless) | Still open / Fixed / Verified on device |
| BUG-05 (buttons) | Still open / Fixed |
| BUG-06 (NL search) | Still open / Fixed |
| BUG-07 (logout back) | Still open / Fixed |

## Decision
[reason for SHIP or BLOCK]
```

---

## History

| Date | Verdict | Notes |
|------|---------|-------|
| 2026-04-08 | First structured run | 7 bugs found; hero path passes end-to-end |
