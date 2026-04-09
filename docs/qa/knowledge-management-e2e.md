# Knowledge Management E2E Checklist

Tests the full doctor knowledge lifecycle: ingestion from all sources → list/search/edit →
KB feeds into follow-up reply draft → citation display → teaching loop → reference tracking.

This is the core "AI thinks like me" value loop. The existing `knowledge-citation-e2e.md`
covers diagnosis citations. This checklist covers **follow-up reply** citations (the
primary use case), all ingestion methods, NL patient search, and the teaching loop.

**Tool**: gstack `/qa` (headless Chromium via `$B`) or manual browser at http://127.0.0.1:5173/doctor
**Test account**: `doctor_id=test_doctor`
**Backend**: port 8000 (dev), port 8001 (isolated runs — never use 8001 for sim)
**Time to complete**: ~45 min manual, ~20 min automated
**Dependencies**: at least 1 patient with a recent inbound message (for TC-8)

---

## Setup

```bash
# Start backend (no hot reload — embedding loading is expensive)
NO_PROXY=* no_proxy=* .venv/bin/uvicorn main:app --port 8000

# Start frontend
cd frontend/web && npm run dev

# Confirm backend healthy
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" | python3 -m json.tool | head -5

# Seed demo patients if needed (provides patients + inbound messages for TC-8)
curl -s -X POST "http://127.0.0.1:8000/api/manage/onboarding/seed-demo?doctor_id=test_doctor"
```

Navigate to: `http://127.0.0.1:5173/doctor?doctor_id=test_doctor`

---

## TC-1 · Text Knowledge Ingestion

Starting point: 我的AI tab → 我的知识库 → + add button.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 1.1 | Open 我的知识库 | Subpage opens; existing items listed (or empty state shown) |
| 1.2 | Tap + / add button | Add knowledge subpage opens with text input |
| 1.3 | Enter: `术后患者出现发热超过38.5℃，首先排查切口感染，不要等待自行退热` → save | POST `/api/manage/knowledge → 200`; item appears in list with auto-generated title |
| 1.4 | Enter a second rule: `服用华法林的患者复查时必须同时检查INR，目标范围2.0–3.0` → save | Second item appears; list shows 2 items |
| 1.5 | Note both item IDs (shown in URL or API response) | IDs will be `KB-{id}` in LLM output |

**Verify via API:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; [print(i['id'], i['source'], i['content'][:60]) for i in items[-2:]]"
```
Expected: both items with `source = "doctor"`.

---

## TC-2 · URL Knowledge Ingestion

| # | Action | Pass Criteria |
|---|--------|--------------|
| 2.1 | In add knowledge subpage, switch to URL tab | URL input field shown |
| 2.2 | Paste a URL to a real medical article (e.g. a clinical guideline page) | "提取中…" loading state shown |
| 2.3 | Wait for extraction (< 15s) | Extracted text shown in preview; POST `/api/manage/knowledge/fetch-url → 200` |
| 2.4 | Review extracted text → confirm save | Item saved with `source = "url"`, `source_url` populated |
| 2.5 | Return to knowledge list | URL-sourced item visible; source badge shows "网页" or domain name |

**Verify via API:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; url_items=[i for i in items if i.get('source')=='url']; print(url_items)"
```
Expected: `source = "url"`, `source_url` non-null.

**Edge cases:**
- 2.6: Paste an invalid / unreachable URL → error message shown, no crash
- 2.7: Paste a URL to a non-medical page (e.g. news site) → extraction completes; text shown (no filtering)

---

## TC-3 · Photo / Camera Knowledge Ingestion

| # | Action | Pass Criteria |
|---|--------|--------------|
| 3.1 | In add knowledge subpage, switch to photo/camera tab | Camera/upload option shown |
| 3.2 | Upload a photo of a handwritten clinical note or printed guideline | Upload accepted; OCR processing starts |
| 3.3 | Wait for OCR extraction (< 30s) | Extracted text shown in preview |
| 3.4 | Review extracted text → confirm save | Item saved with `source = "photo"` or `source = "image"` |
| 3.5 | Item appears in knowledge list | Source badge shows 图片/照片 |

