# Workflow 17 — QR invite + Patient preview

Ship gate for **患者预问诊码** — the QR generation flow where a doctor
creates a patient entry, generates a shareable pre-interview link, and
can preview the patient-side AI interview experience from within the
doctor app. Completing the preview creates a real review task.

This workflow spans SettingsPage QR subpage (`/doctor/settings/qr`),
the `PatientPreviewPage` component (`/doctor/preview/:previewId`),
and the round-trip back to review.

**Area:** `src/pages/doctor/SettingsPage.jsx` (QR subpage at line 413+),
`src/pages/doctor/DoctorPage.jsx` (`PatientPreviewPage` at line 286+),
onboarding patient entry API
(`POST /api/manage/onboarding/patient-entry` — see `api.js:734-745`),
QR token API (`POST /api/auth/qr-token` — see `api.js:713-723`),
patient interview APIs (`/api/patient/interview/{start,turn,confirm}`)
**Spec:** `frontend/web/tests/e2e/17-qr-patient-preview.spec.ts`
**Estimated runtime:** ~8 min manual / ~45 s automated

---

## Scope

**In scope**

- Navigate to QR subpage from settings (設置 → 我的二维码) or from
  MyAI page shortcut.
- QR subpage shell: `SubpageHeader` titled "患者预问诊码", back arrow,
  patient name input, "生成入口" button.
- Generate flow: enter patient name → tap "生成入口" → API call to
  `POST /api/manage/onboarding/patient-entry` → QR code renders with
  patient name, description text, "复制" and "预览" buttons.
- Empty name guard: "生成入口" button disabled when name field is empty.
- Error display: if generation fails, red error text appears.
- Copy link: "复制" button copies `portal_url` to clipboard; label
  changes to "已复制" for 1.8s.
- Preview navigation: "预览" button navigates to
  `/doctor/preview/:patientId?patient_token=...&patient_name=...`.
- `PatientPreviewPage` renders: intro card "患者端预览" with description,
  AI interview chat interface, message input, send button.
- Interview flow: patient messages are sent via
  `POST /api/patient/interview/start` then `/turn`; AI replies appear;
  progress indicator tracks collected fields (7 total).
- Summary sheet: when enough fields collected, summary sheet shows
  collected data with field-by-field status.
- Confirm & submit: confirming triggers
  `POST /api/patient/interview/confirm` → success card with "去审核"
  and task navigation buttons.
- Post-completion: "去审核" navigates to
  `/doctor/review/:recordId?source=patient_preview`.
- Exit dialog: back button during interview shows `ConfirmDialog` with
  "退出预览" title, "保存退出" cancel, "放弃重来" confirm (danger).

**Out of scope**

- Actual QR code scanning by a real device — manual/physical test only.
- Patient portal flow when accessed from a real patient device —
  covered by patient-side workflows (20-24).
- LLM response quality in the interview — eval suite, not Playwright.
- Bulk export — separate workflow.

---

## Pre-flight

Standard pre-flight. The spec registers a fresh doctor via `doctorAuth`
fixture. QR generation creates a patient entry via API, so no
pre-seeding of patients is needed.

---

## Steps

