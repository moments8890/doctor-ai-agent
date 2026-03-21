# UI Design Principals & Shared Components

## Typography Scale

Fixed `px` values. Target: Chinese smartphones (375-414px logical width).
WeChat mini-program native — same approach as WeChat, ABC医疗云, 丁香园.

7 levels defined in `src/theme.js` as `TYPE` object. **Import and use `TYPE`
instead of hardcoded fontSize values.** Changing a value in `theme.js` updates
all pages.

```jsx
import { TYPE } from "../../theme";
// or from "../theme" depending on depth

<Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: TYPE.title.fontWeight }}>
  Page Title
</Typography>
```

| Token | Size | Weight | Color | Use |
|-------|------|--------|-------|-----|
| `title` | 16px | 600 | `#1A1A1A` | Top bar title (SubpageHeader), page title |
| `action` | 15px | 400 | `#07C160` | Top bar actions (BarButton), tappable text |
| `heading` | 14px | 600 | `#1A1A1A` | Section titles in content, card headers, form labels |
| `body` | 14px | 400 | `#1A1A1A` | Primary content text, field values, dialog text |
| `secondary` | 13px | 400 | `#333` | List subtitles (ListCard), descriptions, knowledge items |
| `caption` | 12px | 400/600 | `#666`/`#999` | Section labels (SectionLabel), metadata, timestamps |
| `micro` | 11px | 500 | varies | Badges, tags, source labels, reference counts |

**Bottom nav labels:** 10px (MUI default, keep as-is)

**Icons:** 20px in nav/headers, 16px inline, 48px in EmptyState

### Where each level appears

```
┌─────────────────────────────────────┐
│ ‹  title(16/600)    action(15/400)  │  ← SubpageHeader
├─────────────────────────────────────┤
│ caption(12/600)  "工具"              │  ← SectionLabel
├─────────────────────────────────────┤
│ [avatar]  body(15/500)   caption(12)│  ← ListCard title + right
│           secondary(13)             │  ← ListCard subtitle
├─────────────────────────────────────┤
│ heading(14/600)  "诊断规则"    (3) ›│  ← accordion category
│   secondary(13)  micro(11) caption  │  ← expanded item
├─────────────────────────────────────┤
│ heading(14/600) "内容"               │  ← form label
│ body(14/400) input text             │  ← TextField
│ caption(12) helper text             │  ← hint below input
├─────────────────────────────────────┤
│  首页  患者  任务  设置              │  ← bottom nav (10px)
└─────────────────────────────────────┘
```

### Banned sizes

Do not use: 17px, 18px, 22px, 24px, 28px, 32px, 40px, 64px in content areas.
Exception: EmptyState icon (48px), avatar initials.

---

## Color Palette

| Token | Value | Use |
|-------|-------|-----|
| `primary` | `#1B6EF3` | Links, primary buttons, selected chips |
| `primary-light` | `#E8F0FE` | Knowledge source badge (医生) |
| `success` | `#2BA471` | Confirm, save, BarButton, active nav (muted green) |
| `success-light` | `#EDF5F0` | Knowledge source badge (AI学习), confirmed status |
| `danger` | `#D65745` | Delete, reject, red flags, clinical urgency (muted red) |
| `warning` | `#F59E0B` | Pending, attention needed |
| `warning-light` | `#FFF7E6` | Pending status badge |
| `text-1` | `#1A1A1A` | Primary text |
| `text-2` | `#333` | Secondary content text |
| `text-3` | `#666` | Labels (SectionLabel) |
| `text-4` | `#999` | Metadata, timestamps, placeholders |
| `border` | `#E5E5E5` | Card borders, dividers |
| `border-light` | `#f0f0f0` | List row separators |
| `surface` | `#f7f7f7` | Page background |
| `surface-alt` | `#ededed` | Settings page background |
| `white` | `#fff` | Card backgrounds, inputs |

**Banned:** No purple/violet, no teal, no gradients.

---

## Spacing

4px base unit. Compact density for clinical data.

| Token | Value | Use |
|-------|-------|-----|
| `xs` | 4px | Tight gaps (badge padding) |
| `sm` | 8px | Inner card padding, chip gaps |
| `md` | 12px | Content padding, section gaps |
| `lg` | 16px | Page padding (px: 2) |
| `xl` | 24px | Large section gaps |

**Border radius:** 4px buttons/chips, 6px cards, 8px dialogs, 16px pill chips (SuggestionChips)

---

## Page Layout

### Desktop (3-column)
```
[Sidebar 220px] | [List pane (resizable 200-500px)] | [Detail pane (flex)]
```
- Sidebar: handled by `DoctorPage.jsx` (`DesktopSidebar`)
- List + Detail: use `PageSkeleton`

### Mobile
```
[SubpageHeader: back | title | actions]
[Content (scrollable)]
[Bottom nav]
```
- Bottom nav: handled by `DoctorPage.jsx` (`MobileBottomNav`)
- Header + content: use `PageSkeleton`
- Drill-down subpages: pass `mobileView` to `PageSkeleton`

### PageSkeleton Props
```jsx
<PageSkeleton
  title="患者"              // mobile SubpageHeader title
  headerRight={<BarButton>新建</BarButton>}  // mobile header actions
  isMobile={isMobile}
  listPane={<MyList />}     // left column content
  detailPane={<MyDetail />} // right column content (null = placeholder)
  mobileView={subpage}      // fullscreen override for drill-downs
/>
```

---

## Button Classes

Two types — never mix them.

### BarButton — top bar actions only
Plain text, no background. Green `#07C160`, weight 400, 15px.
Visually distinct from bold title text.