**Verify via API:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; photo=[i for i in items if 'photo' in i.get('source','') or 'image' in i.get('source','')]; print(photo)"
```

**Edge cases:**
- 3.6: Upload a blurry/low-quality image → extraction returns partial text or empty; no crash; user can still save manually
- 3.7: Upload a non-image file as photo → validation error shown

> **Note:** Uses the vision LLM path (httpx trust_env=False fixed in BUG-04).
> If extraction fails with "Connection error", check proxy settings.

---

## TC-4 · PDF Knowledge Ingestion

| # | Action | Pass Criteria |
|---|--------|--------------|
| 4.1 | In add knowledge subpage, switch to document/file tab | File upload shown |
| 4.2 | Upload a single-page PDF containing clinical text | Upload accepted |
| 4.3 | Wait for extraction (< 60s — uses vision LLM per page) | Extracted text shown in preview |
| 4.4 | Save | Item saved with `source = "file"` or `source = "pdf"` |
| 4.5 | Upload a multi-page PDF (3–5 pages) | All pages extracted and concatenated; `PDF_LLM_MAX_PAGES` default is 10 |

**Edge cases:**
- 4.6: Upload a scanned PDF (image-only, no text layer) → vision path triggers; text extracted from images
- 4.7: Upload a PDF exceeding `PDF_LLM_MAX_PAGES` (>10 pages) → only first 10 pages extracted; no crash

> **Note:** Falls back to `pdftotext` if `pdftoppm` is unavailable. Check which path runs:
> `grep "pdftoppm\|pdftotext" logs/app.log | tail -5`

---

## TC-5 · Knowledge List, Detail, and NL Search

### 5a — List

| # | Action | Pass Criteria |
|---|--------|--------------|
| 5.1 | Open 我的知识库 | All items listed, sorted by activity (most recently used first) |
| 5.2 | Each row shows: title, summary, source badge, reference count | No blank titles; no raw `[KB-N]` in any field |
| 5.3 | Dates on knowledge cards | Shows 今天 / 昨天 / N天前 — **not** -1天前 or future date (BUG-01 fix) |

### 5b — Detail

| # | Action | Pass Criteria |
|---|--------|--------------|
| 5.4 | Click any item | Detail subpage opens with full text |
| 5.5 | Detail shows: full content, source label, created date, reference count | All fields populated |
| 5.6 | Edit button visible | Tapping edit makes content editable inline |
| 5.7 | Make a small edit → save | Edit persisted; `updated_at` refreshed; returns to detail view |

### 5c — Text Search

> **Requires TC-1:** Search looks for "华法林" which is added in TC-1 step 1.4.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 5.8 | Type "华法林" in the search bar | Results filter to matching items only |
| 5.9 | Clear search | Full list restored |

### 5d — NL Patient Search (verify BUG-06 fix)

This tests the NL search in the 患者 tab, not knowledge. Included here as part of the
recent-fix regression sweep.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 5.10 | Go to 患者 tab; type "最近来诊的男性" in search | Returns male patients with recent records — **not** empty list |
| 5.11 | Type "姓张的女性" in search | Returns female patients with surname 张 |
| 5.12 | Type "60多岁高血压患者" | Returns patients aged 60–69 with hypertension-related records |

**Verify via API (5.10):**
```bash
curl -s "http://127.0.0.1:8000/api/manage/patients/search?doctor_id=test_doctor&q=最近来诊的男性" \
  | python3 -c "import sys,json; data=json.load(sys.stdin); print([(p['name'], p.get('gender')) for p in data.get('patients',[])])"
