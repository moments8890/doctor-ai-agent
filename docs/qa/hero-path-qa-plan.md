# QA Test Plan — Hero Path

End-to-end test of the primary doctor + patient workflow. Covers the UI paths
a real doctor and patient would follow on their first meaningful session.

**Scope:** User-facing hero path only. Backend internals, concurrency,
data isolation, and WeChat channel are out of scope for this plan.
**Tool**: gstack `/qa` (headless Chromium) or manual browser
**Test account**: Register via `POST /api/auth/unified/register/doctor` (see Pre-flight). `test_doctor` does not exist in a fresh DB.
**Backend**: port 8000 | **Frontend**: port 5173
**Reference run**: 2026-04-08 (7 bugs found — see Known Issues below)

---

## Pre-flight

```bash
# Start backend — NO_PROXY required or all LLM calls silently fail (BUG-04)
NO_PROXY=* no_proxy=* PYTHONPATH=src .venv/bin/python -m uvicorn main:app --port 8000 --app-dir src

# Start frontend
cd frontend/web && npm run dev

# Register a test doctor (fresh DB has no accounts)
curl -s -X POST "http://127.0.0.1:8000/api/auth/unified/register/doctor" \
  -H "Content-Type: application/json" \
  -d '{"name":"测试医生","phone":"13800138001","year_of_birth":1980,"invite_code":"WELCOME"}'
# → returns doctor_id (e.g. inv_xxxxx) and token

# Register a test patient linked to that doctor
curl -s -X POST "http://127.0.0.1:8000/api/auth/unified/register/patient" \
  -H "Content-Type: application/json" \
  -d '{"name":"测试患者","phone":"13900139001","year_of_birth":1990,"doctor_id":"<doctor_id_from_above>","gender":"male"}'

# Login (昵称 = phone, 口令 = year_of_birth as integer)
# Doctor: 13800138001 / 1980
# Patient: 13900139001 / 1990

# Open doctor app — login at:
# http://127.0.0.1:5173/login
```

---

## 1. App Load & Login

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 1.1 | Cold load | Navigate to `http://127.0.0.1:5173/login` → login with registered doctor | App loads with no console errors; 我的AI tab shown by default |
| 1.2 | Bottom nav renders | View mobile layout | **4 tabs** visible: 我的AI / 患者 / 审核 / 任务; icons and labels correct |
| 1.3 | Login with valid credentials | Enter 昵称 (phone number) + 口令 (birth year as integer) → tap 登录 | Redirected to doctor workbench; 我的AI tab active |
| 1.4 | Logout | Settings → logout button | Session cleared; redirected to `/login` |
| 1.5 | Browser back after logout | Logout → press browser back | Returns to `/login` — not a doctor page. **BUG-07 open**: currently shows settings page with no data (no PHI visible, but route is accessible) |
| 1.6 | No console errors | Navigate all 4 main tabs | Zero JS exceptions in DevTools console |

**Edge cases:**
- Load with an expired / invalid `doctor_id` param — graceful error, not blank screen
- Resize to desktop viewport — layout adapts, no overflow

---

## 2. 我的AI Tab

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 2.1 | Tab loads | Tap 我的AI | Page loads; doctor name shown ("X 的 AI"); 3 stats visible (7天引用 / 待确认 / 今日处理); no NaN |
| 2.2 | AI Persona card | Scroll to 我的AI人设 card in knowledge preview | Card shows "待学习 · 已收集 N 条回复"; tapping opens `/doctor/settings/knowledge/persona` |
| 2.3 | Knowledge preview | Scroll to 我的知识库 preview | Up to N recent items listed; AI Persona pinned first; "全部 N 条 ›" link visible |
| 2.4 | Knowledge card dates | Check dates on knowledge preview cards | Shows 今天 / 昨天 / N天前 — **not** -1天前 or future date (BUG-01 fix) |
| 2.5 | Navigate to full knowledge list | Tap 我的知识库 button | KnowledgeSubpage opens; all items listed |
| 2.6 | Knowledge item detail | Tap any item | Detail subpage slides in; full text shown; no `[KB-N]` visible |
| 2.7 | Back navigation | Tap back from knowledge detail | Slides back to knowledge list; then back to 我的AI |
| 2.8 | Flagged patients | Check flagged / needs-attention section | Patients needing action (overdue tasks, unread escalations) surfaced |

**Edge cases:**
- 我的AI with zero knowledge items — empty state shown
- Knowledge item with very long title — truncated cleanly, no overflow

---

