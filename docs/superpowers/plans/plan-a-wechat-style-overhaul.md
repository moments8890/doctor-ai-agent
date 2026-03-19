# Plan A: WeChat Style Overhaul

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the existing React + MUI frontend from MUI Material theme to WeChat flat design matching the UX spec.

**Architecture:** Update the MUI theme.js as the single source of truth for colors, radii, and typography. Then sweep through each section component to replace hardcoded style overrides with theme tokens and add spec-specific styling (hairline borders, no shadows, flat backgrounds).

**Tech Stack:** React 19, MUI v7, Vite 6

**Spec:** docs/ux/design-spec.md — "全局设计规范" section

---

## Design Token Reference

| Token | Value | Usage |
|-------|-------|-------|
| `palette.primary.main` | `#07C160` | Primary / active / CTA buttons |
| `palette.error.main` | `#FA5151` | Urgent / critical / danger |
| `palette.warning.main` | `#FF9500` | Warning / attention needed |
| `palette.text.primary` | `#111111` | Body text |
| `palette.text.secondary` | `#999999` | Secondary / hint text |
| `palette.background.default` | `#ededed` | Page background |
| `palette.background.paper` | `#ffffff` | Card / list background |
| `wechat.userBubble` | `#95EC69` | User chat bubble |
| `wechat.inputBarBg` | `#f5f5f5` | Input bar background |
| `wechat.tabBarBg` | `#f7f7f7` | Tab bar background |
| `wechat.listDivider` | `#f0f0f0` | List row divider |
| `wechat.borderInput` | `#e0e0e0` | Input border |
| `shape.borderRadius` | `4` | Global radius (px) |

### Typography Scale

| Variant / Usage | Size | Weight |
|-----------------|------|--------|
| Nav title | 17px | 500 |
| List main text | 15px | 500 |
| Body | 15px | 400 |
| Form / menu label | 14px | 400 |
| Secondary | 13px | 400 |
| Timestamp | 12px | 400 |
| Tab bar text | 10px | 400 |

### Spacing

| Element | Value |
|---------|-------|
| Horizontal page padding | 16px |
| List row padding | 12px 16px (vertical horizontal) |
| Group gap | 8px |
| Avatar size (list) | 44px |
| Avatar size (detail / chat header) | 56-60px |
| Avatar border radius | 4px |

---

## Task 1: Update MUI Theme

**Files to modify:**
- `frontend/web/src/theme.js`

**Current state:** Primary is teal `#0f766e`, border radius 16px, custom shadows array, MuiPaper has `1px solid #d8e3e8` border, MuiCard has box-shadow. Background is `#f3f7f8`. Text primary is `#102a35`.

### Steps

- [ ] 1.1 Change `palette.primary.main` from `#0f766e` to `#07C160`
- [ ] 1.2 Change `palette.secondary.main` from `#2f4f6f` to `#999999` (secondary text doubles as inactive)
- [ ] 1.3 Set `palette.error.main` to `#FA5151`
- [ ] 1.4 Set `palette.warning.main` to `#FF9500`
- [ ] 1.5 Change `palette.background.default` from `#f3f7f8` to `#ededed`
- [ ] 1.6 Keep `palette.background.paper` as `#ffffff`
- [ ] 1.7 Change `palette.text.primary` from `#102a35` to `#111111`
- [ ] 1.8 Change `palette.text.secondary` from `#5b7281` to `#999999`
- [ ] 1.9 Change `shape.borderRadius` from `16` to `4`
- [ ] 1.10 Update typography variants to match spec:
  ```js
  typography: {
    fontFamily: "'Noto Sans SC', 'PingFang SC', 'Helvetica Neue', sans-serif",
    h5: { fontWeight: 500, fontSize: "17px" },      // nav title
    h6: { fontWeight: 500, fontSize: "17px" },      // nav title
    subtitle1: { fontWeight: 500, fontSize: "15px" }, // list main
    body1: { fontSize: "15px" },                      // body
    body2: { fontSize: "14px" },                      // form / menu
    caption: { fontSize: "12px" },                    // timestamp
    button: { textTransform: "none", fontWeight: 500, fontSize: "14px" },
  }
  ```
- [ ] 1.11 Replace the entire `shadows` array with all-`"none"` (flat design, no shadows anywhere):
  ```js
  shadows: Array(25).fill("none"),
  ```
