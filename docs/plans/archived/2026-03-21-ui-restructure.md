# UI Restructure Implementation Plan

> **Status: ✅ DONE** — implementation complete, merged to main.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure 3 views (patient detail, tasks, briefing) and demote chat from top-level nav to subpage.

**Architecture:** Frontend-heavy — patient detail and tasks are pure React restructuring with no backend changes. Briefing requires a new backend endpoint that queries tasks/reviews/records and runs LLM analysis. Nav change touches DoctorPage.jsx and constants.jsx shared across all views.

**Tech Stack:** React 18 + MUI 5 (frontend), FastAPI + SQLAlchemy (backend), existing LLM dispatch via `services.ai.agent.dispatch`

**Spec:** `docs/specs/archived/2026-03-21-patient-detail-upgrade-design.md`
**Mockups:** `docs/specs/archived/2026-03-21-mockups/reference-views.html`

---

## File Structure

### Frontend — New files
- `frontend/web/src/pages/doctor/BriefingSection.jsx` — AI agent briefing landing page
- `frontend/web/src/pages/doctor/BriefingCard.jsx` — individual briefing card component

### Frontend — Modified files
- `frontend/web/src/pages/doctor/constants.jsx` — NAV items, tab group mapping
- `frontend/web/src/pages/DoctorPage.jsx` — nav change (chat→home), route for briefing, chat as subpage
- `frontend/web/src/pages/doctor/PatientDetail.jsx` — collapsible profile, tabs, sticky header, remove avatar
- `frontend/web/src/pages/doctor/PatientsSection.jsx` — update MobilePatientDetailView
- `frontend/web/src/pages/doctor/TasksSection.jsx` — unified list with filter chips
- `frontend/web/src/pages/doctor/ChatSection.jsx` — add back button header
- `frontend/web/src/api.js` — add `getBriefing()` and `dismissBriefingCard()` API functions

### Backend — New files
- `src/channels/web/ui/briefing_handlers.py` — GET /api/doctor/briefing endpoint

### Backend — Modified files
- `src/channels/web/ui/__init__.py` — register briefing router

---

## Task 1: Nav + Constants Update

**Files:**
- Modify: `frontend/web/src/pages/doctor/constants.jsx:61-66`
- Modify: `frontend/web/src/pages/DoctorPage.jsx:214-215, 221`

- [ ] **Step 1: Update NAV constant**

In `constants.jsx`, add `HomeOutlinedIcon` import and change the NAV array:

```jsx
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
```

Replace line 61-66:
```jsx
export const NAV = [
  { key: "home", label: "首页", icon: <HomeOutlinedIcon fontSize="medium" /> },
  { key: "patients", label: "患者", icon: <PeopleOutlineIcon fontSize="medium" /> },
  { key: "tasks", label: "任务", icon: <AssignmentOutlinedIcon fontSize="medium" /> },
  { key: "settings", label: "设置", icon: <SettingsOutlinedIcon fontSize="medium" /> },
];
```

Remove the `ChatOutlinedIcon` import (line 4) since it's no longer used in NAV.

- [ ] **Step 2: Add tab group mapping constant**

Append to `constants.jsx`:
```jsx
export const RECORD_TAB_GROUPS = [
  { key: "", label: "全部", types: null },
  { key: "medical", label: "病历", types: ["visit", "dictation", "import", "surgery", "referral"] },
  { key: "lab_imaging", label: "检验/影像", types: ["lab", "imaging"] },
  { key: "interview", label: "问诊", types: ["interview_summary"] },
];

export const TASK_FILTER_CHIPS = [
  { key: "all", label: "全部" },
  { key: "review", label: "待审核" },
  { key: "task", label: "待办" },
  { key: "done", label: "已完成" },
];
```

- [ ] **Step 3: Update DoctorPage routing**

In `DoctorPage.jsx`:

1. Add import for BriefingSection:
```jsx
import BriefingSection from "./doctor/BriefingSection";
```

2. Change default section (line 215):
```jsx
const activeSection = patientId ? "patients" : (section || "home");
```

3. Update `handleNav` (line 221):
```jsx
function handleNav(key) { navigate(key === "home" ? "/doctor" : `/doctor/${key}`); }
```

