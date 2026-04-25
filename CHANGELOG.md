# Changelog

All notable changes to doctor-ai-agent are documented here.

## [Unreleased] — Patient app · doctor-UI parity (2026-04-24)

Brought the v2 patient portal to visual + structural parity with the v2 doctor app. 24-task plan, 30 commits, 4 Codex review rounds on the spec, two-stage subagent review per task.

Plan: `docs/superpowers/plans/2026-04-24-patient-app-doctor-ui-parity.md` · Spec (v3.1): `docs/superpowers/specs/2026-04-24-patient-app-doctor-ui-parity-design.md`

### Added
- Patient task per-id endpoint: `GET /api/patient/tasks/{id}` with ownership isolation (404 for missing/wrong-patient/non-patient-targeted) — `4d6c1028`
- `completed_at` and `source_record_id` exposed on `PatientTaskOut` (derived from `task.record_id`, NOT `task.source_id`) — `e3ff99c6`
- Patient zustand auth store (`store/patientStore.js`) with atomic `loginWithIdentity` / partial `mergeProfile` (never touches token) / `clearAuth` + one-shot legacy-localStorage migration — `e12dffb2 / 83da69bc`
- Patient React Query hooks (`lib/patientQueries.js`): 5 queries + 2 mutations; `initialDataUpdatedAt` inheritance for instant detail render — `ec719ef7 / 82fd8278`
- Shared v2 primitives: `Card`, `TintedIconRow` extracted from doctor `SettingsPage` locals — `7051445d / b28a5e02`
- Patient-local font scale util (`v2/lib/patientFontScale.js`) — preserves `large` default + 3-tier 标准/大/特大 selector — `dd4c7a06`
- Patient subpages with real card-pattern content: `PatientRecordDetailPage` (against actual `PatientRecordDetailOut` fields, no invented names), `PatientTaskDetailPage` (with complete/undo + per-id endpoint), `PatientAboutSubpage`, `PatientPrivacySubpage` — `3a7fff36 / caab0f62 / 76ce99b3 / 261bf904`
- 3 new E2E specs: `25-patient-record-detail`, `26-patient-task-detail`, `27-patient-my-subpages` (9 tests) — `00d83380`
- Patient app smoke gallery: spec + 10 captured surfaces in `public/wiki/smoke-shots/patient-*.png` + wiki gallery section — `e1a59fcf`
- Shared `PrivacyContent` component consumed by both `/privacy` standalone route and `/patient/profile/privacy` subpage — `261bf904`
- Shared `APP_VERSION` source at `v2/version.js` (consumed by both doctor + patient about subpages) — `76ce99b3`
- `lint-ui.sh` guard against re-introducing the deprecated `SectionHeader` import — `fea70a5c`

### Changed
- Patient identity now reads from `usePatientStore` (scoped selectors for perf) — replaces 4 inline `useState` calls + per-key localStorage scheme — `7e71c646 / 207cc634`
- Patient `LoginPage` writes through `loginWithIdentity` instead of legacy 4-key localStorage (closes a redirect-loop that the store-only migration would have caused) — `272bf741`
- `RecordsTab`, `TasksTab`, `PatientPage` shell consume React Query hooks; ChatTab intentionally NOT migrated (preserves bespoke 10s/60s polling + optimistic dedupe + unread badge logic) — `408bd6dd / ab900667`
- `MyPage`: full rewrite mirroring doctor `SettingsPage` card pattern (profile + 我的医生 + 通用 + danger logout + security footer) — `f9524a8e`
- `RecordsTab`: gray `pageContainer` + per-record `Card` + `Ellipsis rows={1}` overflow + `PullToRefresh`; timeline view simplified (month section header, dropped rail+dot per CLAUDE.md card pattern) — `823df900`
- `TasksTab`: `Card` per task + visible 36px tinted-circle tap-target prefix (NO SwipeAction — patient audience needs visible affordance) + `PullToRefresh` — `2ef3a014`
- `ChatTab` QuickActions row → `Card` + 2 `TintedIconRow` (新问诊 / 查看病历); polling untouched — `b19c0611`
- Doctor `SettingsPage` and `AboutSubpage` migrated to consume shared `Card` / `TintedIconRow` (deletes local copies, visual no-op) — `85bc054f`
- Renamed `v2/components/SectionHeader.jsx` → `ListSectionDivider.jsx` (cleaned up SectionHeader naming collision; symbol rename + alias removal completed in Phase 5) — `6fb7d1c3 / 2bec0363 / fea70a5c`

