# UI Design Principles & Component Guide

> Source of truth for all frontend visual and interaction decisions.
> Read this before creating or modifying any UI component.

## Live Showcases

> **Do not use static PNG screenshots** — always reference the live debug views.

| Showcase | URL | What it shows |
|----------|-----|---------------|
| **Shared Components** | [`/debug/components`](http://localhost:5173/debug/components) | All reusable UI in `src/components/` and `src/components/doctor/` |
| **Doctor Pages** | [`/debug/doctor-pages`](http://localhost:5173/debug/doctor-pages) | Page-level mockups with sample data |
| **Doctor Components** | [`/debug/doctor-components`](http://localhost:5173/debug/doctor-components) | Doctor-specific components (DiagnosisCard, FieldReviewCard, etc.) |

Source: [`src/pages/admin/ComponentShowcasePage.jsx`](../../frontend/web/src/pages/admin/ComponentShowcasePage.jsx)

---

## Quick Reference — Component File Map

### App Shell
| Component | File | Purpose |
|-----------|------|---------|
| MobileFrame | [`src/App.jsx`](../../frontend/web/src/App.jsx) | Phone-shaped container for desktop |
| DoctorPage | [`src/pages/doctor/DoctorPage.jsx`](../../frontend/web/src/pages/doctor/DoctorPage.jsx) | Doctor app shell (top bar + content + nav) |
| PatientPage | [`src/pages/patient/PatientPage.jsx`](../../frontend/web/src/pages/patient/PatientPage.jsx) | Patient portal shell |
| LoginPage | [`src/pages/LoginPage.jsx`](../../frontend/web/src/pages/LoginPage.jsx) | Unified login (doctor/patient tabs) |

### Top Bar & Navigation
| Component | File | Purpose |
|-----------|------|---------|
| SubpageHeader | [`src/components/SubpageHeader.jsx`](../../frontend/web/src/components/SubpageHeader.jsx) | ‹ back + title + action |
| BarButton | [`src/components/BarButton.jsx`](../../frontend/web/src/components/BarButton.jsx) | Top bar text action button |
| MobileBottomNav | [`src/pages/doctor/DoctorPage.jsx`](../../frontend/web/src/pages/doctor/DoctorPage.jsx) | 4-tab bottom navigation |

### Layout & Structure
| Component | File | Purpose |
|-----------|------|---------|
| PageSkeleton | [`src/components/PageSkeleton.jsx`](../../frontend/web/src/components/PageSkeleton.jsx) | Page layout wrapper (list + detail) |
| SectionLabel | [`src/components/SectionLabel.jsx`](../../frontend/web/src/components/SectionLabel.jsx) | Section header label (12px/600) |
| EmptyState | [`src/components/EmptyState.jsx`](../../frontend/web/src/components/EmptyState.jsx) | Centered "暂无XX" placeholder |

### Buttons & Actions
| Component | File | Purpose |
|-----------|------|---------|
| AppButton | [`src/components/AppButton.jsx`](../../frontend/web/src/components/AppButton.jsx) | Content-level button (primary/secondary/danger) |
| CancelConfirm | [`src/components/CancelConfirm.jsx`](../../frontend/web/src/components/CancelConfirm.jsx) | Two-step cancel popup (确認\|返回) |
| ConfirmDialog | [`src/components/ConfirmDialog.jsx`](../../frontend/web/src/components/ConfirmDialog.jsx) | Compact confirm/destructive dialog |
| ActionPanel | [`src/components/ActionPanel.jsx`](../../frontend/web/src/components/ActionPanel.jsx) | Slide-up action sheet (camera, gallery, file, patient) |

### Content Components
| Component | File | Purpose |
|-----------|------|---------|
| ListCard | [`src/components/ListCard.jsx`](../../frontend/web/src/components/ListCard.jsx) | List row (avatar + title + subtitle + chevron) |
| NewItemCard | [`src/components/NewItemCard.jsx`](../../frontend/web/src/components/NewItemCard.jsx) | "+" dashed new item row |
| RecordCard | [`src/components/RecordCard.jsx`](../../frontend/web/src/components/RecordCard.jsx) | Expandable medical record card |
| RecordFields | [`src/components/RecordFields.jsx`](../../frontend/web/src/components/RecordFields.jsx) | NHC structured field rows |
| DetailCard | [`src/components/DetailCard.jsx`](../../frontend/web/src/components/DetailCard.jsx) | Compact key-value card |

### Chat & Input
| Component | File | Purpose |
|-----------|------|---------|
| AskAIBar | [`src/components/AskAIBar.jsx`](../../frontend/web/src/components/AskAIBar.jsx) | Floating "问 AI" entry bar |
| SuggestionChips | [`src/components/SuggestionChips.jsx`](../../frontend/web/src/components/SuggestionChips.jsx) | Quick-reply options above input |
| DoctorBubble | [`src/components/DoctorBubble.jsx`](../../frontend/web/src/components/DoctorBubble.jsx) | Doctor reply message bubble |
| VoiceInput | [`src/components/VoiceInput.jsx`](../../frontend/web/src/components/VoiceInput.jsx) | Press-to-talk voice input |

### Dialogs & Pickers
| Component | File | Purpose |
|-----------|------|---------|
| SheetDialog | [`src/components/SheetDialog.jsx`](../../frontend/web/src/components/SheetDialog.jsx) | Bottom-sheet dialog shell |
| BottomSheet | [`src/components/BottomSheet.jsx`](../../frontend/web/src/components/BottomSheet.jsx) | Swipe-up panel overlay |
| RecordEditDialog | [`src/components/RecordEditDialog.jsx`](../../frontend/web/src/components/RecordEditDialog.jsx) | Medical record field editor |
| ExportSelectorDialog | [`src/components/ExportSelectorDialog.jsx`](../../frontend/web/src/components/ExportSelectorDialog.jsx) | PDF export field picker |
| ImportChoiceDialog | [`src/components/ImportChoiceDialog.jsx`](../../frontend/web/src/components/ImportChoiceDialog.jsx) | Import method selector |
| PatientPickerDialog | [`src/components/PatientPickerDialog.jsx`](../../frontend/web/src/components/PatientPickerDialog.jsx) | Patient search and select |

### Badges & Avatars
| Component | File | Purpose |
|-----------|------|---------|
| StatusBadge | [`src/components/StatusBadge.jsx`](../../frontend/web/src/components/StatusBadge.jsx) | Colored status pill (高/中/低/急诊) |
| PatientAvatar | [`src/components/PatientAvatar.jsx`](../../frontend/web/src/components/PatientAvatar.jsx) | Colored circle with surname |
| RecordAvatar | [`src/components/RecordAvatar.jsx`](../../frontend/web/src/components/RecordAvatar.jsx) | Record type icon (visit/lab/imaging) |

### Doctor-Specific Components
| Component | File | Purpose |
|-----------|------|---------|
| DiagnosisCard | [`src/components/doctor/DiagnosisCard.jsx`](../../frontend/web/src/components/doctor/DiagnosisCard.jsx) | Collapsible diagnosis review card (5 states) |
| FieldReviewCard | [`src/components/doctor/FieldReviewCard.jsx`](../../frontend/web/src/components/doctor/FieldReviewCard.jsx) | Carry-forward / import field review |
| InterviewCompleteDialog | [`src/components/doctor/InterviewCompleteDialog.jsx`](../../frontend/web/src/components/doctor/InterviewCompleteDialog.jsx) | NHC preview + save/diagnose popup |

### Page-Level Components
| Component | File | Purpose |
|-----------|------|---------|
| HomePage | [`src/pages/doctor/HomePage.jsx`](../../frontend/web/src/pages/doctor/HomePage.jsx) | Home tab: stats + onboarding |
| ChatPage | [`src/pages/doctor/ChatPage.jsx`](../../frontend/web/src/pages/doctor/ChatPage.jsx) | AI chat with quick commands |
| PatientsPage | [`src/pages/doctor/PatientsPage.jsx`](../../frontend/web/src/pages/doctor/PatientsPage.jsx) | Patient list + detail drill-down |
| PatientDetail | [`src/pages/doctor/patients/PatientDetail.jsx`](../../frontend/web/src/pages/doctor/patients/PatientDetail.jsx) | Patient profile + records + actions |
| TasksPage | [`src/pages/doctor/TasksPage.jsx`](../../frontend/web/src/pages/doctor/TasksPage.jsx) | Task list with filter chips |
| SettingsPage | [`src/pages/doctor/SettingsPage.jsx`](../../frontend/web/src/pages/doctor/SettingsPage.jsx) | Profile, tools, knowledge base |
| ReviewPage | [`src/pages/doctor/ReviewPage.jsx`](../../frontend/web/src/pages/doctor/ReviewPage.jsx) | Diagnosis review subpage |
| InterviewPage | [`src/pages/doctor/InterviewPage.jsx`](../../frontend/web/src/pages/doctor/InterviewPage.jsx) | Doctor interview (chat + fields) |

### Theme & Tokens
| File | Purpose |
|------|---------|
| [`src/theme.js`](../../frontend/web/src/theme.js) | `TYPE`, `ICON`, `COLOR` tokens + MUI theme |
| [`src/api.js`](../../frontend/web/src/api.js) | All API functions |
| [`src/store/doctorStore.js`](../../frontend/web/src/store/doctorStore.js) | Auth state (Zustand) |
| [`src/pages/doctor/constants.jsx`](../../frontend/web/src/pages/doctor/constants.jsx) | Labels, enums, field definitions |

---

## 1. Overall Design Philosophy

### Identity

WeChat-native medical assistant. The app should feel like a professional
extension of WeChat — familiar to Chinese smartphone users, not a foreign
SaaS product. Every interaction should feel like messaging a trusted assistant.

### Core Principles

1. **Function over decoration** — No visual element without purpose. If it
   doesn't help the doctor treat patients faster, remove it.
2. **Flat and clean** — No shadows, no gradients, no 3D effects. WeChat flat
   design: white cards on gray backgrounds, hairline borders, text hierarchy
   through size and weight only.
3. **Mobile-first, mobile-only (for now)** — All views render as mobile layout.
   Desktop shows a phone-shaped frame. Optimize for one-thumb operation.
4. **Scan, don't read** — Doctors have 30 seconds per patient. Use brief labels
   for scanning (card titles), full text for reading (expanded detail).
   Collapse by default, expand on tap.
5. **Safety through layout** — Destructive actions (delete) always on the left,
   constructive actions (save, confirm) always on the right. Red for danger,
   green for go. No exceptions.
6. **Consistent density** — Clinical data is dense. Use compact spacing (4px
   base unit) but never sacrifice tap targets (min 44px touch area).
7. **Chinese-first** — All UI text in Chinese. Preserve medical abbreviations
   (CT, MRI, NIHSS). No English UI labels except technical identifiers.

8. **Flat icons only** — Use MUI outlined icons (`@mui/icons-material/*Outlined`).
   Never use emoji (💬📋), Unicode symbols (✓✗◫⚙✦◆), or icon fonts.
   Emoji render inconsistently across devices and look unprofessional.
   MUI outlined icons match WeChat's flat, consistent icon style.

### What We Don't Do

- No skeleton screens for fast loads (<200ms) — show content directly
- No emoji or Unicode symbol icons — use MUI outlined icons only
- No toast notifications for expected outcomes — only for errors and
  async completions
- No modal dialogs unless blocking is intentional (delete confirmation,
  interview complete choice)
- No hover effects — this is a touch-first UI
- No animations except page transitions and loading spinners
- No color for color's sake — gray is the default, color = meaning

---

## 2. Platform & Frame

### MobileFrame

Desktop browsers render the app inside a phone-shaped container:

```
┌─────────────── viewport ───────────────┐
│                                         │
│         ┌───────────────┐               │
│         │   Phone App   │               │
│         │   (9:19.5)    │               │
│         │               │               │
│         │               │               │
│         └───────────────┘               │
│                                         │
│         #e8e8e8 background              │
└─────────────────────────────────────────┘
```

- Ratio: 9:19.5 (modern phone).
- **Constraint-driven sizing** — uses CSS `min()` to pick whichever dimension
  would cause overflow:
  - Wide screen → height is constraint, width = `95vh * 9/19.5`
  - Short screen → width is constraint, height = `90vw * 19.5/9`
  - Always maintains phone proportions regardless of viewport shape.
- `transform: translateZ(0)` creates a containing block so `position: fixed`
  elements stay inside the frame.
- Rounded corners: `16px border-radius`. Subtle shadow: `0 4px 24px rgba(0,0,0,0.12)`.
- On actual mobile (<520px viewport): full screen, no frame, no rounding.

### Breakpoint Override

`theme.js` sets `sm: 9999` so all `useMediaQuery(down("sm"))` returns `true`.
This forces mobile layout everywhere. To enable desktop layout later, revert
`sm` to `600` and remove MobileFrame wrapping.

---

## 3. Three-Component Page Architecture

Every page is composed of exactly 3 components stacked vertically:

```
┌─────────────────────────────────────┐
│          TOP BAR (48px)             │  Fixed. Navigation + 1 action.
├─────────────────────────────────────┤
│                                     │
│          CONTENT (flex: 1)          │  Scrollable. Different per page.
│                                     │
├─────────────────────────────────────┤
│       BOTTOM NAVIGATION (64px)      │  Fixed. 4 tabs. Always visible.
└─────────────────────────────────────┘
```

No page deviates from this structure. Top bar and bottom nav are shared
chrome. Only the content area changes between pages.

---

### 3A. Top Bar

**Purpose:** Where am I, how to go back, what's the one action here.

```
┌─────────────────────────────────────┐
│  ‹       Title Text          Action │  48px
└─────────────────────────────────────┘
```

| Element | Rule |
|---------|------|
| **Background** | White `#fff`, border-bottom `0.5px solid #d9d9d9` |
| **Height** | 48px |
| **Back (‹)** | Chevron only, no text. 44x48px tap area. Present on subpages, hidden on root tabs. |
| **Title** | `TYPE.title` (16px/600), centered. Page name or patient name. |
| **Action** | Max 1 BarButton. Max 2 Chinese characters. Green `#07C160`, `TYPE.action` (15px/400). |
| **No icons** | Text-only. Icons belong in content area. |
| **Overflow** | If 2+ actions needed, put extras in content area. |

**Per-page examples:**

| Page | ‹ | Title | Action |
|------|---|-------|--------|
| 首页 | — | 首页 | — |
| 患者 | — | 患者 | — |
| 患者详情 | ‹ | 李复诊 | 门诊 |
| 对话 | ‹ | 对话工作区 | 清空 |
| 诊断审核 | ‹ | 诊断审核 | 完成 |
| 新建病历 | ‹ | 新建病历 | 46% |
| 任务 | — | 任务 | — |
| 设置 | — | 设置 | — |

---

### 3B. Content Area

**Purpose:** The doctor's workspace. Different per page. Always scrollable,
always has 64px bottom padding to clear the nav.

**Each page defines its own content layout.** There is no single content
template. The shared rules (cards, spacing, components) are in sections 4-6.

**Per-page content structure:**

| Page | Screenshot | Layout |
|------|-----------|--------|
| **首页** | [`/doctor`](http://localhost:5173/doctor) | Stat cards (2-col grid) → onboarding hint card → AI chat entry bar |
| **患者** | [`/doctor/patients`](http://localhost:5173/doctor/patients) | Search bar → "新建患者" card → patient list rows |
| **患者详情** | [`/doctor/patients/:id`](http://localhost:5173/doctor/patients) | Collapsible profile → record tabs → record cards → 患者消息 |
| **对话** | [`/doctor/chat`](http://localhost:5173/doctor/chat) | Chat bubbles → quick command chips → input bar + mic |
| **诊断审核** | [`/doctor/review/:id`](http://localhost:5173/doctor) | Record summary → diagnosis sections → sticky bottom bar |
| **新建病历** | (interview) | Progress bar → conversation → carry-forward → input bar |
| **任务** | [`/doctor/tasks`](http://localhost:5173/doctor/tasks) | Filter chips → "新建任务" card → task list |
| **设置** | [`/doctor/settings`](http://localhost:5173/doctor/settings) | Profile → tools (模板, 知识库) → general → 退出登录 |

**Shared content rules:**

1. White cards on gray `#ededed` background, 8px gap between cards
2. Stack vertically — no columns, no grids
3. Bottom clearance: always `pb: 64px`
4. Sticky bars (e.g., review bottom bar) sit above bottom nav, never overlapping

---

### 3C. Bottom Navigation

**Purpose:** One tap to any section. Visible on main tab pages only.

```
┌─────────────────────────────────────┐
│   ✦        👤        ☑        ✉    │  64px
│  我的AI    患者      审核      随访   │  + safe-area-inset
└─────────────────────────────────────┘
```

| Rule | Detail |
|------|--------|
| **Position** | `absolute` (not fixed — contained by MobileFrame) |
| **Background** | `#f7f7f7`, border-top `0.5px solid #d9d9d9` |
| **Height** | 64px + `env(safe-area-inset-bottom)` |
| **Active** | Green icon + text `#07C160`, fontWeight 600 |
| **Inactive** | Gray icon + text `#999` |
| **Labels** | 10px (MUI default) |
| **Badge** | Red dot + count on 审核 and 随访 when pending |
| **Visibility** | **Main tabs only.** Hidden on subpages. See rule below. |

**Main tab vs subpage rule (WeChat pattern):**

| Page type | Bottom nav | Top bar | Examples |
|-----------|-----------|---------|----------|
| **Main tab** | ✅ Visible | Title only, no back | 我的AI, 患者, 审核, 随访 |
| **Subpage** | ❌ Hidden | ‹ back + title (+ optional action) | 设置, 知识库, 患者详情, 诊断审核, 任务详情 |

A **subpage** is any view pushed onto the navigation stack from a main tab.
It shows a back chevron (‹) in the top bar and hides the bottom nav.
Back always uses browser history (`navigate(-1)`), never a hardcoded path.

This matches WeChat behavior: main tabs show the bottom bar, drilled-in
views hide it and show a back button instead.

**Tab mapping:**

| Tab | Active when viewing |
|-----|-------------------|
| 我的AI | my-ai |
| 患者 | patient list |
| 审核 | review queue |
| 随访 | followup list |
| 设置 | settings, subpages |

---

## 4. Color System

### Semantic Colors

| Color | Hex | Meaning | Where |
|-------|-----|---------|-------|
| **Green** | `#07C160` | Positive, primary, active, go | Buttons, nav, confirm, links |
| **Red** | `#D65745` | Destructive, danger | Delete only. Never for emphasis. |
| **Amber** | `#F59E0B` | Attention, pending, modified | 待审核 badge, edited items, 紧急 urgency |
| **Accent blue** | `#576B95` | Secondary action, info | Edit (✎ 修改), WeChat link style |
| **Gray** | `#999` | Neutral, inactive, metadata | Timestamps, labels, disabled |

### Background Colors

| Surface | Hex | Where |
|---------|-----|-------|
| Page background | `#ededed` | Behind all cards |
| Card background | `#ffffff` | All content cards |
| Bottom bar / surface | `#f7f7f7` | Nav bar, action bars |
| Rejected/dimmed | `#fafafa` | Rejected diagnosis items |

### Text Colors

| Level | Hex | Usage |
|-------|-----|-------|
| `text1` | `#1A1A1A` | Names, headings, primary content |
| `text2` | `#333333` | Body text, field values |
| `text3` | `#666666` | Descriptions, reasoning text |
| `text4` | `#999999` | Labels, metadata, timestamps, section headers |

### Border Colors

| Type | Hex | Usage |
|------|-----|-------|
| Card border | `#E5E5E5` | Around cards, between major sections |
| Hairline divider | `#f0f0f0` | Between rows inside a card |
| Top bar border | `#d9d9d9` | Bottom of top bar, top of bottom nav |

---

## 5. Typography System

Import from `theme.js`. **Never hardcode font sizes.**

```jsx
import { TYPE, ICON, COLOR } from "../../theme";
```

| Token | Size/Weight | Usage |
|-------|------------|-------|
| `TYPE.title` | 16px/600 | Page titles, top bar |
| `TYPE.action` | 15px/400 | Top bar actions, patient name in compact header |
| `TYPE.heading` | 14px/600 | Section titles, form labels |
| `TYPE.body` | 14px/400 | Content text, button labels |
| `TYPE.secondary` | 13px/400 | Descriptions, field labels, action buttons |
| `TYPE.caption` | 12px/400 | Metadata, timestamps, counters |
| `TYPE.micro` | 11px/500 | Badges, tags, status pills |

### Icon Sizes (`ICON`)

| Token | Size | Usage |
|-------|------|-------|
| `xs` | 13px | Inline tiny (sort arrows) |
| `sm` | 16px | Action button icons, inline icons |
| `md` | 18px | List item icons, expand/collapse |
| `lg` | 20px | Nav icons, settings row icons |
| `xl` | 22px | Quick action cards |
| `xxl` | 24px | Detail header icons |
| `hero` | 28px | SubpageHeader back chevron |
| `display` | 48px | Empty state icons |

---

## 6. Component Patterns

> **Live showcase:** [`/debug/components`](http://localhost:5173/debug/components) — all shared components rendered in isolation.
> **Doctor pages:** [`/debug/doctor-pages`](http://localhost:5173/debug/doctor-pages) — page-level mockups with sample data.

### Buttons

**File:** [`src/components/AppButton.jsx`](../../frontend/web/src/components/AppButton.jsx), [`src/components/BarButton.jsx`](../../frontend/web/src/components/BarButton.jsx)

| Type | Style | Where |
|------|-------|-------|
| **BarButton** | Plain text, green, 15px | Top bar only |
| **Primary button** | Green fill, white text | One per screen max |
| **Secondary button** | Gray border, dark text | Cancel, secondary actions |
| **Text button** | No background, colored text | Inline actions (删除, 编辑) |
| **Disabled** | `opacity: 0.4` or `color: #ccc` | Loading, conditions unmet |

**Button text:** Max 2 Chinese characters (e.g., 保存, 取消, 删除, 确认, 返回).
Exceptions only with strong justification (e.g., "保存并诊断 →" on a primary CTA
where the extra context prevents a wrong-action error).

**Action button placement:** destructive left, constructive right. Always.

```
[删除 (red)]  ───── spacer ─────  [编辑 (green)]
```

### Review Surfaces

Used in: diagnosis review, field carry-forward, import preview, other dense
doctor decision screens.

- Visual tone: mostly grayscale. White sections on `#ededed` background,
  hairline separators, minimal chrome.
- Row actions: repeated review actions inside cards or lists use **text
  actions** with small glyphs (`✎ 修改`, `✗ 忽略`, `✓ 确认`). Do not use repeated
  filled buttons for each row.
- Bulk actions: section-level or page-level actions may use stronger buttons.
  This is where green fill belongs.
- Color budget: default to black/gray text. Use color only for state meaning:
  green = confirmed/go, amber = edited/urgent, red = danger.
- Primary CTA count: one strong green CTA per screen. If a sticky bottom CTA
  exists, do not repeat the same primary action in the top bar.
- Meta treatment: risk/urgency/intervention should usually render as quiet text
  on dense review rows. Reserve pills or badges for places where scan speed
  clearly improves.
- Add affordance: on review pages, `添加` should usually be a quiet text action
  in the section header, not a large boxed CTA.

### Debug Showcase / Component Catalog

Used in: internal UI review, component QA, visual regression walkthroughs.

- Single catalog: `/debug/components` is the canonical showcase for all
  reusable UI in `src/components/` and `src/components/doctor/`.
- Separation of concerns: `/debug/doctor-pages` is reserved for page/workflow
  mockups, not reusable component inventory.
- Grouping rule: catalog sections are organized by reusable UI purpose
  (`Buttons`, `Dialogs`, `Doctor`), not by whichever page happens to use them.
- Navigation rule: when section count grows, do not use a horizontally
  scrolling tab/chip bar inside the mobile frame.
- Preferred pattern: use one sticky compact section picker with a dropdown.
  The label should show the current section and update with scroll position,
  not only the last tapped item.
- Visual weight: catalog navigation chrome should stay quieter than the
  showcased components. White surface, hairline border, compact typography.

### Collapsible Profile

**File:** [`src/pages/doctor/patients/PatientDetail.jsx`](../../frontend/web/src/pages/doctor/patients/PatientDetail.jsx) (`CollapsibleProfile`)

*See live: [`/debug/components`](http://localhost:5173/debug/components)*

- Collapsed: one-line summary ("李复诊 女·56岁·门诊1") + "展开 ▾"
- Expanded: demographics grid + stats + action bar (删除 left, 导出 right)
- Toggle: `TYPE.caption` (12px), green. Entire row tappable.

### List Rows

**File:** [`src/components/ListCard.jsx`](../../frontend/web/src/components/ListCard.jsx)

*See live: [`/debug/components`](http://localhost:5173/debug/components)*

- Height: 48-56px
- Avatar (36px) + title (`TYPE.body`) + subtitle (`TYPE.secondary`, `#999`)
- Right: timestamp (`TYPE.caption`) or chevron
- Tap target: full row width

### Record Card

**File:** [`src/components/RecordCard.jsx`](../../frontend/web/src/components/RecordCard.jsx)

*See live: [`/debug/components`](http://localhost:5173/debug/components)*

- Collapsed: type label (colored) + chief complaint preview + date
- Expanded: NHC field rows (label-value, 13px) + 删除/编辑 action bar
- Field rows: label (`60px min, #999`) + value (`#333`), separated by `1px #f0f0f0`
- Same field layout used in: profile demographics, interview preview, review summary

### Diagnosis Review Card

**File:** [`src/components/doctor/DiagnosisCard.jsx`](../../frontend/web/src/components/doctor/DiagnosisCard.jsx)

| Collapsed | Expanded |
|-----------|----------|
| *See live showcase* | *See live showcase* |

5 states indicated by a subtle left border plus right-side status text:

| State | Border | Right label |
|-------|--------|-------------|
| Unreviewed | `#f0f0f0` solid | 待处理 |
| Confirmed | `#07C160` solid | 已确认 |
| Rejected | `#e5e5e5` solid | 已排除 |
| Edited | `#F59E0B` solid | 已修改 |
| Doctor-added | `#07C160` solid | 已补充 |

- Collapsed: diagnosis title + lightweight meta (`高 / 紧急 / 药物`) + quiet status text
- Expanded: detail text + right-aligned text actions (`✎ 修改 | ✗ 排除 | ✓ 确认`)
- Section add action: quiet text action on the right, not a large boxed CTA

### Field Review Card

**File:** [`src/components/doctor/FieldReviewCard.jsx`](../../frontend/web/src/components/doctor/FieldReviewCard.jsx)

*See live: [`/debug/components`](http://localhost:5173/debug/components) → Doctor*

- Purpose: carry-forward and import-preview review for structured fields
- Header: title + subtitle on left, quiet `展开 ▾ / 收起 ▴` text on right
- Per-field layout: label (`TYPE.caption`) above value (`TYPE.secondary`)
- Per-row actions: lightweight text actions with small glyphs, aligned right
  (`✎ 编辑`, `✗ 忽略`, `✓ 沿用/确认`)
- Footer actions: bulk decisions may use stronger full-width buttons
  (`全部忽略` | `全部沿用/全部确认`)
- Edit mode: textarea + lightweight `取消 / 保存` text actions unless a
  stronger CTA is needed for safety

### Settings Rows

**File:** [`src/pages/doctor/SettingsPage.jsx`](../../frontend/web/src/pages/doctor/SettingsPage.jsx)

*See live: [`/debug/components`](http://localhost:5173/debug/components)*

- Icon (colored square) + title + subtitle + chevron (→)
- Grouped by section labels (账户, 工具, 通用, 账户操作)

### Empty State

**File:** [`src/components/EmptyState.jsx`](../../frontend/web/src/components/EmptyState.jsx)

*See live: [`/debug/components`](http://localhost:5173/debug/components)*

- Centered icon (48px, `#ccc`) + "暂无XX" (`TYPE.body`) + hint (`TYPE.caption`, `#999`)
- **Show** when guidance helps user act
- **Hide** when empty section adds no value

### Badges / Status Pills

- Outlined: `border: 0.5px solid; border-radius: 3px; padding: 0 5px`
- Font: `TYPE.micro` (11px/500)
- Red: 急诊. Amber: 紧急/待审核/已修改. Gray: everything else

### Filter Chips

**File:** [`src/pages/doctor/TasksPage.jsx`](../../frontend/web/src/pages/doctor/TasksPage.jsx)

- Active: green fill + white text
- Inactive: gray border + gray text
- Used in: task list (全部/待审核/待办/已完成), record tabs (全部/病历/检验/问诊)

### Action Button Layout

- Cancel + confirm actions in dialog footers use inline `AppButton` pairs
- Destructive left (red), constructive right (green). Always.
- Usage: `<AppButton variant="danger">取消</AppButton> <AppButton>保存</AppButton>`

### AskAIBar

**File:** [`src/components/AskAIBar.jsx`](../../frontend/web/src/components/AskAIBar.jsx)

- Sticky floating "问 AI 任何问题..." entry bar on home page
- Green AI icon + gray placeholder text. Taps navigate to chat.

### BottomSheet

**File:** [`src/components/BottomSheet.jsx`](../../frontend/web/src/components/BottomSheet.jsx)

- Swipe-up panel overlay (~85% screen). Dark backdrop.
- Swipe down or tap backdrop to close.
- Used for: mobile dialogs, pickers, action menus.

### DetailCard

**File:** [`src/components/DetailCard.jsx`](../../frontend/web/src/components/DetailCard.jsx)

- Compact key-value card for short-field detail views
- Title heading + label-value rows. Used in task detail, knowledge detail.

### DoctorBubble

**File:** [`src/components/DoctorBubble.jsx`](../../frontend/web/src/components/DoctorBubble.jsx)

- Doctor reply message bubble in patient chat
- Shows doctor name + timestamp + message content

### ErrorBoundary

**File:** [`src/components/ErrorBoundary.jsx`](../../frontend/web/src/components/ErrorBoundary.jsx)

- React error boundary. Wraps each section in DoctorPage.
- Shows fallback UI on crash instead of blank screen.

### NewItemCard

**File:** [`src/components/NewItemCard.jsx`](../../frontend/web/src/components/NewItemCard.jsx)

- Dashed "+" card for creating new items
- Used at top of: patient list ("新建患者"), task list ("新建任务"), record list ("新建病历")

### PageSkeleton

**File:** [`src/components/PageSkeleton.jsx`](../../frontend/web/src/components/PageSkeleton.jsx)

- Unified page layout wrapper. Handles: SubpageHeader, list/detail split, mobile subpage override.
- Props: `title`, `headerRight`, `listPane`, `detailPane`, `mobileView`

### RecordAvatar

**File:** [`src/components/RecordAvatar.jsx`](../../frontend/web/src/components/RecordAvatar.jsx)

- Colored icon for record type (visit=green, lab=purple, imaging=blue, etc.)
- Shared by doctor and patient views.

### RecordFields

**File:** [`src/components/RecordFields.jsx`](../../frontend/web/src/components/RecordFields.jsx)

- Renders NHC structured fields as label-value rows
- Used in: record card, interview preview dialog, review page summary

### SectionLabel

**File:** [`src/components/SectionLabel.jsx`](../../frontend/web/src/components/SectionLabel.jsx)

- Small gray group header: 12px/600, `#666`
- Examples: "账户", "工具", "最近 · 5位患者"

### StatusBadge

**File:** [`src/components/StatusBadge.jsx`](../../frontend/web/src/components/StatusBadge.jsx)

- Inline colored pill badge for status/category labels
- Props: `label`, `colorMap` (maps label to color)
- Examples: 高/中/低 confidence, 急诊/紧急/常规 urgency

### SuggestionChips

**File:** [`src/components/SuggestionChips.jsx`](../../frontend/web/src/components/SuggestionChips.jsx)

- Floating quick-reply options above input bar
- Multi-select toggle. Selected chips shown as green tags in input field.
- × to dismiss entire bar. Used in: interview (AI suggestions), chat.

### TaskChecklist

**File:** [`src/components/TaskChecklist.jsx`](../../frontend/web/src/components/TaskChecklist.jsx)

- Checkbox list for patient-facing tasks
- Shows: title, subtitle, due-date badge, urgency badge, optional upload button
- Used in: patient portal tasks tab

---

## 7. Interaction Patterns

### Navigation

- **Tab tap** → switch section, no animation
- **List row tap** → push to detail (SubpageHeader with back button)
- **Back button** → pop to previous (browser history)
- **Swipe** → not used (reserved for future)

### Destructive Actions (Delete)

1. **Single tap** shows the delete text button
2. **Second tap** shows inline confirmation: "确认删除？[确认] [取消]"
3. **Third tap** on "确认" executes deletion
4. Never delete in fewer than 2 intentional taps

### Cancel / Discard (leaving unsaved work)

**Every cancel/back action that would discard user work MUST use
`CancelConfirm`** ([`src/components/CancelConfirm.jsx`](../../frontend/web/src/components/CancelConfirm.jsx)).

Two-step flow:
1. User taps cancel/back → `CancelConfirm` popup appears
2. User sees: "确认离开？未保存的内容将会丢失"
3. Two buttons: **确认** (red text, left — discard and leave) | **返回** (green fill, right — continue working)

```
┌────────────────────────┐
│     确认离开？          │
│  未保存的内容将会丢失    │
│                        │
│  [确认]      [返回]     │
│  red,left   green,right │
└────────────────────────┘
```

**When to use:** Any cancel/back that would lose unsaved data:
- Interview in progress → back button
- Record edit dialog → cancel
- Diagnosis review with unsaved decisions → back button
- Any form with user input → cancel

**When NOT to use:** Navigation that doesn't lose data:
- Browsing between tabs (no unsaved state)
- Back from read-only views (patient detail, record view)
- Closing a dialog that has no user input

### Collapsible Content

- **Tap header** → toggle expand/collapse
- **Default state**: collapsed on mobile
- **Auto-collapse**: carry-forward section collapses after all items acted on

### Auto-Save vs Manual Save

- **Diagnosis decisions** (✓/✗/✎): auto-save per item (API call on each action)
- **Record editing**: manual save (edit dialog with 保存 button)
- **Interview**: manual save (完成 button → preview dialog → 保存/保存并诊断)

### Loading States

- **Fast loads** (<200ms): show content directly, no skeleton
- **LLM calls** (5-15s): "AI 正在分析..." with animated skeleton
- **Polling**: every 3 seconds when waiting for async diagnosis results
- **Button loading**: disabled + "保存中..." text replacement

---

## 8. Rules Checklist

Before submitting any UI change, verify:

- [ ] Import `TYPE`, `ICON`, `COLOR` from theme — no hardcoded sizes or colors
- [ ] Delete on left, actions on right — everywhere
- [ ] Max 1 BarButton in top bar, max 2 characters
- [ ] Deletion requires 2-tap confirmation
- [ ] Cancel/back that discards work uses `CancelConfirm` popup (确认|返回)
- [ ] Button text max 2 characters unless justified (保存, 取消, 确认, 删除, 返回)
- [ ] Review rows use text actions before filled buttons
- [ ] Review pages have at most 1 strong green CTA
- [ ] `/debug/components` contains all reusable components, including `components/doctor`
- [ ] Showcase section navigation uses a compact dropdown/picker when groups become numerous
- [ ] Content has bottom padding for nav clearance (`pb: 64px`)
- [ ] Sticky bars don't overlap with bottom nav
- [ ] Empty sections hidden when they add no value
- [ ] Font sizes use only the 7 `TYPE` tokens
- [ ] No shadows, no gradients — flat only
- [ ] `position: absolute` (not fixed) for elements inside MobileFrame
- [ ] Record field labels and values use same `TYPE.secondary` (13px)
- [ ] Chinese text for all UI. English for technical identifiers only.
