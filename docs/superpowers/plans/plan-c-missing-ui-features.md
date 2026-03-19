# Plan C: Missing UI Features

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add missing UI features (task swipe actions, task segments, patient detail menu, PDF export selector, expanded settings) to match the UX design spec.

**Architecture:** Extend existing section components with new sub-components. Follow the established pattern of co-located hooks + presentational components. New sub-pages use the existing push-navigation pattern (state-driven in DoctorPage).

**Tech Stack:** React 19, MUI v7, touch events for swipe

**Spec:** docs/ux/design-spec.md — Screens 3, 4, 5 sections

---

## Task 1: Task Swipe Actions

Add left-swipe gesture on task rows to reveal "完成" (green) and "取消" (gray) action buttons. Tapping a button triggers the existing `handleStatus` flow. The inline `TaskActions` buttons remain for non-touch users; swipe is a touch-only shortcut.

### Files

| Action | Path |
|--------|------|
| Modify | `frontend/web/src/pages/doctor/TasksSection.jsx` |

### Steps

- [ ] **1.1** Add a `SwipeableTaskRow` wrapper component inside `TasksSection.jsx` that wraps each `TaskRow`.

The swipe detection logic (no external library):

```jsx
function SwipeableTaskRow({ children, onSwipeComplete, onSwipeCancel }) {
  const startXRef = useRef(null);
  const [offsetX, setOffsetX] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const THRESHOLD = 70; // px to trigger reveal
  const ACTION_WIDTH = 140; // total width of revealed buttons

  function handleTouchStart(e) {
    startXRef.current = e.touches[0].clientX;
  }
  function handleTouchMove(e) {
    if (startXRef.current === null) return;
    const diff = startXRef.current - e.touches[0].clientX;
    if (diff > 0) {
      setOffsetX(Math.min(diff, ACTION_WIDTH));
    } else {
      setOffsetX(0);
    }
  }
  function handleTouchEnd() {
    if (offsetX >= THRESHOLD) {
      setOffsetX(ACTION_WIDTH);
      setRevealed(true);
    } else {
      setOffsetX(0);
      setRevealed(false);
    }
    startXRef.current = null;
  }
  function handleReset() {
    setOffsetX(0);
    setRevealed(false);
  }

  return (
    <Box sx={{ position: "relative", overflow: "hidden" }}>
      {/* Action buttons behind the row */}
      <Box sx={{
        position: "absolute", right: 0, top: 0, bottom: 0,
        display: "flex", width: ACTION_WIDTH,
      }}>
        <Box onClick={() => { onSwipeComplete(); handleReset(); }}
          sx={{ flex: 1, bgcolor: "#07C160", display: "flex",
            alignItems: "center", justifyContent: "center",
            color: "#fff", fontSize: 14, fontWeight: 600 }}>
          完成
        </Box>
        <Box onClick={() => { onSwipeCancel(); handleReset(); }}
          sx={{ flex: 1, bgcolor: "#b0b0b0", display: "flex",
            alignItems: "center", justifyContent: "center",
            color: "#fff", fontSize: 14, fontWeight: 600 }}>
          取消
        </Box>
      </Box>
      {/* Sliding content */}
      <Box
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        sx={{
          transform: `translateX(-${offsetX}px)`,
          transition: startXRef.current !== null ? "none" : "transform 0.2s ease",
          bgcolor: "#fff", position: "relative", zIndex: 1,
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
```

- [ ] **1.2** In `TaskGroupList`, wrap each `TaskRow` `<Box>` with `SwipeableTaskRow`, passing `onSwipeComplete={() => onComplete(task.id, "completed")}` and `onSwipeCancel={() => onCancel(task.id)}`.

- [ ] **1.3** Only show swipe actions for tasks with `status === "pending"`. For completed/cancelled tasks, render `TaskRow` directly without `SwipeableTaskRow`.

- [ ] **1.4** Add a click-away listener: when user taps outside a revealed row, reset all swipe states. Track the currently-revealed row ID in `TaskGroupList` state to ensure only one row is revealed at a time.

### Verification

- On mobile viewport (Chrome DevTools touch simulation), left-swipe a pending task row: green "完成" and gray "取消" buttons slide in from the right.
- Tap "完成": row disappears from pending list, task status becomes `completed`.
- Tap "取消": confirmation dialog appears (reuse existing `CancelDialog`).
- Swipe on a completed/cancelled row does nothing.

### Commit

```
feat: add swipe-to-reveal actions on task rows
```

---

## Task 2: Task Segment Control

Replace the current horizontal pill filter (待处理 / 已推迟 / 已完成 / 已取消) with a three-segment iOS-style control: **今天 / 待办 / 已完成**. Each segment shows a different data view.

### Files

| Action | Path |
|--------|------|
| Modify | `frontend/web/src/pages/doctor/TasksSection.jsx` |
| Modify | `frontend/web/src/pages/doctor/constants.jsx` |

### Steps

- [ ] **2.1** In `constants.jsx`, add a new constant:

