# Single-tab IA — collapse 我的AI / 患者 / 审核 to one home

**Date:** 2026-04-26
**Author:** Jim (with Claude)
**Status:** Approved design, awaiting implementation plan

## Why

The doctor app currently has a 3-tab bottom navigation (我的AI / 患者 / 审核).
Two of those tabs are already reachable from `MyAIPage` as cards/links:

- 今日关注 rows → `/doctor/review?tab=...`
- 最近使用 "查看更多" → `/doctor/patients`

The TabBar is therefore a duplicate entry point with chrome cost (vertical
space, visual weight) but no exclusive content. The user's working hypothesis
for doctor behavior is **"glance and triage"** — open app, scan today's flags,
act on 1–2, close — which fits a single-surface home better than tab-switching.

Per the durable design rule **"simple by default — added chrome must earn its
keep"** ([memory](../../../../.claude/projects/-Volumes-ORICO-Code-doctor-ai-agent/memory/feedback_simple_by_default.md)),
the TabBar fails the bar: it adds a layer without adding capability the home
doesn't already provide.

## Goal

Collapse to one tab — `/doctor/my-ai` — and remove the bottom TabBar entirely.
Other routes (`/doctor/patients`, `/doctor/review`, `/doctor/settings/*`)
remain as push-navigated subpages reachable from cards/tiles on home.

## Non-goals

- **Restructuring home content.** `MyAIPage` keeps its current shape: identity
  card, hero AI summary banner, 3-tile quick-action card, 今日关注, 最近使用.
- **New instrumentation.** Ship blind. Iterate on user reports.
- **Search-first promotion.** No header search added to home.
- **Migrating `/doctor/patients` or `/doctor/review` page contents.** Only
  their entry points change; the pages themselves are untouched.
- **Feature-flagging or phased rollout.** Single PR, hard cut, revertible if
  it doesn't feel right.

## Decisions captured during brainstorm

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | What drives single-tab? | Simple-by-default heuristic; user's general design philosophy | Saved as durable feedback memory |
| 2 | Dominant doctor flow? | "Glance and triage" hypothesis (B); behavior not measured (E) | Optimize home for triage-at-a-glance |
| 3 | Strip home content? | Keep current content (A) | Smallest change; existing structure already fits |
| 3a | 最近使用 keep / cut? | Keep as-is | Knowledge re-find earns its keep; patient re-find is mild value but no real cost |
| 4 | Patient list entry point? | Persistent home entry (B), not just bottom-link or search-only | New doctors with empty 最近使用 still see it |
| 5 | Where does 全部患者 sit? | Replace one of the 3 quick-action tiles | No new card; uses existing pattern |
| 6 | Which tile gets replaced? | 新建病历 → 全部患者 | New-record creation moves into PatientsPage's "+" |
| 7 | Migration & instrumentation? | Hard cut (A) + ship blind (N) | Low reversal cost; trust the call |

## Architecture

### Routes (unchanged)

```
/doctor/my-ai                    home (only "tab")
/doctor/patients                 push subpage
/doctor/patients/new             intake overlay
/doctor/patients/:id             detail subpage
/doctor/review                   push subpage
/doctor/review/:id               review detail
/doctor/settings/*               settings subpages
```

All routes continue to render through the same `DoctorPage` shell. What
changes: no TabBar visible at the bottom; navigation between sections is
push-only (via cards/tiles/links from home).

### Navigation flow

```
home (/doctor/my-ai)
  ├─ tap 今日关注 row → /doctor/review?tab=...   (push)
  ├─ tap 全部事项 link → /doctor/review?tab=pending (push)
  ├─ tap 全部患者 tile → /doctor/patients         (push)
  ├─ tap 预问诊码 tile → /doctor/settings/qr      (push)
  ├─ tap 知识库 tile  → /doctor/settings/knowledge (push)
  ├─ tap 最近使用 row → /doctor/patients/:id OR /doctor/settings/knowledge/:id
  ├─ tap 设置 gear     → /doctor/settings        (push)
  └─ NavBar popovers (添加到桌面, 反馈)            (overlay, not navigation)
```

Push-notification deep links continue to land on specific routes and back
unwinds through the natural URL hierarchy back to `/doctor/my-ai`.

### Back-stack behavior

| From | Back button → |
|------|---------------|
| `/doctor/patients/:id` | `/doctor/patients` |
| `/doctor/patients` | `/doctor/my-ai` |
| `/doctor/review/:id` | `/doctor/review` |
| `/doctor/review` | `/doctor/my-ai` |
| `/doctor/settings/*` | `/doctor/settings` (or home, depending on entry) |

`useBackWithAnimation` / `useNavigationType` handle direction-based slide
animation already; no tab-specific logic exists in that path, so back-stack
unwinding is unchanged by tab removal.

## Component changes

### `MyAIPage.jsx`

**Single edit: the `quickActions` array** (currently lines 531–547).

Before:

```js
const quickActions = [
  { label: "新建病历", icon: <EditNoteOutlinedIcon />,        onClick: () => navigate(`${dp("patients")}?action=new`) },
  { label: "预问诊码", icon: <QrCodeScannerOutlinedIcon />,   onClick: () => navigate(dp("settings/qr")) },
  { label: "知识库",   icon: <MenuBookOutlinedIcon />,        onClick: () => navigate(dp("settings/knowledge")) },
];
```

After:

