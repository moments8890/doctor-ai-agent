# Patient Pages Design Parity — Design

**Date:** 2026-04-18
**Status:** Draft
**Scope level chosen:** C1 + B — full rewrite with feature parity, patient-friendly defaults preserved, polish included.
**Approach chosen:** β — shell first, data layer next, content + new subpages + polish last.

## Goal

Bring the v2 patient portal (`frontend/web/src/v2/pages/patient/`) to structural and
visual parity with the v2 doctor app (`frontend/web/src/v2/pages/doctor/`). Patient
keeps its own defaults (larger font, WeChat-style chat bubbles) but adopts the same
shell, tokens, data layer, shared components, and subpage pattern as doctor.

## Non-goals

- Chat protocol changes. Polling stays.
- New functional features beyond parity (no patient-side record notes, task
  rescheduling, new task types, or upload flows).
- Doctor-side code changes beyond bug fixes that surface during the sweep.
- Backend changes. All endpoints already exist. (`auth.py:132` returning 404 for
  "token valid but patient missing" is tracked separately — not in this scope.)

## Design

### 1. Shell — `PatientPage.jsx`

Mirror `DoctorPage.jsx` structure.

**Routing** — drop `useParams()`, detect from `location.pathname`:

| Pathname | Renders |
|---|---|
| `/patient`, `/patient/` | ChatTab (default) |
| `/patient/chat` | ChatTab |
| `/patient/records` | RecordsTab |
| `/patient/tasks` | TasksTab |
| `/patient/profile` | MyPage |
| `/patient/records/intake` | IntakePage (full-screen) |
| `/patient/records/:id` | PatientRecordDetailPage (full-screen, new) |
| `/patient/tasks/:id` | PatientTaskDetailPage (full-screen, new) |
| `/patient/profile/about` | PatientAboutSubpage (full-screen, new) |
| `/patient/profile/privacy` | PatientPrivacySubpage (full-screen, new) |

Routes in `v2/App.jsx` already support this (three suffixes: `""`, `"/:tab"`,
`"/:tab/:subpage"` — fixed in this session). No route changes required.

**NavBar** — new, mirrors doctor:
- Fixed at top, height 44. Uses `NavBar` from antd-mobile.
- Title = current tab title (`聊天` / `病历` / `任务` / `我的`).
- Right action: `新问诊` (AddCircleOutline) on `records` tab. No right action on
  other tabs. This replaces the inline "新建病历 — 开始AI预问诊" button currently
  at the top of RecordsTab.
- Hidden when a full-screen subpage is active. Each subpage renders its own
  back-navigation header (SubpageHeader-style).

**TabBar** — updated:
- Active-fill where antd-mobile-icons supports it:
  - `MessageOutline` / `MessageFill` (chat)
  - others (File, UnorderedList, User) fall back to outline-with-active-color,
    since antd-mobile-icons has no Fill variants for them. Document as known
    limitation in `theme.js`.
- Unread badge on chat tab — behavior preserved.
- Icon size from `ICON.lg` (currently 28 at `standard` tier, tier-scaled).

**Section detection** — pure function `detectSection(pathname)` parallel to
`DoctorPage.detectSection`, with matching unit-test-friendly signature.

**Subpage overlay detection** — pure helpers:
`detectRecordDetail`, `detectTaskDetail`, `detectProfileSubpage`. Each returns
either an id / subpage key or null.

### 2. Data layer — `patientQueries.js`

New file: `frontend/web/src/lib/patientQueries.js`. Parallel to `doctorQueries.js`.

Add to `frontend/web/src/lib/queryKeys.js` under new `PK` namespace:

```js
export const PK = {
  patientMe:             () => ["patient","me"],
  patientRecords:        () => ["patient","records"],
  patientRecordDetail:   (id) => ["patient","records", String(id)],
  patientTasks:          () => ["patient","tasks"],
  patientChatMessages:   () => ["patient","chat"],
};
```

Hooks:

| Hook | Backs | Cache policy |
|---|---|---|
| `usePatientMe()` | `getPatientMe` | 5 min stale |
| `usePatientRecords()` | `getPatientRecords` | 30 s stale |
| `usePatientRecordDetail(id)` | `getPatientRecord` | 60 s stale |
| `usePatientTasks()` | `getPatientTasks` | 30 s stale |
| `usePatientChatMessages()` | `getPatientChatMessages` | polling via `refetchInterval: 10_000` while visible, paused on blur via `refetchIntervalInBackground: false` |

Mutations (thin wrappers that invalidate correctly):
- `useCompletePatientTask()` — invalidates `PK.patientTasks()`.
- `useUncompletePatientTask()` — invalidates `PK.patientTasks()`.
- `useSendPatientMessage()` — optimistic update on `PK.patientChatMessages()`,
  then invalidate on success. De-dup behavior preserved.

All hooks pull `token` from `PatientApiContext` internally so callers don't thread it.

### 3. Tab content rewrites

