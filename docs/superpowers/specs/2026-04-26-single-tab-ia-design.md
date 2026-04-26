# Single-tab IA — collapse 我的AI / 患者 / 审核 to one home

**Date:** 2026-04-26
**Author:** Jim (with Claude)
**Status:** Approved design (post-codex review revision), awaiting implementation plan
**Revision:** v2 — expanded scope after codex review surfaced shell-routing,
back-stack, NavBar ownership, safe-area, and "+" affordance issues that the v1
spec hand-waved.

## Why

The doctor app currently has a 3-tab bottom navigation (我的AI / 患者 / 审核).
Two of those tabs are already reachable from `MyAIPage` as cards/links:

- 今日关注 rows → `/doctor/review?tab=pending`, `/doctor/settings/knowledge?tab=pending`, `/doctor/patients`
- 最近使用 "查看更多" → `/doctor/patients`

The TabBar duplicates entry points without adding capability. Per the durable
"simple by default" rule, it doesn't earn its keep. The user's working
hypothesis for doctor behavior is **"glance and triage"** — open app, scan
today's flags, act on 1–2, close — which fits a single-surface home better
than tab-switching.

## Goal

Collapse to one tab — `/doctor/my-ai` — and remove the bottom TabBar.
Restructure shell routing so `/doctor/patients` and the review-detail flow
behave as **true push subpages** (own NavBar, own back arrow, slide-over
animation) rather than section-swaps inside the shell. Delete
`ReviewQueuePage` (the queue-list page) entirely; review work happens by
drilling from the home triage row directly into the first pending item's
detail (`ReviewPage`), which auto-advances to the next pending item on
action or returns home when the queue is empty.

## Non-goals

- **Restructuring home content.** `MyAIPage` keeps its current shape:
  identity card, hero AI summary banner, 3-tile quick-action card,
  今日关注, 最近使用.
- **New instrumentation.** Ship blind.
- **Search-first promotion.** No header search added to home.
- **Migrating `/doctor/settings/*`.** Settings stay as today.
- **Touching the AI suggestion / rules review surface.** "待采纳的规则" row
  still routes to `/doctor/settings/knowledge?tab=pending`, unchanged.
- **Feature flag, rollout phasing, instrumentation.** Hard cut, single PR.
  (See "Risk acceptance" below — codex flagged this as risky for the radius;
  user accepted the risk.)

## Decisions captured during brainstorm + codex review

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | What drives single-tab? | Simple-by-default heuristic | Saved as durable feedback memory |
| 2 | Dominant doctor flow? | "Glance and triage" hypothesis (B); behavior not measured (E) | Optimize home for triage-at-a-glance |
| 3 | Strip home content? | Keep current content (A) | Smallest change to home |
| 3a | 最近使用 keep / cut? | Keep as-is | Knowledge re-find earns its keep |
| 4 | Patient list entry point? | Persistent home entry (B) | New doctors with empty 最近使用 still see it |
| 5 | Where does 全部患者 sit? | Replace one of the 3 quick-action tiles | No new card |
| 6 | Which tile gets replaced? | 新建病历 → 全部患者 | New-record creation moves into PatientsPage's "+" |
| 7 | Migration & instrumentation? | Hard cut (C1), ship blind (D-N) | Codex flagged risk, user accepted |
| 8 | `/patients` push-subpage migration? | Yes — true push subpage (A1) | Codex's review made the section-swap-vs-subpage distinction explicit |
| 9 | `/review` symmetric treatment? | A-2 — drop queue list, keep `/review/:id` with auto-advance | Triage-actor model: "stream of work" replaces "browse the queue" |
| 10 | "全部事项 ›" link in 今日关注 SectionHeader? | α — delete | Rows themselves are the drill-in; link is redundant |
| 11 | Cold-start deep-link fix? | B1 — synthetic history seed at app boot | Single point of change, uniform back-stack |
| 12 | Rollout (revisited after codex)? | C1 — still hard-cut, no flag | Risk acknowledged |
| 13 | Test coverage? | D — adopt codex's full list verbatim | See Testing section |

## Architecture changes

### Routes after the change

```
/doctor                       → redirects to /doctor/my-ai
/doctor/my-ai                 home (only base section)
/doctor/patients              push subpage (PatientsPage as overlay over home)
/doctor/patients/new          intake overlay (unchanged routing)
/doctor/patients/:id          push subpage (PatientDetail)
/doctor/review                DELETED — no route, no component
/doctor/review/:id            push subpage (ReviewPage detail; reached via
                              key.startsWith("review-") in usePageStack)
/doctor/settings/*            push subpages (unchanged)
```

