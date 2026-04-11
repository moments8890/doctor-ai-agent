# QA — Index & Workflow

This folder contains all QA plans, checklists, and session reports for doctor-ai-agent.

---

## When to run what

| Trigger | Run | Time |
|---------|-----|------|
| Before any production deploy | [`release-checklist.md`](release-checklist.md) + all [`workflows/`](workflows/README.md) | ~90 min |
| After any change to a specific feature | The matching file in [`workflows/`](workflows/README.md) | ~5 min per workflow |
| After any change to hero path (interview, review, reply) | [`hero-path-qa-plan.md`](hero-path-qa-plan.md) | ~45 min |
| After any change to knowledge, citations, or teaching loop | [`ai-thinks-like-me-qa-plan.md`](ai-thinks-like-me-qa-plan.md) | ~45 min |
| Before first paying doctor (one-time) | [`deferred-qa-plan.md`](deferred-qa-plan.md) | ~2–4 hrs |
| Quarterly deep audit | [`qa-test-plan.md`](qa-test-plan.md) | ~4 hrs |

> **Per-workflow ship gates** live in [`workflows/`](workflows/README.md).
> Each file is a single doctor workflow (login, persona, review, etc.) with
> a matching Playwright spec in `frontend/web/tests/e2e/`. Use these as the
> default pre-ship check — they're scoped, fast, and automatable.

---

## Pre-release workflow (short version)

```
1. Run automated tests:  pytest tests/ + vitest
2. Start servers:        see Pre-flight in hero-path-qa-plan.md
3. Run hero path:        hero-path-qa-plan.md  (~45 min)
4. Run targeted e2e:     whichever of core-e2e / citation / tasks applies
5. Save report:          reports/qa-report-YYYY-MM-DD.md
6. All bugs P0/P1 fixed? → ship. P2/P3 deferred? → note in report.
```

Full details: [`release-checklist.md`](release-checklist.md)

---

## Test plan files

| File | What it covers | Cadence |
|------|---------------|---------|
| [`workflows/`](workflows/README.md) | **Per-workflow ship gates.** 11 files, one doctor workflow each: auth, onboarding, my-ai overview, persona, knowledge, patient list, patient detail, review diagnosis, draft reply, tasks, settings. Each has a matching Playwright spec. | Per-feature + every release |
| [`hero-path-qa-plan.md`](hero-path-qa-plan.md) | Broad reference: full doctor + patient hero path. Login → interview → diagnosis review → draft reply → send. Source of the BUG-01..07 registry. | Major releases |
| [`ai-thinks-like-me-qa-plan.md`](ai-thinks-like-me-qa-plan.md) | "AI thinks like me" loop. Knowledge ingestion (4 sources) → citation in diagnosis → teaching loop (edit → save rule) → round-trip validation → persona learning. | Every release |
| [`deferred-qa-plan.md`](deferred-qa-plan.md) | Deferred tests: data isolation, teaching loop deep, WeChat miniprogram, concurrency, LLM trust, triage safety. | Pre-first-doctor |
| [`qa-test-plan.md`](qa-test-plan.md) | Exhaustive 21-section pipeline reference covering all backend pipelines. | Quarterly |

---

## Reports

Session reports are saved in `reports/` as `qa-report-YYYY-MM-DD.md`.

Older session-specific QA runs (pre-April 2026) are in dated subdirectories:
`2026-03-25-full-app-qa/`, `2026-03-26-*/`, etc.

---

## Open bugs (as of 2026-04-08)

| ID | Severity | Description |
|----|----------|-------------|
| BUG-01 | P2 | Knowledge card dates show `-1天前` — UTC/local time mismatch |
| BUG-02 | P3 | Doctor greeting "测试医生医生" — redundant 医生 suffix |
| BUG-03 | P1 | Interview send crashes headless Playwright — needs real-device verify |
| BUG-04 | P0→env-fixed | Backend proxy — all LLM calls fail silently without `NO_PROXY=*` |
| BUG-05 | P3 | Review edit buttons 保存/取消 order reversed |
| BUG-06 | P2 | NL patient search returns empty for matching patients |
| BUG-07 | P2 | Browser back after logout shows settings page |

See `hero-path-qa-plan.md §Known Issues` for full details.