```js
const quickActions = [
  { label: "全部患者", icon: <PeopleAltOutlinedIcon />,       onClick: () => navigate(dp("patients")) },
  { label: "预问诊码", icon: <QrCodeScannerOutlinedIcon />,   onClick: () => navigate(dp("settings/qr")) },
  { label: "知识库",   icon: <MenuBookOutlinedIcon />,        onClick: () => navigate(dp("settings/knowledge")) },
];
```

**Import changes:** drop `EditNoteOutlinedIcon`, add
`PeopleAltOutlinedIcon` (already imported from MUI in `DoctorPage.jsx` —
new import added to `MyAIPage.jsx`).

No other changes to `MyAIPage`. Hero banner, 今日关注, 最近使用, identity
card, NavBar (gear icon, popovers) all untouched.

### `DoctorPage.jsx`

**Removals:**
1. `<TabBar>` JSX block at the bottom of the shell render.
2. `TABS` array (line ~48) — three entries, no longer consumed.
3. `badges` state (`useState({ review: 0, patients: 0 })`) — no consumer.
4. Icon imports in `DoctorPage.jsx` that were only consumed by the `TABS`
   array: `PeopleAltIcon`, `PeopleAltOutlinedIcon`, `MailIcon`,
   `MailOutlinedIcon`, `AutoAwesomeIcon`, `AutoAwesomeOutlinedIcon`.
   For each, grep `DoctorPage.jsx` to confirm zero remaining usages in
   *that file* before deleting the import — usage in other files
   (e.g. `MyAIPage.jsx` imports `AutoAwesomeIcon` for its hero banner) is
   independent and unaffected.

   *Note: `PeopleAltOutlinedIcon` becomes a NEW import in `MyAIPage.jsx`
   for the 全部患者 tile. The two import declarations are independent.*
5. Any safe-area / padding compensation tied to the TabBar height.

**Kept:**
- `detectSection()` — still used to switch which subpage component to render
  for a given pathname. Return values unchanged.
- All route handling, nested route rendering, intake-overlay logic.
- `FeedbackPopover`, `AddToDesktopPopover`, NavBar.

### Other files

- **No changes** to `PatientsPage.jsx`, `ReviewPage.jsx`, settings subpages,
  routing config, or `usePageStack`.
- **Each subpage's NavBar must already render its own title** (它们已经在做
  this via `SubpageHeader`). Confirm during implementation; if any was
  relying on `DoctorPage`'s shell to set the title, it must be updated to
  set its own.

## Testing

### Existing test impact

- **Vitest frontend (3 baseline tests)** — none target the TabBar, no edits
  expected.
- **Playwright E2E** — selectors should be checked. Most use route +
  `getByText`, which won't break. Any test that explicitly clicks a TabBar
  item (e.g., `page.getByRole('tab', { name: '审核' })`) needs to be
  rewritten to navigate via the home card or directly via URL.

### New tests

Add one Vitest contract test under `frontend/web/src/v2/__tests__/`:

```js
// DoctorPage.singleTab.test.jsx
test("renders no TabBar — single-tab IA", () => {
  // Mount DoctorPage with a memory router at /doctor/my-ai
  // Assert: no element with role="tablist" or class "adm-tab-bar" in the DOM
});

test("each historical tab route still mounts its subpage", () => {
  // Mount at /doctor/patients → assert PatientsPage rendered
  // Mount at /doctor/review → assert ReviewPage rendered
  // Mount at /doctor/my-ai → assert MyAIPage rendered
});
```

These two tests give us a regression net for both directions: the tab is
truly gone, and the routes still work.

### Manual verification checklist

After the PR:

- [ ] `/doctor/my-ai` renders without TabBar at bottom
- [ ] First quick-action tile reads "全部患者" with people icon, taps → `/doctor/patients`
- [ ] Second tile "预问诊码" → `/doctor/settings/qr`
- [ ] Third tile "知识库" → `/doctor/settings/knowledge`
- [ ] 今日关注 row taps still navigate to review/knowledge/patients as before
- [ ] 最近使用 row taps still open patient detail / knowledge detail
- [ ] Back from any subpage returns to `/doctor/my-ai` cleanly with slide animation
- [ ] Deep-link to `/doctor/review/:id` directly opens that page; back unwinds to `/doctor/review` then `/doctor/my-ai`
- [ ] WeChat ← arrow / hardware back behaves identically to before
- [ ] Run `scripts/lint-ui.sh` — passes
- [ ] No console warnings about removed icon imports

## Risks

| Risk | Mitigation |
|------|------------|
| Doctors miss the at-a-glance 审核 badge on the TabBar | 今日关注 already shows the same count on home — same data, different surface |
| New-record creation now requires 2 taps instead of 1 (home → 全部患者 → "+") | Accepted per Q6 decision; revisit if user reports it as friction |
| Some subpage was relying on `DoctorPage`'s NavBar title and breaks | Verify each subpage NavBar during manual checklist; cheap to fix if found |
| E2E selectors targeting TabBar break CI | Pre-fix during implementation by grepping `.adm-tab-bar` / role="tab" in tests |
| Reversibility | Hard cut, but each removal (TabBar, TABS array, badges state, tile swap) is one chunk — single revert returns to today's state |

## Rollback

If the simplification feels wrong after a few days of dogfooding: revert the
single PR. No DB changes, no API changes, no migration. Routes stayed the
same, so URLs from notifications / WeChat redirects keep working in either
state.

## Open questions for the implementation plan

- Whether to add the 2 Vitest tests in the same PR or a follow-up
- Whether to also kill the `subpageKey` PageSkeleton plumbing for the
  former tab routes (probably no — they're now subpages, the same
  AnimatePresence handling works)
- Whether the `dp()` (doctor-base-path) helper needs any update — likely no