```jsx
export const TASK_SEGMENT_OPTS = [
  { value: "today", label: "今天" },
  { value: "todo", label: "待办" },
  { value: "done", label: "已完成" },
];
```

Keep the existing `TASK_STATUS_OPTS` for backward compatibility (used elsewhere).

- [ ] **2.2** In `TasksSection.jsx`, create a `SegmentControl` component:

```jsx
function SegmentControl({ value, options, onChange }) {
  return (
    <Box sx={{
      display: "flex", bgcolor: "#f2f2f2", borderRadius: "8px",
      p: "3px", mx: 2, flexShrink: 0,
    }}>
      {options.map((opt) => (
        <Box key={opt.value} onClick={() => onChange(opt.value)}
          sx={{
            flex: 1, textAlign: "center", py: 0.6,
            borderRadius: "6px", fontSize: 13, fontWeight: 600,
            cursor: "pointer", transition: "all 0.15s ease",
            bgcolor: value === opt.value ? "#fff" : "transparent",
            color: value === opt.value ? "#07C160" : "#999",
            boxShadow: value === opt.value
              ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
          }}>
          {opt.label}
        </Box>
      ))}
    </Box>
  );
}
```

- [ ] **2.3** Replace `TasksHeader` filter pills with `SegmentControl`. Change the internal state from `statusFilter` (string status value) to `segment` with values `"today"`, `"todo"`, `"done"`.

- [ ] **2.4** Update the data fetching logic in `useTasksState`:
  - `"today"` segment: fetch `status=pending`, then client-side filter to tasks where `due_at` is today. Also include `task_type === "appointment"` tasks for today.
  - `"todo"` segment: fetch `status=pending`, then client-side filter to tasks where `due_at` is after today (or null).
  - `"done"` segment: fetch `status=completed`, then also fetch `status=cancelled`, merge both lists.

- [ ] **2.5** Update `TaskGroupList` rendering per segment:
  - **今天**: Two sub-sections. First: "预约" appointments with time on left side (styled like a timeline). Second: "待办" to-do items with circular checkboxes on the left.
  - **待办**: Keep the existing date-group rendering (已逾期 / 明天 / 本周 / 之后).
  - **已完成**: Flat list sorted by `updated_at` desc, with a strikethrough title and gray text.

- [ ] **2.6** For the "今天" segment appointment rendering, create an `AppointmentRow` sub-component:

```jsx
function AppointmentRow({ task }) {
  const timeStr = task.due_at ? task.due_at.slice(11, 16) : "--:--";
  return (
    <Box sx={{ display: "flex", px: 2, py: 1.2, alignItems: "center" }}>
      <Typography sx={{ fontSize: 14, fontWeight: 600, color: "#07C160",
        width: 50, flexShrink: 0 }}>
        {timeStr}
      </Typography>
      <Box sx={{ flex: 1, ml: 1 }}>
        <Typography sx={{ fontSize: 14, fontWeight: 500 }}>
          {task.title || task.patient_name || "预约"}
        </Typography>
        {task.content && (
          <Typography variant="caption" color="text.secondary">
            {task.content}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
```

- [ ] **2.7** For the "今天" segment to-do items, create a `TodoRow` with a circular checkbox:

```jsx
function TodoRow({ task, onComplete }) {
  return (
    <Box sx={{ display: "flex", px: 2, py: 1.2, alignItems: "center" }}>
      <Box onClick={() => onComplete(task.id, "completed")}
        sx={{
          width: 22, height: 22, borderRadius: "50%",
          border: "2px solid #ddd", flexShrink: 0, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          "&:active": { borderColor: "#07C160" },
        }} />
      <Box sx={{ flex: 1, ml: 1.5 }}>
        <Typography sx={{ fontSize: 14 }}>
          {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
        </Typography>
        {task.patient_name && (
          <Typography variant="caption" color="text.secondary">
            {task.patient_name}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
```

### Verification