**ChatTab**
- Logic unchanged. Replace manual `useState` + polling with
  `usePatientChatMessages()` + `useSendPatientMessage()`.
- QuickActions row stays above the message list. Keep WeChat-style bubbles
  (doctor right-green, AI left-white) — C1 preservation.
- Remove the unused `TabPlaceholder` component in `PatientPage.jsx` (references
  undefined `FONT`, dead code).

**RecordsTab**
- Use `usePatientRecords()`.
- Remove inline "新建病历" button (moved to NavBar).
- Wrap list in antd-mobile `PullToRefresh`.
- `EmptyState` with illustration (antd-mobile `ErrorBlock status="empty"` +
  custom description).
- Tap → `navigate(\`/patient/records/${id}\`)` — shell overlay takes over.
- Keep existing filter pills (`全部 / 病历 / 问诊`) and list-vs-timeline toggle.

**TasksTab**
- Use `usePatientTasks()` + the mutation hooks.
- `PullToRefresh` wrap.
- antd-mobile `SwipeAction`:
  - Pending task: left-swipe reveals `完成` (primary color).
  - Completed task: left-swipe reveals `撤销` (default color).
  - Inline mini Button extras removed.
- Tap → `navigate(\`/patient/tasks/${id}\`)`.
- `EmptyState` with illustration.

**MyPage**
- Three list sections kept: patient info / doctor info / general.
- `关于`, `隐私政策` → push real subpages (see §4).
- `字体大小` Popup kept.
- `重新查看引导` reload flow kept.
- Font scale replaced: drop local `FONT_SCALE_KEY` + `getFontScale` + inline
  `applyFontScale` wiring. Use `useFontScaleStore` (the same zustand store
  doctor uses). Patient role gets `"large"` as its default tier — set in the
  store's hydration guard, not as a localStorage fallback in MyPage.
- Logout flow unchanged.

### 4. New subpages

All four use a shared `SubpageHeader` pattern: NavBar at top with back arrow,
scrollable body below, `PageSkeleton mobileView` for slide transition.

**PatientRecordDetailPage** (`/patient/records/:id`) — read-only.
- Data: `usePatientRecordDetail(id)` (new hook, backed by
  `getPatientRecord(id)` which already exists at `api.js:983`).
- Sections:
  - Header: record type tag + created_at + status tag.
  - 主诉 (chief complaint) block.
  - 现病史 / 既往史 / 用药史 / 过敏史 (from `structured.*`).
  - 诊断 (diagnosis) block.
  - 原始内容 (raw content), collapsible.
- Layout: `pageContainer` + `scrollable` + section cards with `RADIUS.lg`.

**PatientTaskDetailPage** (`/patient/tasks/:id`).
- Data: read from the cached `usePatientTasks()` list (common case);
  fallback to per-id fetch only for deep links (backend has no per-id
  endpoint — defer, use cache-only for v1, show "task not found" if missing).
- Sections:
  - Title + status tag.
  - Full description (`content`).
  - Due date (if present).
  - Source info (`source_type`, source record link if task type = follow-up).
  - Created / completed timestamps.
- Actions: single primary button at bottom — `标记完成` (pending) or
  `撤销完成` (completed). Uses mutation hooks. Dialog confirm on undo.

**PatientAboutSubpage** (`/patient/profile/about`).
- Copy doctor's `settings/AboutSubpage.jsx` structure.
- Version string (from `VERSION` file / build-time injected).
- Build hash if available.
- `隐私政策` link → navigate to profile/privacy.
- Terms of service link (open external URL).

**PatientPrivacySubpage** (`/patient/profile/privacy`).
- Reuse existing `PrivacyPage` content, rendered inside a SubpageHeader frame
  instead of as a standalone route. Extract body into a shared component
  consumed by both the existing `/privacy` route and this subpage.

### 5. PatientOnboarding

Cosmetic restyle only. Replace:
- Hardcoded font sizes → `FONT.*`.
- Hardcoded icon sizes → `ICON.*`.
- Hardcoded colors → `APP.*`.
- `borderRadius: N` literals → `RADIUS.*`.

Keep the 3-step flow, copy, and dismissal behavior.

### 6. Polish + token cleanup

- Dead code: remove `TabPlaceholder` in `PatientPage.jsx` (it references
  undefined `FONT`, and no caller renders it).
- Hardcoded icon sizes: sweep `RecordsTab`, `TasksTab`, `MyPage`, `ChatTab`.
  Replace `fontSize: 20 / 22 / 24` with `ICON.sm / ICON.md / ICON.lg`.
- `FONT.main` alias → `FONT.base`. Keep the `--adm-font-size-main` CSS
  variable (antd-mobile internals). Remove the JS-side `FONT.main` key with
  a deprecation comment.
- TabBar active-fill icons: use `MessageFill`. For File / UnorderedList / User
  keep outline + active color (no Fill variant available in antd-mobile-icons).
- Chat bubble tokens: replace any hardcoded `#95EC69` with `APP.wechatGreen`.

## Data flow (canonical example)