## 3. 患者 Tab — Patient List

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 3.1 | Patient list loads | Tap 患者 tab | Patient list shown under "最近 · N位患者"; search bar says "搜索患者 (共N人)，或用自然语言描述" |
| 3.2 | Patient card content | Scan card rows | Name, gender·age·record count (e.g. "男 · 36岁 · 1份病历"), last activity as relative date (今天/昨天) — not raw ISO timestamp |
| 3.3 | Text search | Type a patient name (e.g. `张`) in search bar | List filters in real time; "X 清除" button appears; autocomplete shows "+ 新建患者「张」" option |
| 3.4 | Clear search | Tap X in search field | Full list restored |
| 3.5 | NL patient search — male | Type `最近来诊的男性` | Returns male patients with recent records — **not** empty list (BUG-06 fix) |
| 3.6 | NL patient search — surname | Type `姓张的女性` | Returns female patients with surname 张 |
| 3.7 | NL patient search — age+condition | Type `60多岁高血压患者` | Returns patients aged ~60 with hypertension records |
| 3.8 | No match search | Type `xyznotapatient` | Empty state shown; no crash |

**Edge cases:**
- 0 patients — empty state shown with prompt to add first patient
- 100+ patients — list scrolls smoothly
- Search with special characters — no crash

---

## 4. 患者 Tab — Patient Detail

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 4.1 | Open patient detail | Tap any patient card | Patient detail opens at `/doctor/patients/<id>`; bottom nav hidden; `‹` back visible in header |
| 4.2 | Patient bio | View patient header | Name shown; 门诊N / 检验N / 影像N counts; 最近 date; 出生 year; 建档 date |
| 4.3 | Records section | View 病历记录 section | Sub-tabs: 全部 / 病历 / 检验/影像 / 问诊; record rows show source (预问诊), status (待审核), date, chief complaint |
| 4.4 | Tap a record | Tap record row | Navigates to review page (`/doctor/review/<id>`) with full NHC fields |
| 4.5 | Messages shortcut | Tap "患者消息(N) 查看聊天记录 ›" | Navigates to chat view (`/doctor/patients/<id>?view=chat`) |
| 4.6 | 需要你处理 banner | Check if pending items exist | Yellow "⚡ 需要你处理" banner shows count; tapping navigates to relevant review |
| 4.7 | Back navigation | Press back | Returns to patient list |

**Edge cases:**
- Patient with zero records — empty timeline; no crash
- Patient with 20+ messages — chat scrolls without freezing

---

## 5. 审核 Tab — Review Queue

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 5.1 | Review queue loads | Tap 审核 tab | Queue shown; pending count badge correct |
| 5.2 | Three tabs visible | Check tab bar | **待审核 / 待回复 / 已完成** tabs all present |
| 5.3 | 待审核 tab (diagnosis suggestions) | Tap 待审核 | Pending diagnosis suggestions listed with patient names and triage badges |
| 5.4 | Suggestion card | View a card in 待审核 | Shows: patient avatar, name, red "紧急" or amber "待处理" badge, "主诉：X", "预问诊 · AI：Y" preview, date |
| 5.5 | Open suggestion detail | Tap a card | Navigates to `/doctor/review/<record_id>`; "诊断审核" header; `‹` back; no bottom nav |
| 5.6 | Three suggestion sections | Scan review page | Three sections: 鉴别诊断 / 检查建议 / 治疗方向; each has "+ 添加" button; no raw `[KB-N]` in any text |
| 5.7 | Expand suggestion | Tap a suggestion row (▾) | Expands to show full AI explanation text; "确认 / 修改 / 移除" action row appears |
| 5.8 | Confirm suggestion | Tap 确认 | Row turns green with ✓; "修改 / 移除" remain; count in section header increments |
| 5.9 | Reject suggestion | Tap 移除 on a confirmed suggestion | Item returns to unconfirmed/dimmed state; not deleted from list |
| 5.10 | Edit suggestion | Tap 修改 → modify text → save | Edited text persisted. **BUG-05 open**: currently 保存 LEFT / 取消 RIGHT — should be 取消 LEFT / 保存 RIGHT |
| 5.11 | Add custom suggestion | Tap "+ 添加" in any section | Inline form: "建议内容" (required) + "详细说明（可选）"; empty content = add button disabled; saved item appended to section |
| 5.12 | Record summary collapse | Tap record summary header ("收起 ▴") | Collapses to single-line preview with chief complaint; tap "展开 ▾" to re-expand; uses MUI Collapse animation |
| 5.13 | Back to queue | Press back | Returns to 审核 list; badge count updated |

**Edge cases:**
- Empty queue — empty state shown per tab (not blank)
- Urgent suggestion — 紧急 red badge displayed, sorted to top
- Suggestion with no citation — no citation badge, no crash

---

