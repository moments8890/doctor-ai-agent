# Core E2E Regression Checklist

Scripted walkthrough of the primary doctor workflow. Run this after any big change
to confirm nothing in the critical path is broken.

**Tool**: gstack `/qa` (headless Chromium via `$B`) or manual browser at http://127.0.0.1:5173/doctor
**Test account**: `doctor_id=test_doctor` (URL param or cookie)
**Backend**: default port **8000** (`./dev.sh`); use **8001** for isolated API-only runs (`uvicorn --port 8001`). curl examples below use 8000 — substitute 8001 when running isolated.
**Time to complete**: ~20 min manual, ~10 min automated

---

## Setup

```bash
# Start dev server (no hot reload — embedding loading is expensive)
./dev.sh

# Or start backend only (for API-only verification)
PYTHONPATH=src uvicorn main:app --port 8001
```

Navigate to: `http://127.0.0.1:5173/doctor?doctor_id=test_doctor`

---

## TC-1 · Doctor Setup

| # | Action | Pass Criteria |
|---|--------|--------------|
| 1.1 | Open app as a new doctor (clear state) | Setup dialog appears before main content |
| 1.2 | Enter doctor name "测试医生" → confirm | Dialog closes, 我的AI tab loads |
| 1.3 | Mid-interview, click back button | Confirm-leave dialog: "确认离开？未保存内容将会丢失" with 取消 / 离开 buttons |

---

## TC-2 · New Patient Interview

Starting point: `新建病历` button on 我的AI tab.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 2.1 | Click 新建病历 | Navigates to `/doctor/patients/new`; chat interface loads with AI system message |
| 2.2 | Type: `患者李明，男，45岁，胸痛2天，伴有呼吸困难` → send | AI extracts name; status bar shows `李明 · 必填 1/2` |
| 2.3 | Type: `既往高血压病史5年，无药物过敏` → send | Status bar updates to `必填 2/2 ✓`; 完成 button becomes enabled |
| 2.4 | Check quick-reply chips | Chips appear below input (e.g., `无`, `不详`, `否`) |

**Voice mode toggle** (BUG-NEW-001 regression):
| # | Action | Pass Criteria |
|---|--------|--------------|
| 2.5 | Click mic icon (left of text input) | Voice mode activates: shows "按住说话" + **keyboard icon appears on the left** |
| 2.6 | Click keyboard icon | Returns to normal text input mode |

---

## TC-3 · Save Record + Trigger Diagnosis

| # | Action | Pass Criteria |
|---|--------|--------------|
| 3.1 | Click 完成 | Preview dialog opens showing structured fields (主诉, 现病史, 既往史 at minimum) |
| 3.2 | Check field count | At least 3–4 of 13 fields populated |
| 3.3 | Click 保存并诊断 | `POST /api/records/interview/confirm → 200`; then `POST /api/doctor/records/{id}/diagnose → 202` |
| 3.4 | Check navigation | Navigates to `/doctor/review/{record_id}` |
| 3.5 | Wait for suggestions to load | Polling `GET /api/doctor/records/{id}/suggestions` → non-empty list within **30s**; if spinner persists past 30s, treat as FAIL and check BUG-001 |

**Expected diagnosis output for the Li Ming case:**
- 鉴别诊断: 5+ items including 不稳定型心绞痛, 急性心肌梗死
- 检查建议: 4+ items including 心电图, 心肌酶谱
- 治疗方向: 1+ items

---

## TC-4 · Review Suggestions

| # | Action | Pass Criteria |
|---|--------|--------------|
| 4.1 | Click a diagnosis row | Row expands showing clinical description (Collapse animation) |
| 4.2 | Click inside expanded row | Green checkmark toggles; row highlights |
| 4.3 | Click 完成审核 | `POST /api/doctor/suggestions/{id}/decide → 200`; `POST /api/doctor/records/{id}/review/finalize → 200` |
| 4.4 | Toast appears | "审核完成" toast shown |

**Post-review navigation** (BUG-NEW-002 regression):
| # | Action | Pass Criteria |
|---|--------|--------------|
| 4.5 | After finalize (no new tasks) | Navigates to **patient detail page** `/doctor/patients/{patient_id}`, NOT back to empty interview page |

---

## TC-5 · Review Queue Display

Navigate to 审核 tab.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 5.1 | View 待审核 list | Items show: patient name + urgency badge + record type + "AI：{diagnosis}" |
| 5.2 | Check "主诉" label | **No** items show `主诉：急性心肌梗死` or any AI diagnosis name as chief complaint |
| 5.3 | After backend restart | Items with a record that has `chief_complaint` populated show `主诉：{actual complaint}` |