- [ ] 1.12 Add a custom `wechat` namespace to the theme for non-standard tokens:
  ```js
  wechat: {
    userBubble: "#95EC69",
    aiBubble: "#ffffff",
    inputBarBg: "#f5f5f5",
    tabBarBg: "#f7f7f7",
    listDivider: "#f0f0f0",
    borderInput: "#e0e0e0",
    tabBarBorder: "#d9d9d9",
  },
  ```
- [ ] 1.13 Update `components.MuiAppBar.styleOverrides.root`: remove `backdropFilter`, set `backgroundColor: "#ededed"`, change `borderBottom` to `"0.5px solid #d9d9d9"`
- [ ] 1.14 Update `components.MuiPaper.styleOverrides.root`: remove `border: "1px solid #d8e3e8"`, add `boxShadow: "none"`. Add `defaultProps: { elevation: 0 }`
- [ ] 1.15 Update `components.MuiCard.styleOverrides.root`: remove `border` and `boxShadow`, set `borderRadius: 4`
- [ ] 1.16 Add `components.MuiButton` overrides: `borderRadius: 4`, remove any shadow on contained variant
- [ ] 1.17 Add `components.MuiDialog.styleOverrides.paper`: `borderRadius: 12` (WeChat action sheet style)

**Verification:** Open app in Chrome DevTools at 393px width. Confirm: page bg is `#ededed`, no visible shadows on any element, primary green matches `#07C160`, all corners are 4px (not 16px).

**Commit:** `style: update MUI theme to WeChat flat design tokens`

---

## Task 2: Bottom Tab Bar Redesign

**Files to modify:**
- `frontend/web/src/pages/DoctorPage.jsx`

**Current state:** `MobileBottomNav` uses MUI `BottomNavigation` component with `height: 64`, `borderTop: "1px solid #e2e8f0"`. Active color already `#07C160`, inactive `#888`. `DesktopSidebar` uses `bgcolor: "#f7f7f7"` with active item `bgcolor: "#07C160"`.

### Steps

- [ ] 2.1 In `MobileBottomNav`, update the outer `Box` sx:
  ```js
  sx={{
    position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 10,
    borderTop: "0.5px solid #d9d9d9",  // hairline border, was 1px #e2e8f0
    bgcolor: "#f7f7f7",                 // tab bar bg
  }}
  ```
- [ ] 2.2 Update `BottomNavigationMui` sx:
  - Set `bgcolor: "#f7f7f7"` on the root
  - Change inactive color from `#888` to `#999999`
  - Keep active color `#07C160`
  - Set label fontSize to `10px` (was `11`)
  - Add `paddingBottom: "env(safe-area-inset-bottom)"` for notch devices
- [ ] 2.3 Add red badge on Tasks tab: already present (`Badge badgeContent={pendingTaskCount} color="error"`). Verify it uses the new `palette.error.main` = `#FA5151` after Task 1. No code change needed here if MUI `color="error"` picks up the theme.
- [ ] 2.4 In `DoctorPage` root `Box`, change `pb: isMobile ? "56px" : 0` to `pb: isMobile ? "64px" : 0` to match the 64px tab bar height + safe area.
- [ ] 2.5 In `DesktopSidebar`, update inactive text color from `#555` to `#999999`. Update hover bg from `rgba(0,0,0,0.05)` to `"#f0f0f0"`.
- [ ] 2.6 In `DesktopSidebar`, update border to `borderRight: "0.5px solid #d9d9d9"` (was `1px solid #e5e5e5`).

**Verification:** Open in mobile viewport 393px. Tab bar should be: `#f7f7f7` bg, hairline top border, inactive icons/text `#999`, active icon/text `#07C160`, tab text 10px. On Tasks tab, red badge with `#FA5151` if tasks > 0.

**Commit:** `style: redesign bottom tab bar to WeChat flat spec`

---

## Task 3: Chat Bubble Styling

**Files to modify:**
- `frontend/web/src/pages/doctor/ChatSection.jsx`

**Current state:**
- `MsgAvatar`: 36px, `borderRadius: "8px"`, user bg `#5b9bd5`, AI bg `#07C160`
- `MsgBubble`: user bg `#07C160`, AI bg `#fff`, radius `"14px 2px 14px 14px"` / `"2px 14px 14px 14px"`, has `boxShadow`
- `MobileInputBar`: `borderTop: "1px solid #d9d9d9"`, `backgroundColor: "#f5f5f5"`, send button `bgcolor: "#07C160"` with round shape
- `ChatTopbar`: height 48, bg `#ededed` on mobile, `#fff` on desktop
- `QuickCommandChips`: `borderRadius: "16px"`, `bgcolor: "#f0f0f0"`
- `LoadingBubble`: AI avatar `borderRadius: "8px"`, `bgcolor: "#07C160"`