4. In `SectionContent`, add home section and chat subpage handling. Replace the `activeSection === "chat"` block (lines 125-135) with:
```jsx
{activeSection === "home" && (
  <ErrorBoundary label="首页">
    <BriefingSection doctorId={doctorId} onNavigateToChat={() => navigate("/doctor/chat")} />
  </ErrorBoundary>
)}
{activeSection === "chat" && (
  <ErrorBoundary label="聊天">
    <ChatSection doctorId={doctorId} onMessageCountChange={() => {}}
      externalInput={chatInsertText} onExternalInputConsumed={() => setChatInsertText("")}
      onPatientCreated={() => setPatientRefreshKey((k) => k + 1)}
      autoSendText={chatAutoSendText !== chatAutoSendConsumedRef.current ? chatAutoSendText : ""}
      onAutoSendConsumed={() => { chatAutoSendConsumedRef.current = chatAutoSendText; setChatAutoSendText(""); }}
      onContextCleared={onContextCleared}
      onStartPatientInterview={() => { setTriggerInterview(true); navigate("/doctor/patients"); }}
      onBack={() => navigate("/doctor")} />
  </ErrorBoundary>
)}
```

5. In `DesktopSidebar` navBadge, change `chat` key to `home`:
```jsx
navBadge={{ tasks: pendingTaskCount + pendingReviewCount, home: pendingRecord ? 1 : 0 }}
```

6. In `MobileBottomNav`, same change:
```jsx
: item.key === "home" && pendingRecord ? <Badge variant="dot" color="warning">{item.icon}</Badge>
```

- [ ] **Step 4: Verify app loads**

Run: `cd frontend/web && npm start`
Expected: App loads with 首页 as default tab (shows empty BriefingSection placeholder)

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/doctor/constants.jsx frontend/web/src/pages/DoctorPage.jsx
git commit -m "refactor: nav from AI助手 to 首页, add constants for tabs and task filters"
```

---

## Task 2: ChatSection — Add Back Button

**Files:**
- Modify: `frontend/web/src/pages/doctor/ChatSection.jsx`

- [ ] **Step 1: Add onBack prop and header**

Add `onBack` to the component props. At the top of the returned JSX (before DashboardSummary), add a header bar when `onBack` is provided:

```jsx
{onBack && (
  <Box sx={{ background: "#fff", borderBottom: "0.5px solid #d9d9d9", px: 2, py: 1.5, display: "flex", alignItems: "center", gap: 1 }}>
    <Box onClick={onBack} sx={{ cursor: "pointer", color: "#999", fontSize: 14 }}>←</Box>
    <Typography sx={{ fontSize: 15, fontWeight: 600 }}>AI 助手</Typography>
    <Box sx={{ flex: 1 }} />
    <Typography onClick={() => { /* existing clear logic */ }} sx={{ fontSize: 12, color: "#999", cursor: "pointer" }}>清除记录</Typography>
  </Box>
)}
```

Wire the "清除记录" to the existing clear context handler.

- [ ] **Step 2: Verify chat with back button**

Navigate to `/doctor/chat` from briefing. Back button should return to `/doctor`.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/ChatSection.jsx
git commit -m "feat: add back button header to ChatSection for subpage mode"
```

---

## Task 3: Patient Detail — Collapsible Profile

**Files:**
- Modify: `frontend/web/src/pages/doctor/PatientDetail.jsx`
- Modify: `frontend/web/src/pages/doctor/PatientsSection.jsx:273-279`

- [ ] **Step 1: Add helper functions**

At top of `PatientDetail.jsx`, add masking and stats utilities:

```jsx
function maskPhone(phone) {
  if (!phone || phone.length < 7) return phone || "—";
  return phone.slice(0, 3) + "****" + phone.slice(-4);
}

function maskIdNumber(id) {
  if (!id || id.length < 8) return id || "—";
  return id.slice(0, 4) + "****" + id.slice(-4);
}

function computeRecordStats(records) {
  const medical = ["visit", "dictation", "import", "surgery", "referral"];
  let visitCount = 0, labCount = 0, imagingCount = 0, lastDate = null;
  for (const r of records) {
    if (medical.includes(r.record_type)) visitCount++;
    else if (r.record_type === "lab") labCount++;
    else if (r.record_type === "imaging") imagingCount++;
    const d = r.created_at;
    if (d && (!lastDate || d > lastDate)) lastDate = d;
  }
  const lastVisit = lastDate ? new Date(lastDate) : null;
  const lastVisitStr = lastVisit ? `${String(lastVisit.getMonth() + 1).padStart(2, "0")}-${String(lastVisit.getDate()).padStart(2, "0")}` : "—";
  return { visitCount, labCount, imagingCount, lastVisitStr };
}
```