### Section model: from "3 base sections" to "1 base section + push subpages"

Today, `DoctorPage` has a `baseSection` concept — `my-ai`, `patients`, or
`review` — and the shell renders one of three component trees while the
TabBar provides the entry point. NavBar title and right-action are derived
from `baseSection`.

After the change:
- `baseSection` always equals `my-ai`. The shell renders `MyAIPage` as the
  only base section.
- `/doctor/patients` and `/doctor/review/:id` reach the user via
  `usePageStack` overlay entries (the same mechanism that already handles
  `patient-{id}`, `review-{id}`, `settings-*` keys today).
- Shell NavBar simplifies: title is always `我的AI`, right action is the
  `my-ai` cluster (FeedbackPopover + AddToDesktopPopover).
- Each push subpage (`PatientsPage`, `PatientDetail`, `ReviewPage`,
  `SettingsPage` and friends) renders its **own** NavBar/SubpageHeader with
  back arrow and any page-specific right-actions. Most already do; the
  exceptions are `PatientsPage` (currently relies on shell NavBar for title
  + "+" affordance) and `ReviewQueuePage` (deleted).

### `PatientsPage` migration to true subpage

| Concern | Today | After |
|---------|-------|-------|
| NavBar title | Shell renders `患者` from TABS | PatientsPage renders own SubpageHeader with title `患者` and back arrow |
| `+` (new record) | Shell button when `baseSection === "patients"` (DoctorPage.jsx:464) | Moves into PatientsPage's SubpageHeader as a right-action button, navigates to `?action=new` (same destination) |
| Back behavior | Tap a TabBar item or use browser back | SubpageHeader back arrow → `useBackWithAnimation` → home |
| Local state (search text, NL results, section collapse) | Persists because PatientsPage stays mounted as a base section | **Resets on each push.** Acceptable per Q-A discussion: "glance and triage" doctors don't park inside the patient list; reopening from home is the expected flow |
| `?action=new` cleanup effect | Already exists | Unchanged |
| Pull-to-refresh | Existing | Unchanged |

### `/review/:id` auto-advance (replaces the deleted queue list)

`ReviewPage` already navigates after a finalize action (today: to the
patient detail page or the patient list — see ReviewPage.jsx:1300-1308).
The change:

1. Add a `useReviewQueue(doctorId)` lookup in `ReviewPage` (the hook already
   exists and is used by `MyAIPage`).
2. After finalize, before falling through to "navigate to patient detail,"
   compute `nextPendingId = queue.find(item => item.id !== currentId && item.status === "pending")?.id`.
3. If `nextPendingId` exists: `navigate(dp(\`review-${nextPendingId}\`))`
   so the same `ReviewPage` component remounts with the next record. Toast:
   `继续下一项 (剩余 N 项)`.
4. If `nextPendingId` is null (queue empty): `navigate(dp("my-ai"))` and
   Toast `已处理完今日全部 N 项`.
5. The legacy "navigate to patient detail" branch is preserved as a fallback
   when the user explicitly chooses to view the patient (a separate button
   on the review screen, not the finalize button).

### Home triage rows — re-targeting

`MyAIPage` `triageRows` array (MyAIPage.jsx:498-529) gets one edit:

| Row | Today | After |
|-----|-------|-------|
| "待审核诊断建议" | `navigate(\`${dp("review")}?tab=pending\`)` | `navigate(dp(\`review-${firstPendingReviewId}\`))` — drill straight into first pending item |
| "待采纳的规则" | `navigate(\`${dp("settings/knowledge")}?tab=pending\`)` | unchanged |
| "新患者" | `navigate(dp("patients"))` | unchanged in target; lands on push subpage now |

The `firstPendingReviewId` comes from the same `useReviewQueue` hook
already in scope. If queue is empty, the row already self-hides (count
filter at MyAIPage.jsx:529).

### "全部事项 ›" SectionHeader link