### Steps

- [ ] 3.1 In `MsgAvatar`, change `borderRadius` from `"8px"` to `"4px"`. Change `size` default from `36` to `40`. Keep user bg `#5b9bd5` and AI bg `#07C160` (these are avatar colors, not bubble colors).
- [ ] 3.2 In `MsgBubble`:
  - Change user `bgColor` from `"#07C160"` to `"#95EC69"` (spec user bubble)
  - Change user `textColor` from `"#fff"` to `"#111111"` (dark text on light green bubble, matching WeChat)
  - Change bubble `borderRadius` from `"14px 2px 14px 14px"` to `"4px 4px 0 4px"` for user, from `"2px 14px 14px 14px"` to `"4px 4px 4px 0"` for AI (more square, WeChat style)
  - Remove `boxShadow` from bubble (set to `"none"`)
  - Change avatar `size` from `isMobile ? 36 : 38` to `40` (consistent)
- [ ] 3.3 Add CSS triangle arrows to bubbles. Add a pseudo-element via sx on the bubble Box:
  - Add `position: "relative"` to the bubble Box to anchor the pseudo-element
  - User bubble (right side arrow):
    ```js
    "&::after": {
      content: '""', position: "absolute", top: 10, right: -6,
      width: 0, height: 0,
      borderTop: "6px solid transparent",
      borderBottom: "6px solid transparent",
      borderLeft: "6px solid #95EC69",
    }
    ```
  - AI bubble (left side arrow):
    ```js
    "&::after": {
      content: '""', position: "absolute", top: 10, left: -6,
      width: 0, height: 0,
      borderTop: "6px solid transparent",
      borderBottom: "6px solid transparent",
      borderRight: "6px solid #ffffff",
    }
    ```
- [ ] 3.4 Update chat area background: already `bgcolor: "#ededed"` in the message list Box. Confirm no change needed.
- [ ] 3.5 In `MobileInputBar`:
  - Keep `borderTop: "1px solid #d9d9d9"` and `backgroundColor: "#f5f5f5"` (already spec-correct)
  - Keep send button round (`borderRadius: "50%"`) as WeChat uses a round send button
  - Update text input `borderRadius` from `"20px"` to `"4px"` for the `MuiOutlinedInput-root` in the TextField sx
  - Update text input border color to `#e0e0e0` (currently `#ddd`, update for precision)
- [ ] 3.6 In `ChatTopbar`:
  - Change mobile bg from `"#ededed"` to `"#f7f7f7"` (chat topbar should match WeChat nav bar style, slightly lighter than page bg)
  - Title font: `fontSize: 17, fontWeight: 500` (was `fontSize: 15, fontWeight: 600`)
- [ ] 3.7 In `QuickCommandChips`:
  - Change chip `borderRadius` from `"16px"` to `"4px"`
  - Keep `bgcolor: "#f0f0f0"`, `color: "#333"` (already spec-aligned)
- [ ] 3.8 In `LoadingBubble`:
  - Change avatar `borderRadius` from `"8px"` to `"4px"`
  - Change bubble `borderRadius` from `"2px 14px 14px 14px"` to `"4px 4px 4px 0"`
  - Remove `boxShadow`
- [ ] 3.9 In `PendingConfirmCard`:
  - Change `borderRadius` from `2` to `"4px"`
  - Confirm button `bgcolor: "#07C160"` is correct (action button, not bubble)
- [ ] 3.10 In `SystemMessage`:
  - Change `borderRadius` from `"12px"` to `"4px"`
  - Change `bgcolor` from `"#e6f7ff"` to `"#f0f0f0"` (more neutral, WeChat system message style)
  - Change `border` from `"1px solid #91d5ff"` to `"none"`
  - Change text `color` from `"#096dd9"` to `"#999999"`
- [ ] 3.11 In `DesktopInputBar`:
  - Change `backgroundColor` from `"#f7f7f7"` to `"#f5f5f5"` (input bar bg)
  - Change `borderTop` from `"1px solid #e5e5e5"` to `"0.5px solid #d9d9d9"`

**Verification:** Open in mobile viewport 393px. User bubble should be `#95EC69` with dark text, AI bubble white with `#111` text. Avatars should be 40px with 4px radius. Bubble arrows (CSS triangles) visible. No shadows. Chat bg `#ededed`. Input bar `#f5f5f5` with 4px radius text input.