- [ ] **Step 2: Replace PatientProfileBlock with collapsible profile**

Remove the `PatientProfileBlock` function entirely. Replace with a new `CollapsibleProfile` component:

```jsx
function CollapsibleProfile({ patient, age, records, patientLabels, labelPickerOpen, labelAnchorRef, allLabels, labelError, exportingPdf, exportingReport, expanded, onToggle, onOpenLabelPicker, onRemoveLabel, onAssignLabel, onLabelsChange, onCloseLabelPicker, onExportPdf, onExportReport, onDeleteOpen }) {
  const stats = computeRecordStats(records);
  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: "4px", px: 1.5, pt: 1.5, pb: 1.5, mb: 0.8 }}>
      {/* Header: name + summary + toggle */}
      <Box onClick={onToggle} sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1, cursor: "pointer" }}>
        <Box>
          <Typography component="span" sx={{ fontWeight: 600, fontSize: expanded ? 16 : 15 }}>{patient.name}</Typography>
          {expanded ? (
            <Typography component="span" sx={{ fontSize: 13, color: "#999", ml: 1 }}>
              {[patient.gender ? { male: "男", female: "女" }[patient.gender] : null, age ? `${age}岁` : null].filter(Boolean).join(" · ")}
            </Typography>
          ) : (
            <Typography component="span" sx={{ fontSize: 12, color: "#999", ml: 1 }}>
              {[patient.gender ? { male: "男", female: "女" }[patient.gender] : null, age ? `${age}岁` : null, `门诊${stats.visitCount}`, `最近${stats.lastVisitStr}`].filter(Boolean).join(" · ")}
            </Typography>
          )}
        </Box>
        <Typography sx={{ fontSize: 11, color: "#07C160", flexShrink: 0, ml: 1 }}>
          {expanded ? "收起 ▴" : "展开 ▾"}
        </Typography>
      </Box>

      {/* Expanded: stats row */}
      {expanded && (
        <Box sx={{ display: "flex", gap: 2, fontSize: 12, color: "#999", py: 1, borderTop: "0.5px solid #f0f0f0", borderBottom: "0.5px solid #f0f0f0", mb: 1 }}>
          <span>门诊 <b style={{ color: "#1A1A1A" }}>{stats.visitCount}</b></span>
          <span>检验 <b style={{ color: "#1A1A1A" }}>{stats.labCount}</b></span>
          <span>影像 <b style={{ color: "#1A1A1A" }}>{stats.imagingCount}</b></span>
          <span>最近就诊 <b style={{ color: "#1A1A1A" }}>{stats.lastVisitStr}</b></span>
        </Box>
      )}

      {/* Expanded: demographics grid */}
      {expanded && (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px", fontSize: 12, mb: 1, pb: 1, borderBottom: "0.5px solid #f0f0f0" }}>
          <Box><Typography component="span" sx={{ color: "#999", display: "inline-block", minWidth: 40, fontSize: 12 }}>电话</Typography> <Typography component="span" sx={{ color: "#333", fontSize: 12 }}>{maskPhone(patient.phone)}</Typography></Box>
          <Box><Typography component="span" sx={{ color: "#999", display: "inline-block", minWidth: 40, fontSize: 12 }}>出生</Typography> <Typography component="span" sx={{ color: "#333", fontSize: 12 }}>{patient.year_of_birth ? `${patient.year_of_birth}年` : "—"}</Typography></Box>
          <Box><Typography component="span" sx={{ color: "#999", display: "inline-block", minWidth: 40, fontSize: 12 }}>身份证</Typography> <Typography component="span" sx={{ color: "#333", fontSize: 12 }}>{maskIdNumber(patient.patient_id_number)}</Typography></Box>
          <Box><Typography component="span" sx={{ color: "#999", display: "inline-block", minWidth: 40, fontSize: 12 }}>建档</Typography> <Typography component="span" sx={{ color: "#333", fontSize: 12 }}>{patient.created_at ? patient.created_at.slice(0, 10) : "—"}</Typography></Box>
        </Box>
      )}

      {/* Labels */}
      <PatientLabelRow patient={patient} patientLabels={patientLabels} labelPickerOpen={labelPickerOpen} labelAnchorRef={labelAnchorRef} allLabels={allLabels} labelError={labelError} onOpenLabelPicker={onOpenLabelPicker} onRemoveLabel={onRemoveLabel} onAssignLabel={onAssignLabel} onLabelsChange={onLabelsChange} onCloseLabelPicker={onCloseLabelPicker} />

      {/* Expanded: action bar */}
      {expanded && (
        <PatientActionBar exportingPdf={exportingPdf} exportingReport={exportingReport} onExportPdf={onExportPdf} onExportReport={onExportReport} onDeleteOpen={onDeleteOpen} />
      )}
    </Box>
  );
}
```