```jsx
<BarButton onClick={fn}>新建</BarButton>
<BarButton onClick={fn} color="#999">导出</BarButton>  // muted
<BarButton onClick={fn} loading>保存</BarButton>
```

### AppButton — content-level actions
Filled buttons for forms, dialogs, detail views.

| Variant | Color | Use |
|---------|-------|-----|
| `primary` | green `#07C160` | save, confirm, complete |
| `secondary` | gray `#f5f5f5` | cancel, dismiss |
| `danger` | red `#FA5151` | delete, reject |
| `ghost` | green border | toggle, secondary positive |

| Size | Use |
|------|-----|
| `lg` | primary actions in detail views |
| `md` | dialog buttons (default) |
| `sm` | inline/field buttons |

```jsx
<AppButton variant="primary" size="lg" fullWidth onClick={fn}>完成任务</AppButton>
<AppButton variant="danger" onClick={fn} loading loadingLabel="删除中…">删除</AppButton>
```

### ActionButtonPair — dialog cancel/confirm row
```jsx
<ActionButtonPair onCancel={fn} onConfirm={fn} confirmLabel="保存" loading={saving} />
<ActionButtonPair onCancel={fn} onConfirm={fn} confirmLabel="删除" danger />
```

---

## Content Components

### ListCard — unified list row
Used by patient list, task list, record list, any row with avatar + title + subtitle.

```jsx
<ListCard
  avatar={<PatientAvatar name="王五" size={36} />}
  title="王五"                    // 15px/500
  subtitle="男 · 52岁 · 头痛"     // 13px/400 #999
  right={<Typography sx={{ fontSize: 12, color: "#999" }}>昨天</Typography>}
  onClick={fn}
/>
```

### SectionLabel — group header
12px/600, color `#666`. Left-aligned, compact.

```jsx
<SectionLabel>账户</SectionLabel>
<SectionLabel>最近 · 5位患者</SectionLabel>
```

### StatusBadge — inline colored badge
11px, bordered pill.

```jsx
<StatusBadge label="高" colorMap={{ 高: "#07C160", 中: "#ff9500", 低: "#999" }} />
```

### EmptyState — centered placeholder
Icon 48px `#ccc`, title body2 disabled, subtitle caption disabled.

```jsx
<EmptyState icon={<SomeIcon />} title="暂无任务" subtitle="点击新建" />
```

### SuggestionChips — floating quick-reply bar
Multi-select toggle chips above input bar. Wraps to multiple lines.

```jsx
<SuggestionChips
  items={["今天开始", "两三天了", "一周以上"]}
  selected={selectedSuggestions}
  onToggle={(text) => toggle(text)}
  onDismiss={() => setSuggestions([])}
  disabled={loading}
/>
```

- Selected: green border `#07C160` + light green bg `#e8f5e9`
- Unselected: border `#E5E5E5`, white bg, shadow
- Selected items appear as green tags (12px pill) inside input field
- × to dismiss entire bar

### AskAIBar — sticky "问 AI" entry point
Only used in dashboard/briefing.

```jsx
<AskAIBar onClick={() => navigate("/doctor/chat")} />
```

---

## Knowledge Base UI Pattern

The knowledge base (`SettingsSection.jsx → KnowledgeSubpage`) uses:

### Accordion categories
5 categories: 问诊指导, 诊断规则, 危险信号, 治疗方案, 自定义.
One expanded at a time. Category header: heading(14/500) + count caption(12).
Items: secondary(13) text + micro(11) source badge + caption(12) date + AI引用 count.

### Add form
Category chip selector (QuickCommandBar style) + free text input + help icon
with 2-3 examples per category.

### Knowledge detail
Tap item → detail subpage. Fields: caption(11) label + body(14) value.
Delete action at bottom with confirmation dialog.

### Case library
Confirmed cases only. Shows chief_complaint → diagnosis (body 14/500),
reference count (caption 11), tap for detail with embedding status.

---

## Patient Page Pattern

Patient page mirrors doctor layout: 4 tabs (主页 | 病历 | 任务 | 设置).
Mobile-only. Uses `SubpageHeader` for navigation.

- **主页:** Quick action cards (新问诊, 我的病历) + AI chat. Chat persists in localStorage.
- **病历:** Record list using `ListCard` with type-colored avatars.
- **任务:** Placeholder (future: reminders, follow-ups from doctor).
- **设置:** Profile + logout.

---

## Rules

1. **All pages use `PageSkeleton`** — never build layout from scratch
2. **Top bar: max 2 BarButtons** — if 3+ actions needed, put them in page content as `AppButton`s
3. **Top bar actions = `BarButton`**, content actions = `AppButton` — no filled buttons in headers
4. **`SubpageHeader`** handles back navigation — pass `onBack` for subpages, omit for top-level
5. **List rows use `ListCard`** — avatar (36px) + title (15/500) + subtitle (13/400) + right meta (12)
6. **"New item" rows use `NewItemCard`** — dashed `+` icon, same ListCard layout across all pages
7. **Section headers use `SectionLabel`** — never inline Typography for group labels
8. **Desktop list pane has no back icon** — it's not a subpage
9. **Mobile subpages** go through `mobileView` prop — fullscreen with SubpageHeader back button
10. **Column width is resizable** on desktop (200-500px, persisted to localStorage)
11. **Use only the 7 font sizes** — title(16), action(15), heading(14/600), body(14), secondary(13), caption(12), micro(11)
12. **Deletion always requires confirmation dialog** — never delete on single tap
13. **Detail field format** — compact `label：value` on one line, no cards/borders, just bottom dividers