```
Expected: non-empty list; all results have `gender in ['male', '男']`.

---

## TC-6 · Knowledge Delete

| # | Action | Pass Criteria |
|---|--------|--------------|
| 6.1 | Add a throwaway item: `测试删除规则` | Item saved |
| 6.2 | Open detail → delete | Confirmation dialog shown (cancel LEFT, delete RIGHT) |
| 6.3 | Confirm delete | `DELETE /api/manage/knowledge/{id} → 200`; item removed from list |
| 6.4 | Reload knowledge list | Item gone; count decremented |
| 6.5 | If the deleted item was previously cited in a suggestion, reload that review page | Page does not crash; citation indicator either hidden or shows "已删除" |

**Anti-regression:** `/api/manage/knowledge/batch` must handle missing IDs gracefully
(return empty for those IDs, not 404).

---

## TC-7 · AI Persona Knowledge

| # | Action | Pass Criteria |
|---|--------|--------------|
| 7.1 | Go to 我的AI tab → scroll to AI Persona section | Persona card shown (may be empty/placeholder if not yet set) |
| 7.2 | Tap persona card / edit | Persona detail page opens |
| 7.3 | View current persona content | Shows doctor's communication style fields; no raw `[KB-N]` visible |
| 7.4 | Persona is listed first in 我的知识库 | Pinned at top of knowledge list (BUG from last session confirmed fixed) |

---

## TC-8 · KB → Follow-up Reply Citation (Core Loop)

This is the primary "AI thinks like me" test. Tests the **follow-up reply** path (not diagnosis).

> **ISOLATION WARNING (from Codex + Claude review):** `seed-demo` creates preseeded drafts
> with `cited_knowledge_ids` already populated by `preseed_service.py`. Using those drafts
> means TC-8 passes WITHOUT any live LLM citation call — the core loop is never exercised.
> You MUST create a fresh inbound message AFTER TC-1's KB rules are saved, and verify the
> draft's `created_at` is newer than the KB rules before checking citations.

### Setup

```bash
# Step A: Record the KB rule timestamps from TC-1
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; [print(i['id'], i['created_at']) for i in items[-2:]]"
# Save these timestamps as LAST_KB_TIME

# Step B: Create a FRESH inbound patient message (after TC-1 completes)
# Use a real patient from the seeded list — send a message via API or patient portal
# The message content should relate to TC-1's KB rules (e.g., "我术后发烧了怎么办")
curl -s -X POST "http://127.0.0.1:8000/api/patient/messages" \
  -H "Content-Type: application/json" \
  -d '{"patient_token": "<patient_token>", "content": "我术后发烧了怎么办，今天38.6度"}'

# Step C: Wait for background draft generation (batch runs ~5s)
sleep 10

# Step D: Verify the NEW draft was generated AFTER TC-1's KB rules
curl -s "http://127.0.0.1:8000/api/manage/drafts?doctor_id=test_doctor" \
  | python3 -c "
import sys, json
from datetime import datetime
data = json.load(sys.stdin)
drafts = data.get('drafts', [])
for d in drafts:
    print(d.get('id'), d.get('created_at'), d.get('status'))
"
# ONLY proceed if a draft exists with created_at > LAST_KB_TIME
# If no fresh draft: seed-demo may have seeded stale ones; dismiss and wait for regeneration
```

### Test steps

| # | Action | Pass Criteria |
|---|--------|--------------|
| 8.1 | Go to 审核 tab → 待回复 subtab | At least 1 draft shown with `created_at > LAST_KB_TIME` (the fresh one from Setup) |
| 8.2 | Open the fresh draft (NOT a seeded one) | Draft reply detail shown |
| 8.3 | Check citation display | At least 1 `引用:` badge visible on the draft bubble |
| 8.4 | Expand detail text | No raw `[KB-N]` in displayed text |
| 8.5 | Tap a `引用:` badge | Navigates directly to knowledge detail subpage (NOT a popover) |
| 8.6 | Knowledge detail subpage shows the correct rule | Rule title and full text match the KB rule from TC-1 |

> **UI note:** The follow-up path renders clickable `引用: <title>` badges that navigate
> directly. There is no CitationPopover or "查看全文" link in this path — that is the
> diagnosis path UI. If you see a popover, you are on the wrong page.

**Verify citation in raw API:**
```bash
DRAFT_ID=<id of fresh draft from 8.1>
curl -s "http://127.0.0.1:8000/api/manage/drafts/$DRAFT_ID?doctor_id=test_doctor" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('cited_ids:', d.get('cited_knowledge_ids'), '\ndraft_text (first 100):', d.get('draft_text','')[:100])"
```
Expected: `cited_knowledge_ids` is a non-empty list containing IDs from TC-1.

**Verify LLM call actually ran:**
```bash
# Confirm a draft_reply LLM call exists with timestamp after LAST_KB_TIME
python3 -c "
import json
from datetime import datetime
with open('logs/llm_calls.jsonl') as f:
    calls = [json.loads(l) for l in f if '\"op\":\"draft_reply\"' in l or '\"op\":\"followup' in l]