- [ ] **Step 3: Replace RecordFilterPills with record tabs**

Remove the `RecordFilterPills` component. Replace with:

```jsx
import { RECORD_TAB_GROUPS } from "./constants";

function RecordTabs({ activeTab, records, onChange }) {
  return (
    <Box sx={{ display: "flex", borderBottom: "0.5px solid #f0f0f0" }}>
      {RECORD_TAB_GROUPS.map((tab) => {
        const count = tab.types ? records.filter((r) => tab.types.includes(r.record_type)).length : records.length;
        return (
          <Box key={tab.key} onClick={() => onChange(tab.key)}
            sx={{ padding: "10px 14px", fontSize: 13, cursor: "pointer",
              color: activeTab === tab.key ? "#07C160" : "#999",
              fontWeight: activeTab === tab.key ? 600 : 400,
              borderBottom: activeTab === tab.key ? "2px solid #07C160" : "2px solid transparent" }}>
            {tab.label} <span style={{ fontWeight: 400, opacity: 0.7 }}>{count}</span>
          </Box>
        );
      })}
    </Box>
  );
}
```

- [ ] **Step 4: Update PatientDetail main component**

In the `PatientDetail` default export:

1. Add `expanded` state: `const [expanded, setExpanded] = useState(!isMobile);`
2. Change `recordTypeFilter` to `activeTab`: `const [activeTab, setActiveTab] = useState("");`
3. Compute filtered records from tab groups:
```jsx
const activeGroup = RECORD_TAB_GROUPS.find((t) => t.key === activeTab);
const filteredRecords = activeGroup?.types ? records.filter((r) => activeGroup.types.includes(r.record_type)) : records;
```
4. Replace `<PatientProfileBlock ...>` with `<CollapsibleProfile ... expanded={expanded} onToggle={() => setExpanded(!expanded)} records={records} />`
5. In `RecordListSection`, replace `<RecordFilterPills>` with `<RecordTabs activeTab={activeTab} records={records} onChange={setActiveTab} />`
6. Remove the `PatientAvatar` import since it's no longer used in this file.

- [ ] **Step 5: Add sticky top bar**

In `PatientDetail`, add a sticky header above the scrollable content:

```jsx
<Box sx={{ bgcolor: "#fff", borderBottom: "0.5px solid #d9d9d9", px: 2, py: 1.5, display: "flex", alignItems: "center", gap: 1.2, position: "sticky", top: 0, zIndex: 2 }}>
  {isMobile && <Box onClick={() => navigate("/doctor/patients")} sx={{ cursor: "pointer", color: "#999", fontSize: 14 }}>←</Box>}
  <Typography sx={{ fontSize: 15, fontWeight: 600 }}>{patient.name}</Typography>
  <Box sx={{ flex: 1 }} />
  <Typography onClick={handleStartInterview} sx={{ fontSize: 12, color: "#07C160", fontWeight: 500, cursor: "pointer" }}>新建病历</Typography>
  <Typography onClick={handleStartInterview} sx={{ fontSize: 12, color: "#07C160", fontWeight: 500, cursor: "pointer" }}>问诊</Typography>
  <Typography onClick={() => setExportOpen(true)} sx={{ fontSize: 12, color: "#999", cursor: "pointer" }}>导出</Typography>
</Box>
```

Wire `handleStartInterview` and export handlers to existing functions. Add `navigate` via `useNavigate()`.

