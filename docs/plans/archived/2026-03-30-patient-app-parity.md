# Patient App Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade patient app to match doctor app component patterns and quality. Mobile-only, pattern parity not feature parity.

**Architecture:** Swap inline UI patterns for shared components (FilterBar, MsgAvatar, IconBadge, PageSkeleton). Add Fade tab transitions. Rebuild ProfileTab as settings list. Extract shared badge constants from doctor/constants.

**Tech Stack:** React, MUI 5, shared component library in `frontend/web/src/components/`

**Spec:** `docs/specs/2026-03-30-patient-app-parity-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/web/src/shared/badgeConfigs.js` | Create | Shared RECORD_TYPE_BADGE + ICON_BADGES extracted from doctor/constants |
| `frontend/web/src/pages/patient/constants.jsx` | Modify | Add filter configs, rename nav tab, import shared badges |
| `frontend/web/src/pages/patient/RecordsTab.jsx` | Modify | FilterBar, PageSkeleton, type filter |
| `frontend/web/src/pages/patient/subpages/RecordDetail.jsx` | Modify | Fix navigate(-1) |
| `frontend/web/src/pages/patient/ChatTab.jsx` | Modify | MsgAvatar, IconBadge, theme tokens |
| `frontend/web/src/pages/patient/MyPage.jsx` | Create | Settings list replacing ProfileTab |
| `frontend/web/src/pages/patient/ProfileTab.jsx` | Delete | Replaced by MyPage.jsx |
| `frontend/web/src/pages/patient/PatientPage.jsx` | Modify | Fade transitions, nav styling, import MyPage |
| `frontend/web/src/pages/patient/TasksTab.jsx` | Modify | FilterBar for status filter |
| `frontend/web/src/pages/patient/InterviewPage.jsx` | Modify | Token/icon cleanup |
| `frontend/web/src/pages/doctor/constants.jsx` | Modify | Re-export from shared (backward compat) |

---

### Task 1: Extract Shared Badge Constants

**Files:**
- Create: `frontend/web/src/shared/badgeConfigs.js`
- Modify: `frontend/web/src/pages/doctor/constants.jsx`
- Modify: `frontend/web/src/pages/patient/ChatTab.jsx` (import path)
- Modify: `frontend/web/src/pages/patient/RecordsTab.jsx` (import path)

- [ ] **Step 1: Create shared badge config file**

Create `frontend/web/src/shared/badgeConfigs.js` with the ICON_BADGES and RECORD_TYPE_BADGE constants extracted from doctor/constants.jsx:

```js
/**
 * Shared icon badge configs used by both doctor and patient apps.
 * Extracted from doctor/constants.jsx to avoid cross-app imports.
 */
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import FileUploadOutlinedIcon from "@mui/icons-material/FileUploadOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import EventRepeatOutlinedIcon from "@mui/icons-material/EventRepeatOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import { COLOR } from "../theme";

export const SHARED_ICON_BADGES = {
  // Chat avatars
  ai:           { icon: SmartToyOutlinedIcon, bg: COLOR.primary },
  patient:      { icon: PersonOutlineIcon, bg: COLOR.accent },
  notification: { icon: NotificationsNoneOutlinedIcon, bg: COLOR.borderLight, color: COLOR.text4 },

  // Record types
  rec_visit:     { icon: LocalHospitalOutlinedIcon, bg: COLOR.primary },
  rec_dictation: { icon: MicNoneOutlinedIcon, bg: COLOR.recordDoc },
  rec_import:    { icon: FileUploadOutlinedIcon, bg: COLOR.recordDoc },
  rec_lab:       { icon: BiotechOutlinedIcon, bg: COLOR.accent },
  rec_imaging:   { icon: MonitorHeartOutlinedIcon, bg: COLOR.accent },
  rec_surgery:   { icon: LocalHospitalOutlinedIcon, bg: COLOR.danger },
  rec_interview: { icon: ChatOutlinedIcon, bg: COLOR.primary },

  // Task types
  task_follow_up:  { icon: EventRepeatOutlinedIcon, bg: COLOR.primary },
  task_medication: { icon: MedicationOutlinedIcon, bg: COLOR.accent },
  task_checkup:    { icon: BiotechOutlinedIcon, bg: COLOR.accent },
  task_general:    { icon: AssignmentOutlinedIcon, bg: COLOR.recordDoc },
  task_imaging:    { icon: MonitorHeartOutlinedIcon, bg: COLOR.accent },
};

export const RECORD_TYPE_BADGE = {
  visit:              SHARED_ICON_BADGES.rec_visit,
  dictation:          SHARED_ICON_BADGES.rec_dictation,
  import:             SHARED_ICON_BADGES.rec_import,
  lab:                SHARED_ICON_BADGES.rec_lab,
  imaging:            SHARED_ICON_BADGES.rec_imaging,
  surgery:            SHARED_ICON_BADGES.rec_surgery,
  interview_summary:  SHARED_ICON_BADGES.rec_interview,
};

export const TASK_TYPE_BADGE = {
  follow_up:  SHARED_ICON_BADGES.task_follow_up,
  medication: SHARED_ICON_BADGES.task_medication,
  checkup:    SHARED_ICON_BADGES.task_checkup,
  general:    SHARED_ICON_BADGES.task_general,
  imaging:    SHARED_ICON_BADGES.task_imaging,
};
```

