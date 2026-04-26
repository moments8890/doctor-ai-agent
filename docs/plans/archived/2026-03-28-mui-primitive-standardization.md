# MUI Primitive Standardization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace thin shared UI wrappers with public MUI components where that buys semantics, accessibility, and maintainability, while preserving the current WeChat-like visual language and keeping domain-heavy workflow components custom.

**Architecture:** Keep the app-level wrapper API stable and change implementation behind the wrappers. Centralize shared visual rules in `frontend/web/src/theme.js`, migrate one primitive family per commit, verify against `/debug/components` plus real pages, and use commit-level rollback if a family looks worse after migration.

**Tech Stack:** React 19, MUI v7 public components, existing `theme.js` tokens, Vite, Vitest, React Testing Library

---

## Scope

### In Scope
- Button primitives
- List-row primitives
- Avatar primitives
- Chip / badge primitives
- Tab-like filter primitives
- Dialog / sheet primitives where MUI already provides the right public surface
- Showcase coverage and lightweight primitive smoke tests
- UX docs sync for the new primitive policy and file inventory

### Out of Scope
- Rewriting workflow-heavy components to raw MUI layouts
- Visual redesign of the product
- Permanent feature flags for primitive selection
- Migrating unrelated pages just because they import one of the wrappers

## Guardrails

1. Keep wrapper exports stable.
   `AppButton`, `BarButton`, `ListCard`, `NameAvatar`, `StatusBadge`, `SuggestionChips`, `FilterBar`, `ConfirmDialog`, and `SheetDialog` keep their public names and near-identical props during phase 1.

2. Use public MUI APIs only.
   Rely on component props, slots, `sx`, and theme `components` overrides. Do not depend on internal `.Mui*` DOM structure or private classes beyond stable public theme override keys.

3. Land one family per commit.
   Buttons, lists/avatars, chips/tabs, and sheets/dialogs should each be their own commit so visual rollback is surgical.

4. Validate wrappers in two places.
   Every family must pass both:
   - `/debug/components`
   - at least one production page that uses the wrapper heavily

5. Do not flatten domain UI.
   `DiagnosisCard`, `FieldReviewCard`, `MessageTimeline`, `RecordCard`, `PageSkeleton`, and `SubpageHeader` remain custom unless a later plan explicitly revisits them.

## Rollback Strategy

### Primary rollback unit
- One primitive family per commit.
- If a family regresses visually, revert only that commit:

```bash
git revert <family_commit_sha>
```

### Why no permanent runtime flag
- The wrapper layer is already the abstraction seam.
- A runtime `legacy vs MUI` toggle would add code paths, extra QA burden, and long-tail cleanup.
- Commit-level rollback is enough if the work stays batched by family.

### Extra safety steps before each batch
- Capture baseline screenshots from:
  - `/debug/components`
  - `/debug/doctor-pages`
  - one or two real routes that stress the wrapper family
- Do not start the next family until the current family has manual sign-off.

