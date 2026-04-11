# Workflow 02 — Doctor onboarding wizard

Ship gate for the **first-run experience** — the 3-step wizard a brand-new
doctor sees right after their first login. This is the single most
important workflow for activation: if any step breaks, a new doctor's
first 5 minutes with the product fail silently.

**Area:** `src/pages/doctor/OnboardingWizard.jsx`,
`src/pages/doctor/onboardingWizardState.js`, `AddKnowledgeSubpage.jsx` (step
1 destination), `seedDemo` + `createOnboardingPatientEntry` API
**Spec:** `frontend/web/tests/e2e/02-onboarding.spec.ts`
**Estimated runtime:** ~5 min manual / ~40 s automated

---

## Scope

**In scope**

- Wizard entry from a fresh doctor with no prior knowledge items.
- Step 1 (添加一条规则): navigate to AddKnowledge, save any one of the 3
  source types (file / URL / text), return to wizard with progress recorded.
- Step 2 (看AI怎么用它): proof card with tap-to-confirm diagnosis row and
  tap-to-send AI draft reply; 下一步 unlocks only after both actions.
- Step 3 (确认并开始): completion screen + optional embedded patient
  preview sheet + "完成引导" ends the wizard and lands on `/doctor`.
- Progress persistence — reloading mid-wizard should restore the current
  step and saved-source state.
- Skip + Restart confirmation dialogs.
- Seeded demo data appears after completion (seedDemo promise).

**Out of scope**

- Full knowledge CRUD — see [05-knowledge](05-knowledge.md).
- The embedded patient interview UX — covered in the patient portal QA.
- Account registration itself — see [01-auth](01-auth.md).

---

## Pre-flight

Requires a **fresh doctor** with no wizard progress and no knowledge items.
The spec uses the `doctorAuth` fixture and clears both wizard keys from
`onboardingWizardState.js` before starting:

- `onboarding_wizard_progress:<doctorId>` — current step + saved-source state
- `onboarding_wizard_done:<doctorId>` — completion flag (`"completed" | "skipped"`)

For manual runs:

```bash
# Register a brand new doctor (unique phone each time)
curl -s -X POST http://127.0.0.1:8000/api/auth/unified/register/doctor \
  -H "Content-Type: application/json" \
  -d '{"name":"测试医生","phone":"13811110001","year_of_birth":1980,"invite_code":"WELCOME"}'
```

Then log in at `http://127.0.0.1:5173/login` and navigate to
`/doctor/onboarding?step=1`.

---

## Steps

### 1. Wizard shell

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Open `/doctor/onboarding?step=1` as a fresh doctor | Header "添加一条规则"; progress bar at 33% (步骤 1/3); bottom footer shows `下一步` (disabled), `重新开始`, `跳过引导` |
| 1.2 | Observe ContextCard | Text: "添加一条你的诊疗规则，让 AI 学会你的思维方式" |
| 1.3 | Observe three source rows | 文件上传 / 网址导入 / 手动输入 — each shows "待添加" on right and has chevron |
| 1.4 | The first unsaved row | Has green dashed outline (SpotlightHint) |

### 2. Step 1 — add one rule (manual text source)

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Tap `手动输入` row | Navigates to `/doctor/settings/knowledge/add?onboarding=1&source=text&wizard=1` |
| 2.2 | Fill in title + content (e.g. "高血压患者头痛鉴别要点" / rule body) → save | Returns to wizard with query `?saved=text&savedTitle=...&savedId=...` |
| 2.3 | URL is cleaned of `saved*` params after return | `window.location.search` no longer contains `saved=` |
| 2.4 | The text row now shows "已完成" on right | No more SpotlightHint on it |
| 2.5 | Footer `下一步` is enabled (green) | Progress text shows "已完成" |