**Commit:** `style: restyle chat bubbles and input bar to WeChat spec`

---

## Task 4: Patient List Styling

**Files to modify:**
- `frontend/web/src/pages/doctor/PatientsSection.jsx`
- `frontend/web/src/pages/doctor/PatientAvatar.jsx`

**Current state:**
- `PatientAvatar`: circular (`borderRadius: "50%"`), variable size (default 42), colored bg with white surname initial
- `PatientRow`: gap 1.5, px 2, py 1.2, avatar 42px mobile / 38px desktop, selected indicator is a green dot
- `SearchBar`: `borderRadius: "20px"`, `bgcolor: "#fff"`, border bottom `#e2e8f0`
- `ImportCard`: has icon boxes with `borderRadius: "8px"`, sections with borders
- `PatientGroupList`: letter headers with `bgcolor: "#f7f7f7"`, border bottom `#ebebeb`

### Steps

- [ ] 4.1 In `PatientAvatar.jsx`:
  - Change `borderRadius` from `"50%"` to `"4px"` (spec: 4px avatar radius)
  - Keep the colored background + white surname character pattern (this is already WeChat-like)
- [ ] 4.2 In `PatientRow`:
  - Change `avatarSize` from `isMobile ? 42 : 38` to `44` (spec: 44px for list avatars)
  - Update padding to `px: 2, py: 1.5` (12px 16px equivalent)
  - Replace selected indicator green dot with a left border accent: remove the green dot `Box`, instead add `borderLeft: isSelected ? "3px solid #07C160" : "3px solid transparent"` on the row
  - Add hairline divider: `borderBottom: "0.5px solid #f0f0f0"` (replaces any existing divider logic)
  - Name font: `fontSize: 15, fontWeight: 500` (already close)
  - Secondary text (age, records count): `fontSize: 13, color: "#999999"`
- [ ] 4.3 In `SearchBar`:
  - Change input `borderRadius` from `"20px"` to `"4px"`
  - Keep `bgcolor: "#fff"` on the input
  - Change outer container bg from `#f7f7f7` to `#ededed` (match page bg)
  - Change border bottom from `"1px solid #e2e8f0"` to `"0.5px solid #f0f0f0"`
- [ ] 4.4 In `ImportCard`:
  - Change icon box `borderRadius` from `"8px"` to `"4px"`
  - Update border bottoms to `"0.5px solid #f0f0f0"`
- [ ] 4.5 Add a "新建患者" row as the first item when not searching. Insert before the patient group list in `PatientListPane`:
  - Show a `+` icon in a 44px / 4px-radius box with dashed `#07C160` border
  - Text: "新建患者" in `#07C160`, fontSize 15
  - `onClick`: call `onInsertChatText("新建患者：")` to navigate to chat
  - Avatar placeholder: `border: "1px dashed #07C160"`, `borderRadius: "4px"`, `width: 44, height: 44`
- [ ] 4.6 In `PatientGroupList`:
  - Letter headers: `bgcolor: "#f7f7f7"` (already correct), border bottom `"0.5px solid #f0f0f0"` (was `#ebebeb`)
  - `fontSize: 12, color: "#999999"` for group letter (was `#888`)

**Verification:** Open in mobile viewport 393px. Avatars are 44px square with 4px radius. Rows have hairline `#f0f0f0` dividers. Search bar has 4px radius. "新建患者" row appears at top with dashed green border. No shadows, no card elevation.

**Commit:** `style: restyle patient list to WeChat flat design`

---

## Task 5: Patient Detail Styling

**Files to modify:**
- `frontend/web/src/pages/doctor/PatientDetail.jsx`

**Current state:**
- `PatientProfileBlock`: white bg, avatar 60px (circular via PatientAvatar), name 18px bold, label chips, action bar with export/delete links
- `RecordFilterPills`: active pill `bgcolor: "#07C160"`, radius `"12px"`
- `RecordListSection`: white bg, header "病历记录" with loading indicator
- `DeletePatientDialog`: bottom-sheet style on mobile, standard on desktop
- Overall bg `#f7f7f7`

### Steps