### Escape hatch if one family remains visually unstable
- Only if commit-level rollback proves too coarse for a specific family, add a short-lived wrapper-local toggle and delete it before merging the batch.
- Do not add a global permanent primitive mode.

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/web/src/theme.js` | Modify | Add theme-level style overrides for MUI-backed primitives without changing design tokens |
| `frontend/web/src/components/AppButton.jsx` | Modify | Render MUI `Button` instead of clickable `Box` |
| `frontend/web/src/components/BarButton.jsx` | Modify | Render text-style MUI `Button` with app header styling |
| `frontend/web/src/components/ConfirmDialog.jsx` | Modify | Standardize on `DialogTitle`, `DialogContent`, `DialogActions`, and MUI-backed buttons |
| `frontend/web/src/components/ListCard.jsx` | Modify | Replace hand-built row shell with MUI list primitives |
| `frontend/web/src/components/NewItemCard.jsx` | Modify | Adapt to updated `ListCard` structure |
| `frontend/web/src/components/KnowledgeCard.jsx` | Modify | Adapt to updated list-row primitive semantics |
| `frontend/web/src/components/PatientPickerDialog.jsx` | Modify | Reuse updated list-row and dialog primitives |
| `frontend/web/src/components/NameAvatar.jsx` | Modify | Render MUI `Avatar` with existing name-color logic |
| `frontend/web/src/components/RecordTypeAvatar.jsx` | Modify | Render MUI `Avatar` with icon-centered variants |
| `frontend/web/src/components/StatusBadge.jsx` | Modify | Render MUI `Chip` in status-pill form |
| `frontend/web/src/components/SuggestionChips.jsx` | Modify | Render MUI `Chip` group for quick replies |
| `frontend/web/src/components/FilterBar.jsx` | Modify | Render MUI `Tabs` and `Tab` instead of clickable boxes |
| `frontend/web/src/components/ActionPanel.jsx` | Modify | Move bottom-sheet behavior onto MUI drawer primitive |
| `frontend/web/src/components/SheetDialog.jsx` | Modify | Clarify dialog-vs-sheet usage and keep a single shell for mobile-docked dialogs |
| `frontend/web/src/components/BottomSheet.jsx` | Create only if needed | Thin shared bottom-sheet wrapper over `Drawer` / `SwipeableDrawer` |
| `frontend/web/src/pages/admin/ComponentShowcasePage.jsx` | Modify | Ensure all primitive states are visible for before/after QA |
| `frontend/web/src/components/primitives.test.jsx` | Create | Lightweight semantic smoke tests for wrapper families |
| `docs/ux/UI-DESIGN.md` | Modify | Align docs to actual primitives and file names |
| `docs/ux/component-matrix.html` | Modify only if component inventory changes materially | Keep matrix aligned with actual reusable primitives |

## Task 1: Lock Baseline and Verification Harness

**Files:**
- Modify: `frontend/web/src/pages/admin/ComponentShowcasePage.jsx`
- Create: `frontend/web/src/components/primitives.test.jsx`

- [ ] **Step 1: Expand showcase coverage for primitive states**

Add or verify showcase examples for:
- `AppButton`: primary, secondary, danger, loading, disabled
- `BarButton`: normal, disabled, loading
- `ListCard`: avatar, subtitle, right content, chevron
- `NameAvatar` and `RecordTypeAvatar`
- `StatusBadge` and `SuggestionChips`
- `FilterBar`
- `ConfirmDialog`, `SheetDialog`, and `ActionPanel`

- [ ] **Step 2: Add primitive smoke tests**

Create `frontend/web/src/components/primitives.test.jsx` with React Testing Library checks for:
- `AppButton` renders a semantic `button`
- disabled and loading states block clicks
- `ListCard` exposes a button-like interactive root when clickable
- `NameAvatar` and `StatusBadge` render accessible text labels
- `FilterBar` exposes tab semantics after migration

Use this import pattern:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
```

- [ ] **Step 3: Record baseline verification commands**

Run:

```bash
cd frontend/web
npm run test -- src/components/primitives.test.jsx
npm run build
```

Expected:
- Tests pass
- Vite production build succeeds

- [ ] **Step 4: Capture baseline visuals**

Before touching wrapper internals, review:
- `/debug/components`
- `/debug/doctor-pages`
- doctor patient detail page
- any page that uses `FilterBar` and `SuggestionChips`

Store screenshots or notes outside the code diff if needed, but complete this step before Task 2.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/admin/ComponentShowcasePage.jsx frontend/web/src/components/primitives.test.jsx
git commit -m "test(ui): add primitive showcase coverage and smoke tests"
```

## Task 2: Theme Foundation for MUI-Backed Primitives

**Files:**
- Modify: `frontend/web/src/theme.js`

- [ ] **Step 1: Keep tokens unchanged**

Do not change `TYPE`, `ICON`, `BUTTON`, or `COLOR` values in this task. The goal is implementation standardization, not a visual redesign.

- [ ] **Step 2: Add component-level overrides for migrated families**

Extend `components` overrides in `frontend/web/src/theme.js` for:
- `MuiButton`
- `MuiIconButton` if needed for header actions
- `MuiListItemButton`
- `MuiChip`
- `MuiAvatar`
- `MuiTabs`
- `MuiTab`
- `MuiDialogActions` if needed

Use the existing token system, for example:

```js
MuiChip: {
  styleOverrides: {
    root: {
      borderRadius: 16,
      fontSize: TYPE.micro.fontSize,
      fontWeight: 600,
    },
  },
},
```

- [ ] **Step 3: Verify no behavior regressions before wrapper migration**

Run:

```bash
cd frontend/web
npm run build
```

Expected:
- Build succeeds
- Existing wrappers still render the same because call sites are unchanged

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/theme.js
git commit -m "refactor(ui): add MUI primitive theme foundation"
```

## Task 3: Migrate Button Primitives

**Files:**
- Modify: `frontend/web/src/components/AppButton.jsx`
- Modify: `frontend/web/src/components/BarButton.jsx`
- Modify: `frontend/web/src/components/ConfirmDialog.jsx`

- [ ] **Step 1: Rebuild `AppButton` on top of MUI `Button`**

Map current wrapper variants to MUI variants and colors:
- `primary` -> `contained`
- `secondary` -> `outlined` or low-emphasis contained style using theme overrides
- `danger` -> `contained` with error color

