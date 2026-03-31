# Patient App Parity — Design Spec

**Goal:** Upgrade patient app to match doctor app component patterns and visual quality. Doctor app is SOT. Mobile-only, no desktop layout.

**Approach:** Pattern parity, not feature parity. Keep patient IA and routes. Swap to shared components. Add transitions. Rebuild ProfileTab.

## Priority Order

1. **RecordsTab** — FilterBar + PageSkeleton for detail subpage
2. **ChatTab** — MsgAvatar, IconBadge, theme tokens (don't touch polling)
3. **ProfileTab → MyPage** — rebuild as patient settings list
4. **PatientPage shell** — Fade around tab content
5. **TasksTab** — FilterBar for status filter (keep TaskChecklist)
6. **InterviewPage** — icon/token cleanup only
7. **Shared constants** — move badge configs out of doctor/constants

## Pre-work: Shared Constants

Move `RECORD_TYPE_BADGE` and related icon configs that patient already imports from `doctor/constants.jsx` into a shared location (e.g., `components/constants.jsx` or `shared/badgeConfigs.js`). Patient already cross-imports these — clean that up first.

## 1. RecordsTab

**Current:** Inline Box tabs for list/timeline toggle. RecordDetail rendered inline via conditional. Hardcoded status colors.

**Changes:**
- Replace inline view toggle (lines 199-215) → `<FilterBar items={[{key:"list",label:"病历"},{key:"timeline",label:"时间线"}]} active={recordView} onChange={setRecordView} />`
- Add record type filter: `<FilterBar items={PATIENT_RECORD_TABS} active={typeFilter} onChange={setTypeFilter} />` with tabs: 全部 / 病历 / 问诊 / 导入
- Wrap in PageSkeleton `isMobile` for RecordDetail subpage (Slide transition)
- Fix RecordDetail back navigation: `navigate(-1)` instead of fixed path
- Add `PATIENT_RECORD_TABS` to patient/constants.jsx

## 2. ChatTab

**Current:** Hand-built avatar boxes with inline styles. Hardcoded `#1B6EF3` and `#E8F0FE`. QuickActions uses inline icon wrappers.

**Changes:**
- AI message avatar (line 251-253) → `<MsgAvatar isUser={false} size={32} />`
- Patient message avatar (line 192-194) → keep PersonOutlineIcon but extract to small component or use IconBadge with patient config
- QuickActions icon boxes (lines 62-65) → `<IconBadge config={...} solid size={36} />`
- Replace `#1B6EF3` → `COLOR.accent`, `#E8F0FE` → use IconBadge tinted style
- Do NOT touch polling, message state, or send logic

## 3. ProfileTab → MyPage

**Current:** Two AccountCards + bare logout button. No ConfirmDialog.

**Rewrite to:**
- NameAvatar or AccountCard header with patient name/info
- `<SectionLabel>我的医生</SectionLabel>` + AccountCard with doctor name/specialty
- `<SectionLabel>通用</SectionLabel>` + settings rows (About, Privacy) using SettingsRow pattern from SettingsListSubpage
- Logout with ConfirmDialog confirmation
- About/Privacy: navigate to existing routes (`/privacy`, etc.) or render inline via simple state toggle
- Reuse existing AboutSubpage and PrivacyPage components

**Rename:** ProfileTab.jsx → MyPage.jsx, update import in PatientPage.jsx

## 4. PatientPage Shell

**Current:** Inline `{tab === "chat" && <ChatTab />}` with instant switch. Bottom nav height 56px.

**Changes:**
- Wrap each tab body in `<Fade in={tab === key} timeout={150}>` (matching DoctorPage SectionContent)
- Only active tab visible, all mounted (prevents polling remount)
- Bottom nav: height → 64px, label fontSize → `TYPE.micro`, selected fontWeight → 600
- Rename nav tab: "设置" → "我的", icon → PersonOutlineIcon
- Add pending task count badge on 任务 tab (requires passing task count up)
- Do NOT use PageSkeleton at shell level

## 5. TasksTab

**Current:** SectionLabel + TaskChecklist for pending/completed. No filtering.

**Changes:**
- Add `<FilterBar items={[{key:"all",label:"全部"},{key:"pending",label:"待完成"},{key:"done",label:"已完成"}]} active={filter} onChange={setFilter} />`
- Filter tasks client-side based on selection
- Keep TaskChecklist (already wraps ActionRow)
- Add relative date formatting for due_at
- No task detail subpage (data too thin)
- Add `PATIENT_TASK_FILTERS` to patient/constants.jsx

## 6. InterviewPage

**Current:** Hardcoded `fontSize: "0.9rem"`. Emoji ✅/⬜ in summary sheet. Inline avatar boxes for chat bubbles.

**Changes:**
- `fontSize: "0.9rem"` → `TYPE.body.fontSize`
- Summary sheet: ✅ → `<CheckCircleOutlineIcon sx={{fontSize:14, color:COLOR.primary}} />`, ⬜ → `<RadioButtonUncheckedIcon sx={{fontSize:14, color:COLOR.border}} />`
- Chat bubble avatars → MsgAvatar for consistency
- No structural changes to interview flow

## 7. constants.jsx Updates

- Add `PATIENT_RECORD_TABS` for record type filtering
- Add `PATIENT_TASK_FILTERS` for task status filtering
- Rename NAV_TABS profile entry: label "设置" → "我的", icon → PersonOutlineIcon
- Import shared badge configs instead of doctor/constants

## Files Changed

| File | Change Level |
|------|-------------|
| patient/constants.jsx | Medium — add filter configs, rename nav |
| patient/RecordsTab.jsx | Medium — FilterBar + PageSkeleton |
| patient/ChatTab.jsx | Low — avatar/icon swaps, color tokens |
| patient/ProfileTab.jsx → MyPage.jsx | Full rewrite |
| patient/PatientPage.jsx | Low — Fade wraps, nav styling |
| patient/TasksTab.jsx | Low — FilterBar addition |
| patient/InterviewPage.jsx | Low — token/icon cleanup |
| patient/subpages/RecordDetail.jsx | Low — fix navigate(-1) |
| Shared badge constants file | New — extract from doctor/constants |

## Non-goals

- Desktop sidebar layout (patient is mobile-only)
- Task detail subpage (task data too thin)
- Replacing TaskChecklist with raw ActionRow (already wrapped)
- Changing interview flow or UX
- Adding features not in doctor app
