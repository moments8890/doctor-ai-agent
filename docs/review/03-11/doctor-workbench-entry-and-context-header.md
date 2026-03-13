# Goal
Turn the Web doctor experience into a composer-led workbench with one visible working context, so the default UI matches the UX contract in [`docs/review/03-11/minimal-doctor-assistant-ux-principles.md`](minimal-doctor-assistant-ux-principles.md).

# Affected files
- docs/review/03-11/doctor-workbench-entry-and-context-header.md
- frontend/src/App.jsx
- frontend/src/pages/DoctorPage.jsx
- frontend/src/pages/doctor/ChatSection.jsx
- frontend/src/pages/doctor/WorkingContextHeader.jsx (new)
- frontend/src/store/doctorStore.js
- frontend/src/api.js
- routers/ui/__init__.py
- services/session.py

# Steps

## 1. Define the doctor-facing working-context contract for Web. ✅
- The header shows: current patient (or "暂无当前患者"), pending draft status, and the next required action when blocked.
- Uses plain doctor-facing labels: "张三", "草稿：王五", "请确认或撤销待审病历草稿".
- No backend terms like pending IDs or router state exposed.

## 2. Add a small backend context endpoint. ✅
- Added `GET /api/manage/working-context` in `routers/ui/__init__.py`.
- Returns `{ current_patient, pending_draft, blocked_write, next_step }` in a single lightweight call.
- Combines session current_patient, pending_record lookup (with expiry validation), blocked-write continuation state, and next-step logic (pending draft → confirm prompt; blocked_write → continuation prompt; pending_create → info prompt; no patient → start prompt).

## 3. Add a shared working-context state layer in the frontend. ✅
- Added `getWorkingContext(doctorId)` API call in `frontend/src/api.js`.
- Added `workingContext` state + 15-second polling in `useDoctorPageState` hook inside `DoctorPage.jsx`.
- Both `DoctorPage` layout and future components can read the same context state.

## 4. Make the default doctor route composer-first. ✅
- `/doctor` and `/doctor/chat` default to the AI chat composer (already was `section || "chat"`).
- Removed `HomeSection` from `SectionContent` rendering — the "home" dashboard is no longer part of primary navigation.
- NAV in `constants.jsx` already has chat first: AI 助手 → 患者 → 任务 → 设置.

## 5. Add a visible working-context header above the main composer flow. ✅
- Created `WorkingContextHeader.jsx` component showing:
  - Current patient chip (green) or "暂无当前患者" text
  - Pending draft chip (amber) with patient name
  - Next-step guidance text when workflow is blocked
- Rendered between the error alert and pending banner in `DoctorPage`.
- Responsive: adapts padding and sizing for mobile vs desktop.

## 6. Keep admin and management surfaces secondary. ✅
- Patient lists, tasks, and settings remain reachable via sidebar/bottom nav.
- HomeSection removed from primary route — no module picker as first screen.
- First screen is the AI chat composer with working context header.

## 7. Add targeted verification. ✅
- Backend: 4 unit tests in `tests/test_working_context.py`:
  - `test_working_context_no_state` — no patient, no draft
  - `test_working_context_with_patient` — patient set
  - `test_working_context_with_pending_draft` — pending draft with expiry
  - `test_working_context_pending_create` — pending patient creation
- Frontend: builds successfully with `npm run build`.
- 937 unit tests passing (no regressions from this work).

# Risks / open questions
- ~~The current frontend already defaults to `/doctor`, but the page still spreads attention across sections; route cleanup alone will not satisfy the UX contract.~~ Resolved: HomeSection removed from primary nav.
- ~~There may not be one existing backend endpoint that cleanly exposes current patient plus waiting-for-next-step state.~~ Resolved: `/api/manage/working-context` endpoint added.
- Web and WeChat wording should stay aligned, or the shared mental model will drift again. The working-context endpoint uses the same session state and next-step language patterns as WeChat.
- Working context header polls every 15 seconds. If latency or battery concerns arise on mobile, consider event-driven updates (e.g. refresh after chat response) instead.
- HomeSection still exists as a component but is no longer rendered in the primary flow. It could be exposed as a "dashboard" route if needed.