- [ ] **Step 2: Update doctor/constants.jsx to re-export from shared**

In `frontend/web/src/pages/doctor/constants.jsx`, replace the `RECORD_TYPE_BADGE` definition block (lines 347-355) with a re-export:

```js
// Record type → IconBadge config lookup (shared with patient app)
export { RECORD_TYPE_BADGE } from "../../shared/badgeConfigs";
```

Keep doctor-only `ICON_BADGES` in place (it has doctor-specific entries like qr_code, kb_*, etc.).

- [ ] **Step 3: Update patient imports**

In `frontend/web/src/pages/patient/ChatTab.jsx`, change:
```js
import { RECORD_TYPE_BADGE } from "../doctor/constants";
```
to:
```js
import { RECORD_TYPE_BADGE } from "../../shared/badgeConfigs";
```

In `frontend/web/src/pages/patient/RecordsTab.jsx`, same change:
```js
import { RECORD_TYPE_BADGE } from "../doctor/constants";
```
to:
```js
import { RECORD_TYPE_BADGE } from "../../shared/badgeConfigs";
```

- [ ] **Step 4: Verify app still renders**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds with no import errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/shared/badgeConfigs.js frontend/web/src/pages/doctor/constants.jsx frontend/web/src/pages/patient/ChatTab.jsx frontend/web/src/pages/patient/RecordsTab.jsx
git commit -m "refactor: extract shared badge configs from doctor/constants"
```

---

### Task 2: Update patient/constants.jsx

**Files:**
- Modify: `frontend/web/src/pages/patient/constants.jsx`

- [ ] **Step 1: Add filter configs and rename nav tab**

Add these exports and update NAV_TABS in `frontend/web/src/pages/patient/constants.jsx`:

1. Change the icon import: replace `SettingsOutlinedIcon` with `PersonOutlineIcon`:
```js
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
```
(Remove the `SettingsOutlinedIcon` import.)

2. In NAV_TABS, change the last entry from:
```js
  { key: "profile", label: "设置", icon: <SettingsOutlinedIcon />, title: "设置" },
```
to:
```js
  { key: "profile", label: "我的", icon: <PersonOutlineIcon />, title: "我的" },
```

3. Add these new exports at the bottom (before the `formatDate` helper):

```js
// ---------------------------------------------------------------------------
// Filter configs
// ---------------------------------------------------------------------------

export const PATIENT_RECORD_TABS = [
  { key: "", label: "全部" },
  { key: "medical", label: "病历", types: ["visit", "dictation", "import"] },
  { key: "interview", label: "问诊", types: ["interview_summary"] },
];