*(BUG-NEW-003 regression: the `主诉` field must never show the AI's diagnosis name)*

---

## TC-6 · Knowledge → Citation Smoke Test

Seed requires at least one KB rule. Full checklist: `docs/qa/knowledge-citation-e2e.md`.

```bash
# Confirm KB item exists — must print "N KB items" with N ≥ 1 before proceeding
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; print(len(items), 'KB items'); exit(0 if items else 1)"
```

If this prints `0 KB items` or exits non-zero, seed a KB rule via the 我的知识库 UI before continuing.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 6.1 | Run the Li Ming 胸痛 diagnosis (TC-2→TC-3) with at least 1 KB rule saved | Review page loads with suggestions |
| 6.2 | Inspect a suggestion row | At least 1 suggestion shows a citation indicator (`引用: {rule title}`) |
| 6.3 | Verify no raw markers | `document.body.innerText.includes('[KB-')` returns `false` in browser console |
| 6.4 | Return to 我的知识库 | Cited rule shows `reference_count ≥ 1` |

**Operational note:** After editing `src/agent/prompts/intent/diagnosis.md`, always run
`POST /api/test/reset-caches` before testing — prompt loader caches for process lifetime.

---

## TC-7 · Draft & Reply Smoke Test

Requires seeded patient messages. Full checklist: `docs/qa/qa-test-plan.md §7`.

```bash
# Seed demo data (or reset + re-seed) — must return {"status":"ok"} or {"already_seeded":true}
curl -s -X POST "http://127.0.0.1:8000/api/manage/onboarding/seed-demo" \
  -H "Content-Type: application/json" -d '{"doctor_id":"test_doctor"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'), '— already_seeded:', d.get('already_seeded', False))"
```

If the command errors (connection refused), the backend is not running. Do not proceed.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 7.1 | Navigate 审核 → 待回复 tab | At least 1 draft card visible with patient name + triage color |
| 7.2 | Click a draft card | Navigates to `/doctor/patients/{id}?view=chat`; draft bubble shows AI text + cited rules |
| 7.3 | Chat view shows messages | Message history visible — **not** "暂无消息" (BUG-CHAT-001 regression) |
| 7.4 | Click "确认发送 ›" | **Confirmation sheet opens** showing patient message, draft text, AI disclosure — does NOT send immediately (BUG-DRAFT-002 regression) |
| 7.5 | Click 发送 in sheet | Sheet closes; draft removed from list; outbound message appears in chat |
| 7.6 | Click "修改" on a different draft, make a significant edit, tap send | If edit is significant: "保存为知识规则" dialog appears — **teaching loop visible** (BUG-DRAFT-003 regression) |
| 7.7 | In teaching dialog, tap 保存 | `POST /api/manage/drafts/{id}/save-as-rule` returns `200` — **not 500** (BUG-DRAFT-004 regression) |
| 7.8 | Inspect 待回复 list for any undrafted item | Label shows "需手动回复" — **not** "AI已起草" (BUG-DRAFT-005 regression) |

---

## Regression Bug Rechecks

These bugs were fixed; confirm they don't regress.

### BUG-001 · Diagnosis Pipeline Never Hangs

| Check | Pass Criteria |
|-------|--------------|
| `POST /api/doctor/records/{id}/diagnose` | Returns `202`, not `200` or `5xx` |
| Subsequent GET suggestions poll | Eventually returns non-empty suggestions (< 30s typical) |
| No permanent "处理中" spinner | If LLM fails, `diagnosis_failed` status shown with retry option (not infinite loading) |

### BUG-002 · Unnamed Patient Gets Editable Name Field

| Check | Pass Criteria |
|-------|--------------|
| Interview with no name (e.g., `男，50岁，腹痛3天，无过敏史`) | Status bar shows `未命名 · 必填 2/2 ✓` |
| Click 完成 → preview dialog | Green-bordered name input field `请输入患者姓名` is shown |
| 保存并诊断 button | **Disabled** until name is entered |
| Enter name "张三" → button enables | Saves correctly with the entered name |

### BUG-003 · Compound Surname Accepted

| Check | Pass Criteria |
|-------|--------------|
| Interview input: `患者欧阳明，女，35岁，头痛3天` | Status bar shows `欧阳明 · 必填 1/2` (name extracted correctly) |
| NOT shown | `未命名` or name validation error |

Other compound surnames to spot-check if needed: 司马, 诸葛, 上官, 欧阳.

### BUG-004 · Chat View Shows Patient Messages

| Check | Pass Criteria |
|-------|--------------|
| Open `/doctor/patients/{id}?view=chat` for a patient with messages | Chat history loads; **not** "暂无消息" |
| Network tab | Request is `/api/manage/patients/{id}/chat?doctor_id=test_doctor` — `doctor_id` param present |

*(BUG-CHAT-001 fix: `getPatientChat()` was missing the `doctor_id` query param, causing backend to default to `web_doctor` with no messages.)*

### BUG-005 · Draft Send Requires Confirmation

| Check | Pass Criteria |
|-------|--------------|
| Click "确认发送 ›" on a draft bubble | Confirmation `SheetDialog` opens — draft is **NOT** sent immediately |
| Sheet shows | Patient message, draft reply text, cited rules, AI disclosure label |
| Click 发送 | Draft is sent; sheet closes; message appears in chat |
| Click 取消 | Sheet closes; draft unchanged |

*(BUG-DRAFT-002 fix: `handleDraftSend()` now calls `getDraftConfirmation()` before `sendDraft()`.)*

### BUG-006 · Teaching Loop Prompts After Significant Edit

| Check | Pass Criteria |
|-------|--------------|
| Click 修改 on a draft; replace text with something substantively different; tap send | "保存为知识规则" `ConfirmDialog` appears |
| Tap 保存 | `POST /api/manage/drafts/{id}/save-as-rule` returns **200** (not 500) |
| Tap 跳过 | Dialog dismisses; send proceeds normally |

*(BUG-DRAFT-003 fix: `editDraft()` return value now captured; BUG-DRAFT-004 fix: `rule.content` used instead of `rule.text`, values captured before `db.commit()`.)*

---

## Pass/Fail Criteria Summary

| Area | Must pass to ship |
|------|------------------|
| TC-1 Setup | Doctor setup completes; confirm-leave guard works |
| TC-2 Interview | AI extracts name + required fields; voice toggle works both ways |
| TC-3 Diagnosis | confirm → 200, diagnose → 202, suggestions load |
| TC-4 Review | decide → 200, finalize → 200, navigates to patient (not blank interview) |
| TC-5 Queue | No AI diagnosis names shown as 主诉 |
| TC-6 Citations | Suggestion shows rule title; no raw `[KB-N]` in UI; reference count increments |
| TC-7 Draft & Reply | Confirmation dialog appears; chat shows messages; teaching loop visible; save-as-rule 200 |
| BUG-001 | Diagnosis never stuck; diagnosis_failed handled |
| BUG-002 | Unnamed patients get editable name field |
| BUG-003 | Compound surnames accepted |
| BUG-004 | Chat view shows messages (doctor_id param present) |
| BUG-005 | Confirmation sheet before draft send |
| BUG-006 | Teaching loop dialog + save-as-rule 200 |

Any **FAIL** in TC-1 through TC-4 blocks the release. TC-5 through TC-7 and all BUG checks are high-value regression checks; failures should be fixed before shipping a draft-related change.

---

## Running with gstack `/qa`

```
/qa
```

In the `/qa` prompt, describe the flow:
> Run the core E2E doctor workflow: (1) new patient interview (患者李明 男 45岁 胸痛2天 伴呼吸困难 / 既往高血压病史5年无药物过敏) → save + diagnose → review suggestions → finalize. (2) Voice mic → keyboard toggle exits voice mode. (3) Post-review navigation lands on patient detail not empty interview. (4) Review queue 主诉 field doesn't show AI diagnosis names. (5) Draft & Reply smoke: open 待回复 tab, click a draft, verify confirmation sheet appears on 确认发送, verify chat shows messages (not 暂无消息), verify teaching dialog appears after a significant edit. Report pass/fail per TC above.

Results land in `.gstack/qa-reports/` as a dated HTML file.

---

## History

| Date | Result | Notes |
|------|--------|-------|
| 2026-03-31 | 17/20 pass | BUG-NEW-001/002/003 found and fixed same session |
| 2026-04-01 | KC E2E 12/13 pass | Knowledge → Citation: FINDING-001 fixed (prompt + batch title). See `qa-report-knowledge-citation-2026-04-01-rerun.md` |
| 2026-04-01 | §7 Draft 2/10 (pre-fix) | 6 bugs found and fixed (BUG-CHAT-001, BUG-DRAFT-001–005). See `qa-report-draft-reply-2026-04-01.md`. Full rerun pending. |