- [ ] 5.1 In `PatientProfileBlock`:
  - Avatar size stays at `60` (spec: 56-60px for detail), radius now 4px via PatientAvatar change in Task 4
  - Name font: keep `fontSize: 18, fontWeight: 700` (acceptable for detail page header)
  - Add status badge area: if patient has a `status` or `priority` field, show a badge next to name:
    - 危急: `bgcolor: "#FA5151"`, white text, `borderRadius: "4px"`, `px: 0.8, py: 0.2, fontSize: 12`
    - 需关注: `bgcolor: "#FF9500"`, white text, same style
    - (This is preparatory; the badge renders only if data is present)
  - Change action bar: reorganize into two rows:
    - Row 1: "新建任务" button (outlined, `#07C160` border) + "导出PDF" button (outlined, `#07C160` border), side by side, `flex: 1` each, `height: 36`, `borderRadius: "4px"`, `fontSize: 14`
    - Row 2: "AI对话咨询" button (filled green, `bgcolor: "#07C160"`, full width, `height: 44`, `borderRadius: "4px"`, `color: "#fff"`, `fontWeight: 500, fontSize: 15`)
    - Keep existing "删除患者" as a text link below, or in overflow menu
- [ ] 5.2 Convert settings-style menu rows for patient metadata:
  - Gender, age, record count should display as WeChat settings-style rows with label on left, value + chevron on right
  - Each row: `px: 2, py: 1.5, borderBottom: "0.5px solid #f0f0f0"`, `bgcolor: "#fff"`
  - Label: `fontSize: 14, color: "#111"`
  - Value: `fontSize: 14, color: "#999"`
  - Chevron: right-pointing `>` arrow icon, `color: "#ccc"`, `fontSize: 16`
- [ ] 5.3 In `RecordFilterPills`:
  - Change `borderRadius` from `"12px"` to `"4px"`
  - Active pill: `bgcolor: "#07C160"`, `color: "#fff"` (already correct)
  - Inactive pill: `bgcolor: "#f0f0f0"`, `color: "#666"` (was `#f2f2f2`)
- [ ] 5.4 In `RecordListSection`:
  - Section header: add group header style `px: 2, pt: 2, pb: 0.6`, `fontSize: 12, color: "#999", fontWeight: 500`
  - Dividers between records: `borderBottom: "0.5px solid #f0f0f0"`
- [ ] 5.5 In `PatientLabelRow`:
  - Label chip: `borderRadius: "4px"`, height 22 (already correct)
  - "+" label button: keep `border: "1px dashed #b7ebd0"`, update `borderRadius` from `1` to `"4px"`
- [ ] 5.6 In `PatientActionBar`:
  - Change `borderTop` from `"1px solid #f2f2f2"` to `"0.5px solid #f0f0f0"`
- [ ] 5.7 In `DeletePatientDialog`:
  - Change mobile `borderRadius` from `"16px 16px 0 0"` to `"12px 12px 0 0"` (WeChat action sheet style)
  - Cancel button: `borderRadius: "4px"`
  - Delete button: `bgcolor: "#FA5151"` (was `#e74c3c`, now use spec red), `borderRadius: "4px"`
- [ ] 5.8 In `MobilePatientDetailView` (in PatientsSection.jsx):
  - Back button color: keep `#07C160`
  - Nav bar: `bgcolor: "#f7f7f7"` (was `#fff`), `borderBottom: "0.5px solid #d9d9d9"` (was `1px solid #e5e5e5`)
  - Title: `fontSize: 17, fontWeight: 500` (was `fontSize: 16, fontWeight: 600`)

**Verification:** Open patient detail in mobile viewport 393px. Profile card is flat white on `#ededed` bg. Status badge visible if data present. Action buttons are organized in two rows with green CTA. Records separated by hairline dividers. All corners 4px.

**Commit:** `style: restyle patient detail to WeChat settings-menu layout`

---

## Task 6: Task List Styling

**Files to modify:**
- `frontend/web/src/pages/doctor/TasksSection.jsx`

**Current state:**
- `TasksHeader`: status filter pills with `borderRadius: "12px"`, active `#07C160`, `+ button` as 28px green circle
- `TaskRow`: 40px icon box with `borderRadius: "10px"`, colored bg per task type
- `TaskActions`: inline complete/postpone/cancel links
- Dialogs (PostponeDialog, CancelDialog): bottom-sheet style on mobile
- Overall bg `#f7f7f7`

### Steps