export const PATIENT_TASK_FILTERS = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待完成" },
  { key: "done", label: "已完成" },
];
```

- [ ] **Step 2: Verify build**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/constants.jsx
git commit -m "feat(patient): add filter configs, rename nav tab 设置→我的"
```

---

### Task 3: Upgrade RecordsTab

**Files:**
- Modify: `frontend/web/src/pages/patient/RecordsTab.jsx`
- Modify: `frontend/web/src/pages/patient/subpages/RecordDetail.jsx`

- [ ] **Step 1: Add FilterBar and PageSkeleton to RecordsTab**

In `frontend/web/src/pages/patient/RecordsTab.jsx`:

1. Add imports:
```js
import FilterBar from "../../components/FilterBar";
import PageSkeleton from "../../components/PageSkeleton";
import { PATIENT_RECORD_TABS } from "./constants";
```

2. Remove the unused `CircularProgress` from MUI imports if present.

3. Inside the component, add type filter state:
```js
const [typeFilter, setTypeFilter] = useState("");
```

4. Add filtered records computation after `loadRecords`:
```js
const filteredRecords = typeFilter
  ? records.filter(rec => {
      const tab = PATIENT_RECORD_TABS.find(t => t.key === typeFilter);
      return tab?.types?.includes(rec.record_type);
    })
  : records;
```

5. Replace the inline view toggle Box (the `<Box sx={{ display: "flex", gap: 1, px: 2, py: 1 }}>` block with list/timeline buttons) with:
```jsx
<FilterBar
  items={[{ key: "list", label: "病历" }, { key: "timeline", label: "时间线" }]}
  active={recordView}
  onChange={setRecordView}
/>
```

6. Add record type filter below the view toggle:
```jsx
{records.length > 0 && (
  <FilterBar
    items={PATIENT_RECORD_TABS}
    active={typeFilter}
    onChange={setTypeFilter}
  />
)}
```

7. Replace all `records.map` and `records.length` references in the list/timeline rendering with `filteredRecords`.

8. Wrap the entire return in PageSkeleton for the subpage transition. Replace the current conditional `if (urlSubpage && urlSubpage !== "interview")` block and the main return with:

```jsx
const detailSubpage = (urlSubpage && urlSubpage !== "interview") ? (
  <RecordDetail
    recordId={urlSubpage}
    token={token}
    onBack={() => navigate(-1)}
  />
) : null;

return (
  <PageSkeleton
    title="病历"
    isMobile
    mobileView={detailSubpage}
    listPane={
      <Box sx={{ flex: 1, overflowY: "auto", position: "relative" }}>
        <NewItemCard title="新建病历" subtitle="开始AI预问诊" onClick={onNewRecord} />
        {/* ... filter bars and record list content ... */}
      </Box>
    }
  />
);
```

- [ ] **Step 2: Fix RecordDetail back navigation**

In `frontend/web/src/pages/patient/subpages/RecordDetail.jsx`, the `onBack` prop is passed from RecordsTab. The change is already in Step 1: `onBack={() => navigate(-1)}` instead of `onBack={() => navigate("/patient/records")}`.

No changes needed inside RecordDetail.jsx itself since it calls `onBack()` which is the passed prop.

