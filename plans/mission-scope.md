# Mission Scope (Python Mainline)

Single objective for orchestrator rounds: make Python/FastAPI backend the sole
production source of truth, while selectively adopting useful OpenClaw workflow patterns.
Do not assume any checklist item is complete until re-verified.

## Completion Checklist
- [x] P1-A1: Intake contracts in Python support text/message/voice/pdf metadata
- [x] P1-A2: Source-specific required fields are validated safely | depends: P1-A1
- [x] P1-A3: Text extraction fallback handles raw/transcript/attachment deterministically | depends: P1-A1
- [x] P1-A4: Tests cover intake validation matrix across source types | depends: P1-A2, P1-A3
- [x] P1-A5: Intake path persists normalized multimodal metadata to timeline records | depends: P1-A4
- [x] P1-A6: Router/service integration tests cover multimodal intake persistence | depends: P1-A5

- [x] P1-B1: Record structuring parses model output safely with deterministic fallback
- [x] P1-B2: Structuring normalization preserves clinical abbreviations verbatim | depends: P1-B1
- [x] P1-B3: Tests verify STEMI/BNP/EF/EGFR/HER2/ANC/PCI preservation | depends: P1-B2
- [x] P1-B4: Structured output remains export-ready and stable | depends: P1-B3

- [x] P1-C1: Timeline reads return longitudinal events consistently
- [x] P1-C2: Session state transitions remain low-friction in doctor workflows | depends: P1-C1
- [x] P1-C3: Tests cover timeline/workflow continuity regressions | depends: P1-C2

- [x] P2-A1: DB APIs expose stable timeline/task/risk read-write semantics
- [x] P2-A2: Routers/services use DB layer (no ad hoc direct DB access) | depends: P2-A1
- [x] P2-A3: Tests validate ordering, event types, and doctor isolation | depends: P2-A2

- [x] P2-B1: Risk rules remain deterministic and severity-mapped
- [x] P2-B2: Task queue prioritization respects risk + due time ordering | depends: P2-B1
- [x] P2-B3: Tests validate deterministic risk/priority outputs | depends: P2-B2

- [x] P2-C1: Layered low/medium/high communication routing implemented
- [x] P2-C2: Low-risk path auto-replies within policy bounds | depends: P2-C1
- [x] P2-C3: Medium-risk path enforces doctor-review draft flow | depends: P2-C1
- [x] P2-C4: High-risk path escalates for manual doctor handling | depends: P2-C1
- [x] P2-C5: Tests verify routing policy and doctor control boundaries | depends: P2-C2, P2-C3, P2-C4

- [x] P2-D1: Repetitive low-complexity intents are auto-triaged within safe bounds
- [x] P2-D2: Tests cover triage and draft behavior for repetitive intents | depends: P2-D1

- [x] P2-E1: History-first decision context combines prior records + timeline + trend
- [x] P2-E2: Replies consume history-first context before current intent | depends: P2-E1
- [x] P2-E3: Tests cover missing-history clarification/doctor-review fallback | depends: P2-E2

- [x] P3-A1: Knowledge-trigger interface exists for key disease-course decision points
- [x] P3-A2: Guideline/research triggers are integrated with safe fallback | depends: P3-A1
- [x] P3-A3: Tests validate trigger conditions and fallback behavior | depends: P3-A2

- [x] P3-B1: Calibration hooks allow safe prompt/rule tuning with audit metadata
- [x] P3-B2: Tests ensure calibration changes are traceable and non-breaking | depends: P3-B1

- [x] P3-C1: Structured interaction traces persist for replay/research
- [x] P3-C2: Decision traces persist (inputs/rules/outcomes) for teaching auditability | depends: P3-C1
- [x] P3-C3: Tests validate trace completeness and retrieval semantics | depends: P3-C2

- [x] P3-D1: Runbook validates Python app smoke path (API + DB + scheduler hooks)
- [x] P3-D2: End-to-end smoke verifies intake -> record -> risk -> task -> notification | depends: P3-D1
- [x] P3-D3: Production-like checklist passes with no critical gaps | depends: P3-D2

## Notes
- Keep each round incremental and reviewable.
- Mark complete only with explicit evidence from current execution.

## Latest Round Evidence
- Date: 2026-03-04 (America/Los_Angeles)
- Subagent logs:
  - `.coord/subagents/subagent-1-p1ab.txt`
  - `.coord/subagents/subagent-2-p1c-p2.txt`
  - `.coord/subagents/subagent-3-p3abc.txt`
  - `.coord/subagents/subagent-4-gates.txt`
- Full gates summary: 473 tests passed, coverage 91.21%, diff-cover passed.