### 1. QR subpage shell

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/settings/qr` (via 设置 → 我的二维码) | Header "患者预问诊码"; back arrow top-left |
| 1.2 | Observe form section | Title "为患者生成专属入口"; description text about creating entry first; patient name `TextField` with placeholder "请输入患者姓名，例如：李阿姨" |
| 1.3 | "生成入口" button state | Button disabled (grey) when name field is empty |

### 2. Generate QR code

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Type "张三" in patient name field | "生成入口" button becomes enabled (primary green) |
| 2.2 | Tap "生成入口" | Button shows "生成中…" loading state |
| 2.3 | Wait for response | QR code SVG renders; patient name "张三" displayed below QR; description "患者扫码后将进入 AI 预问诊，确认提交后自动创建审核任务。"; two buttons: "复制" LEFT, "预览" RIGHT |
| 2.4 | Verify API call | `POST /api/manage/onboarding/patient-entry` with body `{ doctor_id, patient_name: "张三" }` |

### 3. Copy link

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap "复制" button | Button label changes to "已复制" |
| 3.2 | Wait ~2 seconds | Label reverts to "复制" |

### 4. Navigate to preview

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Tap "预览" button | URL changes to `/doctor/preview/:patientId?patient_token=...&patient_name=张三` |
| 4.2 | Preview page loads | Intro card visible: title "患者端预览"; description mentions "2 分钟左右的 AI 预问诊流程" |
| 4.3 | Chat interface | Message input field and send button visible; initial AI greeting message appears |

### 5. Interview flow in preview

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Type a symptom description and send | Message appears as patient bubble (right-aligned); AI reply appears as assistant bubble (left-aligned) |
| 5.2 | Continue conversation (2-3 turns) | Progress indicator updates (filled fields increase); more AI follow-up questions appear |
| 5.3 | When enough fields collected | Summary sheet becomes available; AI may prompt to review collected information |

### 6. Summary and confirm

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Open summary sheet | Sheet shows collected fields with labels: 主诉, 现病史, 既往史, 过敏史, 家族史, 个人史, 婚育史; filled fields have green checkmarks |
| 6.2 | Tap confirm/submit | "确认提交" triggers `POST /api/patient/interview/confirm`; success card appears |
| 6.3 | Success card | Shows patient name; "去审核" button visible; optionally "查看任务" button |

### 7. Post-completion navigation

| # | Action | Verify |
|---|--------|--------|
| 7.1 | Tap "去审核" | Navigates to `/doctor/review/:recordId?source=patient_preview&review_task_id=...` |

### 8. Exit dialog

| # | Action | Verify |
|---|--------|--------|
| 8.1 | Start a new preview; during interview, tap back | `ConfirmDialog` opens: title "退出预览"; message "要保留当前预问诊进度，还是放弃本次预览？" |
| 8.2 | "保存退出" button (LEFT, grey) | Saves progress and exits preview |
| 8.3 | "放弃重来" button (RIGHT, red/danger) | Discards and exits |

---

## Edge cases

- **Missing patient token** — if `patient_token` query param is absent
  or invalid, `PatientPreviewPage` shows error "缺少患者预览凭证，请重新
  生成预问诊入口。"
- **Empty patient name** — "生成入口" button is disabled; no API call
  fires.
- **Network failure on generate** — error text appears below the form
  in red (`qrError` state).
- **Clipboard API unavailable** — `navigator.clipboard.writeText` may
  throw in insecure contexts; "复制" silently fails (no crash).
- **Rapid double-tap on "生成入口"** — `qrLoading` disables the button
  during the API call, preventing duplicate requests.
- **Very long patient name** — QR description text wraps; name under
  QR code wraps.
- **Preview re-entry** — navigating back to `/doctor/preview/:id` with
  the same patient reuses `lastPreviewToken` from onboarding state
  (localStorage).
- **Interview LLM timeout** — if `/api/patient/interview/turn` is slow
  (>10s), the sending state persists; no timeout UI currently shown.

---

## Known issues

No open bugs as of 2026-04-11.

---

## Failure modes & debug tips

- **QR code doesn't render** — check that
  `POST /api/manage/onboarding/patient-entry` returns `portal_url`
  and `patient_id`. The `qrUrl` state drives QR rendering.
- **Preview page shows error immediately** — `parsePreviewSession`
  couldn't find a token. Verify `patient_token` query param or
  `lastPreviewToken` in localStorage onboarding state.
- **Interview won't start** — `/api/patient/interview/start` requires
  a valid patient Bearer token. The preview page uses
  `sessionConfig.token` which comes from the QR generation response.
- **"去审核" navigates to wrong page** — the path is built from
  `submitted.record_id` and `submitted.review_id`. If the confirm
  response is missing these fields, navigation breaks.
- **Onboarding state collision** — `parsePreviewSession` compares
  `lastPreviewPatientId` with current `previewId`; if they don't
  match (e.g. different patient), it won't reuse the cached token.
  This is correct behavior, not a bug.