Preserve current props:
- `variant`
- `size`
- `loading`
- `loadingLabel`
- `disabled`
- `fullWidth`
- `onClick`
- `sx`

- [ ] **Step 2: Rebuild `BarButton` on top of MUI `Button`**

Use `variant="text"` and keep the existing green action styling from tokens rather than hardcoded DOM behavior.

- [ ] **Step 3: Update `ConfirmDialog` to use MUI dialog subcomponents cleanly**

Use:
- `DialogTitle`
- `DialogContent`
- `DialogActions`
- migrated `AppButton`

Keep the existing button order rule:
- destructive left, constructive right

- [ ] **Step 4: Verify buttons on real surfaces**

Review:
- `/debug/components`
- pages that use `AppButton`
- top bars that use `BarButton`
- dialogs that use `ConfirmDialog`

Run:

```bash
cd frontend/web
npm run test -- src/components/primitives.test.jsx
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/components/AppButton.jsx frontend/web/src/components/BarButton.jsx frontend/web/src/components/ConfirmDialog.jsx
git commit -m "refactor(ui): migrate button primitives to public MUI buttons"
```

## Task 4: Migrate List and Avatar Primitives

**Files:**
- Modify: `frontend/web/src/components/ListCard.jsx`
- Modify: `frontend/web/src/components/NewItemCard.jsx`
- Modify: `frontend/web/src/components/KnowledgeCard.jsx`
- Modify: `frontend/web/src/components/PatientPickerDialog.jsx`
- Modify: `frontend/web/src/components/NameAvatar.jsx`
- Modify: `frontend/web/src/components/RecordTypeAvatar.jsx`

- [ ] **Step 1: Rebuild `ListCard` using MUI list primitives**

Use:
- `ListItem`
- `ListItemButton` when `onClick` exists
- `ListItemAvatar`
- `ListItemText`

Preserve current visual rules:
- 48-56px row height
- white background
- hairline separators
- full-width tap target

- [ ] **Step 2: Rebuild avatars on top of MUI `Avatar`**

`NameAvatar` keeps deterministic color logic.

`RecordTypeAvatar` keeps the current type-to-icon map but renders inside a rounded `Avatar`.

- [ ] **Step 3: Adapt list consumers to the new structure**

Check and adjust:
- `NewItemCard.jsx`
- `KnowledgeCard.jsx`
- `PatientPickerDialog.jsx`

The goal is to preserve the same rendered shape with better semantics underneath.

- [ ] **Step 4: Verify on high-usage pages**

Review:
- `/debug/components`
- patient picker dialog
- settings and knowledge pages
- any patient list or knowledge list screen that uses `ListCard`

Run:

```bash
cd frontend/web
npm run test -- src/components/primitives.test.jsx
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/components/ListCard.jsx frontend/web/src/components/NewItemCard.jsx frontend/web/src/components/KnowledgeCard.jsx frontend/web/src/components/PatientPickerDialog.jsx frontend/web/src/components/NameAvatar.jsx frontend/web/src/components/RecordTypeAvatar.jsx
git commit -m "refactor(ui): migrate list and avatar primitives to public MUI components"
```

## Task 5: Migrate Chip, Badge, and Tab Primitives

**Files:**
- Modify: `frontend/web/src/components/StatusBadge.jsx`
- Modify: `frontend/web/src/components/SuggestionChips.jsx`
- Modify: `frontend/web/src/components/FilterBar.jsx`

- [ ] **Step 1: Rebuild `StatusBadge` using `Chip`**

Keep the current pill look by styling `Chip` through tokens:
- small height
- outlined treatment for quiet states
- color meaning driven by the existing `colorMap`

- [ ] **Step 2: Rebuild `SuggestionChips` using clickable/deletable `Chip`**

Use MUI `Chip` click and delete affordances for:
- selected vs unselected state
- dismiss button
- disabled behavior

- [ ] **Step 3: Rebuild `FilterBar` using `Tabs` and `Tab`**

Current behavior is single-select view switching, so it should expose tab semantics.

Preserve current styling:
- thin underline
- compact font
- green active state
- counts appended to labels

- [ ] **Step 4: Verify on pages that stress these controls**

Review:
- `/debug/components`
- patient detail record tabs
- intake or chat pages using `SuggestionChips`
- any page showing status pills

Run:

```bash
cd frontend/web
npm run test -- src/components/primitives.test.jsx
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/components/StatusBadge.jsx frontend/web/src/components/SuggestionChips.jsx frontend/web/src/components/FilterBar.jsx
git commit -m "refactor(ui): migrate chip and tab primitives to public MUI components"
```

