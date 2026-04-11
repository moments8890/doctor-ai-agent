# Patient App MVP — Design Spec (v2, post-Codex review)

**Date:** 2026-04-11
**Goal:** Ship-ready patient app with bug fixes + UI parity + essential MVP features.
**Approach:** Experience-First — fix existing bugs while adding features, touch files once.
**Channel:** WeChat Mini Program (primary, wraps web) + standalone web portal.

## Context

The patient app has a solid foundation: 4-tab shell, AI chat with polling, pre-visit
interview, records, tasks, profile, voice input, 3 login flows. Theme token adoption
is ~95%. The doctor app recently added AI persona (phase 1).

This spec covers the gap between "working prototype" and "ship-ready product."

## Codex Review Summary

Codex found 20 issues in v1. Key changes:
- **Chat has bugs that must be fixed first**: fake AI reply, message deduplication, stale doctor name
- **Read receipts dropped from MVP**: `read_at` is patient-side only (marks patient's reads), NOT doctor-read tracking. Need new backend mechanism — deferred.
- **Onboarding simplified**: single dismissible sheet, not 3-screen wizard
- **SettingsRow extraction dropped**: YAGNI (only one consumer)
- **Font scale**: device-level setting shared between doctor/patient (same SPA, same global multiplier)
- **localStorage keys scoped**: patient_id prefix for patient-specific state
- **RecordsTab existing bug**: `diagnosis_status` vs `status` field mismatch — fix while cleaning up

## Design Decisions

- **AI identity:** Hybrid — AI messages show "{doctorName}的AI助手" with SmartToyOutlinedIcon badge
- **Font scale:** Device-level (not per-user) — doctor and patient share the same SPA global multiplier
- **localStorage scoping:** Patient-specific keys use `patient_{patientId}_` prefix
- **Health education:** Deferred to post-MVP
- **Push notifications:** Deferred — polling adequate for MVP
- **Read receipts:** Deferred — needs doctor-side read tracking mechanism
- **Symptom tracking:** Deferred

## Work Items (Experience-First Sequence)

### Phase 0: Fix Chat Bugs (prerequisite for all chat work)

**Files:** `ChatTab.jsx`

#### 0A. Remove fake AI reply

**Bug:** After patient sends a message, ChatTab appends a fake reply: `data.reply || "收到您的消息。"` (line ~156). The backend `POST /api/patient/chat` returns `reply=""` and `ai_handled=false` — it schedules a doctor draft, not a patient-visible reply.

**Fix:** Remove the fake assistant message append. Patient should only see their own message immediately (optimistic), then real replies when they arrive via polling.

#### 0B. Fix message deduplication

**Bug:** Optimistic send appends a local message with no `id`. Polling later appends the saved DB message because dedupe only checks `id` match (line ~105/161). Result: duplicate patient messages.

**Fix:** After successful `POST /api/patient/chat`, use the returned message data (which has an `id`) to replace the optimistic message. Or: tag optimistic messages with a temp client ID and remove them when the real message arrives via polling.

#### 0C. Fix stale doctor name in welcome

**Bug:** Welcome message initializes from `doctorName` on first render (line ~84). If `/api/patient/me` fills doctor info later (async), the welcome stays stale.

**Fix:** Derive welcome text from a reactive state (the localStorage values are set by PatientPage after `/me` completes). Use a useEffect or compute from current state.

### Phase 1: Chat Persona + Chat Polish

**Files:** `ChatTab.jsx`, `PatientPage.jsx`, `patient/constants.jsx`, `chat.py` (backend)

#### 1A. Backend: Expose ai_handled in patient chat API

**File:** `src/channels/web/patient_portal/chat.py`

Add `ai_handled: Optional[bool] = None` to `ChatMessageOut` schema (line ~54-61).
Add `ai_handled=msg.ai_handled` to `_msg_to_out()` (line ~75-83).

Also: add backend filter to exclude `source="ai"` with `ai_handled=False` from patient-visible messages (these are drafts awaiting doctor review). Currently no filter exists (line ~174).

#### 1B. Hybrid AI persona attribution in chat bubbles

Current: All AI messages show generic `MsgAvatar` robot.

Changes to ChatTab.jsx:
- `source: "doctor"` → `NameAvatar` with doctor's name initial + caption "{doctorName}"
- `source: "ai"` with `ai_handled: true` → `NameAvatar` with doctor initial + small `SmartToyOutlinedIcon` overlay (bottom-right, 14px, `COLOR.text4`). Caption: "{doctorName}的AI助手"
- Fallback (no doctor name available): show current `MsgAvatar` with "AI健康助手"

Doctor name source: `localStorage.getItem("patient_portal_doctor_name")` — already set by PatientPage after `/api/patient/me`.

#### 1C. Chat header with doctor info

**File:** `PatientPage.jsx` (NOT ChatTab — PatientPage owns the header, line ~147)

When active tab is "chat":
- Header title: "{doctorName}" (instead of "消息")
- Subtitle: doctor specialty (from localStorage `patient_portal_doctor_specialty` — need to add this to the `/me` storage logic if not already saved)

#### 1D. Chat UI token cleanup

While touching ChatTab.jsx:
- Extract repeated bubble border-radius pattern (lines ~251/259/265) to constant: `BUBBLE_RADIUS_LEFT = \`${RADIUS.sm} ${RADIUS.sm} ${RADIUS.sm} 0\``
- Line ~286: `borderRadius: 2` → `RADIUS.sm`
- Line ~63: Inline box-shadow — remove or extract

### Phase 2: Onboarding + MyPage Polish

**Files:** `PatientPage.jsx`, `MyPage.jsx`, new `PatientOnboarding.jsx`

#### 2A. Patient onboarding (simplified)

**Trigger:** When patient enters app and `localStorage["patient_{patientId}_onboarding_done"]` is not set. Scoped to patient_id so shared devices work.

**Design:** Single full-screen dismissible sheet (NOT a multi-screen wizard — Codex correctly flagged overbuilding):
- Doctor avatar (NameAvatar) + name + specialty
- "我是{doctorName}的AI健康助手，我会帮助医生为你提供更好的随访服务"
- 3 bullet points with IconBadge: 随时咨询, 健康档案, 任务提醒
- "开始使用" `AppButton` (primary) → set localStorage flag, dismiss
- Skip link at top-right

Components: NameAvatar, IconBadge, AppButton, SheetDialog (full-screen mode). No new shared components.

#### 2B. MyPage additions

Keep existing structure. Changes:
- Add "重新查看引导" row → clears onboarding flag, shows onboarding sheet
- Add font scale row → toggles device-level font scale (see Phase 3)
- Fix: `MyPage` receives `doctorId` prop but doesn't use it — clean up
- Keep inline SettingsRow (only one consumer, extraction is YAGNI)

#### 2C. Logout cleanup

**File:** `PatientPage.jsx` (line ~117)

When patient logs out, also clear patient-scoped localStorage keys:
- `patient_{patientId}_onboarding_done`
- (font scale stays — it's device-level, not account-level)

### Phase 3: Font Scale

**Files:** `PatientPage.jsx`, `MyPage.jsx`, `main.jsx`

#### 3A. Device-level font scale

The font scale system is a global multiplier in theme.js. Doctor and patient routes share the same SPA root. Rather than creating a parallel patient store (which would fight over the same global):

- **Reuse the existing `useFontScaleStore`** — it already works
- The localStorage key `"doctor-font-scale"` is a misnomer but works fine for device-level setting
- When patient app renders, the existing font scale applies automatically (proxy-based TYPE already works)
- The patient just needs a UI to change it

Add to MyPage: A font scale picker matching doctor's SettingsListSubpage pattern. Call `useFontScaleStore.getState().setFontScale(level)` + `triggerFontScaleRerender()`. No server sync for patient (fire-and-forget localStorage only).

### Phase 4: Cleanup (fix while touching)

**Files:** `InterviewPage.jsx`, `RecordsTab.jsx`

#### 4A. InterviewPage cleanup

- Line ~138: native `alert()` → `ConfirmDialog`
- Line ~179: `borderRadius: 3` → `RADIUS.sm`
- Lines ~232-247 / ~258-272: Extract duplicate chip render to inline helper
- Use `SmartToyOutlinedIcon` if any AI icon reference exists (per MUI icon policy)

#### 4B. RecordsTab cleanup + bug fix

- **Bug fix:** UI reads `rec.diagnosis_status` (line ~84, ~232) but patient API returns `status`. Either:
  - Fix backend to return `diagnosis_status`, or
  - Fix frontend to read `status` (check which name the backend actually uses)
- Lines 33-34: Remove duplicate `_DL` / `_DC` maps → import from constants.jsx
- Lines 36-41: Remove `RECORD_TYPE_ICON_COLOR` → use RECORD_TYPE_BADGE
- Line 22: Remove unused `DateAvatar` import

### Phase 5: Playwright Patient Workflow Tests

**Files:** `tests/e2e/fixtures/`, new test specs

#### 5A. Patient auth fixture

Add to `fixtures/doctor-auth.ts`:
- `authenticatePatientPage(page, patient)` — sets localStorage keys:
  - `patient_portal_token`, `patient_portal_name`, `patient_portal_doctor_id`, `patient_portal_doctor_name`
- Export `patientPage` fixture that uses `authenticatePatientPage`
- Note: E2E_API_BASE_URL defaults to port 8000 in fixtures — tests should use port 8001 per repo rules (env var override)

#### 5B. Seed helpers needed

Add to `fixtures/seed.ts`:
- `createPatientTask(request, doctor, patientId, opts)` — creates a patient-targeted task via doctor API
- `sendDoctorReply(request, doctor, patientId, text)` — sends a doctor message visible to patient (need to check which API creates doctor→patient messages)

#### 5C. Test specs

**`20-patient-auth.spec.ts`** — Patient login smoke
- Auth fixture seeds patient → page loads
- Bottom nav visible with 4 tabs (消息, 健康档案, 任务, 我)
- Default tab is chat

**`21-patient-chat.spec.ts`** — Chat workflow
- Send a message, verify it appears (single bubble, no duplicate)
- Seed a doctor-sent message via API → verify it shows with doctor attribution
- Verify no fake "收到您的消息" reply appears

**`22-patient-records.spec.ts`** — Records workflow
- Seed a completed interview → verify record appears in list
- Navigate to record detail → verify fields visible
- Filter tabs work

**`23-patient-tasks.spec.ts`** — Task workflow (requires seed helper)
- Seed patient task → verify in pending list
- Complete → verify in completed
- Uncomplete → verify back in pending

**`24-patient-onboarding.spec.ts`** — Onboarding flow
- Fresh patient (no localStorage flag) → onboarding sheet appears
- Tap "开始使用" → dismissed, chat tab visible
- Reload → onboarding does NOT reappear
- MyPage "重新查看引导" → onboarding reappears

## Files Changed Summary

| File | Change Level | Phase |
|------|-------------|-------|
| `patient/ChatTab.jsx` | High — fix bugs + persona attribution + token cleanup | 0, 1 |
| `patient/PatientPage.jsx` | Medium — chat header, onboarding gate, logout cleanup | 1, 2 |
| `patient/MyPage.jsx` | Medium — font scale, onboarding replay, prop cleanup | 2, 3 |
| `patient/PatientOnboarding.jsx` | New — single-sheet onboarding | 2 |
| `patient/constants.jsx` | Low — add onboarding constants | 2 |
| `patient/InterviewPage.jsx` | Low — token/dialog cleanup | 4 |
| `patient/RecordsTab.jsx` | Low — bug fix + dedup constants | 4 |
| `theme.js` | Low — add BUBBLE_RADIUS constants | 1 |
| `src/channels/web/patient_portal/chat.py` | Medium — expose ai_handled, filter drafts | 1 |
| `tests/e2e/fixtures/doctor-auth.ts` | Medium — add patientPage fixture | 5 |
| `tests/e2e/fixtures/seed.ts` | Medium — add task + reply seed helpers | 5 |
| `tests/e2e/20-patient-auth.spec.ts` | New | 5 |
| `tests/e2e/21-patient-chat.spec.ts` | New | 5 |
| `tests/e2e/22-patient-records.spec.ts` | New | 5 |
| `tests/e2e/23-patient-tasks.spec.ts` | New | 5 |
| `tests/e2e/24-patient-onboarding.spec.ts` | New | 5 |

## Non-goals

- Push notifications (polling adequate for MVP)
- Read receipts (needs new doctor-side tracking — deferred)
- Symptom tracking / health timeline (post-MVP)
- Health education content system (chat quick actions cover basic Q&A)
- Desktop layout for patient (mobile-only)
- Multi-doctor support (patient scoped to one doctor)
- Dark mode
- Medication adherence tracking
- SettingsRow extraction (YAGNI — only one consumer)