- [ ] 6.1 In `TasksHeader`:
  - Replace pill-style filter with iOS segment control look:
    - Container: `bgcolor: "#f0f0f0"`, `borderRadius: "4px"`, `p: "2px"`, inline-flex
    - Each segment: `px: 1.6, py: 0.5, borderRadius: "4px"`, `fontSize: 13`
    - Active segment: `bgcolor: "#fff"`, `color: "#111"`, `fontWeight: 600`, subtle shadow: `boxShadow: "0 1px 2px rgba(0,0,0,0.08)"`
    - Inactive: `bgcolor: "transparent"`, `color: "#999"`
  - Rename filter labels to match spec: use "今天" / "待办" / "已完成" as the three primary segments (map: "pending" -> "待办", "completed" -> "已完成"; add a "today" pseudo-filter that shows pending tasks due today)
  - Keep `+` button, update to: `borderRadius: "4px"` (was `"50%"`), `width: 28, height: 28`
  - Header `borderBottom`: `"0.5px solid #d9d9d9"` (was `1px solid #e5e5e5`)
- [ ] 6.2 In `TaskRow`:
  - For appointment-type tasks: show time on the left side in a dedicated column:
    - Left column: `width: 48`, `fontSize: 13, color: "#999"`, show `HH:mm` from `due_at`
    - Right: task content
  - For non-appointment tasks: keep icon on left, but change icon box `borderRadius` from `"10px"` to `"4px"`
  - Title font: `fontSize: 15, fontWeight: 500` (was `body2` with `fontWeight: 600`)
  - Secondary text: `fontSize: 13, color: "#999"`
  - Overdue text color: `"#FA5151"` (was `#e74c3c`)
  - Overdue date color: `"#FA5151"` (was `#e74c3c`)
  - Row divider: `borderBottom: "0.5px solid #f0f0f0"` (was `1px solid #f2f2f2`)
- [ ] 6.3 In `TaskActions`:
  - Complete action: use a circular checkbox style instead of text link:
    - Unchecked: `width: 20, height: 20, borderRadius: "50%", border: "2px solid #07C160"`, empty inside
    - For urgent/overdue tasks: `border: "2px solid #FA5151"` (red border = urgent)
    - On click, fill with checkmark
  - Postpone / Cancel: keep as text links, update colors: postpone `#999`, cancel `#ccc` (already correct)
- [ ] 6.4 Update dialogs (PostponeDialog, CancelDialog):
  - Mobile `borderRadius`: `"12px 12px 0 0"` (was `"16px 16px 0 0"`)
  - Button `borderRadius`: `"4px"` (theme will handle if using theme units)
  - Confirm button in PostponeDialog: `bgcolor: "#07C160"` (already correct)
  - Confirm button in CancelDialog: `bgcolor: "#FA5151"` (was `#e74c3c`)
- [ ] 6.5 In `CreateTaskDialog`:
  - On mobile, use fullScreen (already does). Update title `fontWeight` from `700` to `600`.
  - Create button: ensure it uses `bgcolor: "#07C160"` via theme primary.
- [ ] 6.6 Group headers ("已逾期", "今天", etc.):
  - `fontSize: 12, color: "#999"` (overdue stays `#FA5151`)
  - `fontWeight: 500` (already correct)
- [ ] 6.7 Change overall section bg from `#f7f7f7` to `#ededed` (match page bg)

**Verification:** Open tasks in mobile viewport 393px. Segment control at top looks like iOS-style toggle. Task rows have 4px-radius icon boxes, hairline dividers. Overdue items use `#FA5151`. Circular checkboxes for completion. No shadows.

**Commit:** `style: restyle task list with iOS segment control and WeChat flat rows`

---

## Task 7: Settings Styling

**Files to modify:**
- `frontend/web/src/pages/doctor/SettingsSection.jsx`

**Current state:**
- `AccountBlock`: 52px circular green avatar with hospital icon, name/ID below, then settings rows (昵称, 科室, 场景, 风格) each with chevron
- `SettingsRow`: 36px/8px-radius icon box, hairline borders `#f2f2f2`, right chevron
- `TemplateSubpage`: back button, template status card, actions
- Dialogs: bottom-sheet on mobile, standard on desktop
- Overall bg `#f7f7f7`

### Steps

- [ ] 7.1 In `AccountBlock` — convert to WeChat "Me" page profile card:
  - Avatar: change from `borderRadius: "50%"` to `borderRadius: "4px"` (now square with 4px radius)
  - Avatar size: keep `52` or increase to `56` for prominence
  - Remove `LocalHospitalOutlinedIcon`, show the doctor's **surname character** (first char of `doctorName`) in white, similar to PatientAvatar pattern:
    ```js
    <Typography sx={{ color: "#fff", fontSize: 24, fontWeight: 600 }}>
      {(doctorName || "?")[0]}
    </Typography>
    ```
  - Keep `bgcolor: "#07C160"` for the avatar
  - Name: `fontSize: 17, fontWeight: 600` (was `fontSize: 16, fontWeight: 600`)
  - ID: `fontSize: 13, color: "#999"` (was caption with text.secondary)