- The header now shows a three-segment pill control instead of four filter pills.
- "今天" shows appointments at top with times, to-do items below with checkboxes.
- "待办" shows future tasks grouped by date (same as before but without today's tasks).
- "已完成" shows both completed and cancelled tasks in a flat gray list.
- Tapping the checkbox on a to-do row completes it immediately.
- The "+" create button remains visible in all segments.

### Commit

```
feat: replace task status pills with iOS-style segment control (今天/待办/已完成)
```

---

## Task 3: Task Detail Page

Add a push-navigation detail page for a single task. Tapping a task row navigates to the detail view (hiding the bottom tab bar on mobile). The detail page shows full task info and action buttons.

### Files

| Action | Path |
|--------|------|
| Modify | `frontend/web/src/pages/doctor/TasksSection.jsx` |

### Steps

- [ ] **3.1** Add a `TaskDetailView` component inside `TasksSection.jsx`:

```jsx
function TaskDetailView({ task, onBack, onComplete, onCancel }) {
  const iconColor = TASK_TYPE_ICON_COLOR[task.task_type] || "#999";
  const TaskIcon = TASK_TYPE_ICON[task.task_type] || AssignmentOutlinedIcon;
  const statusLabel = TASK_STATUS_LABEL[task.status] || task.status;
  const isActionable = task.status === "pending";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%",
      bgcolor: "#f7f7f7" }}>
      {/* Nav bar */}
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1,
        bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center",
          gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>返回</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600,
          fontSize: 16, mr: 5 }}>任务详情</Typography>
      </Box>
      {/* Content */}
      <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
        {/* Type + Icon */}
        <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
            <Box sx={{ width: 48, height: 48, borderRadius: "12px",
              bgcolor: iconColor, display: "flex", alignItems: "center",
              justifyContent: "center" }}>
              <TaskIcon sx={{ color: "#fff", fontSize: 26 }} />
            </Box>
            <Box>
              <Typography sx={{ fontWeight: 700, fontSize: 17 }}>
                {task.title || TASK_TYPE_LABEL[task.task_type]}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {TASK_TYPE_LABEL[task.task_type]}
              </Typography>
            </Box>
          </Box>
          {/* Fields */}
          {task.patient_name && <DetailField label="关联患者"
            value={task.patient_name} />}
          <DetailField label="创建时间"
            value={task.created_at?.slice(0, 16).replace("T", " ")} />
          {task.due_at && <DetailField label="截止时间"
            value={task.due_at.slice(0, 16).replace("T", " ")} />}
          <DetailField label="状态" value={statusLabel} />
          {task.content && <DetailField label="备注" value={task.content} />}
        </Box>
      </Box>
      {/* Action buttons */}
      {isActionable && (
        <Box sx={{ p: 2, bgcolor: "#fff",
          borderTop: "1px solid #f2f2f2" }}>
          <Box onClick={() => onComplete(task.id, "completed")}
            sx={{ py: 1.3, borderRadius: 2, bgcolor: "#07C160",
              textAlign: "center", color: "#fff", fontWeight: 600,
              fontSize: 16, mb: 1, cursor: "pointer",
              "&:active": { opacity: 0.8 } }}>
            标记完成
          </Box>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Box sx={{ flex: 1, py: 1.1, borderRadius: 2, border: "1px solid #e5e5e5",
              textAlign: "center", color: "#333", fontSize: 14, cursor: "pointer",
              "&:active": { bgcolor: "#f5f5f5" } }}>
              编辑
            </Box>
            <Box onClick={() => onCancel(task.id)}
              sx={{ flex: 1, py: 1.1, borderRadius: 2, textAlign: "center",
                color: "#e74c3c", fontSize: 14, cursor: "pointer",
                "&:active": { bgcolor: "#fef2f2" } }}>
              取消任务
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  );
}

function DetailField({ label, value }) {
  return (
    <Box sx={{ display: "flex", py: 0.8,
      borderBottom: "1px solid #f8f8f8" }}>
      <Typography sx={{ fontSize: 14, color: "#999", width: 80,
        flexShrink: 0 }}>{label}</Typography>
      <Typography sx={{ fontSize: 14, color: "#333",
        flex: 1 }}>{value || "—"}</Typography>
    </Box>
  );
}
```

- [ ] **3.2** Add `selectedTask` state to `useTasksState`. When a user taps a `TaskRow`, set `selectedTask` to that task object.

- [ ] **3.3** In `TasksSection`, when `selectedTask` is set, render `TaskDetailView` instead of the main list view. Pass `onBack={() => setSelectedTask(null)}`.

- [ ] **3.4** Import `ArrowBackIcon` (already imported in SettingsSection; add import to TasksSection).

- [ ] **3.5** Wire up "标记完成" to call `handleStatus(task.id, "completed")` then `setSelectedTask(null)`. Wire up "取消任务" to open the existing `CancelDialog`.

### Verification

- Tap a task row: the list view is replaced by the detail view with a back arrow.
- Detail view shows type icon, title, linked patient, timestamps, status, content.
- "标记完成" (green button) completes the task and returns to list.
- "取消任务" (red text) opens the cancel confirmation.
- Back arrow returns to the list.
- On completed/cancelled tasks, action buttons are hidden.

### Commit

```
feat: add task detail push-navigation page
```

---

## Task 4: Patient Detail Menu Navigation

Add WeChat settings-style menu rows between the diagnosis tags and the record list on the patient detail page. Each row navigates to a filtered sub-page.

### Files

| Action | Path |
|--------|------|
| Modify | `frontend/web/src/pages/doctor/PatientDetail.jsx` |
| Modify | `frontend/web/src/pages/doctor/constants.jsx` |

### Steps

- [ ] **4.1** In `constants.jsx`, add menu configuration:

```jsx
import CalendarMonthOutlinedIcon from "@mui/icons-material/CalendarMonthOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";

export const PATIENT_MENU_ITEMS = [
  {
    key: "visit",
    label: "就诊记录",
    icon: CalendarMonthOutlinedIcon,
    iconColor: "#07C160",
    iconBg: "#e8f5e9",
    recordTypes: ["visit", "dictation", "interview_summary"],
  },
  {
    key: "prescription",
    label: "处方记录",
    icon: DescriptionOutlinedIcon,
    iconColor: "#e8833a",
    iconBg: "#fff3e0",
    recordTypes: ["visit"],   // prescriptions extracted from visit records
    filterTag: "处方",
  },
  {
    key: "lab",
    label: "检验报告",
    icon: ScienceOutlinedIcon,
    iconColor: "#1890ff",
    iconBg: "#e3f2fd",
    recordTypes: ["lab"],
  },
  {
    key: "allergy",
    label: "过敏信息",
    icon: WarningAmberOutlinedIcon,
    iconColor: "#e74c3c",
    iconBg: "#fef2f2",
    recordTypes: [],          // extracted from patient tags/records
    filterTag: "过敏",
  },
];
```

- [ ] **4.2** In `PatientDetail.jsx`, add a `PatientMenuSection` component:

```jsx
function PatientMenuSection({ records, onNavigate }) {
  // Count records per menu category
  const counts = {};
  PATIENT_MENU_ITEMS.forEach((item) => {
    if (item.recordTypes.length > 0) {
      counts[item.key] = records.filter(
        (r) => item.recordTypes.includes(r.record_type)
      ).length;
    } else {
      counts[item.key] = 0; // placeholder for allergy/prescription
    }
  });
  // Detect abnormal labs (any lab record with "异常" in content or tags)
  const hasAbnormalLab = records.some(
    (r) => r.record_type === "lab" &&
      ((r.content || "").includes("异常") ||
       (r.tags || "").includes("异常"))
  );

  return (
    <Box sx={{ bgcolor: "#fff", mb: 0.8, py: 0.5 }}>
      {PATIENT_MENU_ITEMS.map((item, idx) => {
        const Icon = item.icon;
        const count = counts[item.key];
        return (
          <Box key={item.key} onClick={() => onNavigate(item.key)}
            sx={{
              display: "flex", alignItems: "center", px: 2, py: 1.3,
              cursor: "pointer",
              borderBottom: idx < PATIENT_MENU_ITEMS.length - 1
                ? "1px solid #f5f5f5" : "none",
              "&:active": { bgcolor: "#f9f9f9" },
            }}>
            <Box sx={{
              width: 36, height: 36, borderRadius: "8px",
              bgcolor: item.iconBg,
              display: "flex", alignItems: "center",
              justifyContent: "center", flexShrink: 0, mr: 1.5,
            }}>
              <Icon sx={{ color: item.iconColor, fontSize: 20 }} />
            </Box>
            <Typography sx={{ flex: 1, fontSize: 15, color: "#222" }}>
              {item.label}
            </Typography>
            {count > 0 && (
              <Typography sx={{
                fontSize: 13, mr: 0.5,
                color: item.key === "lab" && hasAbnormalLab
                  ? "#e74c3c" : "#999",
                fontWeight: item.key === "lab" && hasAbnormalLab
                  ? 600 : 400,
              }}>
                {count} 项{item.key === "lab" && hasAbnormalLab
                  ? " (有异常)" : ""}
              </Typography>
            )}
            <ArrowBackIcon sx={{
              fontSize: 16, color: "#ccc",
              transform: "rotate(180deg)",
            }} />
          </Box>
        );
      })}
    </Box>
  );
}
```

- [ ] **4.3** Add a `RecordSubPage` component for listing filtered records:

```jsx
function RecordSubPage({ title, records, doctorId, onBack, setRecords }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column",
      height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48,
        px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5",
        flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex",
          alignItems: "center", gap: 0.3, cursor: "pointer",
          color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>
            返回
          </Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center",
          fontWeight: 600, fontSize: 16, mr: 5 }}>{title}</Typography>
      </Box>
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {records.length === 0 ? (
          <Box sx={{ py: 6, textAlign: "center" }}>
            <Typography color="text.secondary">暂无记录</Typography>
          </Box>
        ) : (
          records.map((r) => (
            <RecordCard key={r.id} record={r} doctorId={doctorId}
              onUpdated={(updated) => setRecords((prev) =>
                prev.map((x) => x.id === updated.id
                  ? { ...x, ...updated } : x))}
              onDeleted={(id) => setRecords((prev) =>
                prev.filter((x) => x.id !== id))} />
          ))
        )}
        <Box sx={{ height: 24 }} />
      </Box>
    </Box>
  );
}
```

- [ ] **4.4** Add `menuSubpage` state to `usePatientDetailState`. When set (e.g., `"visit"`, `"lab"`), render `RecordSubPage` instead of the main detail view. Pass records filtered by the corresponding `recordTypes` from `PATIENT_MENU_ITEMS`.

- [ ] **4.5** In the main `PatientDetail` render, insert `<PatientMenuSection>` between `PatientProfileBlock` and `RecordListSection`. Import `ArrowBackIcon` and the new constants.

- [ ] **4.6** Import `PATIENT_MENU_ITEMS` from `constants.jsx` and `RecordCard` (already imported).

### Verification

- Patient detail now shows four menu rows between the profile block and records list.
- Each row shows an icon, label, count, and chevron.
- Tapping "就诊记录" pushes a sub-page showing only visit/dictation/interview_summary records.
- Tapping "检验报告" shows lab records; if any contain "异常", the count text is red.
- Back button returns to the main patient detail view.

### Commit

```
feat: add WeChat-style menu navigation to patient detail page
```

---

## Task 5: PDF Export Content Selector

Replace the simple "病历PDF" download button with a bottom sheet that lets the doctor select which sections to include and how many visit records to export.

### Files

| Action | Path |
|--------|------|
| Modify | `frontend/web/src/pages/doctor/PatientDetail.jsx` |
| Modify | `frontend/web/src/api/doctor.js` |
| Modify | `src/channels/web/export.py` |
| Modify | `src/services/export/pdf_export.py` |

### Steps

- [ ] **5.1** In `PatientDetail.jsx`, create a `PdfExportSheet` bottom-sheet component:

```jsx
const PDF_SECTIONS = [
  { key: "basic_info", label: "基本信息", alwaysOn: true },
  { key: "diagnosis", label: "诊断信息", default: true },
  { key: "visits", label: "就诊记录", default: true },
  { key: "prescriptions", label: "处方记录", default: true },
  { key: "labs", label: "检验报告", default: true },
  { key: "allergies", label: "过敏信息", default: false },
];

const VISIT_RANGE_OPTS = [
  { value: 5, label: "最近5次" },
  { value: 10, label: "最近10次" },
  { value: 0, label: "全部" },
];

function PdfExportSheet({ open, isMobile, exporting, onClose, onExport }) {
  const [selected, setSelected] = useState(() =>
    PDF_SECTIONS.filter((s) => s.alwaysOn || s.default)
      .map((s) => s.key)
  );
  const [visitRange, setVisitRange] = useState(5);

  function toggle(key) {
    const sec = PDF_SECTIONS.find((s) => s.key === key);
    if (sec?.alwaysOn) return;
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key)
        : [...prev, key]
    );
  }

  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile
        ? { position: "fixed", bottom: 0, left: 0, right: 0,
            m: 0, borderRadius: "16px 16px 0 0", width: "100%",
            maxHeight: "70vh" }
        : { borderRadius: 2, minWidth: 340 } }}
      sx={isMobile ? { "& .MuiDialog-container":
        { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 16, mb: 2,
          textAlign: "center" }}>
          导出病历PDF
        </Typography>
        {PDF_SECTIONS.map((sec) => (
          <Box key={sec.key} onClick={() => toggle(sec.key)}
            sx={{ display: "flex", alignItems: "center", py: 1,
              cursor: sec.alwaysOn ? "default" : "pointer" }}>
            <Box sx={{
              width: 20, height: 20, borderRadius: "4px", mr: 1.5,
              border: "2px solid",
              borderColor: selected.includes(sec.key)
                ? "#07C160" : "#ddd",
              bgcolor: selected.includes(sec.key)
                ? "#07C160" : "transparent",
              display: "flex", alignItems: "center",
              justifyContent: "center",
            }}>
              {selected.includes(sec.key) && (
                <Typography sx={{ color: "#fff", fontSize: 12,
                  lineHeight: 1 }}>✓</Typography>
              )}
            </Box>
            <Typography sx={{
              fontSize: 15,
              color: sec.alwaysOn ? "#999" : "#333",
            }}>
              {sec.label}
              {sec.alwaysOn && " (必选)"}
            </Typography>
          </Box>
        ))}
        {/* Visit range selector (only when visits checked) */}
        {selected.includes("visits") && (
          <Box sx={{ mt: 1.5, ml: 3.5 }}>
            <Typography sx={{ fontSize: 12, color: "#999",
              mb: 0.5 }}>
              就诊记录范围
            </Typography>
            <Box sx={{ display: "flex", gap: 0.6 }}>
              {VISIT_RANGE_OPTS.map((opt) => (
                <Box key={opt.value}
                  onClick={() => setVisitRange(opt.value)}
                  sx={{
                    px: 1.2, py: 0.3, borderRadius: "12px",
                    fontSize: 12, cursor: "pointer",
                    bgcolor: visitRange === opt.value
                      ? "#07C160" : "#f2f2f2",
                    color: visitRange === opt.value
                      ? "#fff" : "#666",
                    fontWeight: visitRange === opt.value
                      ? 600 : 400,
                  }}>
                  {opt.label}
                </Box>
              ))}
            </Box>
          </Box>
        )}
        <Box onClick={!exporting ? () => onExport({
          sections: selected, visitRange }) : undefined}
          sx={{ mt: 2.5, py: 1.3, borderRadius: 2,
            bgcolor: exporting ? "#ccc" : "#07C160",
            textAlign: "center", color: "#fff", fontWeight: 600,
            fontSize: 16, cursor: exporting ? "default" : "pointer",
            "&:active": exporting ? {} : { opacity: 0.8 } }}>
          {exporting ? "生成中…" : "生成PDF"}
        </Box>
      </Box>
    </Dialog>
  );
}
```

- [ ] **5.2** In `PatientDetail.jsx`, add state `pdfSheetOpen` to `usePatientDetailState`. Change the "病历PDF" button's `onClick` to open the sheet instead of calling `handleExportPdf` directly.

- [ ] **5.3** Update `handleExportPdf` to accept `{ sections, visitRange }` and pass them to the API call.

- [ ] **5.4** In `api/doctor.js`, update `exportPatientPdf` to accept optional `sections` and `visitRange` parameters:

```js
export async function exportPatientPdf(
  patientId, doctorId,
  { sections, visitRange } = {}
) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  if (sections && sections.length > 0) {
    qs.set("sections", sections.join(","));
  }
  if (visitRange !== undefined && visitRange > 0) {
    qs.set("visit_limit", String(visitRange));
  }
  // ... rest same as current implementation
}
```

- [ ] **5.5** In `src/channels/web/export.py`, update `export_patient_pdf` endpoint to accept optional query params:

```python
@router.get("/patient/{patient_id}/pdf")
async def export_patient_pdf(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    sections: str | None = Query(default=None),      # NEW
    visit_limit: int | None = Query(default=None),    # NEW
):
```

Parse `sections` as a comma-separated string into a set. Pass `sections` and `visit_limit` to `generate_records_pdf`.

- [ ] **5.6** In `src/services/export/pdf_export.py`, update `generate_records_pdf` to accept `sections: set[str] | None = None` and `visit_limit: int | None = None`. When `sections` is provided:
  - Always include the patient info block (basic_info).
  - Filter records by type based on selected sections before rendering.
  - Apply `visit_limit` to visit-type records only.

- [ ] **5.7** Close the bottom sheet and show success feedback after PDF download completes.

### Verification

- Clicking "病历PDF" opens a bottom sheet with section checkboxes.
- "基本信息" is always checked and cannot be unchecked.
- Unchecking "检验报告" then generating PDF: the result omits lab records.
- Selecting "最近5次" with 10+ visit records: PDF contains only the 5 most recent visits.
- The generate button shows "生成中…" during download, then the sheet closes.

### Commit

```
feat: add PDF export content selector bottom sheet
```

---

## Task 6: Settings Expansion

Restructure the Settings page with grouped menu sections (WeChat-style), a richer profile card, and new stub pages for AI settings, knowledge base, notifications, and about.

### Files

| Action | Path |
|--------|------|
| Modify | `frontend/web/src/pages/doctor/SettingsSection.jsx` |
| Modify | `frontend/web/src/api/doctor.js` |

### Steps

- [ ] **6.1** Add knowledge base API functions to `api/doctor.js`:

```js
export async function getKnowledgeItems(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/knowledge?${qs.toString()}`);
}