## 6. 审核 Tab — 待回复 (Pending Replies)

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 6.1 | 待回复 tab | Tap 待回复 | Tab label "患者消息 · 待回复"; patient messages listed |
| 6.2 | Draft card | View a draft card | Shows: patient avatar, name, message preview in quotes, "AI已起草 · 常规咨询" (or 紧急) label |
| 6.3 | Open draft | Tap card | Navigates to `/doctor/patients/<id>?view=chat`; shows chat thread; AI draft bubble labeled "AI起草回复 · 待你确认"; "修改" and "确认发送 ›" inline actions |
| 6.4 | No raw citations | Check draft text | No `[KB-N]` visible anywhere in draft bubble |
| 6.5 | Edit draft | Tap 修改 → change text | Bottom input bar switches to edit mode with "正在编辑AI草稿" label; 取消 button appears; edited text pre-filled |
| 6.6 | Edit persists on send | Edit draft → tap send arrow | Confirmation sheet shows **edited** version, not original AI draft |
| 6.7 | Send confirmation sheet | Tap 确认发送 › | Bottom sheet slides up titled "确认发送回复"; shows: patient message, reply text, "AI辅助生成，经医生审核" attribution; 取消 LEFT (grey) / 发送 RIGHT (green) |
| 6.8 | Confirm send | Tap 发送 | Sheet closes; item moves from 待回复 to 已完成; doctor chat shows green sent bubble with attribution |
| 6.9 | Patient receives reply | Check patient portal chat | Doctor reply visible in patient's chat thread; text matches what was sent |

**Edge cases:**
- Multiple drafts for same patient — all shown
- Empty 待回复 — empty state shown

---

## 7. Patient Portal — Interview

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 7.1 | Patient portal loads | Navigate to `http://127.0.0.1:5173/patient` (with patient session set, or login first) | "AI 健康助手" header; "新问诊 AI帮您整理病情" + "我的病历 查看历史记录" cards; AI greeting bubble visible; 4-tab bottom nav: 主页 / 病历 / 任务 / 我的 |
| 7.2 | Patient login | At `/login` tap "患者" tab → enter 昵称 (nickname/phone) + 口令 (numeric passcode/birth year); or register with invitation code WELCOME | Session established; redirected to `/patient`; patient portal home shown |
| 7.3 | Start interview | Tap "新问诊" card | Navigates to `/patient/records/interview`; AI greeting appears within 3s: "您好！我是[doctor name]的AI助手。请描述您的症状..."; progress bar at 0% at top |
| 7.4 | Answer questions | Type response → tap send | Message appears right-aligned (green bubble); AI reply within 10s; progress bar % advances; chat auto-scrolls to bottom |
| 7.5 | Progress indicator | Check progress bar at top | Shows 0%–100% percentage bar advancing as fields are collected (not field count fraction) |
| 7.6 | Complete interview | All required fields filled → AI signals completion | Bottom sheet slides up showing all collected NHC fields; **确认提交** button visible |
| 7.7 | Submit | Tap **确认提交** | Confirmation dialog (取消 LEFT / 确认 RIGHT); on confirm: record created with status `pending_review`; patient sees success state; input disabled |
| 7.8 | Send button (manual) | Type a message → tap send | Message sent and appears in chat — no page navigation crash (BUG-03; verify on real device) |

**Edge cases:**
- Patient abandons mid-interview — partial data not corrupted
- Very long answer (>500 chars) — accepted, no truncation
- Session token expiry — graceful redirect to login

---

## 8. Navigation & UI Polish

| # | Scenario | Steps | Verify |
|---|----------|-------|--------|
| 8.1 | Tab switch transition | Tap between 我的AI / 患者 / 审核 / 任务 | Fade transition (150ms); no flicker |
| 8.2 | Subpage push transition | Enter any subpage | Slide left (300ms); back arrow appears |
| 8.3 | Subpage back transition | Press back on any subpage | Slide right; parent page restored |
| 8.4 | Bottom nav bar padding | View bottom nav on mobile | 8px padding above home indicator; icons not clipped |
| 8.5 | Dialog button order | Trigger any confirm dialog | Cancel LEFT (grey), primary RIGHT (green) — all dialogs |
| 8.6 | Danger dialog | Trigger a delete confirmation | Same layout; primary button red; cancel still LEFT |
| 8.7 | Loading skeletons | Navigate to data-heavy page | Skeleton loaders shown; not raw spinners |
| 8.8 | Empty states | View any empty list | EmptyState component shown; not plain "暂无…" text |
| 8.9 | No console errors | Run all above steps | Zero JS exceptions throughout |

**Edge cases:**
- Rapid tab switching — no state corruption
- Slow connection simulation (Chrome DevTools throttle) — skeletons shown, no blank screens

---

## 9. Regression Checks (run after bug-fix batch)