### 3. Step 2 — proof (diagnosis confirm + reply send)

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap `下一步` from step 1 | Navigates to `?step=2`; header "看AI怎么用它"; progress bar at 66% |
| 3.2 | Observe RuleEchoCard | Shows "你刚添加的规则" header + the rule title/body just saved |
| 3.3 | Observe patient strip | "张秀兰 · 72岁" + "头痛头晕3天 · 高血压10年" |
| 3.4 | Observe diagnosis rows | Row 1 (`高血压脑病/高血压急症`) has SpotlightHint + 引用 badge; rows 2-3 dimmed (opacity 0.5) |
| 3.5 | Tap row 1 | Row shows green ✓ circle; dashed outline disappears |
| 3.6 | Observe AI draft reply bubble | "AI起草回复 · 待你确认" header; highlighted sentence visible; "引用:" badge; 修改 / 确认发送 buttons |
| 3.7 | Tap `确认发送 ›` | Bubble swaps to sent-style (green bg, right-aligned) with final text |
| 3.8 | Footer `下一步` enables only after both 3.5 and 3.7 | Tapping 下一步 advances to `?step=3` |

### 4. Step 3 — complete

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Land on step 3 | Header "确认并开始"; ✓ icon; title "设置完成"; subtitle about trying patient flow |
| 4.2 | Observe optional patient preview card | "可选：体验患者端预问诊" card with "体验患者端 →" button |
| 4.3 | Tap `体验患者端 →` (once `ready` state true) | Bottom sheet opens "患者预问诊体验"; embedded InterviewPage renders with AI greeting |
| 4.4 | Close sheet (tap close or outside) | Returns to step 3 without advancing |
| 4.5 | Tap `完成引导` | `markWizardDone(doctorId, "completed")` called; navigates to `/doctor`; `seedDemo` fires in background; 我的AI tab visible |
| 4.6 | Reload after completion | Wizard is NOT re-shown (done flag persisted); 我的AI tab shows seeded demo patients after seed completes |

### 5. Persistence & skip/restart

| # | Action | Verify |
|---|--------|--------|
| 5.1 | On step 2, reload the page (Cmd-R) | Lands back on step 2; saved-source state still shows the rule saved in step 1 |
| 5.2 | Tap `跳过引导` footer button | Confirm dialog: title "跳过引导？"; cancel LEFT grey / confirm RIGHT green |
| 5.3 | Confirm skip | `markWizardDone(doctorId, "skipped")`; navigates to `/doctor`; wizard not re-shown on reload |
| 5.4 | From step 2, tap `重新开始` | Confirm dialog: "重新开始？" / 当前进度将被清除 |
| 5.5 | Confirm restart | Returns to step 1; saved sources cleared; previously saved knowledge item still exists in DB (the restart only clears local wizard progress) |

---

## Edge cases

- **Add-knowledge cancelled** — if doctor taps a source row and backs out
  without saving, wizard returns with no `?saved` param; the source row
  stays "待添加"; SpotlightHint stays visible. No error toast.
- **Saved rule ID collision on re-runs** — backend may 409 on duplicate
  titles. The wizard should tolerate that (skip into saved-state) rather
  than silently fail.
- **`ensureOnboardingExamples` API failure** — per the code, the effect
  `.catch(() => setCanAdvance(true))`; even if the proof-data fetch fails,
  the doctor can still advance. Verify manually that step 2 is reachable
  when the API is offline.
- **Network partition during `seedDemo` at 4.5** — main navigation should
  still succeed; seeded patients just won't appear until the next successful
  fetch.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues. Onboarding-specific
entries: none as of 2026-04-11.

When the persona-phase1 branch (`feat/persona-phase1`) lands, the wizard
may need a new step for persona rule authoring. Revisit this plan at
merge time.

---

## Failure modes & debug tips

- **Step 1.1 doesn't show the wizard** — `getWizardProgress(doctorId)`
  may already report `done`. Clear with:
  ```js
  localStorage.removeItem(`onboarding_wizard_done:${doctorId}`);
  localStorage.removeItem(`onboarding_wizard_progress:${doctorId}`);
  ```
- **Step 2.5 `下一步` never enables** — check `savedSources.length >= 1`
  condition in `Step1Content`. Likely the `?saved=text` param never got
  written — verify AddKnowledgeSubpage fires `navigate(..., {saved:})` on
  success.
- **Step 3.7 `确认发送` click does nothing** — spec is tapping the Text
  node; the click handler is on the Typography element. Use `{force:true}`
  or target by role. The MD step says to tap the text — make sure the
  spec selector matches.
- **Step 4.3 sheet is empty / crashes** — `usePatientApi` requires
  `PatientApiProvider`. The lazy mount (`showInterview && interviewToken`)
  is the existing fix. If the sheet is blank, check `interviewToken` in
  progress state.