- [ ] **Step 6: Update PatientsSection MobilePatientDetailView**

In `PatientsSection.jsx`, update `MobilePatientDetailView` (lines 273-279) to remove `SubpageHeader` — the sticky top bar is now inside `PatientDetail`:

```jsx
function MobilePatientDetailView({ selectedPatient, doctorId, navigate }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <PatientDetail patient={selectedPatient} doctorId={doctorId} />
      </Box>
    </Box>
  );
}
```

Remove the `SubpageHeader` import if no longer used elsewhere in this file.

- [ ] **Step 7: Verify patient detail**

Open a patient on mobile and desktop. Verify:
- Mobile: collapsed profile, tap "展开" expands
- Desktop: expanded by default
- Tabs show correct counts
- Back button works on mobile
- Quick actions (新建病历, 问诊, 导出) work

- [ ] **Step 8: Commit**

```bash
git add frontend/web/src/pages/doctor/PatientDetail.jsx frontend/web/src/pages/doctor/PatientsSection.jsx
git commit -m "feat: collapsible patient profile, record tabs with counts, sticky header"
```

---

## Task 4: Tasks — Unified List

**Files:**
- Modify: `frontend/web/src/pages/doctor/TasksSection.jsx`

- [ ] **Step 1: Add date grouping utility**

Add at top of `TasksSection.jsx`:

```jsx
function groupByDate(items) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const endOfWeek = new Date(today); endOfWeek.setDate(today.getDate() + (7 - today.getDay()));
  const groups = { "已逾期": [], "今天": [], "本周": [], "之后": [], "无截止日期": [] };
  for (const item of items) {
    const due = item.due_at || item.created_at;
    if (!due) { groups["无截止日期"].push(item); continue; }
    const d = new Date(due);
    const dd = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    if (dd < today) groups["已逾期"].push(item);
    else if (dd.getTime() === today.getTime()) groups["今天"].push(item);
    else if (dd < endOfWeek) groups["本周"].push(item);
    else groups["之后"].push(item);
  }
  return Object.entries(groups).filter(([, items]) => items.length > 0);
}
```

- [ ] **Step 2: Add filter chip bar**

Replace the 3-segment tab control with filter chips:

```jsx
import { TASK_FILTER_CHIPS } from "./constants";

function TaskFilterChips({ active, onChange }) {
  return (
    <Box sx={{ bgcolor: "#ededed", borderBottom: "0.5px solid #d9d9d9", px: 1.5, py: 1, display: "flex", gap: 0.6 }}>
      {TASK_FILTER_CHIPS.map((chip) => (
        <Box key={chip.key} onClick={() => onChange(chip.key)}
          sx={{ fontSize: 12, px: 1.2, py: 0.5, borderRadius: "4px", cursor: "pointer", flexShrink: 0,
            bgcolor: active === chip.key ? "#07C160" : "#fff",
            color: active === chip.key ? "#fff" : "#666",
            fontWeight: active === chip.key ? 600 : 400 }}>
          {chip.label}
        </Box>
      ))}
    </Box>
  );
}
```

- [ ] **Step 3: Create unified task item**

Create a `UnifiedTaskItem` that handles both tasks and review items:

