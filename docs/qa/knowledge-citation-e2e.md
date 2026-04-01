# Knowledge → Citation E2E Regression Checklist

Tests the full "AI thinks like me" loop: doctor adds a knowledge rule → AI cites
it during diagnosis → citation resolves to the rule title in the review UI.

**Tool**: gstack `/qa` (headless Chromium via `$B`) or manual browser at http://127.0.0.1:5173/doctor
**Test account**: `doctor_id=test_doctor`
**Backend**: must be running on port 8000; port 8001 for isolated runs
**Time to complete**: ~25 min manual, ~12 min automated

---

## Setup

```bash
./dev.sh
# Confirm backend is running:
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" | python3 -m json.tool | head -10
```

Navigate to: `http://127.0.0.1:5173/doctor?doctor_id=test_doctor`

---

## TC-1 · Add Knowledge via Text

Starting point: 我的AI tab → 我的知识库 button.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 1.1 | Open 我的知识库 | Knowledge subpage opens, existing items listed |
| 1.2 | Tap + / add button | AddKnowledgeSubpage opens with text input |
| 1.3 | Enter: `胸痛患者首诊必须完善心电图，排除急性冠脉综合征` → save | `POST /api/manage/knowledge → 200`, item appears in list |
| 1.4 | Note the returned item `id` | Item ID will be referenced as `KB-{id}` in LLM output |
| 1.5 | Add second rule: `既往高血压患者出现胸痛，优先排查主动脉夹层` → save | Second item in list |

**Verify via API:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; [print(i['id'], i['content'][:60]) for i in items[-2:]]"
```
Expected: both items visible with correct IDs.

---

## TC-2 · Knowledge Shows in List + Detail

| # | Action | Pass Criteria |
|---|--------|--------------|
| 2.1 | View knowledge list | Both new items show title (auto-generated) + summary |
| 2.2 | Click first item | KnowledgeDetailSubpage opens with full text, source = "doctor" |
| 2.3 | Check reference count | Shows `0次引用` (not yet cited in any diagnosis) |

---

## TC-3 · Trigger Diagnosis — Expect Citations

Run the canonical Li Ming case (same inputs as `core-e2e-regression.md` TC-2 → TC-3).

| # | Action | Pass Criteria |
|---|--------|--------------|
| 3.1 | 新建病历 | Navigates to `/doctor/patients/new` |
| 3.2 | Send: `患者李明，男，45岁，胸痛2天，伴有呼吸困难` | Status bar: `李明 · 必填 1/2` |
| 3.3 | Send: `既往高血压病史5年，无药物过敏` | Status bar: `必填 2/2 ✓`; 完成 enabled |
| 3.4 | Click 完成 → 保存并诊断 | `POST /api/records/interview/confirm → 200`; `POST /api/doctor/records/{id}/diagnose → 202` |
| 3.5 | Wait for suggestions (< 30s) | Review page `/doctor/review/{id}` loads with 5+ suggestions |

**Verify citations present in raw suggestion data:**
```bash
RECORD_ID=<id from step 3.4>
curl -s "http://127.0.0.1:8000/api/doctor/records/$RECORD_ID/suggestions?doctor_id=test_doctor" \
  | python3 -c "import sys,json; data=json.load(sys.stdin); [print(s['id'], s.get('cited_knowledge_ids'), s['content'][:40]) for s in data.get('suggestions', [])]"