Deleted entirely (α decision). Today it routes to
`/review?tab=pending` (the queue list we're removing). The 3 triage rows
themselves are the drill-in affordance.

### Cold-start deep-link history seed (B1)

A WeChat push or shared URL that opens `/doctor/review/abc123` cold (no
prior in-app history) currently makes the back-tap exit the app. Fix:

In `App.jsx` boot effect (or wherever the doctor route tree mounts), after
auth resolves, check if the current pathname is anything other than
`/doctor/my-ai` AND `window.history.length <= 1`. If so, perform a synthetic
seed:

```js
const target = location.pathname + location.search;
navigate("/doctor/my-ai", { replace: true });   // becomes the entry
navigate(target, { replace: false });           // current view, with home behind it
```

After seeding, back-tap from the deep-linked detail page lands on
`/doctor/my-ai` (the synthetic root) instead of exiting. Net cost: ~10
lines, single point of change, applies uniformly to every cold-start
deep link.

### Bottom safe-area handling

The TabBar's `<SafeArea position="bottom" />` (DoctorPage.jsx:540) provides
the bottom inset on home-indicator devices today. After removal, the inset
must be rendered by each base section that's the last visible thing on
screen.

Implementation: `MyAIPage` (the only base section) renders its own
`<SafeArea position="bottom" />` at the end of its scroll container. Push
subpages (PatientsPage, etc.) already include their own bottom inset via
their `pageContainer`/`scrollable` layout helpers — verify each during
implementation; add `<SafeArea position="bottom" />` to any that doesn't.

### NavBar ownership migration

Today's shell NavBar is conditional on `baseSection`:

- `baseSection === "patients"` → shows `+` button
- `baseSection === "my-ai"` → shows FeedbackPopover + AddToDesktopPopover
- (review section had no special right-action, just the title)

After:
- Shell NavBar always shows `我的AI` title + my-ai right-action cluster
  (Feedback + AddToDesktop). The conditional branch on `patients` /
  `review` is deleted.
- The `+` (新建病历) moves into `PatientsPage`'s own SubpageHeader as a
  right-side button.

### Home-shortcut icon on every push subpage

Every push subpage (PatientsPage, PatientDetail, ReviewPage, all settings
subpages) renders a **home icon immediately after the back arrow** in its
`NavBar` `backArrow` slot. Layout convention:

```
[← 🏠]    页面标题      [page-specific right action]
```

- Icon: `HomeOutlinedIcon` from `@mui/icons-material`, sized at
  `ICON.sm` (20px), color `APP.text2`.
- Tap behavior: call `markIntentionalBack()` then
  `navigate("/doctor/my-ai")`. The intentional-back flag ensures the
  slide-out animation plays correctly, even though we're navigating to a
  specific path rather than calling `navigate(-1)`.
- The home icon is shown on **all** push subpages, regardless of stack
  depth. From a 1-level subpage it's redundant with the back arrow; from
  a 2+ level deep page (home → patients → patient detail) it's a one-tap
  shortcut.

Implementation pattern — antd-mobile `NavBar` accepts a single `backArrow`
prop. To render two icons, pass a fragment:

```jsx
<NavBar
  backArrow={
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <LeftOutline />
      <HomeOutlinedIcon
        sx={{ fontSize: ICON.sm, color: APP.text2 }}
        onClick={(e) => { e.stopPropagation(); markIntentionalBack(); navigate("/doctor/my-ai"); }}
      />
    </span>
  }
  onBack={() => navigate(-1)}
>
```

The `e.stopPropagation()` is required so tapping the home icon doesn't
also fire the NavBar's `onBack` handler.

## Component changes

### `MyAIPage.jsx`

1. **`quickActions` array**: replace 新建病历 with 全部患者:
   ```js
   { label: "全部患者", icon: <PeopleAltOutlinedIcon ... />, onClick: () => navigate(dp("patients")) }
   ```
   Drop `EditNoteOutlinedIcon` import; add `PeopleAltOutlinedIcon` import.
2. **`triageRows`**: change "待审核诊断建议" row's `onClick` to drill into
   first pending review item (see "Home triage rows" above).
3. **Delete the "全部事项 ›" `actionLabel` from the 今日关注 SectionHeader**
   (MyAIPage.jsx:672-676 — drop the `actionLabel` and `onAction` props).
4. **Add `<SafeArea position="bottom" />`** at the end of the scroll
   container.

### `DoctorPage.jsx`

1. **Delete `<TabBar>`** block.
2. **Delete `TABS` array** and any references.
3. **Delete `badges` state** (placeholder zeros, no consumer).
4. **Simplify `baseSection` detection** — always `my-ai`.
5. **Remove the conditional in NavBar `right` prop** for `patients` /
   `review` branches; keep only the my-ai right-action cluster.
6. **Remove the `baseSection === "patients" ? <PatientsPage /> :
   baseSection === "review" ? <ReviewQueuePage /> : ...` branches** —
   home always renders `<MyAIPage />` as the base; PatientsPage and
   ReviewPage are reached only via `usePageStack` overlays.
7. **Delete the `<SafeArea position="bottom" />`** that was inside the
   TabBar block.
8. **Drop tab-only icon imports** (`PeopleAltIcon`, `MailIcon`,
   `MailOutlinedIcon`, `AutoAwesomeIcon`, `AutoAwesomeOutlinedIcon`,
   `PeopleAltOutlinedIcon`) **after grepping `DoctorPage.jsx` to confirm
   each has zero remaining usages in this file**. `PeopleAltOutlinedIcon`
   is independently imported by `MyAIPage` for the new quick-action tile;
   the two import declarations are unrelated.
9. **Remove the `handleTabChange` function** (DoctorPage.jsx:441-444),
   no longer used.

### `PatientsPage.jsx`

1. **Add an antd-mobile `NavBar`** at the top of the component, with title
   `患者`, the back+home cluster in the `backArrow` slot (see
   "Home-shortcut icon on every push subpage" above), and a right-side `+`
   button that navigates to `?action=new`.
2. Verify the `pageContainer` / `scrollable` layout already includes a
   bottom safe-area inset; if not, add it.
3. Otherwise unchanged — search state, NL results, popup, pull-to-refresh,
   `?action=new` cleanup all stay. Acceptable that local state resets on
   each push from home; the user is expected to drill in from home, not
   park here.

### `ReviewPage.jsx`

1. **Add `useReviewQueue(doctorId)`** lookup at the top.
2. **Modify the post-finalize navigation block** (ReviewPage.jsx:1296-1310):
   - Compute `nextPendingId` from the queue (excluding current record).
   - If present: navigate to `dp(\`review-${nextPendingId}\`)` with Toast
     `继续下一项 (剩余 N 项)`.
   - If absent: navigate to `dp("my-ai")` with Toast `已处理完今日全部 N 项`.
   - Preserve the existing patient-detail / patient-list fallback ONLY for
     non-finalize navigation paths (e.g., if the user explicitly taps "查看患者").
3. **Update the existing NavBar's `backArrow` slot** to include the
   home-shortcut icon (per "Home-shortcut icon on every push subpage").
4. SubpageHeader / NavBar already exists on this page (verify during
   implementation).

### `ReviewQueuePage.jsx`

**Delete the file.** Remove its import from `DoctorPage.jsx`.

### `App.jsx` (or doctor route boot)

Add the cold-start history seed effect (see "Cold-start deep-link history
seed (B1)" above).

### Settings subpages (sweep — home icon only)

Each push subpage in the doctor app — `PersonaSubpage`, `KnowledgeSubpage`,
`AddKnowledgeSubpage`, `KnowledgeDetailSubpage`, `AboutSubpage`,
`TeachByExampleSubpage`, `PendingReviewSubpage`, `PersonaOnboardingSubpage`,
`TemplateSubpage`, `QrSubpage`, `PatientChatPage`, `PatientDetail`,
`OnboardingWizard`, plus `SettingsPage` — gets its existing `NavBar
backArrow={<LeftOutline />}` updated to include the home-shortcut icon
(see "Home-shortcut icon on every push subpage").

No other behavior changes in these files.

**Scope clarification:** This sweep applies to **doctor-app** subpages
only. Patient-portal pages (`PatientPrivacySubpage`, `PatientTaskDetailPage`,
`PatientRecordDetailPage`, etc.) are **not** in scope — those are a separate
surface with their own IA.

### Other files

- **No changes** to routing config beyond the deletions above,
  `usePageStack`, or `useNavDirection`.

## Testing

### New Vitest tests (adopt codex's list verbatim)

Add a `frontend/web/src/v2/__tests__/` test file covering:

1. **TabBar absence:** mount `DoctorPage` at `/doctor/my-ai`; assert no
   `.adm-tab-bar` element in the DOM.
2. **Each historical tab route still mounts a subpage:**
   - `/doctor/patients` → renders `PatientsPage` content
   - `/doctor/review/:id` → renders `ReviewPage` content (use a fixture
     record id)
3. **Home → patients → back returns to home (not browser exit).**
   Programmatic test using MemoryRouter; verify history length and
   final pathname after back.
4. **Home → review/:id → detail → back chain.** Same mechanism.
5. **Cold-start deep link to `/doctor/review/:id`** with empty history
   (`window.history.length === 1`): assert the seed effect runs and back
   unwinds to `/doctor/my-ai` instead of exiting.
6. **`?action=new` replace semantics** preserved after removing the home
   shortcut: navigate to `/doctor/patients?action=new` directly, verify
   the picker opens and the URL is cleaned (existing useEffect in
   PatientsPage).
7. **iOS swipe vs in-app back:** mock `markIntentionalBack` flag; verify
   slide-out animation only runs when intentional, and is suppressed for
   gesture/browser back. (May require fixture mocking of `useNavDirection`.)
8. **`/mock/doctor/*` path behavior:** verify `dp()` helper still produces
   correct paths after `DoctorPage` hardcoded `/doctor/...` references are
   updated to use `dp()` where they were tab-related.
9. **Home-icon shortcut on subpage NavBars:** mount `PatientsPage` (or any
   doctor subpage), simulate a click on the home icon inside `backArrow`,
   assert pathname becomes `/doctor/my-ai` AND the back-arrow `onBack`
   handler did not also fire.

### Manual verification checklist

After the PR:

- [ ] `/doctor/my-ai` renders without TabBar at bottom
- [ ] First quick-action tile reads "全部患者" with people icon, taps → `/doctor/patients`
- [ ] Second tile "预问诊码" → `/doctor/settings/qr`
- [ ] Third tile "知识库" → `/doctor/settings/knowledge`
- [ ] 今日关注 row "待审核诊断建议" drills into first pending review item directly (not list)
- [ ] On finalize, ReviewPage advances to next pending review item; on last item, returns to `/doctor/my-ai` with Toast
- [ ] 今日关注 SectionHeader has no "全部事项 ›" link
- [ ] 最近使用 row taps still open patient detail / knowledge detail
- [ ] PatientsPage NavBar shows `[← 🏠]` + 患者 title + `+` button
- [ ] PatientsPage `+` opens the new-record picker
- [ ] Home icon (🏠) on PatientsPage navigates to `/doctor/my-ai` with slide animation
- [ ] Home icon on PatientDetail (2-level deep: home → patients → detail) returns to `/doctor/my-ai` in one tap, skipping the patient list
- [ ] Home icon on ReviewPage navigates to `/doctor/my-ai` with slide animation
- [ ] Home icon on every settings subpage (Persona, Knowledge, About, etc.) navigates to `/doctor/my-ai`
- [ ] Tapping home icon does NOT also fire the back arrow (no double-nav)
- [ ] Back from PatientsPage returns to `/doctor/my-ai` cleanly with slide animation
- [ ] WeChat push deep link to `/doctor/review/:id` cold-start: tap back → lands on `/doctor/my-ai`, does not exit app
- [ ] WeChat ← arrow / hardware back: still no slide animation (only in-app back arrow animates)
- [ ] Bottom inset visible on iPhone X-class devices on home, patient list, review detail
- [ ] No clipped last rows on any scrollable surface
- [ ] Run `scripts/lint-ui.sh` — passes
- [ ] No console warnings about removed icon imports

### E2E selectors to audit

Grep `frontend/web/tests/` (Playwright) for:
- `getByRole('tab', ...)` → must be replaced with route-based or button-based locators
- `.adm-tab-bar` → no longer exists
- Any explicit click on a TabBar item to switch sections → replace with `goto('/doctor/<route>')` or click on the corresponding home tile

## Risk acceptance

Codex flagged the hard-cut/no-flag rollout as unsafe for this radius — the
change touches root IA, browser history, push-subpage migration, deep-link
seeding, NavBar ownership migration, and platform-specific back gestures.
Regressions on WeChat/iOS are subtle and history-dependent.

User explicitly chose to proceed with the hard cut anyway. Mitigations:

- Test coverage expansion (codex's list verbatim, including cold-start
  deep-link, back-swipe, `?action=new`, `/mock/doctor/*`).
- Manual verification checklist explicitly includes WeChat push deep-link
  cold-start back behavior — this is the test that matters most.
- Single revert restores prior state (the dropped `ReviewQueuePage` file
  comes back via revert; no DB or API surface changed).

If the WeChat regression appears after ship, the fastest path is `git
revert` + manual fix forward, not a hotfix patch on top.

## Rollback

A single `git revert` of the implementation PR returns the app to its prior
state. No DB migrations, no API changes, no router schema migration. URLs
that were valid before (`/doctor/patients`, `/doctor/review`,
`/doctor/review/:id`) remain valid afterward — `/doctor/review` (the
deleted queue) becomes invalid and 404s during the single-tab era; revert
restores it.

WeChat shared URLs and notification deep links that point to specific
patient/review detail records remain functional in either state.

## Open questions for the implementation plan

- Whether `useReviewQueue`'s shape gives us "next pending excluding current"
  cleanly or we need a small helper.
- Whether the cold-start seed should also handle `/doctor/patients/:id`
  deep links (probably yes — same logic, just generalize the "if not home,
  seed home behind"). Implementation plan should generalize.
- Whether `PatientsPage`'s SubpageHeader needs any new icon import (likely
  reuses existing `AddCircleOutline` from antd-mobile-icons).
- Confirm `ReviewPage` is the only consumer of `useReviewQueue` other than
  `MyAIPage` after `ReviewQueuePage` is deleted, so no unexpected query
  invalidation gaps.
