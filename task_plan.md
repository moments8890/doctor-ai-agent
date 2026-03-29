# Task Plan: MUI Primitive Standardization

## Goal
Produce a concrete implementation plan to migrate thin shared UI primitives to public MUI components while preserving the current visual language and keeping domain-heavy doctor workflows custom.

## Current Phase
Phase 4

## Phases

### Phase 1: Inventory & Constraints
- [x] Review the UX inventory in `docs/ux/component-matrix.html` and `docs/ux/UI-DESIGN.md`
- [x] Read the current primitive implementations in `frontend/web/src/components/`
- [x] Separate thin wrappers from domain-specific workflow components
- **Status:** complete

### Phase 2: Public MUI Mapping
- [x] Compare the primitive layer to current public MUI components
- [x] Identify where MUI public components should replace hand-rolled wrappers
- [x] Identify components that should remain custom
- **Status:** complete

### Phase 3: Rollback Strategy
- [x] Define the rollback unit for the refactor
- [x] Decide whether a runtime flag is necessary
- [x] Define the visual verification loop before and after each batch
- **Status:** complete

### Phase 4: Plan Authoring
- [x] Write the repo plan document
- [x] Update planning artifacts with decisions and file targets
- [x] Prepare execution handoff options
- **Status:** complete

## Key Questions
1. Which shared components are only reimplementing standard button, list, chip, avatar, tab, dialog, or drawer behavior?
2. Which components encode product workflow logic and therefore should stay custom?
3. How do we stage the refactor so a visual mismatch can be reverted without backing out unrelated work?
4. Which docs need to change so the component inventory matches the actual code after the refactor?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep exported wrapper names stable in phase 1 | Limits call-site churn and makes rollback cheap |
| Use only public MUI components, props, slots, and theme overrides | Avoids fragile dependence on internal MUI class structure |
| Land one primitive family per commit | Makes visual rollback surgical instead of all-or-nothing |
| Do not add a permanent feature flag up front | Wrapper isolation plus commit-level rollback is cheaper and simpler |
| Keep `DiagnosisCard`, `FieldReviewCard`, `MessageTimeline`, `RecordCard`, `PageSkeleton`, and `SubpageHeader` custom | These are domain components, not generic primitives |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Existing planning files tracked an unrelated finished task | 1 | Reset planning artifacts for the current refactor-planning task |

## Notes
- Visual comparison should run through `/debug/components` before and after each batch.
- Manual QA must include at least one real page that uses each wrapper family, not just the showcase.
- Docs drift already exists around `BottomSheet.jsx` and `TasksPage.jsx`; plan includes cleanup.
