# Workflow 05 — Knowledge CRUD (4 sources)

Ship gate for the **我的知识库** list + add + detail flow. Doctors teach
the AI by adding rules, guidelines, and templates through 4 input sources:
text, file (PDF/Word), web URL, and camera/photo. If any source breaks,
the AI can't learn — this is the most common "I taught my AI but it
didn't listen" failure mode.

**Area:** `src/pages/doctor/subpages/KnowledgeSubpage.jsx`,
`AddKnowledgeSubpage.jsx`, `KnowledgeDetailSubpage.jsx`, `components/KnowledgeCard.jsx`
**Spec:** `frontend/web/tests/e2e/05-knowledge.spec.ts`
**Estimated runtime:** ~10 min manual / ~90 s automated

---

## Scope

**In scope**

- Knowledge list view: stats bar, search, sorting, persona card pinned
  at top, empty state.
- Add via **text** input (manual typing + optional LLM processing).
- Add via **file upload** (PDF / DOCX / TXT — extract → preview → edit → save).
- Add via **web URL** (fetch → preview → save).
- Add via **camera/photo** (file picker with `capture="environment"`).
- Detail page: full text, reference count, delete action.
- Post-add return to list with new item sorted to top by recency.
- Search filter (title + full text content).
- Empty state CTAs.

**Out of scope**

- Voice input in the text source — not widely tested, skip in automation.
- Knowledge citation in diagnosis output — covered by
  `ai-thinks-like-me-qa-plan.md`.
- LLM processing quality (whether the "AI整理" produces good text) —
  eval suite.

---

## Pre-flight

Standard pre-flight. The test file expects an example PDF and HTML in
`frontend/web/public/examples/` (already shipped with the app — used as
onboarding pre-fills). Spec references:

- `public/examples/pci-antiplatelet-guide.html` — used as URL import fixture.
- `tests/e2e/fixtures/files/sample-guide.pdf` — create this small PDF
  fixture if not present; a 1-page generated PDF is enough.

---

## Steps

### 1. List page

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/settings/knowledge` | PageSkeleton header "我的方法" (or "知识库"); back arrow; bottom nav hidden |
| 1.2 | Fresh doctor (no items) | Persona card at top ("我的AI人设" with source `system`); below it EmptyState "暂无知识条目" + primary button "添加第一条规则" |
| 1.3 | Seeded doctor (≥1 items) | Search bar `搜索知识规则 (共N条)`; 3-stat row `条规则` / `本周引用` / `未引用`; `NewItemCard` "添加知识"; persona card pinned first; regular items below, sorted usage-desc then created-desc |
| 1.4 | Date on each card | `今天` / `昨天` / `N天前` — not `-1天前` (BUG-01 gate) |

### 2. Add via text

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Tap `NewItemCard` "添加知识" (or `添加第一条规则` button) | Navigates to `/doctor/settings/knowledge/add`; sourceTab defaults to "text" |
| 2.2 | Source tab row visible | Three tabs: 上传文件 / 网页导入 / 拍照; text mode is the default body (no tab needed) |
| 2.3 | Type content: "高血压患者新发头痛→排除高血压脑病" | Content length counter updates; `保存` button enables |
| 2.4 | Tap primary action (AI整理 or 保存) | If AI整理: preview dialog opens with processed text; else: saved directly |
| 2.5 | On save success | Toast "已添加"; returns to list; new item appears at top with source `doctor` / `text`; 规则总数 incremented |

### 3. Add via URL

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap `网页导入` source tab | URL input field appears; "获取" button next to it |
| 3.2 | Paste `${window.location.origin}/examples/pci-antiplatelet-guide.html` | Input shows URL |
| 3.3 | Tap `获取` | Spinner; after a few seconds, extracted text appears in preview sheet |
| 3.4 | Edit text if needed, then save | Item added; back to list; source badge "网页" or URL source |

### 4. Add via file upload

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Tap `上传文件` source tab | File picker button visible |
| 4.2 | Choose `tests/e2e/fixtures/files/sample-guide.pdf` | Spinner "提取中…"; then preview sheet opens with extracted text |
| 4.3 | The sheet shows the filename + extracted text | Filename row + multiline text field (editable) |
| 4.4 | Optional: tap "AI整理" | Text replaced with processed version; badge "AI已整理" |
| 4.5 | Tap save | Returns to list; new item at top; source badge "文件" |

### 5. Add via camera/photo

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Tap `拍照` source tab | Camera button visible; file input has `capture="environment"` attr |
| 5.2 | Choose an image (in Playwright: set a file input with a test image) | Spinner; then preview with OCR/extracted text |
| 5.3 | Save | Returns to list; new item added |

### 6. Search + filter

| # | Action | Verify |
|---|--------|--------|
| 6.1 | With ≥3 items, type a substring in the search bar | List filters in real time by title + text + content |
| 6.2 | Clear search | Full list restored, sort order intact |
| 6.3 | Type nonsense `zzz` | List empty (no "未找到" text shown, just empty rows — acceptable) |

### 7. Detail view

| # | Action | Verify |
|---|--------|--------|
| 7.1 | Tap any knowledge row | Navigates to `/doctor/settings/knowledge/<id>`; detail page slides in |
| 7.2 | Page content | Title, full text (not summary), source, created date, reference count |
| 7.3 | Edit inline (if supported) | Text field becomes editable; save persists; list reflects change on back |
| 7.4 | Delete button | ConfirmDialog ("确认删除"); confirm removes item; returns to list; 规则总数 decrements |
| 7.5 | Back arrow | Returns to list without reload; scroll position preserved |

### 8. Stats

| # | Action | Verify |
|---|--------|--------|
| 8.1 | With N items, some cited | `条规则` = total; `本周引用` = sum of citations this week; `未引用` = count with `usage_count = 0` (colored warning if > 0) |

---

## Edge cases

- **0-byte file upload** — server returns error; UI shows toast, sheet
  stays open.
- **Huge file (>10 MB)** — should be rejected client-side with a clear
  error, not crash the extract pipeline.
- **URL that 404s** — error toast; URL input stays filled.
- **Non-UTF8 PDF** — extracted text may contain replacement chars;
  verify no crash, even if the text is unreadable.
- **LLM processing timeout** — "AI整理" button should re-enable; text
  preserved; error shown.
- **Double-save** — clicking save twice in quick succession must not
  create duplicates (guard on `saving` state).
- **Emoji/special chars in text** — persisted and rendered correctly
  in both list and detail.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues:

- **BUG-01** — ✅ Fixed. Regression gate: step 1.4 — no `-1天前`.

---

## Failure modes & debug tips

- **Item doesn't appear in list after save** — React Query didn't
  invalidate. Check `queryClient.invalidateQueries({queryKey: QK.knowledge(doctorId)})`
  fires in `AddKnowledgeSubpage` save handler.
- **URL fetch hangs** — `fetchKnowledgeUrl` API call; check backend
  `/api/doctor/knowledge/fetch-url` route, and CORS if the URL is external.
- **File extract returns empty** — PDF library may not handle that format.
  Fall back path: user can paste text manually into the preview sheet.
- **Search doesn't filter persona card** — by design: persona is always
  pinned regardless of search state. Not a bug.
- **Stats `未引用` stuck at 0** — usage counts come from `stats` prop; if
  parent doesn't pass it, falls back to `reference_count` on each item.
