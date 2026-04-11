# Workflow 03 — My AI tab overview

Ship gate for the **我的AI** tab — the doctor's home screen and the primary
dashboard showing the AI's identity, learned knowledge, quick actions,
and recent activity. Every doctor lands here after login, so any
regression is immediately user-visible.

**Area:** `src/pages/doctor/MyAIPage.jsx`, persona + knowledge + activity
React Query hooks in `src/lib/doctorQueries.js`
**Spec:** `frontend/web/tests/e2e/03-my-ai-overview.spec.ts`
**Estimated runtime:** ~4 min manual / ~20 s automated

---

## Scope

**In scope**

- Header + AI identity card (AI name, knowledge count subtitle, settings icon).
- 3-stat row: `7天引用` / `待确认` / `今日处理` — tap behaviors.
- CTA row: `编辑人设` / `添加知识` buttons.
- 快捷入口 section: `新建病历`, `患者预问诊码`, optional `重新体验引导`.
- 我的AI人设 card: preview text, edit count, tap → PersonaSubpage.
- 我的知识库 card: up to 3 items, `全部 N 条 ›` link, tap → KnowledgeSubpage.
- 最近由AI处理 section: up to 3 items with badge (紧急 / AI已起草回复 /
  AI诊断建议 / 知识库引用 / 待办任务), tap navigation by item type.
- Empty state: zero knowledge + zero activity render CTAs instead of raw
  "暂无…" text.
- Pull-to-refresh triggers data refetch.
- Disclaimer banner "本服务为AI生成内容…" always visible.

**Out of scope**

- Persona editing — [04-persona-rules](04-persona-rules.md).
- Knowledge editing — [05-knowledge](05-knowledge.md).
- Task / review actions from activity — [08](08-review-diagnosis.md) / [10](10-tasks.md).
- Onboarding wizard re-entry UX — covered under [02](02-onboarding.md)
  (the "重新体验引导" row just routes there).

---

## Pre-flight

Uses `doctorAuth` + `seed.ts` fixtures. The spec seeds:

1. 2–3 knowledge rules (varying `source`) via `seed.addKnowledgeText`.
2. 1 completed patient interview (→ creates a pending review) via
   `seed.completePatientInterview`.
3. 1 persona rule via `seed.addPersonaRule` so the persona card is
   non-empty.

These give non-zero stats and populate all three list sections. A separate
test case runs with an empty doctor to verify the empty states.

---

## Steps

### 1. Page shell

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Tap 我的AI bottom-nav tab (or navigate to `/doctor/my-ai`) | Header "我的AI" visible; no back arrow; disclaimer banner "本服务为AI生成内容，结果仅供参考" rendered |
| 1.2 | Check console | Zero JS errors on mount |

### 2. Hero identity card

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Inspect AI avatar | Square-rounded, `COLOR.primary` bg, "AI" text inside |
| 2.2 | Inspect AI name line | Reads `${doctorName} 的 AI` — no duplicated "医生" suffix (BUG-02 gate) |
| 2.3 | Inspect subtitle | `已学会 N 条知识` where N = seeded knowledge count; when N=0 reads `尚未添加知识` |
| 2.4 | Tap settings icon (top-right) | Navigates to `/doctor/settings` |
| 2.5 | 3-stat row | Three columns: `7天引用`, `待确认`, `今日处理`; values are integers (not NaN, not null); dividers between columns |
| 2.6 | Tap `待确认` column | Navigates to `/doctor/review?tab=pending` |
| 2.7 | Tap `今日处理` column | Navigates to `/doctor/review?tab=completed` |

### 3. CTA row

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Two buttons side-by-side | `编辑人设` (primary green) left, `添加知识` (secondary) right; equal width |
| 3.2 | Tap `编辑人设` | Navigates to `/doctor/settings/persona` (PersonaSubpage) |
| 3.3 | Back, then tap `添加知识` | Navigates to `/doctor/settings/knowledge/add` (AddKnowledgeSubpage) |

### 4. 快捷入口 (Quick actions)

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Section label "快捷入口" visible | |
| 4.2 | `新建病历` row | IconBadge + title + subtitle "语音或文字录入患者信息" + chevron; tap → `/doctor/patients/new` (URL-driven, not query-param) |
| 4.3 | `患者预问诊码` row | Tap → `/doctor/settings/qr` |
| 4.4 | `重新体验引导` row | **Only visible** when `isWizardDone(doctorId) === true`; tap clears wizard-done flag and routes to `/doctor/onboarding?step=1` |