print(f'Found {len(calls)} draft_reply LLM calls')
if calls:
    print('Latest:', calls[-1].get('timestamp'), '| status:', calls[-1].get('status'))
"
```
If no `draft_reply` LLM calls exist, the test used seeded data and the core loop was never exercised.

---

## TC-9 · Teaching Loop (Save-as-Rule from Edit)

> **Blocked by TC-8:** Only run TC-9 if TC-8 produced a fresh draft with non-empty
> `cited_knowledge_ids`. If TC-8 used seeded data or failed, TC-9 results are not meaningful.

Tests that a significant doctor edit triggers a "save as rule?" prompt, and that saving
creates a new knowledge rule.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 9.1 | Open a draft reply (same as TC-8) | Draft detail shown |
| 9.2 | Tap "修改" (edit) | Edit textarea appears |
| 9.3 | Make a **significant** change (rewrite >30% of the text, e.g. add a specific medication recommendation) | Edit textarea shows new text |
| 9.4 | Tap save/send | `PUT /api/manage/drafts/{id}/edit → {teach_prompt: true}` |
| 9.5 | "保存为规则？" prompt appears | Dialog or bottom sheet shown with the edited text snippet |
| 9.6 | Tap "保存" | `POST /api/manage/drafts/{id}/save-as-rule → 200`; new knowledge rule created |
| 9.7 | Open 我的知识库 | New rule appears with `source = "teaching"` or similar label |

**Verify teaching rule created:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; teaching=[i for i in items if i.get('source')=='teaching']; [print(i['id'], i['source'], i['content'][:60]) for i in teaching]"
```