### Fixed
- Patient task detail no longer shows false-negative "任务不存在" on hard-refresh (now uses per-id endpoint, not cache-only)
- `mergeProfile` cannot wipe token on `/patient/me` refresh (token deliberately not in the merge payload — Codex review v2→v3)
- Task detail uses correct field semantics: `task_type === "follow_up"` (not `source_type`), `status === "completed"` (not `"done"`), `source_record_id` from `task.record_id` (Codex review v2→v3)
- Record detail uses real `PatientRecordDetailOut` fields: `structured.present_illness` (not invented `history_of_present_illness`), no `differential` / `raw_content` / `medication_history` (Codex review v1→v2)
- TasksTab optimistic-override flicker eliminated: overrides cleared on `dataUpdatedAt` change (atomic with canonical refetch), not on mutation `onSuccess` (Task 3.3 fix)
- Drop dead `ChevronRightIcon` import in doctor `SettingsPage` after primitive extraction — `c9ca8fbf`
- Drop dead `FONT` import + `data.doctor_name` (never present on unified-login response) in `LoginPage` patient branch — `207cc634`

### Notes
- Patient font scale stays local-only (no doctor backend cross-contamination); default `large` (1.15×) preserved; 3-tier Popup preserved (NOT downgraded to binary Switch — patients need 特大).
- VERSION not bumped in this entry — release packaging is a separate decision.

## [2.0.0.0] - 2026-04-09

### Added
- New doctor registration now auto-preseeds demo knowledge and patients on signup — doctors see a populated 我的AI on first visit without completing the onboarding wizard
- WeChat mini app auth hardened: JWT payload decoded on frontend to get canonical doctor identity, eliminating the postMessage timing race that showed the wrong doctor's name after login/register
- Logout in mini app now redirects natively to the login page, ensuring wx.storage is cleared and a fresh WebView is created for subsequent logins
- React Query cache cleared on logout to prevent stale data flash for the next user

### Fixed
- Preseed API call in onboarding wizard was missing the Authorization header — silently 401'd in production, leaving new doctors with empty knowledge library
- Wrong doctor shown after registration: WeChat's postMessage delivers async relative to redirectTo, so app.globalData could be stale when doctor.js.onLoad fires; fix reads doctor_id and name from JWT payload instead of URL params
- Mini app logout flow broken: clicking logout did SPA navigation within the same WebView, queuing the logout postMessage but never delivering it; fix uses wx.miniProgram.redirectTo to navigate natively
- Date display showing -1天前 due to mixed UTC/local timestamp handling
- Duplicate AI suggestions on re-trigger of diagnosis
- Phantom KB citation IDs leaking into suggestion detail
- AI persona card not navigable until content was loaded
- Button order inconsistencies in various dialogs (cancel left, confirm right, danger red)
- Patient search, logout history, greeting text issues (QA pass)

### Changed
- Diagnosis pipeline uses has_suggestions flag and module-level DoctorKnowledgeItem import for cleaner initialization
- LLM clients isolated from system proxy (trust_env=False) for reliable provider connections
- Persona knowledge item pinned as first entry in MyAI knowledge preview

## [1.2.0] - 2026-03-28

Initial tracked release. Medical-style UI, WeChat mini program channel, knowledge base with URL/photo import, review queue redesign, component unification (IconBadge, ActionRow, KnowledgeCard, MessageItem).
