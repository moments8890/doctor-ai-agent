# Knowledge List Redesign — Remove Category Grouping + Unified Input Processing

**Date:** 2026-03-27
**Status:** Approved
**Codex review:** Consulted (session 019d3181)

## Problem

Two issues:

1. **Dead category UI.** The backend has removed knowledge categorization —
   `knowledge_handlers.py:77` hardcodes all items to `category="custom"`. But
   `KnowledgeSubpage.jsx` still renders 5 category sections with colored bars,
   collapsible headers, and per-category grouping.

2. **Inconsistent input processing.** File uploads run through LLM processing when
   >500 chars (condensed into clean knowledge snippets, capped at 3000 chars). But
   manual text input has no size limit and no LLM processing — a doctor can paste
   a massive wall of text that goes straight into the DB uncondensed.

## Decision

1. Redesign KnowledgeSubpage as a flat chronological list using the `ListCard` pattern
   (same as PatientsPage), with source-type avatars replacing category colors.
2. Unify input processing: manual text >=500 chars gets LLM-processed with preview,
   same as file uploads. All items capped at 3000 chars.

## Design

### Row Layout (KnowledgeRow wrapper)

```
[Source Avatar 36x36] [gap 1.5] [Title + Subtitle flex:1] [Right metadata]
```

| Slot | Content |
|------|---------|
| Avatar | 36x36 colored square with MUI icon, by source type |
| Title | First non-empty line of text, single line with ellipsis, fontWeight 500 |
| Subtitle | Upload filename (if file source) OR source label ("手动添加" / "AI生成") |
| Right | `引用{n}次` (if >0) + formatted date |

### Source-Type Avatars

| Source value | Label | Icon | Background color |
|---|---|---|---|
| `doctor` | 手动添加 | `EditNoteOutlined` | `COLOR.primary` (#1B6EF3) |
| `upload:*` | filename extracted | `DescriptionOutlined` | `COLOR.success` (#07C160) |
| `agent_auto` | AI生成 | `SmartToyOutlined` | `COLOR.text3` (existing theme token) |

Colors use existing theme tokens — no new one-off values.

### List Structure

1. **NewItemCard** at top: "添加知识" / "手动输入或上传文件"
2. **SectionLabel**: "共 X 条知识"
3. **KnowledgeRow** items sorted by `created_at` DESC
4. **EmptyState** when no items: icon=`MenuBookOutlined`, "暂无知识条目"

### Tap Behavior

- **Read-only in this pass.** Tap shows full text in an expandable area (not inline edit).
- Inline edit is deferred until a `PATCH /api/manage/knowledge/{id}` endpoint exists.
- Delete remains accessible via a delete icon/button visible when expanded.

Rationale (from Codex review): The current `onEdit` handler in `SettingsPage.jsx:188`
only mutates local state (TODO comment). Exposing edit UI without persistence will
confuse users.

### Sorting

- Sort by `created_at` DESC (newest first).
- Items are effectively immutable until edit API lands, so `created_at` = `updated_at`.
- The DB query orders by `updated_at DESC` but API only exposes `created_at` — this is
  consistent for now.

### Unified Input Processing (manual text >=500 chars)

Current file upload flow already works:
```
file → extract text → if >500 chars: LLM process → preview dialog → save (3000 cap)
```

Add the same flow for manual text input:
```
manual text → if >=500 chars: LLM process → preview dialog → save (3000 cap)
             if <500 chars: save directly (as today)
```

**Backend: new endpoint `POST /api/manage/knowledge/process-text`**

```
Request:  { "text": "..." }
Response: { "processed_text": "...", "original_length": 1200, "processed_length": 480, "llm_processed": true }
```

- Reuses the existing `_llm_process_knowledge_text()` function from `doctor_knowledge.py`
  (same LLM prompt as file uploads: `knowledge_ingest.md`)
- If text <500 chars, returns it unchanged with `llm_processed: false`

**Frontend: AddKnowledgeSubpage manual text flow**

1. Doctor types/pastes text in textarea
2. On submit, if text >=500 chars:
   - Call `processKnowledgeText(text)` → new API function
   - Show preview dialog (same as file upload preview): "AI已整理" badge, editable textarea
   - Doctor can edit the processed result
   - On confirm → call existing `addKnowledgeItem()` to save
3. If text <500 chars: save directly as today

**Backend: add 3000 char cap to `add_knowledge` handler**

The `POST /api/manage/knowledge` handler currently has no size limit on `content`.
Add validation: `if len(content) > 3000: raise HTTPException(400, "内容过长")`.
This makes the cap consistent with the upload path.

## Files to Change

### Frontend (5 files)

| File | Change |
|------|--------|
| `KnowledgeSubpage.jsx` | Rewrite: remove category constants, section headers, collapsible logic. New flat list with `KnowledgeRow` using `ListCard`. Add expand-on-tap for full text. |
| `AddKnowledgeSubpage.jsx` | Manual text >=500 chars: call process endpoint, show preview dialog before save. Reuse existing preview dialog pattern from file upload flow. |
| `SettingsPage.jsx` | Clean up wrapper: remove `onEdit` prop (deferred), simplify state. |
| `MockData.jsx` | Remove `category` field from `MOCK_KNOWLEDGE_ITEMS`. Set all items to realistic source values. Sort by `created_at` DESC. |
| `mockApi.js` | Remove category logic. Add mock `processKnowledgeText`. Return items sorted by `created_at` DESC. |

### Backend (2 files)

| File | Change |
|------|--------|
| `knowledge_handlers.py` | Add `POST /api/manage/knowledge/process-text` endpoint. Add 3000 char cap to `add_knowledge` handler. |
| `doctor_knowledge.py` | Extract `_llm_process_knowledge_text()` call into a reusable public function `process_knowledge_text(text)` for the new endpoint. |

### API (1 file)

| File | Change |
|------|--------|
| `api.js` | Add `processKnowledgeText(doctorId, text)` function for the new endpoint. |

### Not Changed (intentional)

| File | Reason |
|------|--------|
| `knowledge_ingest.md` | LLM prompt stays the same — reused for both flows. |

## Out of Scope

- **Edit API** (`PATCH /api/manage/knowledge/{id}`) — separate backend task.
- **Search/filter** — not needed until knowledge base grows significantly.
- **Category field removal from DB** — column stays for backwards compat, unused.
- **Showcase/debug page updates** — update after main component ships.

## Codex Feedback Incorporated

1. Use `KnowledgeRow` wrapper instead of raw `ListCard` — agreed.
2. Keep `category` as hidden metadata, don't delete from API contract — agreed.
3. Use first non-empty line for title, filename fallback for uploads — agreed.
4. Don't expose edit UI without persistence — agreed, deferred to edit API task.
5. Use existing theme tokens for avatar colors, no hardcoded purple — agreed.
6. Subtitle should not be overloaded — simplified to source label only.

## Input Processing Summary

| Input path | <500 chars | >=500 chars |
|---|---|---|
| Manual text | Save directly | LLM process → preview → save (3000 cap) |
| File upload | Save directly | LLM process → preview → save (3000 cap) |
| All paths | 3000 char hard cap enforced at API level |
