# Workflow 14 — Persona onboarding (first-time style setup)

Ship gate for the **初始化风格** wizard — the first-time persona setup
flow where a doctor picks response styles from scenario-based options.
After completing all scenarios, a summary of extracted rules is shown for
confirmation. This is the primary way new doctors establish their AI
persona before any patient interactions.

This workflow targets `PersonaOnboardingSubpage.jsx`, reachable from the
persona settings tree at `/doctor/settings/persona/onboarding`.

**Area:** `src/pages/doctor/subpages/PersonaOnboardingSubpage.jsx`,
onboarding API (`GET /api/manage/persona/onboarding/scenarios?doctor_id=`,
`POST /api/manage/persona/onboarding/complete?doctor_id=` with
`{ picks: [{ scenario_id, option_id }] }` body — see
`frontend/web/src/api.js:690-701`), `useDoctorStore`, `QK.persona(doctorId)`
cache key
**Spec:** `frontend/web/tests/e2e/14-persona-onboarding.spec.ts`
**Estimated runtime:** ~4 min manual / ~25 s automated

---

## Scope

**In scope**

- Loading state (CircularProgress spinner) while scenarios fetch.
- Error state when scenario fetch fails ("加载失败，请重试").
- Progress bar across scenario steps (width = `step / total * 100%`).
- Title shows current position, e.g. "1 / 3".
- Scenario card: title, patient_info, patient_message in surfaceAlt box.
- Option cards: tappable, highlight with primary border + primaryLight bg
  on selection.
- Auto-advance: picking an option on scenarios 1..(N-1) immediately
  advances to the next scenario.
- Last scenario pick: transitions to summary step.
- Summary step: header "确认风格"; rules listed with CheckCircle icons,
  grouped by field label.
- "返回修改" button (secondary/left) goes back to last scenario.
- "确认开始" button (primary/right) calls `completeOnboarding` API.
- Saving state: button shows "保存中..." with loading spinner.
- Save error: "保存失败，请重试" text shown.
- On success: query invalidation for `QK.persona(doctorId)` and
  `onComplete` or `onBack` callback fires.
- Back navigation: step 0 → `onBack`; step N → step N-1.

**Out of scope**

- Persona rules CRUD after onboarding — covered in
  [04-persona-rules.md](04-persona-rules.md).
- Doctor registration onboarding wizard — covered in
  [02-onboarding.md](02-onboarding.md).

---

## Pre-flight

Shared pre-flight lives in [`README.md`](README.md#shared-pre-flight).
This workflow additionally needs:

- The backend `/api/manage/persona/onboarding/scenarios` endpoint must
  return at least 2 scenarios with 2+ options each.
- No pre-existing persona rules needed (this is a first-time flow).

---

## Steps

### 1. Loading and error states

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/settings/persona/onboarding` | `PageSkeleton` header "初始化风格"; CircularProgress spinner visible while scenarios load |
| 1.2 | (Network error variant) Intercept scenarios request to return 500 | Spinner replaced by "加载失败，请重试" in danger color |

### 2. Scenario step navigation

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Scenarios load successfully | Title shows "1 / N" (N = total scenarios); progress bar at ~0% width; scenario title, patient_info, patient_message all visible |
| 2.2 | Instruction text visible | "选择你更习惯的回复方式：" shown below patient message |
| 2.3 | Option cards render | At least 2 option cards with readable text; none pre-selected |
| 2.4 | Tap an option | Card highlights (primary border + light bg) |
| 2.5 | Auto-advance triggers | After picking, view jumps to scenario 2; title updates to "2 / N"; progress bar width increases |
| 2.6 | Back arrow on step 2 | Returns to step 1; previous pick still highlighted |

### 3. Summary step

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Pick options on all remaining scenarios | After last pick, view transitions to summary; header becomes "确认风格" |
| 3.2 | Summary content | Intro text "根据你的选择，AI将按以下偏好回复患者："; each extracted rule shows CheckCircleOutlined icon (green), field label (caption text4), and rule text |
| 3.3 | Footer buttons | "返回修改" (secondary/left) and "确认开始" (primary/right) in equal-width 2-column grid |
| 3.4 | Tap "返回修改" | Returns to last scenario step; previous picks preserved |

### 4. Confirm and save

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Return to summary (re-pick if needed) and tap "确认开始" | Button shows "保存中…" loading state; "返回修改" disabled |
| 4.2 | API call succeeds | `POST /api/manage/persona/onboarding/complete` fires with `{ picks: [...] }`; page navigates away (onComplete/onBack) |
| 4.3 | Navigate to `/doctor/settings/persona` | Persona rules reflect the choices made during onboarding |

### 5. Save error handling

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Intercept complete endpoint to return 500, tap "确认开始" | Loading appears then resets; "保存失败，请重试" text visible in danger color; buttons re-enabled |
| 5.2 | Remove intercept, tap "确认开始" again | Saves successfully this time |

---

## Edge cases

- **Empty extracted rules** — if no traits map from picks, summary shows
  "未检测到偏好，请返回重新选择" fallback text.
- **Double-tap "确认开始"** — `confirmingRef` guard prevents duplicate
  API calls.
- **Rapid option switching** — only the last pick per scenario is
  recorded in the `picks` map.
- **Back from summary, change pick, re-advance** — the summary
  recomputes traits from the updated picks, not stale state.
- **Scenario with unknown field in traits** — field label falls back to
  the raw key string (no crash).

---

## Known issues

No open bugs as of 2026-04-11. This page is new on the
`feat/persona-phase1` branch.

---

## Failure modes & debug tips

- **Spinner never resolves** — verify
  `GET /api/manage/persona/onboarding/scenarios?doctor_id=` returns
  `{ scenarios: [...] }`. The component reads `data.scenarios`.
- **Options don't highlight on tap** — check that `onClick` calls
  `handlePick(scenarioId, optionId)` and `picks` state updates.
- **Summary shows no rules** — the traits extraction loops over
  `option.traits`. If the API returns options without `traits`, the
  summary will be empty. Verify API shape.
- **"确认开始" does nothing** — the `confirmingRef.current` guard may be
  stuck true from a prior failed attempt. Check that `finally` block
  resets it.
- **Query cache not invalidated** — `completeOnboarding` success must
  call `queryClient.invalidateQueries({ queryKey: QK.persona(doctorId) })`.