Run these after each bug is fixed to confirm it stays fixed.

| # | Bug | Status | Check | Pass Criteria |
|---|-----|--------|-------|--------------|
| R.1 | BUG-01 (date display) | **OPEN** | Knowledge cards created today | Shows 今天 — not -1天前 or future |
| R.2 | BUG-02 (greeting suffix) | **OPEN** | Start patient interview as doctor named "测试医生" | Greeting shows "测试医生的AI助手" — not "测试医生医生的AI助手" |
| R.3 | BUG-04 (proxy isolation) | **ENV-FIXED** (not permanent) | Any LLM-driven action (diagnosis, draft, interview) | Completes without "Connection error"; permanent fix = `trust_env=False` in httpx LLM client |
| R.4 | BUG-05 (button order) | **OPEN** | 审核 → open suggestion → edit form | 取消 LEFT (grey), 保存 RIGHT (green) |
| R.5 | BUG-06 (NL search gender) | **OPEN** | Search "最近来诊的男性" | Non-empty results; all male patients |
| R.6 | BUG-07 (logout back) | **OPEN** | Logout → press browser back | Lands on `/login` — settings page not accessible |

---

## Known Issues (as of 2026-04-08)

| ID | Description | Status | Impact |
|----|-------------|--------|--------|
| BUG-01 | Knowledge card dates show -1天前 — UTC vs local time mismatch in `formatRelativeDate` | **Open** | Cosmetic; confusing but not blocking |
| BUG-02 | Doctor greeting renders "测试医生医生" — redundant 医生 suffix | **Open** | Cosmetic |
| BUG-03 | Patient interview send button crashes headless Playwright — native form submit race before React `preventDefault` | **Deferred** — needs real WeChat WebView verification | Unknown until verified on device |
| BUG-04 | Python backend routes LLM calls through dead system proxy 127.0.0.1:1081 — all LLM calls fail silently | **Env-fixed** (NO_PROXY=* at startup) — permanent fix is `trust_env=False` in httpx LLM client | P0 if not set — entire AI pipeline broken |
| BUG-05 | Review suggestion edit modal: 保存 LEFT / 取消 RIGHT — reversed from app-wide convention | **Open** | Polish; violates design convention |
| BUG-06 | NL patient search returns no results for queries like "最近来诊的男性" despite matching patients existing | **Open** | P2; undermines NL search feature |
| BUG-07 | Browser back after logout shows settings page — React Router history not cleared | **Open** | P2; no PHI visible (shows "未设置"), but route accessible |
| BUG-DRAFT-003 | Teaching loop "save as rule" prompt not shown after significant edit | **Likely Fixed** | Not in hero path scope; see knowledge-management-runbook.md |
| FINDING-001 | LLM citation tagging unreliable in diagnosis path | **Open** | Verify in §5.7 (no [KB-N] visible in suggestion text) |

---

## Priority Order

Test in this sequence — earlier sections gate later ones:

1. **Pre-flight** — backend + frontend must be running
2. **Section 1** (App Load) — gates everything
3. **Section 3** (Patient List) — validates seeded data
4. **Section 4** (Patient Detail) — validates records exist
5. **Section 5** (Review Queue 门诊) — core doctor workflow
6. **Section 6** (待回复) — draft reply workflow
7. **Section 2** (我的AI) — knowledge + activity
8. **Section 7** (Patient Portal) — patient-facing
9. **Section 8** (Navigation) — polish checks
10. **Section 9** (Regressions) — quick sweep at the end

---

## Report Template

Save results to `.gstack/qa-reports/qa-report-hero-path-YYYY-MM-DD.md`:

```markdown
# QA Report — Hero Path
**Date:** YYYY-MM-DD
**Checklist:** docs/qa/hero-path-qa-plan.md
**Backend:** http://127.0.0.1:8000 | **Frontend:** http://127.0.0.1:5173
**Doctor:** test_doctor
**Duration:** ~XX min

## Summary

| Section | Area | Result | Notes |
|---------|------|--------|-------|
| 1 | App Load & Login | | |
| 2 | 我的AI | | |
| 3 | Patient List | | |
| 4 | Patient Detail | | |
| 5 | Review Queue (门诊) | | |
| 6 | 待回复 | | |
| 7 | Patient Portal | | |
| 8 | Navigation & UI | | |
| 9 | Regressions | | |

**Overall: X PASS, Y FAIL, Z PARTIAL**
**Health score: XX/100**

## Bugs Found
[new bugs found this run]
```

---

## History

| Date | Result | Notes |
|------|--------|-------|
| 2026-04-08 | 7 bugs found | BUG-01–07 triaged; all fixed except BUG-03 (deferred) |