- [ ] **Step 3: Verify build and test navigation**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/patient/RecordsTab.jsx
git commit -m "feat(patient): upgrade RecordsTab with FilterBar + PageSkeleton"
```

---

### Task 4: Upgrade ChatTab

**Files:**
- Modify: `frontend/web/src/pages/patient/ChatTab.jsx`

- [ ] **Step 1: Swap avatars and icons**

In `frontend/web/src/pages/patient/ChatTab.jsx`:

1. Add import:
```js
import MsgAvatar from "../../components/MsgAvatar";
import { SHARED_ICON_BADGES } from "../../shared/badgeConfigs";
```

2. In `renderMessage`, replace the AI avatar box (the `<Box sx={{ width: 32, height: 32, borderRadius: RADIUS.sm, bgcolor: COLOR.primary, ...` block around SmartToyOutlinedIcon) with:
```jsx
<MsgAvatar isUser={false} size={32} />
```

3. Replace the patient avatar box (the `<Box sx={{ width: 32, height: 32, borderRadius: RADIUS.sm, bgcolor: COLOR.recordBlue, ...` block around PersonOutlineIcon) with:
```jsx
<IconBadge config={SHARED_ICON_BADGES.patient} size={32} solid />
```

4. In `QuickActions`, replace the inline icon wrapper boxes with IconBadge. Change the action definitions:
```js
const actions = [
  { label: "新问诊", subtitle: "AI帮您整理病情",
    icon: <IconBadge config={{ icon: AddIcon, bg: COLOR.primary }} size={36} solid />,
    onClick: onNewInterview },
  { label: "我的病历", subtitle: "查看历史记录",
    icon: <IconBadge config={{ icon: DescriptionOutlinedIcon, bg: COLOR.accent }} size={36} solid />,
    onClick: onViewRecords },
];
```

Then simplify the action rendering to remove the manual icon box wrapper — just render `{a.icon}` directly since IconBadge handles all styling.

5. Remove the inner `<Box sx={{ width: 36, height: 36, borderRadius: RADIUS.md, bgcolor: ... }}>` wrapper around each action icon since IconBadge handles it.

6. Remove unused icon imports: `SmartToyOutlinedIcon` and `PersonOutlineIcon` (now handled by MsgAvatar/IconBadge).

- [ ] **Step 2: Verify build**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/ChatTab.jsx
git commit -m "feat(patient): upgrade ChatTab with MsgAvatar + IconBadge"
```

---

### Task 5: Create MyPage (replacing ProfileTab)

**Files:**
- Create: `frontend/web/src/pages/patient/MyPage.jsx`
- Delete: `frontend/web/src/pages/patient/ProfileTab.jsx`
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx` (import swap)

- [ ] **Step 1: Create MyPage.jsx**

Create `frontend/web/src/pages/patient/MyPage.jsx`:

```jsx
/**
 * MyPage — patient "我的" settings page.
 *
 * Follows SettingsListSubpage pattern from doctor app.
 * Sections: patient info, doctor info, general (about/privacy), logout.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import PolicyOutlinedIcon from "@mui/icons-material/PolicyOutlined";
import AccountCard from "../../components/AccountCard";
import SectionLabel from "../../components/SectionLabel";
import ConfirmDialog from "../../components/ConfirmDialog";
import PageSkeleton from "../../components/PageSkeleton";
import { TYPE, ICON, COLOR, RADIUS } from "../../theme";
import AboutSubpage from "../doctor/subpages/AboutSubpage";
import PrivacySubpage from "../PrivacyPage";

function SettingsRow({ icon, label, sublabel, onClick }) {
  return (
    <Box onClick={onClick} sx={{
      display: "flex", alignItems: "center", px: 2, py: 1.5,
      cursor: onClick ? "pointer" : "default",
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      "&:active": onClick ? { bgcolor: COLOR.surface } : {},
    }}>
      <Box sx={{
        width: 36, height: 36, borderRadius: RADIUS.sm,
        bgcolor: COLOR.primaryLight,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0, mr: 1.5,
      }}>
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.text1 }}>{label}</Typography>
        {sublabel && <Typography variant="caption" color="text.secondary">{sublabel}</Typography>}
      </Box>
      {onClick && <ArrowBackIcon sx={{ fontSize: ICON.sm, color: COLOR.text4, transform: "rotate(180deg)" }} />}
    </Box>
  );
}

export default function MyPage({ patientName, doctorName, doctorSpecialty, doctorId, onLogout }) {
  const [subpage, setSubpage] = useState(null); // "about" | "privacy" | null
  const [showLogoutDialog, setShowLogoutDialog] = useState(false);

  const subpageContent = subpage === "about"
    ? <AboutSubpage onBack={() => setSubpage(null)} isMobile />
    : subpage === "privacy"
    ? <PageSkeleton title="隐私政策" onBack={() => setSubpage(null)} isMobile listPane={<PrivacySubpage />} />
    : null;

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto", bgcolor: COLOR.surfaceAlt }}>
      <SectionLabel>我的信息</SectionLabel>
      <AccountCard
        name={patientName || "患者"}
        subtitle="患者"
        color={COLOR.primary}
      />

      {doctorName && (
        <>
          <SectionLabel>我的医生</SectionLabel>
          <AccountCard
            name={doctorName}
            subtitle={doctorSpecialty || ""}
            color={COLOR.accent}
          />
        </>
      )}

      <SectionLabel>通用</SectionLabel>
      <Box sx={{ bgcolor: COLOR.white }}>
        <SettingsRow
          icon={<InfoOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="关于"
          sublabel="版本信息"
          onClick={() => setSubpage("about")}
        />
        <SettingsRow
          icon={<PolicyOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="隐私政策"
          sublabel="数据使用与保护"
          onClick={() => setSubpage("privacy")}
        />
      </Box>

      <SectionLabel>账户操作</SectionLabel>
      <Box onClick={() => setShowLogoutDialog(true)} sx={{
        bgcolor: COLOR.white, py: 1.5, textAlign: "center", cursor: "pointer",
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        "&:active": { bgcolor: COLOR.surface },
      }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.danger }}>退出登录</Typography>
      </Box>

      <Box sx={{ height: 32 }} />

      <ConfirmDialog
        open={showLogoutDialog}
        onClose={() => setShowLogoutDialog(false)}
        onCancel={() => setShowLogoutDialog(false)}
        onConfirm={onLogout}
        title="退出登录"
        message="确定要退出登录吗？"
        cancelLabel="取消"
        confirmLabel="退出"
        confirmTone="danger"
      />
    </Box>
  );

  return (
    <PageSkeleton
      title="我的"
      isMobile
      mobileView={subpageContent}
      listPane={listContent}
    />
  );
}
```

- [ ] **Step 2: Update PatientPage.jsx import**

In `frontend/web/src/pages/patient/PatientPage.jsx`, change:
```js
import ProfileTab from "./ProfileTab";
```
to:
```js
import MyPage from "./MyPage";
```

And in the render section, change:
```jsx
{tab === "profile" && (
  <ProfileTab patientName={patientName} doctorName={doctorName}
    doctorSpecialty={doctorSpecialty} doctorId={doctorId}
    onLogout={handleLogout} />
)}
```
to:
```jsx
{tab === "profile" && (
  <MyPage patientName={patientName} doctorName={doctorName}
    doctorSpecialty={doctorSpecialty} doctorId={doctorId}
    onLogout={handleLogout} />
)}
```

- [ ] **Step 3: Delete ProfileTab.jsx**

```bash
rm frontend/web/src/pages/patient/ProfileTab.jsx
```

- [ ] **Step 4: Verify build**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/patient/MyPage.jsx frontend/web/src/pages/patient/PatientPage.jsx
git rm frontend/web/src/pages/patient/ProfileTab.jsx
git commit -m "feat(patient): replace ProfileTab with MyPage settings page"
```

---

### Task 6: Add Fade Transitions to PatientPage Shell

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx`

- [ ] **Step 1: Add Fade and update nav styling**

In `frontend/web/src/pages/patient/PatientPage.jsx`:

1. Add Fade import:
```js
import { Box, Fade } from "@mui/material";
```

2. Add TYPE import (add to existing theme import):
```js
import { COLOR, TYPE } from "../../theme";
```

3. Wrap each tab in `<Fade>`. Replace the content area block:

```jsx
{/* Content area */}
<Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
  {tab === "chat" && (
    <ChatTab token={token} doctorName={doctorName} onLogout={handleLogout}
      onNewInterview={startInterview}
      onViewRecords={() => setTab("records")}
      onUnreadCountChange={setUnreadCount} />
  )}
  {tab === "records" && (
    <RecordsTab token={token} onNewRecord={startInterview} urlSubpage={urlSubpage} />
  )}
  {tab === "tasks" && <TasksTab token={token} />}
  {tab === "profile" && (
    <MyPage patientName={patientName} doctorName={doctorName}
      doctorSpecialty={doctorSpecialty} doctorId={doctorId}
      onLogout={handleLogout} />
  )}
</Box>
```

with:

```jsx
{/* Content area — Fade transition matches DoctorPage */}
<Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
  <Fade in={tab === "chat"} timeout={150} unmountOnExit>
    <Box sx={{ position: tab === "chat" ? "relative" : "absolute", inset: 0, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <ChatTab token={token} doctorName={doctorName} onLogout={handleLogout}
        onNewInterview={startInterview}
        onViewRecords={() => setTab("records")}
        onUnreadCountChange={setUnreadCount} />
    </Box>
  </Fade>
  <Fade in={tab === "records"} timeout={150} unmountOnExit>
    <Box sx={{ position: tab === "records" ? "relative" : "absolute", inset: 0, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <RecordsTab token={token} onNewRecord={startInterview} urlSubpage={urlSubpage} />
    </Box>
  </Fade>
  <Fade in={tab === "tasks"} timeout={150} unmountOnExit>
    <Box sx={{ position: tab === "tasks" ? "relative" : "absolute", inset: 0, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <TasksTab token={token} />
    </Box>
  </Fade>
  <Fade in={tab === "profile"} timeout={150} unmountOnExit>
    <Box sx={{ position: tab === "profile" ? "relative" : "absolute", inset: 0, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <MyPage patientName={patientName} doctorName={doctorName}
        doctorSpecialty={doctorSpecialty} doctorId={doctorId}
        onLogout={handleLogout} />
    </Box>
  </Fade>
</Box>
```

4. Update bottom nav styling to match DoctorPage:

Replace the BottomNavigation sx:
```js
sx={{
  flexShrink: 0, height: 56,
  borderTop: `1px solid ${COLOR.border}`, bgcolor: COLOR.surface,
  paddingBottom: "env(safe-area-inset-bottom)",
}}
```
with:
```js
sx={{
  flexShrink: 0, height: 64, bgcolor: COLOR.surface,
  borderTop: `0.5px solid ${COLOR.border}`,
  paddingBottom: "env(safe-area-inset-bottom)",
  "& .MuiBottomNavigationAction-root": { minWidth: 56, paddingTop: "8px", color: COLOR.text4 },
  "& .Mui-selected": { color: COLOR.primary },
  "& .Mui-selected .MuiBottomNavigationAction-label": { color: COLOR.primary, fontWeight: 600 },
}}
```

Remove the per-action `sx={{ "&.Mui-selected": { color: COLOR.primary } }}` since it's now handled at the parent level.

- [ ] **Step 2: Verify build**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "feat(patient): add Fade transitions and match DoctorPage nav styling"
```

---

### Task 7: Add FilterBar to TasksTab

**Files:**
- Modify: `frontend/web/src/pages/patient/TasksTab.jsx`

- [ ] **Step 1: Add FilterBar and filtering logic**

In `frontend/web/src/pages/patient/TasksTab.jsx`:

1. Add imports:
```js
import FilterBar from "../../components/FilterBar";
import { PATIENT_TASK_FILTERS } from "./constants";
```

2. Add filter state inside the component:
```js
const [filter, setFilter] = useState("all");
```

3. Add filtered task computation after the existing `pending`/`completed` splits:
```js
const filtered = filter === "all" ? tasks
  : filter === "pending" ? tasks.filter(t => t.status === "pending" || t.status === "notified")
  : tasks.filter(t => t.status === "completed");
```

4. Replace the existing pending/completed split rendering. Change the return from the current SectionLabel + TaskChecklist blocks to:

```jsx
return (
  <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
    <FilterBar items={PATIENT_TASK_FILTERS} active={filter} onChange={setFilter} />
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {filtered.length === 0 ? (
        <EmptyState icon={<AssignmentOutlinedIcon />} title="暂无任务" subtitle="医生安排的复查、用药提醒将显示在这里" />
      ) : filter === "all" ? (
        <>
          {pending.length > 0 && (
            <>
              <SectionLabel>待完成 · {pending.length}</SectionLabel>
              <TaskChecklist tasks={pending} onComplete={handleComplete} />
            </>
          )}
          {completed.length > 0 && (
            <>
              <SectionLabel sx={{ mt: 1 }}>已完成 · {completed.length}</SectionLabel>
              <TaskChecklist tasks={completed} onUndo={handleUndo} />
            </>
          )}
        </>
      ) : (
        <TaskChecklist
          tasks={filtered}
          onComplete={filter === "pending" ? handleComplete : undefined}
          onUndo={filter === "done" ? handleUndo : undefined}
        />
      )}
    </Box>
  </Box>
);
```

5. Move the early returns for loading and empty state. The loading return stays as-is. The empty-tasks return should be removed (it's now handled inside the filtered view).

- [ ] **Step 2: Verify build**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/TasksTab.jsx
git commit -m "feat(patient): add FilterBar to TasksTab"
```

---

### Task 8: InterviewPage Icon/Token Cleanup

**Files:**
- Modify: `frontend/web/src/pages/patient/InterviewPage.jsx`

- [ ] **Step 1: Fix tokens and replace emojis**

In `frontend/web/src/pages/patient/InterviewPage.jsx`:

1. Add imports:
```js
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import MsgAvatar from "../../components/MsgAvatar";
```

2. Replace hardcoded font size in chat bubbles. Find:
```js
fontSize: "0.9rem",
```
Replace with:
```js
fontSize: TYPE.body.fontSize,
```

3. In the summary sheet, replace the emoji status indicators. Find the `allFields.map` block:
```jsx
<Typography variant="caption" color="text.secondary">{val ? "✅" : "⬜"} {FIELD_LABELS[f]}</Typography>
```
Replace with:
```jsx
<Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
  {val
    ? <CheckCircleOutlineIcon sx={{ fontSize: 14, color: COLOR.primary }} />
    : <RadioButtonUncheckedIcon sx={{ fontSize: 14, color: COLOR.border }} />
  }
  <Typography variant="caption" color="text.secondary">{FIELD_LABELS[f]}</Typography>
</Box>
```

(Add `Box` to the MUI imports if not already there.)

4. In the chat message rendering, replace inline avatar boxes with MsgAvatar. Find the user/assistant message boxes and update:

For assistant messages (the `<Box sx={{ display: "flex", justifyContent: ... }}>` block), wrap with MsgAvatar on the left:
```jsx
{messages.map((msg, i) => (
  <Box key={i} sx={{ display: "flex", alignItems: msg.role === "user" ? "flex-end" : "flex-start", gap: 1, mb: 1.5, flexDirection: msg.role === "user" ? "row-reverse" : "row" }}>
    <MsgAvatar isUser={msg.role === "user"} size={32} />
    <Box sx={{
      maxWidth: "80%", px: 2, py: 1.5, borderRadius: 2,
      bgcolor: msg.role === "user" ? COLOR.wechatGreen : COLOR.white,
      color: COLOR.text2, fontSize: TYPE.body.fontSize, lineHeight: 1.6,
      whiteSpace: "pre-wrap", wordBreak: "break-word",
    }}>{msg.content}</Box>
  </Box>
))}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/InterviewPage.jsx
git commit -m "feat(patient): cleanup InterviewPage tokens and replace emojis with MUI icons"
```

---

### Task 9: Final Verification

- [ ] **Step 1: Full build check**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -10`
Expected: Build succeeds with no errors.

- [ ] **Step 2: Run lint**

Run: `cd frontend/web && npx biome check --fix frontend/web/src/pages/patient/ 2>&1 | tail -10`
Expected: No errors (warnings OK).

- [ ] **Step 3: Run UI lint**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && bash scripts/lint-ui.sh 2>&1 | tail -20`
Expected: No violations in patient files.

- [ ] **Step 4: Verify mock patient app loads**

Run: `cd frontend/web && npx vite --port 3000 &` then check `http://localhost:3000/debug/patient` renders without console errors.

- [ ] **Step 5: Final commit if lint fixes needed**

```bash
git add -A
git commit -m "chore: lint fixes for patient app parity"
```
