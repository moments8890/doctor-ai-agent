# Informational popups → centered dialog

**Date:** 2026-04-23
**Status:** Approved (ready for plan)
**Scope:** v2 (antd-mobile) doctor app only

## Problem

Two v2 popups that show read-only informational content currently render as
bottom sheets. They have working backdrop-tap dismiss (`onMaskClick`) but no
visible close affordance, which leaves users feeling the popup is not closable:

1. `SummaryDetailSheet` in `v2/pages/doctor/MyAIPage.jsx` — tap the green hero
   banner → full 今日摘要 narrative.
2. `CitationPopup` in `v2/components/CitationPopup.jsx` — tap a `[KB-N]` badge
   in a reply draft or diagnose view → single knowledge-rule preview.

Both are informational peeks (read, close, return to task). A centered modal
is the more honest fit for that interaction: lighter weight, "this is just
reference, not a decision surface," and dismissal options are visually obvious.

## Non-goals

- **Not** converting genuine action surfaces (font-size picker, patient
  picker, `FeedbackSheet`, `InterviewCompletePopup`). Bottom sheet is the
  correct pattern for those.
- **Not** touching `ActionSheet.show` context menus — native iOS-style
  ActionSheet is the correct primitive for row overflow menus.
- **Not** touching `Dialog.confirm` / `Dialog.alert` — already centered.
- **Not** touching the v1 (MUI) app's `SheetDialog` or the 22 files using it.
- **Not** introducing a shared `InfoDialog` wrapper component — only two call
  sites benefit, inline is the right choice (YAGNI).
- **Not** adding ESC-to-dismiss — mobile-first app, low value, `CenterPopup`
  does not support it natively.

## Design

### Primitive

Swap antd-mobile `Popup` (bottom-anchored) → antd-mobile **`CenterPopup`** in
both components. `CenterPopup` has the same `visible` / `onMaskClick` /
`onClose` / `bodyStyle` / `destroyOnClose` API as `Popup`; it just renders
centered with a tinted backdrop instead of anchoring to the bottom.

No new dependency, no new wrapper component.

### Dismiss affordances

Both converted popups gain:

1. **Backdrop tap** → close (already works via `onMaskClick`, no change).
2. **× close button** in the header — top-right of the card, 20×20 tappable
   area, `CloseOutline` from `antd-mobile-icons` at `ICON.sm`, color
   `APP.text4`. On tap: calls `onClose`.

### Shape / styling

Shared across both:

- `bodyStyle.borderRadius`: `RADIUS.lg` (12px) — all four corners, not just
  the top two. Matches the centered treatment.
- `bodyStyle.width`: `min(420px, 88vw)` — constrained so it doesn't span the
  full viewport on a desktop frame or tablet.
- `bodyStyle.maxHeight`: `70vh` (was 60vh bottom-sheet; centered we have more
  vertical budget because the sheet isn't pinned to the bottom safe-area).
- `bodyStyle.padding`: `18px 20px 20px` (unchanged).
- Header row: title (left, `FONT.md`, weight 600) + right cluster (existing
  meta — category pill or generation time — followed by × button). Both
  vertically centered.

### Per-popup changes

**`CitationPopup`** (`v2/components/CitationPopup.jsx`):

- Replace `<Popup position="bottom">` with `<CenterPopup>`.
- Header row already contains title + `CategoryPill`. Append `<CloseOutline>`
  to the right of the pill.
- "打开完整详情 ›" footer link unchanged.
- Props / callers unchanged.

**`SummaryDetailSheet`** (`v2/pages/doctor/MyAIPage.jsx`, lines 227-264):

- Replace `<Popup>` with `<CenterPopup>`.
- Header row already contains "今日摘要" title + optional "生成于 HH:MM" meta.
  Append `<CloseOutline>` to the right of the meta (or where the meta would
  be if absent).
- Body content unchanged.
- Props / callers unchanged.

### Call-site impact

**Zero.** Both components keep the same `{ visible, onClose, … }` props. Call
sites in `ReviewPage.jsx`, `PatientChatPage.jsx`, `MyAIPage.jsx` do not change.

## Files touched

1. `frontend/web/src/v2/components/CitationPopup.jsx`
2. `frontend/web/src/v2/pages/doctor/MyAIPage.jsx`

## Testing

Manual QA only. No new automated tests — existing Playwright suite has no
assertions that key on `.adm-popup` bottom positioning for these two popups;
any that do key on `.adm-popup` broadly will still pass (CenterPopup uses the
same base class).

Manual verification:

- **Citation (reply flow):** Open a review item in `ReviewPage`, tap a
  `[KB-N]` badge → centered modal appears → tap × closes → reopen → tap
  backdrop closes.
- **Citation (diagnose / chat flow):** Same in `PatientChatPage`.
- **Summary:** On doctor home, tap the green hero banner → centered modal
  with full 今日摘要 → tap × closes → reopen → tap backdrop closes.
- **Regression:** Confirm `FeedbackSheet`, patient-picker, font-size picker,
  and `InterviewCompletePopup` still render as bottom sheets (unchanged).

## Risks

- **antd-mobile `CenterPopup` z-index stacking:** if a citation is opened
  on top of an existing centered modal, stacking behavior may differ from
  bottom-sheet on top of centered-modal. Verify manually in the review flow
  where a confirm `Dialog` could plausibly sit behind a `CenterPopup`.
  antd-mobile components expose z-index via a CSS custom property
  (`--z-index`) that can be overridden on `bodyStyle` if a fix is needed.
- **Tall content on small viewports:** `maxHeight: 70vh` + centered layout
  means very long summaries scroll internally. Acceptable — matches behavior
  of the current bottom sheet which also scrolls internally.