```
Expected: at least 1 suggestion has non-empty `cited_knowledge_ids` list.

---

## TC-4 · Citation Renders in Review UI

| # | Action | Pass Criteria |
|---|--------|--------------|
| 4.1 | Look for a citation badge/chip on any suggestion row | At least 1 suggestion shows a knowledge citation indicator |
| 4.2 | Click a suggestion row to expand | Detail text shown **without** raw `[KB-N]` markers — stripped server-side |
| 4.3 | Click/hover the citation indicator | `CitationPopover` opens with rule title (e.g. "胸痛患者首诊必须完善心电图…") and summary |
| 4.4 | Popover "查看全文" link | Opens KnowledgeDetailSubpage with the full rule text |

**Anti-regression:** raw `[KB-123]` text must never appear in the suggestion detail. If it does,
`extract_citations` in `diagnosis_handlers.py:_suggestion_to_dict` failed to strip it.

---

## TC-5 · Reference Count Increments

After a diagnosis that cited a KB item, the usage count should go up.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 5.1 | Return to 我的知识库 | Knowledge list visible |
| 5.2 | Find the cited rule | Reference count shows `1次引用` (or higher if cited multiple times) |
| 5.3 | Click item → detail | Usage section shows the record or "最近被引用" entry |

**Verify via API:**
```bash
KB_ID=<id of cited item>
curl -s "http://127.0.0.1:8000/api/manage/knowledge/$KB_ID/usage?doctor_id=test_doctor" | python3 -m json.tool
```
Expected: `reference_count >= 1`.

---

## TC-6 · Hallucinated Citation Not Shown

Verify the system silently drops citations for KB IDs that don't exist in the doctor's
knowledge base (e.g. LLM hallucinating `[KB-99999]`).

| # | Action | Pass Criteria |
|---|--------|--------------|
| 6.1 | Inject a fake citation into a suggestion detail (dev/test only — edit DB directly or use a mock suggestion) | No popover appears for the fake KB ID |
| 6.2 | Check backend logs after diagnosis | Warning: `Hallucinated KB citations ids=[99999]` appears in server log, but suggestion still displayed normally |
| 6.3 | `cited_knowledge_ids` in API response | Hallucinated ID **not** present — `validate_citations` filters it |

> This test requires direct DB access or a debug fixture. Skip for manual UI runs;
> verify via unit test in `tests/test_citation_parser.py` instead.

---

## TC-7 · Delete KB Item — No Stale Citations

| # | Action | Pass Criteria |
|---|--------|--------------|
| 7.1 | Add a new knowledge item: `测试删除规则` | Item saved with known ID |
| 7.2 | Run a new diagnosis (or reuse a record) that cites this item | Suggestion shows citation popover |
| 7.3 | Delete the KB item | `DELETE /api/manage/knowledge/{id} → 200` |
| 7.4 | Reload the review page for the suggestion | Suggestion still shown; citation indicator either hidden or shows "已删除" — no 404 crash |

**Anti-regression:** The review page must not crash if a cited KB item no longer exists.
The `/api/manage/knowledge/batch` endpoint used for citation resolution should handle
missing IDs gracefully (return empty for those IDs, not 404).

---

## TC-8 · URL Import → Citation Chain

| # | Action | Pass Criteria |
|---|--------|--------------|
| 8.1 | In knowledge subpage, paste a URL → extract | `POST /api/manage/knowledge/fetch-url → 200`; extracted text shown |
| 8.2 | Save as knowledge item | Item saved with `source = "url"`, `source_url` stored |
| 8.3 | Run a diagnosis — new item appears in LLM context | Suggestion may cite URL-sourced item with `[KB-N]` |
| 8.4 | Citation popover shows source | "来源：URL" or domain name shown in popover footer |

---

## TC-9 · File Upload → Citation Chain

| # | Action | Pass Criteria |
|---|--------|--------------|
| 9.1 | Upload a PDF or image containing a medical rule | `POST /api/manage/knowledge/upload/extract → 200`; text extracted |
| 9.2 | Review extracted text → save | Item saved with `source = "file"` |
| 9.3 | Run a diagnosis | Uploaded-content item eligible for citation |
| 9.4 | Citation popover shows source | Shows file name or "文件来源" in popover footer |

---

## Regression Checks

### CITE-001 · Raw [KB-N] Never Visible in UI

| Check | Pass Criteria |
|-------|--------------|
| Any suggestion detail text | No literal `[KB-` substring visible in rendered text |
| Browser devtools network | `GET /suggestions` response has clean `detail` (markers stripped) |

`diagnosis_handlers.py:_suggestion_to_dict` strips markers via `_CITATION_RE.sub("", raw_detail)`.

### CITE-002 · Citation Popover — No Blank Title

| Check | Pass Criteria |
|-------|--------------|
| Hover citation badge | Popover title is a real rule string, not empty or `KB-{id}` literal |
| KB item with no title | Falls back to first 40 chars of content (server-side fallback) |

### CITE-003 · Review Queue — rule_cited Shows Correct Title

| Check | Pass Criteria |
|-------|--------------|
| 审核 tab → 待审核 list item with citation | Shows rule name, not raw `[KB-N]` or blank |
| Hover rule chip | (Optional) same CitationPopover appears |

---

## Pass/Fail Summary

| Area | Must pass to ship |
|------|------------------|
| TC-1–2 Knowledge CRUD | Add text items; list + detail render correctly |
| TC-3 Diagnosis triggers | 202 accepted; suggestions with cited_knowledge_ids load |
| TC-4 Citation UI | No raw [KB-N] in detail; CitationPopover opens with correct title |
| TC-5 Reference count | Count increments after diagnosis citing the item |
| TC-7 Delete safety | No crash when cited item deleted |
| CITE-001/002/003 | No raw markers, no blank titles, queue shows correct names |

TC-6 (hallucination) and TC-8/9 (upload sources) are best-effort — skip if no file fixtures.

---

## Running with gstack `/qa`

```
/qa
```

In the `/qa` prompt, describe the flow:
> Test the knowledge → citation E2E chain: (1) add two knowledge rules about chest pain / hypertension, (2) run the Li Ming 胸痛 diagnosis case, (3) verify at least one suggestion on the review page has a citation badge and CitationPopover shows the correct rule title — NOT raw [KB-N] text. (4) Check that the cited rule's reference count incremented in the knowledge list. Report pass/fail per TC above.

Results land in `.gstack/qa-reports/` as a dated HTML file.

---

## History

| Date | Result | Notes |
|------|--------|-------|
| 2026-04-01 | 4/7 pass (TC-3, TC-5 FAIL) | FINDING-001: LLM uses KB content verbatim but doesn't add [KB-N] tags. Citation infrastructure correct; prompt instruction too weak. |
| 2026-04-01 (re-run) | 12/13 pass (TC-4.4 N/A) | FINDING-001 fixed: strengthened citation rules + Example 3 in diagnosis.md; KB block framing in prompt_composer.py. New bug found+fixed: batch endpoint missing `title` field (knowledge_handlers.py:332). Prompt cache gotcha: must hit /api/test/reset-caches after prompt edits. |