## Task 6: Standardize Dialog and Bottom-Sheet Primitives

**Files:**
- Modify: `frontend/web/src/components/SheetDialog.jsx`
- Modify: `frontend/web/src/components/ActionPanel.jsx`
- Modify: `frontend/web/src/components/PatientPickerDialog.jsx`
- Create if needed: `frontend/web/src/components/BottomSheet.jsx`

- [ ] **Step 1: Decide whether `BottomSheet.jsx` earns its keep**

Choose one path:
- If `ActionPanel` and any future mobile sheets would share the same docked behavior, create `BottomSheet.jsx` as a thin wrapper over `Drawer` / `SwipeableDrawer`.
- If not, keep `ActionPanel` directly on `Drawer` and remove the nonexistent `BottomSheet` reference from docs later.

- [ ] **Step 2: Move `ActionPanel` onto MUI drawer primitives**

Use:
- `Drawer` for simplicity, or
- `SwipeableDrawer` if swipe interaction materially improves the mobile feel without harming performance

Preserve:
- bottom anchoring
- backdrop close
- safe mobile spacing
- current action grid

- [ ] **Step 3: Keep `SheetDialog` as the docked-dialog shell**

`SheetDialog` already solves "dialog that docks to the bottom on small screens". Clean up the implementation so it uses MUI dialog subcomponents consistently and does not duplicate behavior that belongs in the bottom-sheet wrapper.

- [ ] **Step 4: Verify all dialog/sheet flows**

Review:
- `/debug/components`
- patient picker dialog
- import/export dialogs
- action panel open/close on a narrow viewport

Run:

```bash
cd frontend/web
npm run test -- src/components/primitives.test.jsx
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/components/SheetDialog.jsx frontend/web/src/components/ActionPanel.jsx frontend/web/src/components/PatientPickerDialog.jsx frontend/web/src/components/BottomSheet.jsx
git commit -m "refactor(ui): standardize dialog and bottom-sheet primitives on MUI public components"
```

If `BottomSheet.jsx` is not created, omit it from `git add`.

## Task 7: Sync UX Docs and Inventory

**Files:**
- Modify: `docs/ux/UI-DESIGN.md`
- Modify if needed: `docs/ux/component-matrix.html`

- [ ] **Step 1: Add the primitive policy to `UI-DESIGN.md`**

Document:
- public MUI components are the default backing layer for shared primitives
- wrappers preserve the product’s visual language and public app API
- domain workflow components remain custom

- [ ] **Step 2: Fix file-name drift**

Correct:
- `TasksPage.jsx` -> `TaskPage.jsx`
- `BottomSheet.jsx` reference only if the file truly exists after Task 6

- [ ] **Step 3: Update component inventory if Task 6 changes it**

If `BottomSheet.jsx` becomes real, document it accurately.

If it does not, remove the stale mention instead of leaving a fake inventory entry.

- [ ] **Step 4: Verify docs against code**

Run:

```bash
rg -n "BottomSheet|TasksPage" docs/ux/UI-DESIGN.md docs/ux/component-matrix.html frontend/web/src
```

Expected:
- no stale references remain

- [ ] **Step 5: Commit**

```bash
git add docs/ux/UI-DESIGN.md docs/ux/component-matrix.html
git commit -m "docs(ui): sync component inventory with MUI primitive refactor"
```

## Manual QA Checklist

- [ ] `/debug/components` matches baseline or is an intentional improvement
- [ ] `/debug/doctor-pages` has no spacing, density, or alignment regressions
- [ ] Header actions still feel lightweight and not over-materialized
- [ ] List rows still read as WeChat-like rows, not generic desktop lists
- [ ] Chips and filter tabs still fit the existing compact Chinese UI density
- [ ] Dialogs and bottom sheets still feel mobile-first
- [ ] No workflow-heavy doctor component was accidentally restyled into a stock MUI look

## Merge Strategy

1. Create a safety branch before Task 1 implementation:

```bash
git checkout -b refactor/mui-primitives
```

2. Implement one task at a time.
3. Do not squash all families into one commit.
4. If a family looks worse, revert that family commit immediately and rework before proceeding.

## Success Criteria

- Primitive wrappers use public MUI components underneath.
- Wrapper APIs remain stable enough that most call sites do not change.
- Build and primitive smoke tests pass.
- `/debug/components` and key real pages preserve the current design language.
- Docs correctly describe the actual primitive inventory.

Plan complete and saved to `docs/plans/2026-03-28-mui-primitive-standardization.md`.

Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - execute tasks in this session in order, with checkpoints after each primitive family
