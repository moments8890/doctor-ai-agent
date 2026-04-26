# Patient App — Doctor UI Parity (visual + finish prior Phases 2/3)

**Date:** 2026-04-24
**Status:** Draft v3.1 — three Codex review passes applied (session `019dc302-91ed-7e91-b704-61be57aac47e`)
**Supersedes / extends:** [`2026-04-18-patient-pages-design-parity-design.md`](./2026-04-18-patient-pages-design-parity-design.md). Prior spec landed Phase 1 (shell, pathname routing, stub subpages) only. Phases 2 (data layer) and 3 (subpage content + polish) were never landed.

## Revision log

**v3 → v3.1** (third Codex pass — two leftovers caught):

| v3 problem | v3.1 fix |
|---|---|
| Section 3 hooks table still referenced `setAuth(...)` (the now-deleted method) on the `usePatientMe()` row | Changed to `mergeProfile(...)` to match the new store API; clarified token is never touched. |
| "CI lint rule (or pre-push hook)" claim was vapor — no husky/lefthook/.githooks/CI-lint exists | Pin enforcement to the real, repo-existing `scripts/lint-ui.sh` (per `CLAUDE.md:73`). Add a 5-line grep check there. |

**v2 → v3** (second Codex pass — residual issues fixed):

| v2 problem | v3 fix |
|---|---|
| `setAuth` merge nullish-preserved stale `patientId/patientName` across QR/login handoff | Split into `loginWithIdentity` (atomic replace at login boundaries) and `mergeProfile` (partial merge for `/patient/me` refresh). Documented multi-tab limitation as a known carry-over. |
| Task detail used wrong field semantics (`source_type === "follow_up"`, `status === "done"`) | Use `task_type === "follow_up"` (real field), `status === "completed"` (real value). `source_record_id` derived from `task.record_id` (not `task.source_id`), typed as `int`. Added `cancelled` status branch. |
| `raw_content` card hand-waved as "verify at impl time" | Card removed entirely. Patient endpoint deliberately exposes only `structured + treatment_plan + diagnosis_status`; raw clinical text is doctor-only. |
| Barrel-export alias was a vague "remove after one release" | Hardened: alias removed as the last step of Phase 5, with a grep guard blocking new `SectionHeader` imports. |

**v1 → v2** (first Codex pass — every concrete claim was wrong, fixed below):

| v1 claim | Reality | v2 fix |
|---|---|---|
| "Hooks read token from `usePatientApi()` internally" | `usePatientApi()` only returns API fns; token is an explicit arg to every patient API call | New Phase 1: lift token into a zustand `usePatientStore`. Hooks read token from it. |
| "Use `useFontScaleStore` (the same store doctor uses); default tier becomes standard" | That store is keyed `"doctor-font-scale"` with default `"large"`, and `App.jsx:222-225` auto-syncs it to doctor backend on every change. Reusing it pollutes doctor state. Defaulting patients to `standard` is also an a11y regression. | Don't unify. Keep patient font scale local-only via a small `patientFontScale.js` util. Default stays `"large"`. Keep the 3-option Popup (drop the binary Switch idea — patients need 特大). |
| "Promote local `SectionHeader` from doctor SettingsPage as shared `CardSectionHeader`" | SettingsPage local uses `Icon + label`; AboutSubpage local uses plain text. They're not the same component. Forcing the abstraction is fake. | Don't extract `CardSectionHeader`. Patient MyPage gets its own local copy of SettingsPage's pattern. Only `Card` and `TintedIconRow` get extracted (real duplicates). |
| "RecordsTab is a consumer of `SectionHeader.jsx`" | It isn't. Only `ReviewPage.jsx` imports it. | Sweep is trivial — 1 import to update. Keep a one-release barrel-export alias for safety. |
| "PatientRecordDetailPage uses `structured.history_of_present_illness` and `differential`" | Real keys are `chief_complaint`, `present_illness`, `past_history`, `allergy_history`, etc. `differential` doesn't exist. `diagnosis_status` (not `status`) is `completed | confirmed | null`. `treatment_plan` is `{medications, follow_up, lifestyle}`. | Rewrite Section 3 record detail against real fields. |
| "PatientTaskDetailPage shows 完成时间 and 来源 card" | `PatientTaskOut` has no `completed_at` and no `source_record_id`. There is also no `GET /api/patient/tasks/:id` endpoint. Cache-only would show "任务不存在" on hard refresh. | New Phase 0: backend adds those two fields and the per-id endpoint. Then Phase 5 builds a real fetchable detail page. |
| "ChatTab — no behavior change" | Current polling: 10s visible / 60s hidden via `setInterval` + `visibilitychange`. Local optimistic dedupe + unread badge side effects. Naive React Query `refetchInterval` would change cadence and break dedupe. | Don't migrate ChatTab to React Query. Keep its existing polling implementation. Only re-skin the QuickActions row. |
| "TasksTab — SwipeAction replaces inline buttons" | Patient audience is older / less tech-comfortable. Hidden swipe actions are less discoverable and forgiving than the current visible tap-target prefix. | Keep current visible tap targets. Optional: add SwipeAction as a *shortcut*, never as the only path. v1 of this spec does not add SwipeAction. |
| Footprint estimate ~12 files / ~5 new | Token + font ownership are not minor edits; backend Phase 0 added | Footprint revised at end. |

