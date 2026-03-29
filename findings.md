# Findings & Decisions

## Requirements
- Write a concrete refactor plan in the repo for replacing thin custom UI primitives with public MUI components where appropriate.
- Preserve the current product look and avoid flattening domain-specific workflows into stock MUI layouts.
- Explicitly consider rollback if the post-refactor UI does not look good.

## Research Findings
- The current primitive layer already depends on MUI, but several wrappers bypass MUI semantics by rendering clickable `Box` elements instead of public MUI components.
- Strong replacement candidates:
  - `AppButton.jsx` and `BarButton.jsx` -> `Button`
  - `ListCard.jsx` family -> `List`, `ListItem`, `ListItemButton`, `ListItemAvatar`, `ListItemText`
  - `NameAvatar.jsx` and `RecordTypeAvatar.jsx` -> `Avatar`
  - `StatusBadge.jsx` and `SuggestionChips.jsx` -> `Chip`
  - `FilterBar.jsx` -> `Tabs` and `Tab`
  - `ActionPanel.jsx` / documented bottom-sheet pattern -> `Drawer` or `SwipeableDrawer`
  - `ConfirmDialog.jsx`, `SheetDialog.jsx`, and `PatientPickerDialog.jsx` -> standardized on MUI dialog primitives
- Components that should remain custom because they encode workflow logic or bespoke layout:
  - `doctor/DiagnosisCard.jsx`
  - `doctor/FieldReviewCard.jsx`
  - `MessageTimeline.jsx`
  - `RecordCard.jsx`
  - `PageSkeleton.jsx`
  - `SubpageHeader.jsx`
- `ComponentShowcasePage.jsx` is the right validation surface because it already renders the shared primitive catalog through `/debug/components`.
- The frontend has `vitest` and `@testing-library/react` installed, but almost no component tests exist yet. A small primitive smoke-test file should be added as part of the refactor.
- Docs drift confirmed:
  - `docs/ux/UI-DESIGN.md` references `frontend/web/src/components/BottomSheet.jsx`, but that file does not exist.
  - `docs/ux/UI-DESIGN.md` references `TasksPage.jsx`; the current file is `TaskPage.jsx`.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Treat wrappers as the migration seam | Lets us improve semantics and maintainability without rewriting every consumer first |
| Use theme-level overrides in `frontend/web/src/theme.js` for shared styling | Keeps MUI-backed primitives visually aligned with the existing system |
| Use commit-level rollback instead of an always-on runtime flag | Lower complexity and enough safety for a family-by-family migration |
| Create `BottomSheet.jsx` only if it materially reduces duplication between current sheet patterns | Avoid adding another abstraction if `SheetDialog` + `ActionPanel` remain clearer |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Planning files belonged to a previous completed task | Rewrote planning artifacts for the current task |

## Resources
- `docs/ux/UI-DESIGN.md`
- `docs/ux/component-matrix.html`
- `frontend/web/src/theme.js`
- `frontend/web/src/pages/admin/ComponentShowcasePage.jsx`
- `frontend/web/src/components/AppButton.jsx`
- `frontend/web/src/components/BarButton.jsx`
- `frontend/web/src/components/ListCard.jsx`
- `frontend/web/src/components/NameAvatar.jsx`
- `frontend/web/src/components/RecordTypeAvatar.jsx`
- `frontend/web/src/components/StatusBadge.jsx`
- `frontend/web/src/components/SuggestionChips.jsx`
- `frontend/web/src/components/FilterBar.jsx`
- `frontend/web/src/components/ConfirmDialog.jsx`
- `frontend/web/src/components/SheetDialog.jsx`
- `frontend/web/src/components/ActionPanel.jsx`
- Official MUI docs for Button, List, Avatar, Chip, Dialog, Drawer, Tabs, Card, Accordion, and the all-components index

## Visual/Browser Findings
- `/debug/components` is the canonical reusable-component review surface.
- `main.jsx` applies `appTheme`, so theme overrides will flow through the primary mobile app surface without extra providers.

---
*Update this file after every major discovery or scope decision.*