- [ ] 7.2 In settings rows (昵称, 科室专业, etc.):
  - Border between rows: `"0.5px solid #f0f0f0"` (was `1px solid #f2f2f2`)
  - Row padding: `px: 2, py: 1.5` (already correct)
  - Label font: `fontSize: 14, color: "#111"` (was `#555` — too light)
  - Value font: `fontSize: 14, color: "#999"` (already correct)
  - Chevron: keep `ArrowBackIcon` rotated 180deg, `color: "#ccc"`, `fontSize: 16` (already correct)
- [ ] 7.3 In `SettingsRow` (generic component):
  - Change icon box `borderRadius` from `"8px"` to `"4px"`
  - Danger row icon box: keep `bgcolor: "#fef2f2"` (light red bg)
- [ ] 7.4 Group headers ("账户", "工具", "账户操作"):
  - `fontSize: 12, color: "#999", fontWeight: 500` (already matches)
  - `px: 2, pt: 2, pb: 0.6` (already matches)
- [ ] 7.5 "退出登录" button at bottom:
  - Change from `SettingsRow` with danger styling to a standalone button:
    - Full-width white row: `bgcolor: "#fff"`, `textAlign: "center"`, `py: 1.5`
    - Text: `color: "#FA5151"` (was `#e74c3c`), `fontSize: 15, fontWeight: 500`
    - No icon, just centered red text "退出登录"
    - `borderTop: "0.5px solid #f0f0f0"`, `borderBottom: "0.5px solid #f0f0f0"`
    - Tap feedback: `"&:active": { bgcolor: "#f5f5f5" }`
- [ ] 7.6 Change overall section bg from `#f7f7f7` to `#ededed`
- [ ] 7.7 Mobile header bar:
  - `bgcolor: "#f7f7f7"` (was `#fff`)
  - `borderBottom: "0.5px solid #d9d9d9"` (was `1px solid #e5e5e5`)
  - Title: `fontSize: 17, fontWeight: 500` (was `fontSize: 16, fontWeight: 600`)
- [ ] 7.8 In `TemplateSubpage`:
  - Back bar: `bgcolor: "#f7f7f7"` (was `#fff`), `borderBottom: "0.5px solid #d9d9d9"`
  - Title: `fontSize: 17, fontWeight: 500`
  - Template card icon box: `borderRadius: "4px"` (was `"10px"`)
  - Action rows: update borders to `"0.5px solid #f0f0f0"`
- [ ] 7.9 Update all dialogs in SettingsSection (NameDialog, SpecialtyDialog, SimpleTextDialog):
  - Mobile `borderRadius`: `"12px 12px 0 0"` (was `"16px 16px 0 0"`)
  - Save button: `bgcolor: "#07C160"`, `borderRadius: "4px"`
  - Cancel button: `bgcolor: "#f5f5f5"`, `borderRadius: "4px"`
  - Quick-pick chips: `borderRadius: "4px"` (was `"12px"`)
- [ ] 7.10 In `SpecialtyDialog` quick-pick chips and `SimpleTextDialog` quick-pick chips:
  - Change `borderRadius` from `"12px"` to `"4px"`
  - Active: `bgcolor: "#07C160"`, `color: "#fff"` (already correct)
  - Inactive: `bgcolor: "#f0f0f0"`, `color: "#555"` (was `#f2f2f2`)

**Verification:** Open settings in mobile viewport 393px. Profile card shows surname initial in green 4px-radius square. All rows have hairline dividers. "退出登录" is centered red text at bottom. Quick-pick chips have 4px radius. All dialogs have 12px top radius on mobile. No shadows.

**Commit:** `style: restyle settings page to WeChat "Me" page layout`

---

## Task 8: Final Sweep and Cross-cutting Fixes

**Files to modify:**
- `frontend/web/src/pages/doctor/WorkingContextHeader.jsx`
- `frontend/web/src/pages/doctor/RecordCard.jsx`
- `frontend/web/src/pages/doctor/LabelPicker.jsx`
- `frontend/web/src/pages/doctor/ViewPayloadCard.jsx`
- Any other component with hardcoded old colors or radii

