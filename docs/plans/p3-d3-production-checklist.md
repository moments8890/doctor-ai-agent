# P3-D3 Production-Like Checklist (Python/FastAPI)

## Goal
Close mission item `P3-D3` by validating a Python production-like release gate with
no critical gaps after `P3-D2` smoke coverage is in place.

## Critical-gap policy
Any unchecked item in **Critical Gates** is a blocking critical gap.
`P3-D3` completes only when all critical gates are checked.

## Critical Gates
- [x] Baseline unit suite passes:
      `.venv/bin/python -m pytest tests/ -v`
- [x] Coverage gate passes (overall >= 81%):
      `bash scripts/test.sh unit`
- [x] Diff coverage gate passes (changed-lines >= 81%):
      `.venv/bin/diff-cover reports/coverage/coverage.xml --compare-branch=origin/main --diff-range-notation=.. --fail-under=81`
- [x] P3-D2 chain test path passes (intake -> record -> risk -> task -> notification):
      `.venv/bin/python -m pytest tests/test_records_chat.py tests/test_patient_risk.py tests/test_tasks.py tests/test_notification.py -v`
- [x] Python mainline binding remains primary:
      `main.py` includes Python routers for records, voice, wechat, tasks, neuro, ui
- [x] Required Python modules exist for migration map:
      `routers/wechat.py`
      `services/transcription.py`
      `services/vision.py`
      `services/structuring.py`
      `services/patient_risk.py`
      `services/tasks.py`
      `services/wechat_notify.py`

## Evidence to include in handoff
- Exact commands executed
- Pass/fail result per gate
- Coverage numbers
- Residual risk summary (must be non-critical)

## Exit Criteria
Mark mission item `P3-D3` complete only when:
1. Every critical gate above is checked.
2. Reviewer confirms `APPROVED` and "no critical gaps" in `.coord/review.md`.

## Latest Validation
- Execution date: 2026-03-04 (America/Los_Angeles)
- Evidence:
  - `.coord/subagents/subagent-1-baseline.txt`
  - `.coord/subagents/subagent-2-coverage.txt`
  - `.coord/subagents/subagent-3-chain-and-binding.txt`
  - `.coord/subagents/subagent-4-modules.txt`