```jsx
function UnifiedTaskItem({ item, onTap }) {
  const isReview = item._type === "review";
  const chipLabel = isReview ? "待审核" : (TASK_TYPE_LABEL[item.task_type] || "任务");
  const chipBg = isReview ? "#FFF7E6" : "#e8f5e9";
  const chipColor = isReview ? "#d46b08" : "#07C160";
  return (
    <Box onClick={() => onTap(item)} sx={{ px: 1.5, py: 1.5, cursor: "pointer", "&:active": { bgcolor: "#f5f5f5" } }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
        <Typography sx={{ fontSize: 15, fontWeight: 500, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {isReview ? `${item.patient_name} 问诊记录` : item.title}
        </Typography>
        <Typography sx={{ fontSize: 11, px: 0.8, py: 0.1, borderRadius: "4px", bgcolor: chipBg, color: chipColor, flexShrink: 0, ml: 1 }}>
          {chipLabel}
        </Typography>
      </Box>
      {isReview && item.chief_complaint && (
        <Typography sx={{ fontSize: 13, color: "#666", mb: 0.3 }}>主诉：{item.chief_complaint}</Typography>
      )}
      <Box sx={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#999" }}>
        <Typography sx={{ fontSize: 11, color: "#999", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {isReview ? (item.diagnosis_status === "completed" ? "AI诊断已完成 · 等待确认" : "AI诊断中...") : (item.content || "")}
        </Typography>
        {item._overdueDays > 0 && (
          <Typography sx={{ fontSize: 11, color: "#FA5151", flexShrink: 0, ml: 1 }}>逾期{item._overdueDays}天</Typography>
        )}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Rewrite main TasksSection**

Replace the segment-based loading with unified fetch + filter:

1. Fetch both `getTasks(doctorId, "pending")`, `getTasks(doctorId, "completed")`, and `getReviewQueue(doctorId, "pending_review")` on mount
2. Normalize review items with `_type: "review"`, tasks with `_type: "task"`
3. Merge into single array, sorted by due date
4. Filter by active chip:
   - `all` → pending tasks + pending reviews
   - `review` → reviews only
   - `task` → tasks only (status=pending)
   - `done` → completed/cancelled tasks + reviewed items
5. Group filtered items by date
6. Render with centered date headers

Keep the existing `TaskDetailPanel`, `CreateTaskDialog`, `PostponeDialog`, `CancelDialog`, and `ReviewDetail` drill-in.

- [ ] **Step 5: Verify task view**

Open tasks tab. Verify:
- Filter chips: 全部 / 待审核 / 待办 / 已完成
- Date groups with centered headers
- Review items show "待审核" chip
- Tasks show type chip (随访, 检验, etc.)
- Tap drill-in works for both types

- [ ] **Step 6: Commit**

```bash
git add frontend/web/src/pages/doctor/TasksSection.jsx
git commit -m "feat: unified task list with filter chips, merged reviews and tasks"
```

---

## Task 5: Briefing Backend Endpoint

**Files:**
- Create: `src/channels/web/ui/briefing_handlers.py`
- Modify: `src/channels/web/ui/__init__.py:26-43`

- [ ] **Step 1: Create briefing handler — data layer**

Create `src/channels/web/ui/briefing_handlers.py`:

```python
"""
AI agent briefing endpoint — generates proactive clinical insights for the
doctor's landing page.

Phase 1: database-driven cards (overdue tasks, pending reviews).
Phase 2: LLM-driven cards (trend detection, pattern recognition).
"""
from __future__ import annotations

from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func

from channels.web.ui.patient_detail_handlers import _require_doctor
from db.engine import get_session
from db.models.patient import PatientDB
from db.models.records import MedicalRecordDB
from db.models.tasks import DoctorTask
from db.models.review_queue import ReviewQueueDB

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/doctor/briefing")
async def get_briefing(doctor_id: str = Depends(_require_doctor)):
    """Return structured briefing cards for the doctor's landing page."""
    cards = []
    async with get_session() as s:
        # 1. Overdue tasks
        today = date.today()
        overdue_q = (
            select(DoctorTask)
            .where(DoctorTask.doctor_id == doctor_id)
            .where(DoctorTask.status == "pending")
            .where(DoctorTask.due_at < datetime.combine(today, datetime.min.time()))
        )
        overdue = (await s.execute(overdue_q)).scalars().all()
        for t in overdue:
            days = (today - t.due_at.date()).days
            patient_name = ""
            if t.patient_id:
                p = await s.get(PatientDB, t.patient_id)
                patient_name = p.name if p else ""
            cards.append({
                "type": "urgent",
                "title": f"{patient_name} {t.title}" if patient_name else t.title,
                "context": f"逾期{days}天 · 建议尽快处理",
                "task_id": t.id,
                "patient_id": t.patient_id,
                "actions": ["complete", "postpone", "view"],
            })

        # 2. Pending reviews
        review_q = (
            select(ReviewQueueDB)
            .where(ReviewQueueDB.doctor_id == doctor_id)
            .where(ReviewQueueDB.status == "pending_review")
        )
        reviews = (await s.execute(review_q)).scalars().all()
        if reviews:
            items = []
            for r in reviews:
                items.append({
                    "patient_name": r.patient_name or "",
                    "chief_complaint": r.chief_complaint or "",
                    "record_id": r.record_id,
                    "queue_id": r.id,
                })
            cards.append({
                "type": "pending_review",
                "title": f"{len(reviews)}条问诊待审核",
                "items": items,
            })

        # 3. Completed today count
        completed_q = (
            select(func.count())
            .select_from(DoctorTask)
            .where(DoctorTask.doctor_id == doctor_id)
            .where(DoctorTask.status == "completed")
            .where(DoctorTask.updated_at >= datetime.combine(today, datetime.min.time()))
        )
        completed_today = (await s.execute(completed_q)).scalar() or 0

    return {"cards": cards, "completed_today": completed_today}
