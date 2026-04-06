# QA Report: Patient Portal Enhancements — 2026-03-26

> **Features tested:** P3.4 (Treatment Plan), P3.5 (Timeline), P3.7 (Medications/Record Restructure), P3.8 (Doctor Info), P4.1-P4.2 (Notifications)
> **Route:** `/patient/*`
> **Method:** Manual walkthrough with headless Chromium (gstack browse), mobile viewport
> **Account:** 李复诊 (patient_id=13, doctor: test_doctor)
> **Backend:** localhost:8000 (FastAPI), localhost:5173 (Vite dev)

---

## Test Results

### P3.4 — Treatment Plan Visibility

| # | Test | Result | Notes |
|---|------|--------|-------|
| 1 | Record detail loads diagnosis data | **PASS** | "2型糖尿病，头晕待查" with "待审核" badge |
| 2 | Diagnosis section renders with SectionLabel | **PASS** | SectionLabel "诊断" + white card |
| 3 | StatusBadge shows correct status | **PASS** | "待审核" badge with border |
| 4 | No medications section (no treatment_plan data) | **PASS** | Section correctly hidden |
| 5 | No follow-up/lifestyle sections (no data) | **PASS** | Sections correctly hidden |

### P3.5 — Health Timeline

| # | Test | Result | Notes |
|---|------|--------|-------|
| 6 | Filter chips render ("病历" / "时间线") | **PASS** | Green active, white inactive |
| 7 | "病历" view shows RecordAvatar list | **PASS** | Type icon + title + date |
| 8 | "时间线" view shows DateAvatar list | **PASS** | "3月" / "25日" + "门诊记录 · 头晕反复发作1月" |
| 9 | DateAvatar month/day formatting | **PASS** | Small gray month on top, bold day below |
| 10 | Timeline entry has chevron (›) | **PASS** | Indicates tappable |
| 11 | Click timeline entry → record detail | **PASS** | Navigates to /patient/records/5 |
| 12 | Switching between views preserves data | **PASS** | Toggle back and forth works |

### P3.7 — Record Detail Restructure

| # | Test | Result | Notes |
|---|------|--------|-------|
| 13 | Action summary shows first (diagnosis) | **PASS** | Diagnosis card at top of detail |
| 14 | "查看完整病历 ▾" toggle visible | **PASS** | Green text, centered |
| 15 | Click expands full 14-field record | **PASS** | Shows 主诉, 既往史, 过敏史, 个人史, 家族史, 初步诊断 |
| 16 | "收起 ▴" collapses back | **PASS** | Returns to summary-only view |
| 17 | Empty sections hidden | **PASS** | No medications/follow-up/lifestyle when data absent |

### P3.8 — Doctor Info Card

| # | Test | Result | Notes |
|---|------|--------|-------|
| 18 | "我的医生" section renders | **PASS** | SectionLabel + ListCard |
| 19 | Doctor avatar with initial | **PASS** | "测" character in colored circle |
| 20 | Doctor name displays | **PASS** | "测试医生" |
| 21 | Doctor specialty hidden (null) | **PASS** | No subtitle when specialty is empty |
| 22 | "我的信息" section renders | **PASS** | SectionLabel + ListCard |
| 23 | Patient avatar + name | **PASS** | "李" + "李复诊" |
| 24 | Patient subtitle shows doctor_id | **PASS** | "test_doctor" |
| 25 | Logout button renders | **PASS** | Red "退出登录", centered |
| 26 | Nav highlight on 设置 tab | **PASS** | Green icon + text |

### P4.1-P4.2 — Notifications

| # | Test | Result | Notes |
|---|------|--------|-------|
| 27 | DoctorTask model has new fields | **PASS** | read_at, link_type, link_id columns added to SQLite |
| 28 | Task API accepts target="patient" | **PASS** | POST /api/tasks returns 201 with target field |
| 29 | Frontend compiles with notification code | **PASS** | No JS errors |
| 30 | Badge import (MUI Badge) | **PASS** | No import errors |
| 31 | System message rendering branch | **PASS** | Code present in renderMessage function |
| 32 | Notification card ListCard rendering | **NEEDS SERVER RESTART** | Backend notification insertion code not in running server |
| 33 | Badge count on 主页 tab | **NEEDS SERVER RESTART** | No system messages to count yet |
| 34 | last_seen_chat localStorage tracking | **PASS** | Key set/read correctly |

### Cross-Cutting

| # | Test | Result | Notes |
|---|------|--------|-------|
| 35 | No JS console errors | **PASS** | Only pre-existing emotion warning |
| 36 | All 4 bottom nav tabs work | **PASS** | 主页, 病历, 任务, 设置 |
| 37 | Nav highlight correct on all tabs | **PASS** | Tested all 4 |
| 38 | Page loads with no 500 errors | **PASS** | All API calls succeed |

---

## Summary

| Category | Pass | Needs Restart | Total |
|----------|------|--------------|-------|
| P3.4 Treatment Plan | 5 | 0 | 5 |
| P3.5 Timeline | 7 | 0 | 7 |
| P3.7 Record Restructure | 5 | 0 | 5 |
| P3.8 Doctor Info | 9 | 0 | 9 |
| P4.1-P4.2 Notifications | 6 | 2 | 8 |
| Cross-Cutting | 4 | 0 | 4 |
| **Total** | **36** | **2** | **38** |

**36/38 tests pass. 2 tests require server restart** to verify notification message insertion and badge count. All frontend code compiles and renders correctly.

---

## Action Required

**Server restart needed** to pick up backend changes for P4.1-P4.2:
- `save_patient_message` insertion on task creation (src/channels/web/tasks.py)
- `save_patient_message` insertion on diagnosis finalize (src/channels/web/ui/diagnosis_handlers.py)
- New `target` field threading through create chain

After restart, verify tests #32 and #33:
1. Create a patient task → system message appears in chat feed as ListCard
2. Badge count shows on 主页 tab when unread messages exist

---

## Screenshots

| # | File | What it shows |
|---|------|---------------|
| 1 | `snapshots/01-chat-tab.png` | Chat tab with AI greeting, quick actions, no badge |
| 2 | `snapshots/02-records-list.png` | Records tab with filter chips (病历 active), RecordAvatar list |
| 3 | `snapshots/03-timeline-view.png` | Timeline view with DateAvatar (3月/25日), combined title |
| 4 | `snapshots/04-record-detail.png` | Record detail: diagnosis summary + "查看完整病历 ▾" |
| 5 | `snapshots/05-record-expanded.png` | Expanded full record (6 NHC fields + "收起 ▴") |
| 6 | `snapshots/06-profile-tab.png` | Profile: doctor card (测试医生) + patient card (李复诊) + logout |
| 7 | `snapshots/07-tasks-tab.png` | Tasks tab with empty state |

See `index.html` for interactive walkthrough with embedded screenshots.
