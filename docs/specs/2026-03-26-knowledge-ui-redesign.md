# Knowledge Base UI Redesign

**Date:** 2026-03-26
**Status:** Approved
**Goal:** Replace the current KnowledgeSubpage (FieldReviewCard-based) with a clean WeChat-inspired collapsible category list with inline edit and swipe-to-delete.

## Current State

KnowledgeSubpage uses FieldReviewCard per category. FieldReviewCard was designed for carry-forward confirm/dismiss actions, not knowledge browsing. The result: "编辑" and "删除" buttons feel forced, category headers lack visual weight, and there's no scaling strategy for large lists.

## Design

### Layout: Collapsible Category Sections

Each category with items renders as a white card with a left color accent bar. Items are clean rows with 2-line text preview and subtle metadata.

```
┌──────────────────────────────────┐
│ ‹        知识库           添加    │  ← SubpageHeader
├──────────────────────────────────┤
│   共 5 条知识                     │  ← count subtitle
├──────────────────────────────────┤
│▌ 危险信号              2    ▾    │  ← red accent bar, expanded
│  ─────────────────────────────── │
│  蛛网膜下腔出血（SAH）：突发      │  ← 2-line clamped text
│  剧烈头痛（雷击样），伴恶心...    │
│  引用5次 · 3月20日               │  ← subtle metadata
│  ─────────────────────────────── │
│  急性脑梗死：突发偏瘫、失语、     │
│  视野缺损。NIHSS评分＞4分...      │
│  引用3次 · 3月18日               │
├──────────────────────────────────┤
│▌ 问诊指导              1    ▾    │  ← green accent bar, expanded
│  ─────────────────────────────── │
│  高血压患者首诊：必须询问头痛、   │
│  头晕、视物模糊、胸闷...         │
│  引用8次 · 3月15日               │
├──────────────────────────────────┤
│▌ 诊断规则              1    ›    │  ← blue, collapsed (if >5 items)
├──────────────────────────────────┤
│▌ 治疗方案              1    ›    │  ← purple, collapsed (if >5 items)
└──────────────────────────────────┘
```

### Section Collapse Behavior

- **≤5 items in category → expanded by default**
- **>5 items in category → collapsed by default** (shows count badge only)
- Tap header → toggle expand/collapse
- Categories with 0 items → hidden entirely

### Category Colors

| Category | Key | Color | Accent |
|----------|-----|-------|--------|
| 危险信号 | `red_flag` | `#E8533F` | Left border 3px |
| 问诊指导 | `interview_guide` | `#07C160` | Left border 3px |
| 诊断规则 | `diagnosis_rule` | `#1B6EF3` | Left border 3px |
| 治疗方案 | `treatment_protocol` | `#8e44ad` | Left border 3px |
| 自定义 | `custom` | `#999` | Left border 3px |

### Item Row

- **Text:** 13px, `COLOR.text2`, `line-height: 1.55`, 2-line clamp (`-webkit-line-clamp: 2`)
- **Metadata:** 10px, `COLOR.text4`, format: `引用{N}次 · {M}月{D}日`
- **Padding:** 10px vertical, content indented past accent bar

### Interactions

**Tap item → inline edit:**
- Text replaces with auto-sizing textarea (same font/size)
- Cancel (left, gray) / 保存 (right, green) buttons appear below
- Save calls `onEdit(id, newText)`, then collapses back to display mode

**Swipe left → delete:**
- Red "删除" button slides in from right (WeChat chat-list pattern)
- Tap delete → ConfirmDialog ("删除后该知识将不再影响 AI 行为")
- Or tap elsewhere to dismiss swipe state

**Header "添加" → existing AddKnowledgeSubpage** (no change)

### Page Structure

- `PageSkeleton` with `title="知识库"`, `onBack`, `headerRight=<BarButton>添加</BarButton>`
- Subtitle: `共 {N} 条知识` in caption text below header
- Content: scrollable list of category sections
- EmptyState when 0 items total

## File Changes

### Modify: `frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx`

Complete rewrite. Remove FieldReviewCard dependency. New structure:

- `KnowledgeSectionHeader` — category header with accent bar, title, count, expand toggle
- `KnowledgeItemRow` — text preview + metadata, tap-to-edit, swipe-to-delete
- `KnowledgeSubpage` — main component, groups items by category, manages expand/edit/delete state

### No other files change

- `SettingsPage.jsx` — already passes `items`, `onDelete`, `onEdit`, `onAdd` to KnowledgeSubpage. Interface unchanged.
- `AddKnowledgeSubpage.jsx` — untouched
- `mockApi.js` — already returns `MOCK_KNOWLEDGE_ITEMS` with correct shape

## What Gets Deleted

- `KnowledgeDetail` component (was the drill-in detail page) — replaced by inline edit
- `FieldReviewCard` import in KnowledgeSubpage — no longer used here
- `sourceBadge` and `formatDate` helpers — replaced by simpler inline metadata

## Not In Scope

- Swipe-to-delete is a nice-to-have. If complex, fall back to long-press → ConfirmDialog (simpler).
- Drag-to-reorder items within a category
- Search/filter across all knowledge items
