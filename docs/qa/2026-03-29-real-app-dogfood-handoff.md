# 2026-03-29 Real App Dogfood Handoff

## Goal

Capture the current implementation/debug state for the deterministic onboarding MVP while dogfooding the real app on `/doctor`, so another agent can continue without re-deriving context.

## Current Environment

- Repo: `/Volumes/ORICO/Code/doctor-ai-agent`
- Date: `2026-03-29`
- Real app URL: `http://127.0.0.1:5173/doctor`
- Backend URL: `http://127.0.0.1:8000`
- Clean doctor account for testing:
  - 昵称: `dev_clean_doctor`
  - 口令: `2468`
- Expected dev fallback behavior remains:
  - no login -> `test_doctor`
  - clean testing requires manual login as `dev_clean_doctor`

## Session Intent

The user is dogfooding the real app and wants issues fixed one at a time. Do not batch-propose redesigns. Record observations, validate root cause, fix one issue, then continue.

## Issues Observed By User

1. `开始体验 0/5` in `我的AI` is not visually obvious as the intended entry point.
2. Step 2 should require adding `3` knowledge entries from different sources, not just one save.
3. `看诊断示例` originally showed nothing for a clean real doctor.
4. Onboarding completion was being marked by click/navigation rather than actual task completion.
5. Diagnosis proof page looked duplicated / noisy / untrustworthy.
6. `完成审核` could be clicked before review work was actually complete.
7. Patient preview could stall at `6/7` or `100%` with no summary or submit path.
8. Patient preview showed intermittent `系统暂时繁忙，请稍后再试。` during otherwise continuing conversation.
9. After interview completion, the UI was repeatedly forcing an end state instead of letting the patient choose when to submit.
10. The top-bar review-ready action should follow the existing UI design and use at most 2 Chinese characters.

## Issues Fixed In This Session

### Issue 1: Patient preview completion state machine

Fixed the patient interview flow so completion emits a real review-ready state instead of silently getting stuck.

Implemented behavior:

- Backend emits `ready_to_review`
- Session moves to `reviewing` when required patient fields are complete
- Frontend auto-surfaces summary only on the first review-ready transition
- Patient can choose `继续补充` or `提交`
- After the first hint, subsequent input is treated as normal supplemental input
- The input bar remains available after review-ready, until actual submission

Files changed:

- [interview_models.py](/Volumes/ORICO/Code/doctor-ai-agent/src/domain/patients/interview_models.py)
- [interview_turn.py](/Volumes/ORICO/Code/doctor-ai-agent/src/domain/patients/interview_turn.py)
- [patient_interview_routes.py](/Volumes/ORICO/Code/doctor-ai-agent/src/channels/web/patient_interview_routes.py)
- [DoctorPage.jsx](/Volumes/ORICO/Code/doctor-ai-agent/frontend/web/src/pages/doctor/DoctorPage.jsx)
- [InterviewPage.jsx](/Volumes/ORICO/Code/doctor-ai-agent/frontend/web/src/pages/patient/InterviewPage.jsx)
- [mockApi.js](/Volumes/ORICO/Code/doctor-ai-agent/frontend/web/src/api/mockApi.js)
- [architecture.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/architecture.md)
- [feature-parity-matrix.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/product/feature-parity-matrix.md)

### Issue 3 blocker: deterministic diagnosis/reply proof data

`看诊断示例` and `看回复示例` were updated earlier in the session to create or reuse deterministic onboarding proof data for a clean real doctor, instead of relying on existing queue data.

Relevant backend/frontend files touched earlier in the session:

- [doctor_profile_handlers.py](/Volumes/ORICO/Code/doctor-ai-agent/src/channels/web/ui/doctor_profile_handlers.py)
- [ReviewPage.jsx](/Volumes/ORICO/Code/doctor-ai-agent/frontend/web/src/pages/doctor/ReviewPage.jsx)
- [ReviewQueuePage.jsx](/Volumes/ORICO/Code/doctor-ai-agent/frontend/web/src/pages/doctor/ReviewQueuePage.jsx)

## Runtime Regressions Fixed In This Session

### `Chip is not defined` in doctor-side patient preview

Root cause:

- Top-bar action in `DoctorPage.jsx` was refactored away from `Chip`
- `PreviewSummarySheet` still uses MUI `Chip`
- The import had been accidentally removed

Fix:

- Restored `Chip` import in [DoctorPage.jsx](/Volumes/ORICO/Code/doctor-ai-agent/frontend/web/src/pages/doctor/DoctorPage.jsx)

### `navigate is not defined` in `TaskPage`

Root cause:

- Task row click handlers called `navigate(...)`
- `TaskPage` never created a `navigate` function

Fix:

- Added `const navigate = useAppNavigate();` to [TaskPage.jsx](/Volumes/ORICO/Code/doctor-ai-agent/frontend/web/src/pages/doctor/TaskPage.jsx)

## Verification Performed

- `git diff --check` on touched frontend files
- `python -m py_compile` on patient interview backend files
- targeted manual smoke for patient interview `ready_to_review` behavior

No automated test suite was run.

## Current Known Remaining Queue

1. `开始体验` section visual hierarchy is still too weak on `我的AI`
2. Knowledge onboarding still completes after one save instead of requiring 3 source types
3. Diagnosis proof screen still needs data-quality / duplication cleanup
4. `完成审核` is still enabled too early and backend finalize still needs gating
5. Patient interview provider path still sometimes surfaces `系统暂时繁忙，请稍后再试。`
6. Onboarding completion semantics are still route/click driven in several screens

## Recommended Next Issue To Fix

Fix `完成审核` gating next.

Validated root cause:

- frontend enables finalize regardless of unresolved review items in [ReviewSubpage.jsx](/Volumes/ORICO/Code/doctor-ai-agent/frontend/web/src/pages/doctor/subpages/ReviewSubpage.jsx)
- backend finalize endpoint does not reject unresolved suggestions in [diagnosis_handlers.py](/Volumes/ORICO/Code/doctor-ai-agent/src/channels/web/ui/diagnosis_handlers.py)

Recommended fix direction:

- frontend: disable finalize until all required suggestions have decisions
- backend: reject finalize while unresolved suggestions remain

## Notes For Next Agent

- User wants incremental fixes, not a broad redesign.
- User is actively testing the real app, not only `/debug/doctor`.
- Do not change dev fallback behavior from `test_doctor` unless explicitly asked.
- If the UI still shows stale onboarding progress for `dev_clean_doctor`, clear:
  - `localStorage.removeItem("doctor_onboarding_state:v1:dev_clean_doctor")`