### 5. 我的AI人设 (Persona preview)

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Section header | Label "我的AI人设" + micro hint "决定AI怎么说话" + "编辑 ›" right-side link |
| 5.2 | Card body (seeded doctor) | Concatenates up to 3 rule texts joined by `；` with `…` suffix if >3; below it: `已学习 N 次编辑` |
| 5.3 | Card body (fresh doctor, no rules) | Text "尚未设置，点击编辑开始配置" in text4 color |
| 5.4 | Tap card body | Navigates to `/doctor/settings/persona` |
| 5.5 | Tap `编辑 ›` link | Same destination as 5.4 |

### 6. 我的知识库 (Knowledge preview)

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Section header | Label "我的知识库" + micro hint "决定AI知道什么" |
| 6.2 | When knowledge count > 0 | Right side shows `全部 N 条 ›` link |
| 6.3 | Card list | Up to 3 `KnowledgeCard` rows (title + summary + meta row with reference count + relative date); last row has `borderBottom: none` |
| 6.4 | Date format | Relative: `今天` / `昨天` / `N天前` — **not** `-1天前` (BUG-01 regression gate) |
| 6.5 | Tap any knowledge row | Navigates to `/doctor/settings/knowledge/<id>` |
| 6.6 | Tap `全部 N 条 ›` | Navigates to `/doctor/settings/knowledge` |
| 6.7 | Empty state (fresh doctor, 0 knowledge) | Two CTA rows shown: `上传指南` and `粘贴常用回复`, both route to `/doctor/settings/knowledge/add` |

### 7. 最近由AI处理 (Activity feed)

| # | Action | Verify |
|---|--------|--------|
| 7.1 | Section header | Label + `全部 N 条 ›` on right |
| 7.2 | Empty state (no activity) | `EmptyState` component with title "暂无AI处理记录" (no raw "暂无…" text) |
| 7.3 | Populated activity row | `NameAvatar` + patient name + badge ("紧急" red / "AI已起草回复" green / "AI诊断建议" orange / "知识库引用" grey / "待办任务" orange) + description + relative time on right |
| 7.4 | Tap `task` type | Routes to `/doctor/tasks/<task_id>` |
| 7.5 | Tap `diagnosis` type | Routes to `/doctor/review/<record_id>` |
| 7.6 | Tap `draft` type | Routes to `/doctor/patients/<patient_id>?view=chat` |
| 7.7 | Tap row without specific type | Routes to `/doctor/review` |
| 7.8 | Tap `全部 N 条 ›` | Routes to `/doctor/review` |

### 8. Pull-to-refresh

| # | Action | Verify |
|---|--------|--------|
| 8.1 | Scroll up from top of the list | Pull-to-refresh spinner appears |
| 8.2 | Release past threshold | Triggers refetch of knowledge + review queue + persona + activity queries; data may not visibly change but no error |

---

## Edge cases

- **100+ knowledge items** — card list still shows only 3; the `全部 N 条` link must show the real total, not `3`.
- **Activity item with no `patient_name`** — NameAvatar renders `?` fallback, no crash.
- **All stats zero (fresh doctor)** — stats show `0`, not `NaN`, not blank.
- **Loading state** — skeleton loaders render (`SectionLoading`), not raw `<CircularProgress>`.
- **Miniprogram context** — extra "添加到手机桌面" row appears when `window.__wxjs_environment === "miniprogram"`; tapping it opens the dark overlay add-to-home card. Not tested in desktop Playwright.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues:

- **BUG-01** — ✅ Fixed. Regression gate: step 6.4 must show correct
  relative date (not `-1天前`).
- **BUG-02** — ✅ Fixed. Regression gate: step 2.2 no duplicate 医生 suffix.

---

## Failure modes & debug tips

- **Stats show `NaN`** — `weekCitations` / `pendingReview` /
  `completedToday` computed before data loads. Check `loading` guards in
  MyAIPage.jsx lines 135-140 and that the derived values default to
  `null` during load.
- **Activity rows missing badges** — `activityBadge(item)` returns based
  on `item.type` + description match. Verify the backend populates
  `type` correctly.
- **"重新体验引导" row not appearing** — `isWizardDone(doctorId)` reads
  localStorage. Ensure fixture actually completes or skips the wizard
  first (or test the row with the wizard seeded as done).
- **Persona card shows "尚未设置" despite seeded rules** — the card reads
  `personaData.fields`. Verify `usePersona()` hook resolves to the
  correct shape.