```
User lands on /patient/records
  → App.jsx Route "/patient/:tab" → PatientPage
  → detectSection("/patient/records") → "records"
  → NavBar renders "病历" + 新问诊 icon
  → RecordsTab renders; usePatientRecords() → React Query cache
  → PullToRefresh wraps List
User taps a record
  → navigate(`/patient/records/42`)
  → detectRecordDetail("/patient/records/42") → "42"
  → PatientPage renders PatientRecordDetailPage instead of RecordsTab
  → NavBar hidden; subpage renders its own SubpageHeader
  → usePatientRecordDetail(42) → React Query cache
User taps back
  → navigate(-1) → URL /patient/records
  → Overlay detection returns null → RecordsTab resumes (React Query returns
    cached list instantly — no reflow)
```

## Error handling

- React Query error states → shared `ErrorBlock` with 重试 button.
- 401/403 → existing `onAuthExpired` middleware redirects to `/login`.
- 404 from `/patient/me` when token references missing patient → not handled
  in this scope. Tracked as a separate backend bug. Client still shows
  ErrorBlock fallback with "重新登录" CTA to clear localStorage.

## Testing

New Playwright specs in `frontend/web/tests/e2e/`:
- `24-patient-shell.spec.ts` — each of 4 tab URLs activates correct tab,
  NavBar title matches, active icon rendered.
- `25-patient-record-detail.spec.ts` — list → detail → back round-trip,
  browser back also works.
- `26-patient-task-detail.spec.ts` — list → detail → complete → list updates;
  undo path.
- `27-patient-my-subpages.spec.ts` — MyPage → About → back; MyPage → Privacy
  → back; font scale popup selects and persists.

Existing specs updated:
- `22-patient-records.spec.ts` — adjust for new NavBar and record detail flow.
- `23-patient-tasks.spec.ts` — swipe-to-complete replaces inline button.

Manual smoke checklist (documented in plan):
- Fresh patient registers via `/login` → lands on `/patient` (chat tab).
- All 4 tabs, all subpages, NavBar title + back correct.
- PullToRefresh works on records and tasks.
- `prefers-reduced-motion` disables slide transitions.
- Font scale Popup changes text size globally.
- Logout clears localStorage and returns to `/login`.

## Risks / open decisions

- **Font scale server sync.** `useFontScaleStore` currently uses `doctorId` for
  server sync. Patient portal has `patient_id` instead. Decision: for this
  spec, **patient font scale stays local (no server sync)**. The store's
  `saveFontScaleToServer` is called only when a `doctorId` is present. Document
  in a comment in `fontScaleStore`. Future work: add patient-role sync endpoint.
- **TabBar Fill variants.** antd-mobile-icons only ships `MessageFill` and
  `TeamFill` for the icons we use. File / UnorderedList / User have no Fill
  variants. Decision: use Fill where available, otherwise outline-with-active-
  color. Visual difference vs doctor is acceptable.
- **SwipeAction UX change on tasks.** Replacing inline complete/undo buttons
  with swipe is a real interaction-model change. Mitigation: keep the primary
  action inside the detail page too, so swipe is a shortcut, not the only path.
- **Task detail fallback.** Backend has no per-id patient task endpoint. For
  v1, detail page reads from the cached tasks list only. A deep-linked URL
  to an uncached task will show "task not found". Add `GET
  /api/patient/tasks/:id` as follow-up if deep links become common.

## Build sequence (phases)

**Phase 1 — Shell**
1. Rewrite `PatientPage.jsx`: NavBar, pathname detection, section + subpage
   matchers, active-fill TabBar, stub renders for new subpages.
2. Create stub components `PatientRecordDetailPage`, `PatientTaskDetailPage`,
   `PatientAboutSubpage`, `PatientPrivacySubpage` — each renders `SubpageHeader`
   + "Coming soon" body.
3. Remove dead `TabPlaceholder`.
4. E2E: existing `22`/`23` specs still pass; new `24-patient-shell.spec.ts`.

**Phase 2 — Data layer**
1. Add `PK` keys to `queryKeys.js`.
2. Create `patientQueries.js` with query + mutation hooks.
3. Migrate `ChatTab`, `RecordsTab`, `TasksTab`, `MyPage` fetch paths to hooks.
4. Loading/error states via shared `LoadingCenter` / `ErrorBlock`.
5. E2E: no behavior change; `22`/`23` still pass.

**Phase 3 — Content + new subpages + polish**
1. `PatientRecordDetailPage` real content.
2. `PatientTaskDetailPage` real content.
3. `PatientAboutSubpage` and `PatientPrivacySubpage` real content (extract
   shared privacy body).
4. `PullToRefresh` on records + tasks.
5. `SwipeAction` on tasks.
6. Active-fill TabBar icons where supported; chat bubble token cleanup.
7. `PatientOnboarding` restyle.
8. Font scale store unification for patient.
9. E2E `25` / `26` / `27`. Update `22` / `23` for new interactions.

Each phase is independently shippable and reviewable.
