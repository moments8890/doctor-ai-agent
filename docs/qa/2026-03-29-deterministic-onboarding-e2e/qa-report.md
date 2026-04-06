# Deterministic Onboarding E2E QA

- Date: 2026-03-29
- Surface: `frontend/web` mock app at `/debug/doctor`
- Mode: deterministic SPA walkthrough with mock API state seeded in-browser
- Result: 8 pass, 0 fail

## Flow Covered

1. `我的AI` checklist
2. Knowledge add with URL / file / text prefills
3. Post-save next-step sheet
4. Diagnosis review proof
5. Reply proof
6. Patient entry QR page
7. Doctor-side patient preview page
8. Patient submit -> review record + review task
9. Review finalize -> follow-up tasks

## Deterministic IDs Used

- Knowledge proof record: `102`
- Reply proof draft: `101`
- Seeded preview patient: `李阿姨`
- Preview-created review record: `108`
- Preview-created review task: `206`
- Finalize-created follow-up tasks: `207`, `208`

## Notes

- The walkthrough stayed in one browser SPA session because the mock provider resets on full page reload.
- The patient-submit and follow-up-task steps were seeded through the same mock API module instance used by the app, so the screenshots reflect real UI state in that session.
- Raw screenshots are embedded in [index.html](index.html).