```

- [ ] **Step 2: Register router**

In `src/channels/web/ui/__init__.py`, add:

```python
from channels.web.ui.briefing_handlers import router as _briefing_router
```

And in the include section:
```python
router.include_router(_briefing_router)
```

- [ ] **Step 3: Test endpoint**

Run: `curl -H "Authorization: Bearer <token>" http://localhost:8000/api/doctor/briefing | python -m json.tool`
Expected: JSON with `cards` array and `completed_today` count.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/ui/briefing_handlers.py src/channels/web/ui/__init__.py
git commit -m "feat: add /api/doctor/briefing endpoint for agent briefing cards"
```

---

## Task 6: Briefing Frontend

**Files:**
- Create: `frontend/web/src/pages/doctor/BriefingSection.jsx`
- Create: `frontend/web/src/pages/doctor/BriefingCard.jsx`
- Modify: `frontend/web/src/api.js`

- [ ] **Step 1: Add API function**

In `api.js`, add:

```jsx
export async function getBriefing(doctorId) {
  return _get(`/api/doctor/briefing`, { doctor_id: doctorId });
}
```

- [ ] **Step 2: Create BriefingCard component**

Create `frontend/web/src/pages/doctor/BriefingCard.jsx`:

```jsx
import { Box, Typography } from "@mui/material";

const CARD_STYLES = {
  urgent: { bg: "#FEF0EE", dot: "#E8533F" },
  pending_review: { bg: "#FFF7E6", dot: "#F59E0B" },
  ai_discovery: { bg: "#E8F0FE", dot: "#1B6EF3" },
  pattern: { bg: "#E8F5E9", dot: "#07C160" },
};