**Edge case:**
- 9.8: Make a **small** change (fix a typo) → no "save as rule?" prompt (small edits don't trigger teaching)

---

## TC-10 · Reference Count and Usage Tracking

> **Blocked by TC-8 (fresh draft):** Reference counts only increment when `draft_reply.py`
> logs citations to `knowledge_usage_log`. This only happens on a live LLM call, not on
> seeded drafts. If TC-8 used seeded data, TC-10 will always show 0次引用 and fail.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 10.1 | After TC-8 run, return to 我的知识库 | Knowledge list visible |
| 10.2 | Find the KB item(s) that were cited in TC-8 | Reference count shows `≥ 1次引用` |
| 10.3 | Click item → detail | Usage section shows recent citation entry (patient name or record date) |
| 10.4 | Run TC-8 again with a different patient (if available) | Reference count increments again |

**Verify via API:**
```bash
KB_ID=<id of item cited in TC-8>
curl -s "http://127.0.0.1:8000/api/manage/knowledge/$KB_ID/usage?doctor_id=test_doctor" | python3 -m json.tool
```
Expected: `reference_count >= 1`, `recent_uses` array non-empty.

---

## Regression Checks

### REG-001 · No Raw [KB-N] Anywhere in UI

| Check | Where to look | Pass Criteria |
|-------|--------------|--------------|
| Knowledge list | All row titles and summaries | No `[KB-` substring visible |
| Draft reply bubble | Expanded detail text | No `[KB-` substring visible |
| Review suggestion detail | Expanded suggestion text | No `[KB-` substring visible |

```javascript
// Run in browser devtools
document.body.innerText.includes('[KB-')  // must be false
```

### REG-002 · Date Display (BUG-01 fix)

| Check | Pass Criteria |
|-------|--------------|
| Knowledge cards `created_at` | Shows 今天 for items created today — not 昨天 or -1天前 |
| Items created > 7 days ago | Shows N月N日 format (not negative number) |

### REG-003 · Dialog Button Order

| Check | Pass Criteria |
|-------|--------------|
| Knowledge delete confirm | 取消 LEFT (grey), 删除 RIGHT (red/primary) |
| Review suggestion edit | 取消 LEFT (grey), 保存 RIGHT (green) — BUG-05 fix |

### REG-004 · NL Search Gender (BUG-06 fix)

```bash
curl -s "http://127.0.0.1:8000/api/manage/patients/search?doctor_id=test_doctor&q=男性" \
  | python3 -c "import sys,json; data=json.load(sys.stdin); genders=[p.get('gender') for p in data.get('patients',[])]; print('genders:', genders)"
```
Expected: returns results (non-empty); all genders are `male` or `男`.

---

## Known Issues from Prior QA (as of 2026-04-08)

> **Note (from Codex + Claude review 2026-04-08):** BUG-DRAFT-002, BUG-DRAFT-003, and
> BUG-DRAFT-004 appear fixed in the frontend code based on static analysis
> (`PatientDetail.jsx` wires `SheetDialog` confirmation and `ConfirmDialog` for teach_prompt;
> `draft_handlers.py` returns 200 for save-as-rule). Status below is updated to
> **Likely Fixed** — verify with first actual test run.

| ID | Description | Status | Reference |
|----|-------------|--------|-----------|
| BUG-DRAFT-002 | No confirmation dialog before send | **Likely Fixed** — verify in TC-8.2 | qa-report-draft-reply-2026-04-01.md |
| BUG-DRAFT-003 | Teaching loop "save as rule" prompt not shown | **Likely Fixed** — verify in TC-9.5 | qa-report-draft-reply-2026-04-01.md |
| BUG-DRAFT-004 | save-as-rule endpoint returns 500 despite success | **Likely Fixed** — verify in TC-9.6 | qa-report-draft-reply-2026-04-01.md |
| FINDING-001 | LLM doesn't reliably tag [KB-N] citations in **diagnosis** path | **Open (diagnosis)** — unknown for follow-up reply path | qa-report-knowledge-citation-2026-04-01.md |

> **FINDING-001 scope:** This was observed in the diagnosis pipeline. TC-8 tests the
> **follow-up reply** pipeline (`draft_reply.py`), which has a different prompt. If TC-8
> consistently returns empty `cited_knowledge_ids`, FINDING-001 affects both paths.
> Do not assume the follow-up path is unaffected until TC-8 passes.

If TC-8 or TC-9 still fail for the same reasons, reference the bugs above rather than filing duplicates.

---

## Report Template

When running this checklist, create a new report at:
`.gstack/qa-reports/qa-report-knowledge-management-YYYY-MM-DD.md`

Use this header:
```markdown
# QA Report — Knowledge Management E2E
**Date:** YYYY-MM-DD
**Checklist:** `docs/qa/knowledge-management-e2e.md`
**Backend:** http://127.0.0.1:8000 | **Frontend:** http://127.0.0.1:5173
**Doctor:** test_doctor
**Duration:** ~XX min
**Test data:** [describe any seeding done]

## Summary

| TC | Scenario | Result | Notes |
|----|----------|--------|-------|
| 1  | Text ingestion | | |
| 2  | URL ingestion | | |
| 3  | Photo ingestion | | |
| 4  | PDF ingestion | | |
| 5a | Knowledge list + detail | | |
| 5b | Text search | | |
| 5c | NL patient search | | |
| 6  | Delete safety | | |
| 7  | AI Persona knowledge | | |
| 8  | KB → reply citation | | |
| 9  | Teaching loop | | |
| 10 | Reference count | | |
| REG-001 | No raw [KB-N] | | |
| REG-002 | Date display | | |
| REG-003 | Button order | | |
| REG-004 | NL search gender | | |

**Overall: X PASS, Y FAIL, Z PARTIAL**
**Health score: XX/100**
```

---

## History

| Date | Result | Notes |
|------|--------|-------|
| (first run) | — | — |