export async function deleteKnowledgeItem(doctorId, itemId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/knowledge/${itemId}?${qs.toString()}`, {
    method: "DELETE",
  });
}

export async function addKnowledgeItem(doctorId, content) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/knowledge?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}
```

> **Note:** The backend API endpoints `/api/manage/knowledge` may need to be created if they don't exist. Check `src/channels/web/` for existing knowledge management routes. If missing, add a simple CRUD router in `src/channels/web/knowledge.py` using the existing `list_doctor_knowledge_items`, `add_doctor_knowledge_item` CRUD functions from `db/crud/doctor.py`. Register the router in `src/channels/web/__init__.py`.

- [ ] **6.2** Replace `AccountBlock` with a `ProfileCard` component featuring a green background header:

```jsx
function ProfileCard({ doctorId, doctorName, specialty }) {
  return (
    <Box sx={{
      bgcolor: "#07C160", borderRadius: "0 0 16px 16px",
      px: 2.5, pt: 3, pb: 2.5, mb: 1.5,
    }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        <Box sx={{
          width: 60, height: 60, borderRadius: "50%",
          bgcolor: "rgba(255,255,255,0.25)",
          display: "flex", alignItems: "center",
          justifyContent: "center",
        }}>
          <LocalHospitalOutlinedIcon
            sx={{ color: "#fff", fontSize: 30 }} />
        </Box>
        <Box>
          <Typography sx={{ fontWeight: 700, fontSize: 20,
            color: "#fff" }}>
            {doctorName || "未设置"}
          </Typography>
          <Typography sx={{ fontSize: 13,
            color: "rgba(255,255,255,0.8)" }}>
            {specialty || "未设置科室"} · {doctorId}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
```

- [ ] **6.3** Create grouped settings menu sections. Replace the flat list with groups:

```jsx
const SETTINGS_GROUPS = [
  {
    title: "个人信息",
    items: [
      { key: "name", label: "昵称", sublabel: (s) => s.doctorName || "未设置" },
      { key: "specialty", label: "科室专业", sublabel: (s) => s.specialty || "未设置" },
      { key: "visitScenario", label: "诊疗场景", sublabel: (s) => s.visitScenario || "未设置" },
      { key: "noteStyle", label: "病历风格", sublabel: (s) => s.noteStyle || "未设置" },
    ],
  },
  {
    title: "AI 设置",
    items: [
      { key: "aiSettings", label: "AI助手设置", sublabel: () => "模型与行为配置" },
      { key: "knowledge", label: "知识库管理", sublabel: () => "自定义医学知识" },
    ],
  },
  {
    title: "文档管理",
    items: [
      { key: "template", label: "报告模板", sublabel: () => "自定义门诊病历报告格式" },
    ],
  },
  {
    title: "系统",
    items: [
      { key: "notifications", label: "通知设置", sublabel: () => "任务提醒方式" },
      { key: "general", label: "通用设置", sublabel: () => "语言、主题" },
      { key: "about", label: "关于", sublabel: () => "版本信息" },
    ],
  },
];
```

- [ ] **6.4** Render the groups in the main settings view:

```jsx
{SETTINGS_GROUPS.map((group) => (
  <Box key={group.title}>
    <Box sx={{ px: 2, pt: 2, pb: 0.6 }}>
      <Typography sx={{ fontSize: 12, color: "#999",
        fontWeight: 500 }}>{group.title}</Typography>
    </Box>
    <Box sx={{ bgcolor: "#fff" }}>
      {group.items.map((item, idx) => (
        <SettingsRow key={item.key}
          icon={getSettingsIcon(item.key)}
          label={item.label}
          sublabel={item.sublabel(settingsState)}
          onClick={() => handleSettingsNav(item.key)}
        />
      ))}
    </Box>
  </Box>
))}
```

- [ ] **6.5** Add a `KnowledgeSubpage` component that lists `doctor_knowledge_items` with ability to add/delete:

```jsx
function KnowledgeSubpage({ doctorId, onBack }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    getKnowledgeItems(doctorId)
      .then((d) => setItems(Array.isArray(d) ? d : (d.items || [])))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [doctorId]);

  async function handleAdd() {
    if (!newContent.trim()) return;
    setAdding(true);
    try {
      const item = await addKnowledgeItem(doctorId, newContent.trim());
      setItems((prev) => [item, ...prev]);
      setNewContent("");
    } catch {}
    finally { setAdding(false); }
  }

  async function handleDelete(itemId) {
    try {
      await deleteKnowledgeItem(doctorId, itemId);
      setItems((prev) => prev.filter((i) => i.id !== itemId));
    } catch {}
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column",
      height: "100%", bgcolor: "#f7f7f7" }}>
      {/* Nav bar */}
      <Box sx={{ display: "flex", alignItems: "center", height: 48,
        px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5",
        flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex",
          alignItems: "center", gap: 0.3, cursor: "pointer",
          color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>
            设置
          </Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center",
          fontWeight: 600, fontSize: 16, mr: 5 }}>
          知识库管理
        </Typography>
      </Box>
      {/* Add input */}
      <Box sx={{ p: 2, bgcolor: "#fff", mb: 0.8 }}>
        <TextField fullWidth size="small" multiline minRows={2}
          placeholder="输入医学知识条目（如：高血压患者优先使用ARB类降压药）"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)} />
        <Box onClick={!adding ? handleAdd : undefined}
          sx={{ mt: 1, py: 0.8, borderRadius: 1.5,
            bgcolor: newContent.trim() ? "#07C160" : "#e0e0e0",
            textAlign: "center", color: "#fff", fontSize: 14,
            fontWeight: 600, cursor: newContent.trim()
              ? "pointer" : "default" }}>
          {adding ? "添加中…" : "添加知识"}
        </Box>
      </Box>
      {/* List */}
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center",
            py: 4 }}>
            <CircularProgress size={24} sx={{ color: "#07C160" }} />
          </Box>
        ) : items.length === 0 ? (
          <Box sx={{ py: 6, textAlign: "center" }}>
            <Typography color="text.secondary">
              暂无知识条目
            </Typography>
          </Box>
        ) : (
          items.map((item) => (
            <Box key={item.id} sx={{ bgcolor: "#fff", px: 2,
              py: 1.5, mb: 0.5 }}>
              <Typography sx={{ fontSize: 14, color: "#333",
                mb: 0.5 }}>{item.content}</Typography>
              <Box sx={{ display: "flex",
                justifyContent: "space-between" }}>
                <Typography variant="caption" color="text.secondary">
                  {item.created_at?.slice(0, 10)}
                </Typography>
                <Typography onClick={() => handleDelete(item.id)}
                  sx={{ fontSize: 12, color: "#e74c3c",
                    cursor: "pointer" }}>
                  删除
                </Typography>
              </Box>
            </Box>
          ))
        )}
      </Box>
    </Box>
  );
}
```

- [ ] **6.6** Add stub subpages for `aiSettings`, `notifications`, `general`:

```jsx
function StubSubpage({ title, onBack }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column",
      height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48,
        px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5",
        flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex",
          alignItems: "center", gap: 0.3, cursor: "pointer",
          color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>
            设置
          </Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center",
          fontWeight: 600, fontSize: 16, mr: 5 }}>
          {title}
        </Typography>
      </Box>
      <Box sx={{ flex: 1, display: "flex", alignItems: "center",
        justifyContent: "center" }}>
        <Typography color="text.secondary">即将推出</Typography>
      </Box>
    </Box>
  );
}
```

- [ ] **6.7** Add an `AboutSubpage` that shows version info:

```jsx
function AboutSubpage({ onBack }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column",
      height: "100%", bgcolor: "#f7f7f7" }}>
      {/* Nav bar (same pattern) */}
      ...
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column",
        alignItems: "center", pt: 6 }}>
        <LocalHospitalOutlinedIcon
          sx={{ fontSize: 48, color: "#07C160", mb: 1.5 }} />
        <Typography sx={{ fontWeight: 700, fontSize: 18, mb: 0.5 }}>
          AI 医生助手
        </Typography>
        <Typography variant="caption" color="text.secondary">
          版本 1.0.0 (MVP)
        </Typography>
        <Typography variant="caption" color="text.secondary"
          sx={{ mt: 0.5 }}>
          © 2024-2026 Doctor AI Agent
        </Typography>
      </Box>
    </Box>
  );
}
```

- [ ] **6.8** Update `subpage` state handling in `SettingsSection` to route to the new subpages. Extend the existing `if (subpage === "template")` pattern:

```jsx
if (subpage === "template")
  return <TemplateSubpage doctorId={doctorId} onBack={goBack} />;
if (subpage === "knowledge")
  return <KnowledgeSubpage doctorId={doctorId} onBack={goBack} />;
if (subpage === "aiSettings")
  return <StubSubpage title="AI助手设置" onBack={goBack} />;
if (subpage === "notifications")
  return <StubSubpage title="通知设置" onBack={goBack} />;
if (subpage === "general")
  return <StubSubpage title="通用设置" onBack={goBack} />;
if (subpage === "about")
  return <AboutSubpage onBack={goBack} />;
```

- [ ] **6.9** Add a red "退出登录" button at the bottom of the settings main view (always visible, not just on mobile):

```jsx
<Box sx={{ px: 2, mt: 2, mb: 4 }}>
  <Box onClick={onLogout}
    sx={{ py: 1.3, borderRadius: 2, bgcolor: "#fff",
      textAlign: "center", color: "#e74c3c", fontSize: 16,
      fontWeight: 600, cursor: "pointer",
      "&:active": { bgcolor: "#fef2f2" } }}>
    退出登录
  </Box>
</Box>
```

Remove the old mobile-only logout section.

- [ ] **6.10** Route clicks from the personal info menu items (`name`, `specialty`, `visitScenario`, `noteStyle`) to open their existing edit dialogs (same behavior, just triggered from the new menu structure).

### Verification

- Settings page now shows a green profile card at top with name, specialty, and doctor ID.
- Four grouped sections are visible: 个人信息, AI 设置, 文档管理, 系统.
- Tapping "知识库管理" opens a subpage listing knowledge items with add/delete.
- Tapping "AI助手设置", "通知设置", "通用设置" shows a "即将推出" stub page.
- Tapping "关于" shows version info.
- "退出登录" red button is visible at the bottom on all screen sizes.
- All existing functionality (name edit, specialty edit, template upload) still works through the new menu structure.

### Commit

```
feat: expand settings with grouped menus, knowledge base UI, and profile card
```

---

## Risks / Open Questions

1. **Knowledge base API endpoints may not exist.** Task 6 requires `/api/manage/knowledge` endpoints. If they don't exist, a new router file `src/channels/web/knowledge.py` must be created using the existing `list_doctor_knowledge_items` and `add_doctor_knowledge_item` CRUD functions from `src/db/crud/doctor.py`. A delete function may also need to be added to the CRUD layer.

2. **PDF section filtering is backend work.** Task 5 requires the backend `generate_records_pdf` function to accept section filters. This is a moderate change to the PDF builder — records must be pre-filtered before being passed to the renderer. The `sections` parameter semantics (which record_types map to which section keys) need clear definition.

3. **Swipe gesture on desktop.** Task 1's swipe detection uses touch events only. Desktop users will continue using the existing inline action buttons. This is intentional — swipe is a mobile-only affordance.

4. **Task segment data loading.** Task 2 changes from server-side status filtering to client-side date filtering for the "今天" segment. If the task list is large (hundreds of tasks), this may cause a brief delay. Consider paginating or adding a backend `due_date` filter in a future iteration.

5. **Prescription and allergy records (Task 4).** The current data model does not have a separate `prescription` record type — prescriptions are embedded within `visit` records. The "处方记录" and "过敏信息" menu items may show 0 items until record extraction is improved. This is acceptable for MVP; the menu structure is in place for when the data becomes available.

6. **No unit tests during MVP.** Per AGENTS.md temporary testing policy, no unit tests are added. Verify features manually via browser/DevTools touch simulation.