export default function BriefingCard({ card, onAction }) {
  const style = CARD_STYLES[card.type] || CARD_STYLES.urgent;

  if (card.type === "pending_review" && card.items) {
    return (
      <Box sx={{ bgcolor: "#fff", borderRadius: "4px", p: 1.5, mb: 0.8 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.2, mb: 1 }}>
          <Box sx={{ width: 40, height: 40, borderRadius: "4px", bgcolor: style.bg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: style.dot }} />
          </Box>
          <Typography sx={{ fontSize: 15, fontWeight: 500 }}>{card.title}</Typography>
        </Box>
        <Box sx={{ ml: "52px" }}>
          {card.items.map((item, i) => (
            <Box key={i} onClick={() => onAction?.("review", item)} sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", py: 1, borderTop: "0.5px solid #f0f0f0", cursor: "pointer" }}>
              <Box>
                <Typography sx={{ fontSize: 13, color: "#333" }}>{item.patient_name} · {item.chief_complaint}</Typography>
              </Box>
              <Typography sx={{ fontSize: 12, px: 1.2, py: 0.5, borderRadius: "4px", bgcolor: "#07C160", color: "#fff", flexShrink: 0 }}>审核</Typography>
            </Box>
          ))}
        </Box>
      </Box>
    );
  }

  return (
    <Box onClick={() => onAction?.(card.type, card)} sx={{ bgcolor: "#fff", borderRadius: "4px", p: 1.5, mb: 0.8, display: "flex", alignItems: "center", gap: 1.2, cursor: "pointer" }}>
      <Box sx={{ width: 40, height: 40, borderRadius: "4px", bgcolor: style.bg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: style.dot }} />
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: 15, fontWeight: 500 }}>{card.title}</Typography>
        <Typography sx={{ fontSize: 12, color: "#999", mt: 0.3 }}>{card.context}</Typography>
      </Box>
      <Typography sx={{ fontSize: 16, color: "#ccc" }}>›</Typography>
    </Box>
  );
}
```

- [ ] **Step 3: Create BriefingSection**

Create `frontend/web/src/pages/doctor/BriefingSection.jsx`:

```jsx
import { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import { getBriefing } from "../../api";
import { useDoctorStore } from "../../store/doctorStore";
import BriefingCard from "./BriefingCard";

export default function BriefingSection({ doctorId, onNavigateToChat }) {
  const doctorName = useDoctorStore((s) => s.doctorName);
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!doctorId) return;
    let cancelled = false;
    getBriefing(doctorId).then((d) => { if (!cancelled) setData(d); }).catch(() => {});
    const id = setInterval(() => {
      getBriefing(doctorId).then((d) => { if (!cancelled) setData(d); }).catch(() => {});
    }, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, [doctorId]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "早上好" : hour < 18 ? "下午好" : "晚上好";
  const cardCount = data?.cards?.length || 0;

  function handleAction(type, item) {
    // TODO: wire to navigation — review drill-in, task detail, etc.
    console.log("briefing action", type, item);
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      {/* Header */}
      <Box sx={{ bgcolor: "#fff", px: 2, pt: 2, pb: 1.5, borderBottom: "0.5px solid #d9d9d9" }}>
        <Typography sx={{ fontSize: 17, fontWeight: 800, color: "#07C160" }}>{greeting}，{doctorName || "医生"}</Typography>
        <Typography sx={{ fontSize: 12, color: "#999", mt: 0.3 }}>
          {cardCount > 0 ? `${cardCount} 件事需要关注` : "暂无待处理事项"}
        </Typography>
      </Box>

      {/* Cards */}
      <Box sx={{ flex: 1, overflowY: "auto", p: 1 }}>
        {data?.cards?.map((card, i) => (
          <BriefingCard key={i} card={card} onAction={handleAction} />
        ))}

        {/* Completed today */}
        {(data?.completed_today || 0) > 0 && (
          <Box sx={{ bgcolor: "#fff", borderRadius: "4px", px: 1.5, py: 1.2, mb: 0.8 }}>
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <Typography sx={{ fontSize: 13, color: "#999" }}>今日已处理 {data.completed_today} 项</Typography>
              <Typography sx={{ fontSize: 11, color: "#07C160" }}>查看 ›</Typography>
            </Box>
          </Box>
        )}

        {/* Ask AI bar */}
        <Box onClick={onNavigateToChat} sx={{ bgcolor: "#fff", borderRadius: "4px", px: 1.5, py: 1.2, display: "flex", alignItems: "center", gap: 1, border: "0.5px solid #d9d9d9", cursor: "pointer" }}>
          <Box sx={{ width: 28, height: 28, borderRadius: "4px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Typography sx={{ color: "#fff", fontSize: 11, fontWeight: "bold" }}>AI</Typography>
          </Box>
          <Typography sx={{ fontSize: 14, color: "#bbb" }}>问 AI 任何问题...</Typography>
        </Box>
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Verify briefing**

Start backend and frontend. Navigate to home tab. Verify:
- Greeting with doctor name
- Cards from backend data
- "问 AI" bar navigates to chat
- Chat has back button

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/doctor/BriefingSection.jsx frontend/web/src/pages/doctor/BriefingCard.jsx frontend/web/src/api.js
git commit -m "feat: AI agent briefing landing page with card components"
```

---

## Task 7: Final Integration + Cleanup

**Files:**
- Modify: `frontend/web/src/pages/doctor/WorkingContextHeader.jsx` (if needed)
- Verify all views work together

- [ ] **Step 1: Remove DashboardSummary from ChatSection**

Since the briefing page replaces the dashboard-at-top-of-chat pattern, remove the `<DashboardSummary>` component from `ChatSection.jsx`. The briefing is now the landing page.

- [ ] **Step 2: End-to-end verification**

Verify the full flow:
1. App opens → 首页 (briefing) is default
2. Bottom nav shows: 首页 | 患者 | 任务 | 设置
3. Briefing shows cards, "问 AI" bar at bottom
4. Tap "问 AI" → chat opens with back button
5. Back → returns to briefing
6. Patients tab → patient list → tap patient → sticky header + collapsible profile + tabs
7. Tasks tab → unified list with filter chips + centered date headers
8. Settings tab → unchanged

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: complete UI restructure — briefing, patient detail, unified tasks"
```
