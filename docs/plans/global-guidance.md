# Global Orchestrator Guidance (Python/FastAPI)

## Product Mission
This codebase is the backend for a specialist physician AI agent (专科医师AI智能体).
The system serves specialist doctors directly.
Core value: reduce documentation burden, enable 1:N patient management at scale,
and surface risk-ranked signals so doctor time is spent on high-value decisions.

## Strategy (OpenClaw ideas, Python implementation)
Do not rewrite the Python app into OpenClaw modules.
Use `doctor-ai-agent` as the primary production system and selectively port useful
orchestration patterns from OpenClaw.

Migration mapping reference:
- `skills/patient-intake` -> `routers/wechat.py`, `services/transcription.py`, `services/vision.py`
- `skills/record-structuring` -> `services/structuring.py`
- `skills/risk-engine` -> `services/patient_risk.py`
- `skills/task-manager` + approval queue -> `db/models.py` (`doctor_tasks`) + `services/tasks.py`
- `skills/notification-dispatch` -> `services/wechat_notify.py`
- `skills/daily-digest` -> scheduled Python job (`services/tasks.py` + scheduler loop)

## Architecture Reference (Python)
- Interaction layer: `routers/wechat.py`, `routers/records.py`, `routers/voice.py`, `routers/ui.py`
- Clinical logic layer: `services/agent.py`, `services/intent.py`, `services/structuring.py`, `services/patient_risk.py`, `services/tasks.py`
- Persistence layer: `db/models.py`, `db/crud.py`
- App boundary: `main.py`

## Clinical Context Rules (history-first)
- Decisions must use longitudinal context, not only the latest message.
- Minimum context for decision/reply:
  - prior structured medical records
  - timeline events (tasks, reminders, transitions)
  - latest risk level/score/tags and trend direction
- If context is missing or inconsistent, route to clarification or doctor review.

## Language & Tooling
- Python/FastAPI only for core medical logic and APIs.
- Unit tests: `.venv/bin/python -m pytest tests/ -v`
- Coverage gate: `bash scripts/test.sh unit`
- Diff coverage gate:
  - `git fetch --no-tags origin main`
  - `.venv/bin/diff-cover reports/coverage/coverage.xml --compare-branch=origin/main --diff-range-notation=.. --fail-under=81`

## Quality Gates
- Unit tests must pass.
- Overall coverage must be >= 81%.
- Diff coverage must be >= 81%.
- Every new function/branch must have direct test coverage.

## Medical Safety (non-negotiable)
- Never fabricate labs/dosages/diagnoses.
- Preserve medical abbreviations verbatim (STEMI, BNP, PCI, EGFR, ANC, HER2, EF, NYHA, ICD).
- Risk triage logic must be deterministic and rule-based.
- Low/medium/high routing must keep doctor control boundaries explicit.

## Orchestration Policy
Use up to 4 parallel subagents per round:
1. Intake/structuring validation
2. Risk/task/notification validation
3. Test+coverage validation
4. Review/evidence packaging

## Review Standards
- Provide file:line references for blocking issues.
- Return `NOT_APPROVED` when critical gates fail.
- Approve only when each acceptance criterion is explicitly verified.

## Commit Format
- Prefix: `feat:` `fix:` `test:` `refactor:` `chore:` `docs:`
- Subject <= 72 chars, no trailing period.
