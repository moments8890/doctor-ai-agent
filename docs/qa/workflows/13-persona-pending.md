# Workflow 13 — Persona pending review (AI discoveries)

Ship gate for the **AI发现** queue where AI-discovered style rules surface
for doctor confirmation. Each item shows a proposed rule, the field it
targets, an evidence summary, and a confidence level. The doctor can
accept (确认) or reject (忽略) each item. Decisions here feed directly
into the persona rule set that shapes every LLM prompt.

This workflow targets `PendingReviewSubpage.jsx`, reachable from the
persona settings tree at `/doctor/settings/persona/pending`.

**Area:** `src/pages/doctor/subpages/PendingReviewSubpage.jsx`, pending
API (`GET /api/manage/persona/pending?doctor_id=`,
`POST /api/manage/persona/pending/{id}/accept?doctor_id=`,
`POST /api/manage/persona/pending/{id}/reject?doctor_id=` — see
`frontend/web/src/api.js:669-688`), `usePersonaPending()` hook,
`QK.personaPending(doctorId)` cache key
**Spec:** `frontend/web/tests/e2e/13-persona-pending.spec.ts`
**Estimated runtime:** ~3 min manual / ~20 s automated

---

## Scope

**In scope**

- Render the pending items list with field label chip, confidence badge,
  proposed rule text, and evidence summary per item.
- Accept (确认) a pending item — item removed from queue, rule added to
  persona.
- Reject (忽略) a pending item — item removed from queue, no rule added.
- Empty state when no items are pending ("暂无待确认的发现").
- Loading skeleton while fetching.
- Button disable guard: while one item is acting (accept/reject in
  flight), all other items' buttons are disabled.
- Field label mapping: `reply_style` → 回复风格, `closing` → 常用结尾语,
  `structure` → 回复结构, `avoid` → 回避内容, `edits` → 常见修改.
- Confidence label mapping: `high` → 确信 (green), `medium` → 可能
  (warning), `low` → 猜测 (grey).

**Out of scope**

- How pending items are generated (backend AI pipeline) — not a UI
  workflow.
- Persona rules CRUD after acceptance — covered in
  [04-persona-rules.md](04-persona-rules.md).
- TeachByExampleSubpage, which also feeds items into this queue — covered
  in [15-persona-teach.md](15-persona-teach.md).

---

## Pre-flight

Shared pre-flight lives in [`README.md`](README.md#shared-pre-flight).
This workflow additionally needs:

- Pending items seeded via the backend API (the spec seeds directly via
  `POST /api/manage/persona/pending` or uses
  `seed.addPendingPersonaItem` if available).
- No special env state beyond a registered doctor.

---

## Steps

### 1. Empty state

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/settings/persona/pending` (or via 人设 → AI发现) | `PageSkeleton` header "AI发现"; back arrow top-left |
| 1.2 | With no pending items seeded | `EmptyState` shows "暂无待确认的发现" |

### 2. Items render correctly

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Seed 2 pending items (different fields, different confidence) and navigate to page | Both items render as cards |
| 2.2 | Check first item | Field label chip visible (e.g. "回复风格"); confidence label visible (e.g. "确信" in green for `high`); proposed rule text visible; evidence summary visible below rule |
| 2.3 | Check action buttons | Each card has two equal-width buttons: "忽略" (secondary/left) and "确认" (primary/right) |

### 3. Accept a pending item

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap "确认" on first item | Button shows loading state; all other buttons disabled |
| 3.2 | Wait for mutation to settle | Item disappears from the list |
| 3.3 | Navigate to `/doctor/settings/persona` | The accepted rule appears under the correct field section |

### 4. Reject a pending item

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Navigate back to pending page | Remaining item still visible |
| 4.2 | Tap "忽略" on the item | Button shows loading state |
| 4.3 | Wait for mutation to settle | Item disappears; empty state shown ("暂无待确认的发现") |
| 4.4 | Navigate to `/doctor/settings/persona` | No new rule from the rejected item |

### 5. Concurrent action guard

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Seed 3 pending items and navigate | All 3 cards visible |
| 5.2 | Tap "确认" on item 1 (intercept network to delay response) | Item 1 buttons show loading; items 2 and 3 buttons are `disabled` |
| 5.3 | Release the network intercept | Item 1 removed; items 2 and 3 buttons re-enabled |

---

## Edge cases

- **All items rejected** — empty state appears after the last rejection;
  no stale card remnants.
- **Network error on accept** — `onSettled` fires, `actingId` resets to
  null, buttons re-enable. Item stays in list (no optimistic removal).
- **Unknown field value from API** — the Chip renders the raw field key
  as fallback (no crash).
- **Unknown confidence value** — falls back to `medium` config ("可能"
  in warning color).
- **Page navigated away mid-mutation** — React Query handles cleanup;
  no orphan state.

---

## Known issues

No open bugs as of 2026-04-11. This page is new on the
`feat/persona-phase1` branch.

---

## Failure modes & debug tips

- **Items don't load** — verify `GET /api/manage/persona/pending?doctor_id=`
  returns `{ items: [...] }`. The hook reads `data.items`.
- **Accept succeeds but item stays** — query invalidation may not fire.
  Check that `useAcceptPendingItem` calls `invalidateQueries` for
  `QK.personaPending(doctorId)`.
- **All buttons permanently disabled** — `actingId` stuck non-null. This
  happens if `onSettled` doesn't fire. Check the mutation's
  `onSettled` callback.
- **Confidence colors wrong** — verify `CONFIDENCE_LABELS` map matches
  the API's `confidence` enum (`high`/`medium`/`low`).