## Goal

Bring the v2 patient portal to **visual language parity** with the v2 doctor app and **finish** the data-layer + real subpage content the prior spec deferred. Patient-specific defaults that exist for legit accessibility reasons (larger default font tier, 3-tier font selector) stay. Chat bubbles already share the same component — no change there.

## Non-goals

- Doctor functional changes (only the `Card` + `TintedIconRow` extractions in Section 1 touch doctor files).
- New patient features beyond the prior spec's surface area (no patient-side record edits, custom task creation, new task types, uploads).
- v1 cleanup (only admin app remains under `src/pages/`; out of scope).
- Doctor `PatientChatPage` `MessageBubble` (doctor's view of patient↔AI chat) stays untouched.
- Replacing patient ChatTab's bespoke polling with React Query.
- Replacing patient TasksTab's visible tap-target rows with SwipeAction.

## Section 0 — Backend additions (small)

`PatientTaskOut` and the patient task router need three additions to make a real task-detail subpage possible.

`src/channels/web/patient_portal/tasks.py`:
- Add `completed_at: Optional[datetime] = None` to `PatientTaskOut`. Populate from `task.completed_at` (already a column on `DoctorTask`) in the list and detail endpoints.
- Add `source_record_id: Optional[int] = None` to `PatientTaskOut`. Derive from `task.record_id` (the FK to `medical_records.id`), NOT from `task.source_id` (which is a different semantic field — not a record link). Populated whenever the task is linked to a record, regardless of `task_type`.
- `task_type` is already on `PatientTaskOut` (`general | follow_up`) — no change needed.
- Add `GET /api/patient/tasks/{task_id}` returning a single `PatientTaskOut` for the requesting patient. 404 if not found, not owned (`task.patient_id != patient.id`), or not patient-targeted (`task.target != "patient"`). Reuses the existing `_authenticate_patient` bearer-token helper.

Mirror in `frontend/web/src/api.js`:
- Add `getPatientTaskDetail(token, taskId)` calling `patientRequest("/api/patient/tasks/" + taskId, token)`.
- Wire through `PatientApiContext.jsx`.
- Add the same fn to `frontend/web/src/api/patientMockApi.js` (returns from the mock list).

Tests: extend `tests/api/test_patient_portal.py` (or equivalent) with one happy-path + one not-found + one cross-patient-isolation case for the new endpoint.

This is the only backend work. ~30 LOC.

## Section 1 — Patient token ownership

The patient token currently lives in `PatientPage` local state and is threaded as an explicit arg through every patient API call. That can't back React Query hooks cleanly.

Create `frontend/web/src/store/patientStore.js` (mirrors `doctorStore.js` shape but minimal). The auth setters are deliberately split so login boundaries replace identity atomically and `/patient/me` refreshes only merge profile fields:

```js
import { create } from "zustand";
import { persist } from "zustand/middleware";

const EMPTY = { token: "", patientId: "", patientName: "", doctorId: "", doctorName: "" };

export const usePatientStore = create(
  persist(
    (set) => ({
      ...EMPTY,
      // Replaces the entire auth identity atomically. Use at login boundaries
      // (QR absorption, /login redirect). Any field not provided is cleared.
      loginWithIdentity: ({ token, patientId, patientName, doctorId, doctorName } = {}) =>
        set({
          token: token || "",
          patientId: patientId || "",
          patientName: patientName || "",
          doctorId: doctorId || "",
          doctorName: doctorName || "",
        }),
      // Merges profile fields without touching token. Use only for /patient/me
      // refresh after login is already established.
      mergeProfile: ({ patientId, patientName, doctorId, doctorName } = {}) =>
        set((s) => ({
          patientId: patientId ?? s.patientId,
          patientName: patientName ?? s.patientName,
          doctorId: doctorId ?? s.doctorId,
          doctorName: doctorName ?? s.doctorName,
        })),
      clearAuth: () => set(EMPTY),
    }),
    { name: "patient-portal-auth" }
  )
);
```

Migrate `PatientPage.jsx`:
- Drop the six `useState` + the localStorage keys (STORAGE_KEY, STORAGE_NAME_KEY, etc.). Read identity from `usePatientStore()`.
- The QR-token absorption block (top of `PatientPage`) calls `loginWithIdentity({ token, patientId: '', patientName: qrName, doctorId: qrDoctorId, doctorName: '' })` — atomic replace, so any stale identity from a prior session is wiped.
- The `getPatientMe` refresh `useEffect` becomes `usePatientMe()` (Phase 3); on success it calls `mergeProfile({...})` (does NOT touch token).
- `handleLogout` → `usePatientStore.getState().clearAuth()`.

Migration safety: on first load after upgrade, hydrate the new store from the *old* localStorage keys if `patient-portal-auth` doesn't exist yet. One-shot migration block in `patientStore.js` (uses `loginWithIdentity` for atomicity). Old keys then deleted.

Multi-tab note: Zustand `persist` middleware does NOT auto-sync across tabs. A logout in one tab will not clear the in-memory store of a sibling tab. This matches the existing pre-store behavior (each tab held its own `useState`). Out of scope; flag in risks.

## Section 2 — Shared primitives + barrel rename

Two real duplicates get extracted. The fake one (`CardSectionHeader`) does not.

| Current | New | Notes |
|---|---|---|
| `v2/components/SectionHeader.jsx` (divider bar w/ `surfaceAlt` bg + top/bottom borders) | rename → `v2/components/ListSectionDivider.jsx` | Sole external consumer: `ReviewPage.jsx`. Update its import. |
| Local `Card` in `doctor/SettingsPage.jsx` AND `doctor/settings/AboutSubpage.jsx` | promote → `v2/components/Card.jsx` | Identical shape (white surface, `RADIUS.lg`, `margin: 0 12px`, `overflow: hidden`). |
| Local `SettingsRow` in `doctor/SettingsPage.jsx` (36px tinted-circle icon + title + subtitle + extra/chevron) | promote → `v2/components/TintedIconRow.jsx` | Currently 1 consumer (SettingsPage). Patient MyPage adds the 2nd. |

NOT extracted in this spec:
- **`CardSectionHeader`** — SettingsPage local uses `Icon + label`, AboutSubpage local uses plain text. Different shapes. Both stay local. Patient MyPage copies SettingsPage's pattern locally.
- The collapsible-header pattern in `doctor/PatientsPage.jsx` (also named `SectionHeader` locally, with badge + chevron toggle) — entirely different again, stays local.

Barrel safety:
- `v2/components/index.js` currently re-exports `SectionHeader`. After rename, add a temporary compat alias:
  ```js
  export { default as ListSectionDivider } from "./ListSectionDivider";
  export { default as SectionHeader } from "./ListSectionDivider"; // DEPRECATED — remove in Phase 5
  ```
- Sweep `ReviewPage.jsx` to import from the new name in the same PR.
- Add `Card`, `TintedIconRow` re-exports.
- Update `doctor/SettingsPage.jsx` to import shared `Card` + `TintedIconRow`; delete its locals.
- Update `doctor/settings/AboutSubpage.jsx` to import shared `Card`; delete its local.

**Hard cleanup commitment**: the `SectionHeader` alias is a transition aid, not a permanent name. As the very last step of Phase 5 (before that phase merges):
1. Grep for any remaining `import { ... SectionHeader ... } from "../../components"` (or analogous relative paths) — must return zero hits.
2. Delete the alias line from `v2/components/index.js`.
3. **Add a real check** to `scripts/lint-ui.sh` (the script that already enforces the v2 token rules per `CLAUDE.md:73`): a `grep -rE` for `SectionHeader` imports from `v2/components` that exits 1 on hit. CLAUDE.md instructs running `lint-ui.sh` before push, and there is no separate CI step for it — the script is the enforcement mechanism. Extending it is a 5-line addition, not new tooling.

If the rename slips out of Phase 5, the alias must NOT outlive a release.

Tests: existing E2E specs unchanged after this phase.

## Section 3 — Data layer

New `frontend/web/src/lib/patientQueries.js`. Hooks read `token` from `usePatientStore` internally.

Add to `queryKeys.js`:

```js
export const PK = {
  patientMe:           () => ["patient","me"],
  patientRecords:      () => ["patient","records"],
  patientRecordDetail: (id) => ["patient","records", String(id)],
  patientTasks:        () => ["patient","tasks"],
  patientTaskDetail:   (id) => ["patient","tasks", String(id)],
};
```

Hooks:

| Hook | Backs | Cache |
|---|---|---|
| `usePatientMe()` | `getPatientMe(token)` | `staleTime: 5 * 60_000`, `enabled: !!token`; on success calls `usePatientStore.getState().mergeProfile({patientName, doctorId, doctorName, patientId})` (never touches `token`) |
| `usePatientRecords()` | `getPatientRecords(token)` | `staleTime: 30_000`, `enabled: !!token` |
| `usePatientRecordDetail(id)` | `getPatientRecordDetail(token, id)` | `staleTime: 60_000`, `enabled: !!token && !!id` |
| `usePatientTasks()` | `getPatientTasks(token)` | `staleTime: 30_000`, `enabled: !!token` |
| `usePatientTaskDetail(id)` | `getPatientTaskDetail(token, id)` | `staleTime: 60_000`, `enabled: !!token && !!id`; uses cached list entry as initialData when present |

Mutations:
- `useCompletePatientTask()` → `completePatientTask(token, taskId)`. Invalidates `PK.patientTasks()` and `PK.patientTaskDetail(taskId)`.
- `useUncompletePatientTask()` → analogous.

**ChatTab is NOT migrated.** Its bespoke polling (10s visible / 60s hidden) + optimistic dedupe + unread side effects stays in place. The hook list does not include `usePatientChatMessages` for this reason.

Migration: `RecordsTab` and `TasksTab` drop their inline `useEffect + useState + manual fetch` and consume hooks. `MyPage` keeps its prop interface; `PatientPage` shell switches to `usePatientMe()` instead of inline `getPatientMe`.

## Section 4 — Per-tab visual rewrites

Each tab gets gray `pageContainer` bg + floating white Cards.

### `patient/MyPage.jsx` — full rewrite, mirror `doctor/SettingsPage.jsx` style

Drop the antd-mobile `<List header>` look. Use the shared `Card` + `TintedIconRow` from Section 2, plus a local `SectionHeader` (icon + label) copied from SettingsPage's pattern (the abstraction stays local until a 3rd consumer appears).

| Section | Content | Pattern |
|---|---|---|
| **Profile card** (top) | `NameAvatar` (size 48) + `patientName` + `患者` sublabel | `<Card>` w/ profile-row layout (display-only, no chevron) |
| **我的医生** (only if `doctorName` present) | Doctor `NameAvatar` (`APP.accent`) + name + specialty | local `<SectionHeader Icon={LocalHospitalOutlined} iconColor={APP.accent} title="我的医生" />` + `<Card>` |
| **通用** | 关于 / 隐私政策 / 字体大小 (current value as `extra`) / 重新查看引导 | local `<SectionHeader Icon={SettingsOutlined} iconColor={APP.accent} title="通用" />` + `<Card>` of `<TintedIconRow>` |
| **Logout button** | `Button block color="danger" fill="outline"` w/ `LogoutOutlined` icon | identical to doctor |
| **Footer** | "退出后将清除本地缓存，确保账号安全" w/ `SecurityOutlined` icon | identical to doctor |

Behavior changes:
- Move inline `getFontScale` / `setFontScaleStored` / `localStorage.FONT_SCALE_KEY` into `frontend/web/src/v2/lib/patientFontScale.js` as named exports (keeps the same storage key, the same `large` default, the same 3-option behavior). MyPage imports from there.
- 字体大小 stays as a 3-option Popup (标准 / 大 / 特大). Do NOT switch to a binary Switch.
- Icons switch from antd-mobile-icons (`InformationCircleOutline`, `LoopOutline`, …) to MUI outlined (`InfoOutlined`, `RefreshOutlined`, …) to match doctor's row icons.
- 关于 / 隐私政策 wire to real subpages (Section 5) — replaces current `onClick={() => {}}`.

### `patient/RecordsTab.jsx` — apply card pattern + PullToRefresh

Keep all data, filter, and view-toggle (list / timeline) logic. Visual chrome only:
- Page background switches to `pageContainer` (gray).
- Filter pills (`CapsuleTabs`) sit on the gray bg above the cards.
- Each record becomes a `<Card>` (`margin: "8px 12px"`) with custom row layout: colored type tag (e.g. 门诊记录 = primaryLight, 预问诊 = accentLight) + title `<Ellipsis rows={1}>` + meta line (date · diagnosis_status label).
- Timeline view: month section uses a small label header on gray bg above per-month Card stack (local impl, not extracted).
- Empty state → shared `EmptyState`.
- Wrap list in antd-mobile `<PullToRefresh>` — calls `refetch()` from `usePatientRecords()`.

### `patient/TasksTab.jsx` — apply card pattern + PullToRefresh

- Already on `pageContainer` (gray).
- Wrap each task as a `<Card>` instead of antd-mobile `List.Item`.
- Custom row preserves the **existing visible tap-target** for complete/undo on the row prefix (a 36px tinted circle: empty for pending, check for done — tapping toggles via `useCompletePatientTask` / `useUncompletePatientTask`).
- Body: title `<Ellipsis rows={2}>` + due-date / status meta line. Tap on the body navigates to detail.
- `<PullToRefresh>` wrap.
- **No SwipeAction in v1.** Can be added as an optional shortcut in a follow-up if usage data shows users want it.

### `patient/ChatTab.jsx` — minimal re-skin only

- Polling, send, optimistic update, unread side effects, `ChatBubble` itself: all unchanged.
- The "QuickActions" row above the messages becomes a `<Card>` containing two `<TintedIconRow>` entries:
  - `新问诊` → primaryLight, `onClick={onNewIntake}` (existing prop, navigates to `/patient/records/intake`)
  - `查看病历` → accentLight, `onClick={onViewRecords}` (existing prop, navigates to `/patient/records`)
- Empty state → shared `EmptyState`.

### `patient/PatientOnboarding.jsx` — token cleanup only

Sweep hardcoded font/icon sizes & colors per the prior spec §5:
- `fontSize: N` → `FONT.*`
- `fontSize: N` (icon) → `ICON.*`
- hex literals → `APP.*`
- `borderRadius: N` → `RADIUS.*`

3-step flow, copy, and dismissal behavior unchanged.

## Section 5 — Real subpage content

All four use `pageContainer` gray bg, top `<NavBar>` w/ back arrow, scrollable body of `<Card>` blocks.

### `PatientRecordDetailPage` (`/patient/records/:id`) — read-only

Wire `usePatientRecordDetail(id)`. **Field names below match the actual `PatientRecordDetailOut` payload**, verified against `src/channels/web/patient_portal/tasks.py` and `src/db/models/records.py`.

| Card | Content | Source |
|---|---|---|
| **Header** | Record type tag (colored) · `relativeDate(created_at)` · `diagnosis_status` label (mapped: `completed`→待审核 primary, `confirmed`→已确认 success, falsy→诊断中 warning) | `record_type`, `created_at`, `diagnosis_status` |
| **主诉** | Plain text block, only if non-empty | `structured.chief_complaint` |
| **现病史** | Plain text block, only if non-empty | `structured.present_illness` |
| **既往史 / 过敏史 / 个人史 / 家族史** | One Card with up to 4 rows (one per non-empty field). If all empty, omit the card. | `structured.past_history`, `structured.allergy_history`, `structured.personal_history`, `structured.family_history` |
| **诊断与用药** (only if `treatment_plan` present) | `treatment_plan.medications` rendered as a list (each item: name, dose, frequency); `treatment_plan.follow_up` as a text row; `treatment_plan.lifestyle` as a text row. | `treatment_plan` dict |

No 原始内容 / raw clinical text card. The patient-facing endpoint (`PatientRecordDetailOut`) deliberately exposes only `structured` + `treatment_plan` + `diagnosis_status`; raw clinical text is doctor-only by design. Don't add a card for data the endpoint doesn't return.

Loading → shared `LoadingCenter`. Error → shared `ErrorBlock` ("加载失败 重试") that calls `refetch()`.

### `PatientTaskDetailPage` (`/patient/tasks/:id`)

Wire `usePatientTaskDetail(id)` (uses cached list as `initialData` when available, then refetches via the new per-id endpoint from Section 0).

| Card | Content | Source |
|---|---|---|
| **Header** | Task title + status tag — `pending`→待完成, `completed`→已完成, `cancelled`→已取消 | `title`, `status` |
| **任务详情** | Full `content` rendered with `<Ellipsis rows={10} expandText="展开">` | `content` |
| **时间** | 截止: `due_at` (if set; render in `APP.danger` if past and `status === "pending"`) · 创建: `created_at` · 完成: `completed_at` (only when `status === "completed"`) | `due_at`, `created_at`, `completed_at` (now exposed per Section 0) |
| **来源** | Render only when `source_record_id` is set (regardless of `task_type` — the field is null whenever the task isn't linked to a record). Row label: 随访任务 · 关联病历 #{id} when `task_type === "follow_up"`, otherwise 关联病历 #{id}. Tap → `/patient/records/:source_record_id`. | `task_type`, `source_record_id` |

Status enum used throughout the patient UI: `pending | completed | cancelled` (matches DB `ck_doctor_tasks_status` constraint).

Bottom action: full-width primary `<Button>`:
- `status === "pending"` → `标记完成` (primary) → `useCompletePatientTask` mutation
- `status === "completed"` → `撤销完成` (default) → `Dialog.confirm` → `useUncompletePatientTask` mutation
- `status === "cancelled"` → no action button; render a small disabled note ("此任务已取消")

404 from per-id endpoint → `ErrorBlock` ("任务不存在或已删除") with back-to-list button.

### `PatientAboutSubpage` (`/patient/profile/about`)

Mirror `doctor/settings/AboutSubpage.jsx` 1:1 using shared `Card` from Section 2.

| Card | Content |
|---|---|
| **App info** | App name (患者助手) · 版本 (from `APP_VERSION`) · build hash (if injected) |
| **法律信息** | 隐私政策 → `navigate("/patient/profile/privacy")` (TintedIconRow with chevron) · 服务条款 → opens external URL |

`APP_VERSION` source-of-truth: at impl time, locate the existing constant by grepping (`doctor/settings/AboutSubpage.jsx` is the most likely site). Three outcomes:
1. Already exported from a shared module → import from there.
2. Hardcoded inline in `AboutSubpage.jsx` → extract to `v2/version.js`, both subpages import from there.
3. Read from `import.meta.env.VITE_APP_VERSION` → use the same source from `v2/version.js`.

### `PatientPrivacySubpage` (`/patient/profile/privacy`)

Extract the body of existing `v2/pages/PrivacyPage.jsx` into a reusable `PrivacyContent` component (sibling file, e.g. `v2/pages/PrivacyContent.jsx`). Two consumers:
- existing `/privacy` route (signup flow) — body becomes `<PrivacyContent />`
- new `/patient/profile/privacy` subpage — wraps `<PrivacyContent />` in NavBar + `pageContainer`

## Tests

### Backend
- `tests/api/test_patient_portal.py` — add cases for the new `GET /api/patient/tasks/:id`: happy path, 404, cross-patient isolation, completed_at and source_record_id surface correctly.

### Manual smoke (run on `:8001`)
- Fresh patient registers via `/login` → lands on `/patient` → all 4 tabs render with new card chrome.
- MyPage → 关于 → back. MyPage → 隐私政策 → back. Font Popup offers 标准/大/特大; selection persists.
- RecordsTab → tap a record → detail page renders all sections present in the payload → back.
- TasksTab → tap row prefix circle → task toggles between pending/done → list updates. Tap task body → detail page → 标记完成 / 撤销完成 (with confirm dialog) → list updates. Hard-refresh on a task detail URL → page renders (per-id endpoint, not cache-only).
- ChatTab unchanged (poll, send, optimistic, unread badge).
- Logout clears persisted store and returns to `/login`.

### Playwright
Updated:
- `22-patient-records.spec.ts` — selectors for new card layout & detail page round-trip (use real field names).
- `23-patient-tasks.spec.ts` — visible-tap-prefix complete/undo flow + body-tap to detail.

New:
- `25-patient-record-detail.spec.ts` — list → detail → back; verify cards conditional on payload (e.g. omits 既往史 card when all 4 fields empty).
- `26-patient-task-detail.spec.ts` — list → body-tap → detail → 标记完成 → list refresh; done → detail → 撤销完成 → confirm → list refresh; deep-link hard-refresh works.
- `27-patient-my-subpages.spec.ts` — MyPage → about → back; MyPage → privacy → back; font Popup selects 特大 and persists.

## Build sequence (5 phases)

### Phase 0 — Backend (Section 0)
1. Add `completed_at` + `source_record_id` to `PatientTaskOut`; populate in list + detail.
2. Add `GET /api/patient/tasks/{task_id}`.
3. Add `getPatientTaskDetail` to `api.js` + mock + `PatientApiContext`.
4. Backend tests.

### Phase 1 — Patient token store (Section 1)
1. Create `store/patientStore.js` with one-shot localStorage migration block.
2. Migrate `PatientPage.jsx` to read identity from the store.
3. Existing E2E specs (`20/21/22/23/24`) still pass.

### Phase 2 — Shared primitives + barrel rename (Section 2)
1. Rename `v2/components/SectionHeader.jsx` → `ListSectionDivider.jsx`.
2. Add temp barrel alias `SectionHeader → ListSectionDivider`. Update `ReviewPage.jsx` import in same PR. (Alias removed in a follow-up release.)
3. Create `v2/components/Card.jsx`, `TintedIconRow.jsx` from `doctor/SettingsPage.jsx` locals.
4. Update `doctor/SettingsPage.jsx` and `doctor/settings/AboutSubpage.jsx` to import shared `Card`; delete locals. SettingsPage also imports shared `TintedIconRow`.
5. Re-export in `v2/components/index.js`.
6. Existing E2E specs unchanged.

### Phase 3 — Patient query layer (Section 3)
1. Add `PK` namespace to `queryKeys.js`.
2. Create `lib/patientQueries.js` with hooks + mutations (token from `usePatientStore`).
3. Migrate `RecordsTab` / `TasksTab` to hooks.
4. `PatientPage` shell uses `usePatientMe()` (writes back to store on success).
5. Loading/error via shared `LoadingCenter` / `ErrorBlock`.
6. **ChatTab not touched.** `21-patient-chat.spec.ts` unchanged & passing.

### Phase 4 — Visual rewrites (Section 4)
1. MyPage rewrite (mirror SettingsPage style; local SectionHeader; antd→MUI icon swap; font Popup preserved; `patientFontScale.js` util extraction).
2. RecordsTab card pattern + PullToRefresh.
3. TasksTab card pattern + PullToRefresh (visible tap-target preserved, no SwipeAction).
4. ChatTab QuickActions row → Card+TintedIconRow.
5. PatientOnboarding token cleanup.
6. Update `22/23` specs for new layouts (selectors only — interaction model unchanged).

### Phase 5 — Real subpage content (Section 5)
1. `PatientRecordDetailPage` real content (real field names, conditional cards).
2. `PatientTaskDetailPage` real content (uses Phase 0 endpoint; deep-link works).
3. `PatientAboutSubpage` real content; `APP_VERSION` source consolidation.
4. Extract `PrivacyContent` from `PrivacyPage.jsx`; `PatientPrivacySubpage` consumes it.
5. New specs `25 / 26 / 27`.

Each phase is independently shippable. Phase 0 unblocks Phase 5; Phase 1 unblocks Phase 3.

## Risks / open decisions

- **Patient font scale stays local-only.** Acceptable for v1. Future: when patient-side preferences endpoint exists, add cross-device sync analogous to doctor.
- **Default tier stays `large`.** Reverses earlier "C — normalize" decision. Codex's accessibility argument (and the prior team's deliberate choice) takes precedence.
- **Font selector stays 3-option Popup.** 特大 (1.3×) is preserved.
- **TasksTab keeps visible tap targets, no SwipeAction.** Reverses earlier swipe decision. Discoverability + forgiveness for older audience wins. Re-evaluate with usage data.
- **ChatTab not migrated to React Query.** Bespoke polling preserved. Migration would change cadence (10s/60s vs single interval) and break optimistic dedupe.
- **TabBar Fill icons.** antd-mobile-icons only ships `MessageFill` / `TeamFill`. `File` / `UnorderedList` / `User` stay outline + active color (carry-over).
- **`raw_content` on patient record detail** — verify at Phase 5 impl time whether the patient endpoint exposes it. If not, drop the 原始内容 card.
- **`treatment_plan` shape** — backend parses it as either dict or `{medications, follow_up, lifestyle}` fallback. UI rendering must handle the fallback shape (medications array may be empty).
- **404 from `/patient/me` when token references missing patient** — out of scope, separate backend bug. Client shows ErrorBlock with "重新登录" CTA that calls `usePatientStore.getState().clearAuth()`.
- **Multi-tab logout / auth sync** — Zustand `persist` doesn't sync across tabs. A logout in tab A leaves tab B's in-memory store stale until the next read of `localStorage`. This matches existing pre-store behavior. Out of scope; revisit if patient session length becomes a problem.
- **Barrel alias lifetime** — the `SectionHeader → ListSectionDivider` alias is removed in Phase 5 with a hard grep guard. If Phase 5 slips, the alias must NOT outlive a release.

## Footprint (revised)

- Backend: ~30 LOC + 3 tests (Phase 0).
- Frontend modified: ~14 files (PatientPage shell, RecordsTab, TasksTab, ChatTab, MyPage, PatientOnboarding, RecordDetail, TaskDetail, AboutSubpage, PrivacySubpage, ReviewPage import, doctor/SettingsPage, doctor/settings/AboutSubpage, PrivacyPage extract).
- Frontend new: ~7 files (`patientStore.js`, `patientFontScale.js`, `patientQueries.js`, `Card.jsx`, `TintedIconRow.jsx`, `ListSectionDivider.jsx` rename, `PrivacyContent.jsx`, optionally `version.js`).
- E2E: 3 new specs, 2 updated.

Larger than v1's estimate because of the token store and the backend additions, but each phase remains independently shippable.