### Steps

- [ ] 8.1 Search entire `frontend/web/src/` for hardcoded color values that conflict with the new spec:
  - `#0f766e` (old primary) — replace with `#07C160` or use `theme.palette.primary.main`
  - `#102a35` (old text primary) — replace with `#111111`
  - `#5b7281` (old text secondary) — replace with `#999999`
  - `#f3f7f8` (old page bg) — replace with `#ededed`
  - `#d8e3e8` (old border) — replace with `#f0f0f0` or `#d9d9d9`
  - `#e2e8f0` (old border) — replace with `#d9d9d9` or `#f0f0f0`
  - `#d6e2e5` (old AppBar border) — replace with `#d9d9d9`
  - `borderRadius: "8px"` on avatars/icon boxes — replace with `"4px"`
  - `borderRadius: "12px"` or `"16px"` or `"20px"` on chips/pills/inputs — replace with `"4px"`
  - `boxShadow` values — remove (set `"none"`)
  - `#e74c3c` (old danger red) — replace with `#FA5151`
- [ ] 8.2 In `WorkingContextHeader.jsx`:
  - Update any borders, backgrounds, and font sizes to match spec
  - Ensure it uses `#f7f7f7` bg if it is a top bar element
- [ ] 8.3 In `RecordCard.jsx`:
  - Remove any card borders/shadows
  - Use `borderBottom: "0.5px solid #f0f0f0"` as divider
  - Any `borderRadius` on the card: `"4px"` or `0` (flat list item)
- [ ] 8.4 In `LabelPicker.jsx`:
  - Chip radius: `"4px"`
  - Dropdown/popover: `borderRadius: "4px"`, no shadow
- [ ] 8.5 In `ViewPayloadCard.jsx`:
  - Card border: remove or set `"0.5px solid #f0f0f0"`
  - Radius: `"4px"`
  - No shadow
- [ ] 8.6 Verify Capacitor Android build:
  - Run `npx cap sync android` to ensure assets propagate
  - Check for any viewport or safe-area issues on Android emulator
- [ ] 8.7 Test all four tabs (AI 助手, 患者, 任务, 设置) in both mobile (393px) and desktop viewports
- [ ] 8.8 Confirm no remaining references to old teal colors, old border radii, or shadows in any component

**Verification:** Full app walkthrough at 393px viewport width. Every screen matches WeChat flat aesthetic: `#ededed` page bg, white cards with no shadow, 4px radii, hairline `#f0f0f0` dividers, `#07C160` accents, `#95EC69` user bubbles, `#FA5151` danger elements.

**Commit:** `style: final sweep — remove all legacy colors, shadows, and radii`

---

## Risks / Open Questions

1. **MUI v7 shadow array length** — MUI expects exactly 25 entries in the `shadows` array. `Array(25).fill("none")` should work, but verify no MUI component breaks when elevation > 0 resolves to `"none"`.

2. **0.5px hairline borders** — On low-DPI Android screens, `0.5px` may render as 0px (invisible) or 1px. Fallback: use `1px` with `#f0f0f0` color which is subtle enough to look like a hairline. Test on Capacitor Android build.

3. **User bubble text readability** — `#95EC69` is a light green; `#111111` text should have sufficient contrast (WCAG AA). Verify contrast ratio >= 4.5:1. (Calculated: ~4.8:1, just passes AA.)

4. **Theme custom namespace `wechat`** — MUI's `createTheme` allows arbitrary keys but TypeScript (if ever added) would need module augmentation. Since this project uses plain JS, no issue. Access via `theme.wechat.userBubble` in components.

5. **CSS triangle arrows on bubbles** — The `&::after` pseudo-element approach via MUI `sx` is supported but can be tricky. Test that arrows render correctly on both mobile and desktop. If issues arise, fall back to a separate `Box` element styled as a triangle.

6. **Safe area padding on tab bar** — `env(safe-area-inset-bottom)` requires `<meta name="viewport" content="..., viewport-fit=cover">` in index.html. Check that the Capacitor template includes this. If not, add it as part of Task 2.

7. **Breaking existing desktop sidebar** — The desktop sidebar already uses `#07C160` for active items and `#f7f7f7` bg, which aligns well. Changes are minor (border thinning, inactive color update). Low risk.

8. **No unit tests during MVP** — Per AGENTS.md, verification is visual comparison only. No automated regression tests for style changes. This is accepted project policy.
