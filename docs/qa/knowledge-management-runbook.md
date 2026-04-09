# QA Runbook — Knowledge Management E2E

Step-by-step execution guide for `docs/qa/knowledge-management-e2e.md`.
Covers all ingestion methods, the KB→reply citation core loop, teaching loop,
and regression checks from the April 2026 bug-fix batch.

**Test account**: `doctor_id=test_doctor`
**Time**: ~45 min manual | ~20 min with `/qa`
**Reference**: `docs/qa/knowledge-management-e2e.md` (checklist + pass criteria)

---

## Pre-flight

| # | Step | Verify |
|---|------|--------|
| P.1 | `NO_PROXY=* no_proxy=* .venv/bin/uvicorn main:app --port 8000` | Backend running on 8000 |
| P.2 | `cd frontend/web && npm run dev` | Vite dev server on 5173 |
| P.3 | `curl -s http://127.0.0.1:8000/health` | `{"status":"ok"}` |
| P.4 | `curl -s -X POST "http://127.0.0.1:8000/api/manage/onboarding/seed-demo?doctor_id=test_doctor"` | `{"status":"ok"}` — seeds patients + inbound messages |
| P.5 | Open `http://127.0.0.1:5173/doctor?doctor_id=test_doctor` in Chrome | 我的AI tab loads, no console errors |
| P.6 | Open DevTools → Console tab, clear existing logs | Console open and empty |

> **If backend fails to start:** check port 8000 is free — `lsof -i :8000`
> **If seed-demo fails:** doctor may not exist — run onboarding first

---

## TC-1 · Text Knowledge Ingestion

**Start**: 我的AI tab

| # | Step | Verify |
|---|------|--------|
| 1.1 | Tap **我的知识库** button in 我的AI tab | KnowledgeSubpage opens; existing items listed or empty state shown |
| 1.2 | Tap **+** (add) button | AddKnowledgeSubpage opens with text input field |
| 1.3 | Type: `术后患者出现发热超过38.5℃，首先排查切口感染，不要等待自行退热` | Text entered in field |
| 1.4 | Tap **保存** | POST `/api/manage/knowledge → 200`; item appears in list; auto-generated title visible |
| 1.5 | Record the item ID from the URL or API (`KB_ID_1`) | ID noted |
| 1.6 | Tap **+** again | AddKnowledgeSubpage opens again |
| 1.7 | Type: `服用华法林的患者复查时必须同时检查INR，目标范围2.0–3.0` | Text entered |
| 1.8 | Tap **保存** | Second item appears; list shows 2 items |
| 1.9 | Record the second item ID (`KB_ID_2`) | ID noted |

**API verify:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; [print(i['id'], i['source'], i['content'][:60]) for i in items[-2:]]"
```
Expected: 2 items with `source = "doctor"`, content matches.

**Record timestamps** (needed for TC-8):
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; [print('LAST_KB_TIME:', i['created_at']) for i in items[-1:]]"
```
Save the `LAST_KB_TIME` value — you will use it in TC-8 to verify draft freshness.

**Edge cases:**
- 1.10: Tap **+** → tap **保存** with empty field → validation error shown, no item created
- 1.11: Enter a text item > 3000 characters → save rejected with error message

---

## TC-2 · URL Knowledge Ingestion

**Start**: 我的知识库 → **+** → URL tab

| # | Step | Verify |
|---|------|--------|
| 2.1 | Tap **+** → switch to **链接/URL** tab | URL input field shown |
| 2.2 | Paste a real URL (e.g. a clinical guideline: `https://www.uptodate.com/...` or any HTTPS medical article) | URL entered in field |
| 2.3 | Tap **提取** or equivalent extract button | "提取中…" loading state shown |
| 2.4 | Wait up to 15s | Extracted text preview appears in text area |
| 2.5 | Review the extracted text | Text is meaningful (not HTML tags or JS); POST `/api/manage/knowledge/fetch-url → 200` |
| 2.6 | Tap **保存** | Item saved; returns to knowledge list |
| 2.7 | Find the new item in the list | Source badge shows "网页" or domain name; title auto-generated |

**API verify:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; url_items=[i for i in items if i.get('source')=='url']; [print(i['id'], i.get('source_url','')[:60]) for i in url_items]"
```
Expected: `source = "url"`, `source_url` non-null.

**Edge cases:**
- 2.8: Enter an invalid URL (`not-a-url`) → error message shown, no crash, no item created
- 2.9: Enter an unreachable URL (`https://localhost:9999/test`) → timeout error shown within 15s
- 2.10: Enter a URL to a non-medical page (e.g. `https://news.ycombinator.com`) → extraction still completes; text shown without filtering

---

## TC-3 · Photo / Camera Knowledge Ingestion

**Start**: 我的知识库 → **+** → 照片/图片 tab

> **Note:** Uses the vision LLM path (httpx `trust_env=False` fix applied in BUG-04).
> If you get "Connection error" here, the proxy fix may not have taken effect — restart backend.

| # | Step | Verify |
|---|------|--------|
| 3.1 | Tap **+** → switch to **照片** or camera tab | Photo upload / camera option shown |
| 3.2 | Select a photo of a printed or handwritten clinical note (or any image with readable text) | Upload accepted; processing indicator shown |
| 3.3 | Wait up to 30s | Extracted text shown in preview area |
| 3.4 | Review extracted text — does it match the image content? | Text is reasonable; may be partial for handwriting |
| 3.5 | Tap **保存** | Item saved with `source = "photo"` or `source = "image"` |
| 3.6 | Check knowledge list | New item appears; source badge shows 图片/照片 |

**API verify:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; photo=[i for i in items if 'photo' in i.get('source','') or 'image' in i.get('source','')]; [print(i['id'], i['source']) for i in photo]"
```

**Edge cases:**
- 3.7: Upload a blurry photo → extraction returns partial text; no crash; user can still edit and save
- 3.8: Upload a PNG file via the photo tab → accepted and processed
- 3.9: Upload a `.exe` or `.zip` via the photo tab → validation error shown, rejected

---

## TC-4 · PDF Knowledge Ingestion

**Start**: 我的知识库 → **+** → 文档/PDF tab

| # | Step | Verify |
|---|------|--------|
| 4.1 | Tap **+** → switch to **文档** or file tab | File upload button shown |
| 4.2 | Upload a single-page PDF with clinical text (e.g. a discharge summary or guideline page) | Upload accepted; processing starts |
| 4.3 | Wait up to 60s | Extracted text shown in preview (uses LLM vision per page) |
| 4.4 | Review extracted text — does it match the PDF content? | Text is readable and complete |
| 4.5 | Tap **保存** | Item saved with `source = "file"` or `source = "pdf"` |
| 4.6 | Upload a 3–5 page PDF | All pages extracted and concatenated; saved as single item |

**Check which extraction path ran:**
```bash
grep "pdftoppm\|pdftotext" logs/app.log | tail -3
```
`pdftoppm` = vision LLM path (better for scanned docs). `pdftotext` = text extraction fallback.

**Edge cases:**
- 4.7: Upload a scanned PDF (image-only, no text layer) → `pdftoppm` path triggers; LLM extracts from images
- 4.8: Upload a PDF with >10 pages → only first 10 extracted (PDF_LLM_MAX_PAGES default); no crash
- 4.9: Upload a password-protected PDF → error shown, no crash

---

## TC-5a · Knowledge List

**Start**: 我的知识库

| # | Step | Verify |
|---|------|--------|
| 5.1 | Scroll through the knowledge list | Items sorted by activity (most recently cited or edited first) |
| 5.2 | Check each row | Title shown (auto-generated, not blank); summary visible; source badge present |
| 5.3 | Check dates on all items | Shows `今天` / `昨天` / `N天前` — **not** `-1天前` or a future date (BUG-01 fix) |
| 5.4 | Check reference counts | Shows `N次引用` per item (0 is OK for new items) |
| 5.5 | Run devtools check | `document.body.innerText.includes('[KB-')` → **false** |

---

## TC-5b · Knowledge Detail and Inline Edit

| # | Step | Verify |
|---|------|--------|
| 5.6 | Tap any knowledge item | Detail subpage opens with full text; source label shown |
| 5.7 | Check all fields | Full content, source, created date, reference count — all populated |
| 5.8 | Tap edit button | Content becomes editable inline |
| 5.9 | Change one word in the text → tap **保存** | Edit persists; `updated_at` refreshed; returns to detail view |
| 5.10 | Verify edit persisted | `curl -s "http://127.0.0.1:8000/api/manage/knowledge/{id}?doctor_id=test_doctor"` — edited text in response |

---

## TC-5c · Text Search

> **Requires TC-1:** "华法林" was added in TC-1 step 1.7.

| # | Step | Verify |
|---|------|--------|
| 5.11 | Type `华法林` in the knowledge search bar | List filters to show only matching items |
| 5.12 | Confirm the INR rule from TC-1 appears | Correct item shown |
| 5.13 | Clear the search field | Full list restored |
| 5.14 | Type `发热` | Returns the post-op fever rule from TC-1 |
| 5.15 | Type a string with no matches (e.g. `xyznotarealterm`) | Empty state shown; no crash |

---

## TC-5d · NL Patient Search (BUG-06 regression)

**Start**: 患者 tab → search bar

| # | Step | Verify |
|---|------|--------|
| 5.16 | Type `最近来诊的男性` | Returns male patients with recent records — **not** empty list |
| 5.17 | Check returned patient genders | All are `male` or `男` — not `female` or `女` |
| 5.18 | Type `姓张的女性` | Returns female patients with surname 张 |
| 5.19 | Type `60多岁高血压患者` | Returns patients aged 60–69 with hypertension-related records |

**API verify (5.16):**
```bash
curl -s "http://127.0.0.1:8000/api/manage/patients/search?doctor_id=test_doctor&q=最近来诊的男性" \
  | python3 -c "import sys,json; data=json.load(sys.stdin); print([(p['name'], p.get('gender')) for p in data.get('patients',[])])"
```
Expected: non-empty list; all genders are `male` or `男`. An empty list means BUG-06 is NOT fixed.

---

## TC-6 · Knowledge Delete

| # | Step | Verify |
|---|------|--------|
| 6.1 | Tap **+** → add a throwaway item: `测试删除规则，请忽略` → save | Item saved; appears in list |
| 6.2 | Tap the throwaway item → open detail | Detail subpage shown |
| 6.3 | Tap **删除** button | Confirmation dialog appears: **取消 LEFT** (grey), **删除 RIGHT** (red) |
| 6.4 | Verify button order before confirming | Cancel is on the left; this is the design rule (BUG-05 area) |
| 6.5 | Tap **删除** (right/red) to confirm | `DELETE /api/manage/knowledge/{id} → 200` |
| 6.6 | Return to knowledge list | Item is gone; count decremented |
| 6.7 | Reload the page | Item still absent; no 404 errors in console |

**API verify:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; print([i['content'][:30] for i in items])"
```
Expected: `测试删除规则` not present.

**Citation safety check (if item was previously cited):**
```bash
# If deleted item had known citations, reload the review page that cited it
# Page must not crash; citation either hidden or shows "已删除"
```

---

## TC-7 · AI Persona

**Start**: 我的AI tab

| # | Step | Verify |
|---|------|--------|
| 7.1 | Scroll to the AI Persona card in 我的AI tab | Persona card visible (may be placeholder if not yet set) |
| 7.2 | Tap the persona card | Persona detail subpage opens |
| 7.3 | Read the persona content | Shows communication style fields; no raw `[KB-N]` visible |
| 7.4 | Return to 我的知识库 | Persona item is **pinned first** at the top of the list (regression check) |

---

## TC-8 · KB → Follow-up Reply Citation (Core Loop)

> **CRITICAL:** Do NOT use seeded drafts for this test. The `seed-demo` preseeds
> `cited_knowledge_ids` directly via `preseed_service.py` — those drafts bypass the LLM
> entirely and will make TC-8 appear to pass without the core loop ever running.
> You must create a fresh inbound message AFTER TC-1's rules are saved.

### TC-8 Setup — Create a fresh inbound message

| # | Step | Verify |
|---|------|--------|
| 8.S1 | Get a patient token from the seeded patients | `curl -s "http://127.0.0.1:8000/api/manage/patients?doctor_id=test_doctor" \| python3 -c "import sys,json; data=json.load(sys.stdin); [print(p['id'], p['name']) for p in data.get('patients',[])[:3]]"` — note a patient ID |
| 8.S2 | Get that patient's portal access token | Use the patient portal login or retrieve from DB |
| 8.S3 | Send a fresh inbound message related to TC-1 KB rules | `curl -s -X POST "http://127.0.0.1:8000/api/patient/messages" -H "Content-Type: application/json" -d '{"patient_token":"<token>","content":"我术后今天烧到38.6度，需要怎么处理"}'` |
| 8.S4 | Wait 10–15s for background draft generation | `sleep 12` |
| 8.S5 | Check that a new draft exists after LAST_KB_TIME | `curl -s "http://127.0.0.1:8000/api/manage/drafts?doctor_id=test_doctor" \| python3 -c "import sys,json; data=json.load(sys.stdin); [print(d.get('id'), d.get('created_at')) for d in data.get('drafts',[])]"` |
| 8.S6 | Confirm draft `created_at > LAST_KB_TIME` | If not, dismiss old drafts and re-trigger. If still no fresh draft, check backend logs for errors. |

### TC-8 Test Steps

**Start**: 审核 tab → 待回复 subtab

| # | Step | Verify |
|---|------|--------|
| 8.1 | Open 审核 tab → tap **待回复** | Patient messages shown — at least 1 with the fresh message from TC-8 setup |
| 8.2 | Tap the fresh draft (the one created AFTER LAST_KB_TIME) | Draft reply detail opens |
| 8.3 | Look for `引用:` badges on the draft bubble | At least 1 `引用: <rule title>` badge visible on the draft |
| 8.4 | Expand / scroll draft detail text | No raw `[KB-N]` text visible anywhere |
| 8.5 | Tap a `引用:` badge | Navigates **directly** to knowledge detail subpage (no popover — follow-up path is not the diagnosis UI) |
| 8.6 | Knowledge detail shows the correct rule | Rule title and text match what was added in TC-1 |
| 8.7 | Press back | Returns to draft reply detail |

**API verify — citations present:**
```bash
DRAFT_ID=<id from fresh draft>
curl -s "http://127.0.0.1:8000/api/manage/drafts/$DRAFT_ID?doctor_id=test_doctor" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('cited_ids:', d.get('cited_knowledge_ids'), '\ntext[:100]:', d.get('draft_text','')[:100])"
```
Expected: `cited_knowledge_ids` is a **non-empty list containing KB_ID_1 or KB_ID_2** from TC-1.

**Verify live LLM call ran (not seeded):**
```bash
python3 -c "
import json
with open('logs/llm_calls.jsonl') as f:
    calls = [json.loads(l) for l in f if 'draft_reply' in l or 'followup' in l.lower()]
print(f'draft_reply LLM calls found: {len(calls)}')
if calls:
    last = calls[-1]
    print('Latest:', last.get('timestamp'), '| status:', last.get('status'), '| model:', last.get('model'))
"
```
If 0 calls found → you used seeded data; the core loop was never tested.

**If `cited_knowledge_ids` is empty despite a live LLM call:**
FINDING-001 (LLM not tagging citations) also affects the follow-up reply path.
Log as `FINDING-002` referencing `draft_reply.py` prompt. Do not fail silently.

**Edge cases:**
- 8.8: Reload draft list after sending — draft moves to completed/sent section
- 8.9: Open the draft detail → check send confirmation dialog appears before sending (BUG-DRAFT-002 was open; should now be fixed)

---

## TC-9 · Teaching Loop

> **Blocked by TC-8:** Only run if TC-8 produced a fresh draft with non-empty `cited_knowledge_ids`.

**Start**: Same draft from TC-8

| # | Step | Verify |
|---|------|--------|
| 9.1 | Open the fresh draft from TC-8 | Draft detail shown |
| 9.2 | Tap **修改** (edit) | Edit textarea appears with current draft text |
| 9.3 | **Small edit test first (9.8):** Fix a single character (e.g. change one punctuation mark) → save | No "保存为规则？" dialog should appear for tiny edits |
| 9.4 | Re-open the draft → tap **修改** again | Edit textarea appears |
| 9.5 | Make a **significant** rewrite: add a specific medication dosage, rewrite >30% of the text (e.g. add "建议使用头孢氨苄500mg，每日3次，连续5天") | Text is substantially different |
| 9.6 | Tap save/send | `PUT /api/manage/drafts/{id}/edit → 200`; response includes `teach_prompt: true` |
| 9.7 | **"保存为规则？"** dialog or bottom sheet appears | Shows the edited text snippet; two buttons visible |
| 9.8 | Tap **保存为规则** | `POST /api/manage/drafts/{id}/save-as-rule → 200`; new rule created |
| 9.9 | Open 我的知识库 | New item appears with `source = "teaching"` or "来自编辑" label |

**API verify:**
```bash
curl -s "http://127.0.0.1:8000/api/manage/knowledge?doctor_id=test_doctor" \
  | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; teaching=[i for i in items if i.get('source')=='teaching']; [print(i['id'], i['source'], i['content'][:60]) for i in teaching]"
```
Expected: at least 1 item with `source = "teaching"`.

**If step 9.7 fails (no dialog):** BUG-DRAFT-003 is NOT fixed. Log as FAIL with evidence.
**If step 9.8 fails (500 error):** BUG-DRAFT-004 is NOT fixed. Check whether rule was still created despite the error.

---

## TC-10 · Reference Count

> **Blocked by TC-8 (fresh draft):** If TC-8 used seeded data, reference counts never incremented and this test will always show 0.

**Start**: 我的知识库

| # | Step | Verify |
|---|------|--------|
| 10.1 | Find the KB rule(s) cited in TC-8 (KB_ID_1 or KB_ID_2) | Item visible in list |
| 10.2 | Check the reference count on that item | Shows `≥ 1次引用` |
| 10.3 | Tap the item → detail subpage | Usage section shows a recent citation entry with patient name or date |
| 10.4 | If a second patient message is available: run TC-8 setup again with a different patient → wait for draft | New draft generated |
| 10.5 | Check reference count again | Count has incremented (N → N+1) |

**API verify:**
```bash
KB_ID=<KB_ID_1 or KB_ID_2 from TC-1>
curl -s "http://127.0.0.1:8000/api/manage/knowledge/$KB_ID/usage?doctor_id=test_doctor" | python3 -m json.tool
```
Expected: `reference_count >= 1`, `recent_uses` array non-empty.

---

## Regression Checks

### REG-001 · No Raw [KB-N] in UI

| # | Step | Verify |
|---|------|--------|
| R1.1 | Open knowledge list | No `[KB-` text visible in any row |
| R1.2 | Open draft reply detail (from TC-8) | No `[KB-` text visible in draft bubble |
| R1.3 | Open any suggestion in 审核 → expand detail | No `[KB-` text visible |
| R1.4 | Run devtools check on each page | `document.body.innerText.includes('[KB-')` → **false** |

---

### REG-002 · Date Display (BUG-01)

| # | Step | Verify |
|---|------|--------|
| R2.1 | Look at knowledge cards created today (TC-1 items) | Shows `今天` — not `昨天` or `-1天前` |
| R2.2 | Find an item created > 7 days ago (from seed data) | Shows `N月N日` format — not a negative number |
| R2.3 | Check the time right after midnight — items created late at night should still show 今天 | Dates display correctly across the UTC→CST boundary |

---

### REG-003 · Dialog Button Order (BUG-05)

| # | Step | Verify |
|---|------|--------|
| R3.1 | Trigger knowledge delete dialog (TC-6.3) | **取消 LEFT** (grey), **删除 RIGHT** (red) |
| R3.2 | Open a suggestion in 审核 → expand → tap edit | Edit form shown |
| R3.3 | Tap cancel or save | **取消 LEFT** (grey), **保存 RIGHT** (green) — BUG-05 fix |

---

### REG-004 · NL Search Gender (BUG-06)

Already covered in TC-5d. Quick re-check via API:

```bash
curl -s "http://127.0.0.1:8000/api/manage/patients/search?doctor_id=test_doctor&q=男性" \
  | python3 -c "import sys,json; data=json.load(sys.stdin); genders=[p.get('gender') for p in data.get('patients',[])]; print('count:', len(genders), '| genders:', genders)"
```
Expected: non-empty list; all values are `male` or `男`.

---

## Report

Create a report at `.gstack/qa-reports/qa-report-knowledge-management-YYYY-MM-DD.md`.

```markdown
# QA Report — Knowledge Management E2E
**Date:** YYYY-MM-DD
**Checklist:** docs/qa/knowledge-management-e2e.md
**Runbook:** docs/qa/knowledge-management-runbook.md
**Backend:** http://127.0.0.1:8000 | **Frontend:** http://127.0.0.1:5173
**Doctor:** test_doctor
**Duration:** ~XX min
**Test data:** [seed-demo seeded, fresh inbound message created at HH:MM, LAST_KB_TIME=...]

## Summary

| TC | Scenario | Result | Notes |
|----|----------|--------|-------|
| 1  | Text ingestion (2 rules) | | |
| 2  | URL ingestion | | |
| 3  | Photo ingestion | | |
| 4  | PDF ingestion | | |
| 5a | Knowledge list + dates | | |
| 5b | Detail + inline edit | | |
| 5c | Text search | | |
| 5d | NL patient search | | |
| 6  | Delete + dialog order | | |
| 7  | AI Persona pinned | | |
| 8  | KB → reply citation (fresh draft) | | |
| 9  | Teaching loop | | |
| 10 | Reference count | | |
| REG-001 | No raw [KB-N] | | |
| REG-002 | Date display | | |
| REG-003 | Button order | | |
| REG-004 | NL search gender | | |

**Overall: X PASS, Y FAIL, Z PARTIAL**
**Health score: XX/100**

## TC-8 Isolation Verification
- LAST_KB_TIME: [timestamp from TC-1]
- Fresh draft created_at: [timestamp]
- Draft is fresh (created_at > LAST_KB_TIME): YES / NO
- LLM call confirmed in llm_calls.jsonl: YES / NO
- cited_knowledge_ids: [list]

## Bugs Found
[new bugs found this run]

## Known Bug Status (from prior QA)
- BUG-DRAFT-002 (confirm dialog): CONFIRMED FIXED / STILL OPEN
- BUG-DRAFT-003 (teach prompt): CONFIRMED FIXED / STILL OPEN
- BUG-DRAFT-004 (save-as-rule 500): CONFIRMED FIXED / STILL OPEN
- FINDING-001 scope: follow-up path AFFECTED / UNAFFECTED
```

---

## Priority Order

Run in this order — earlier tests are prerequisites for later ones:

1. **TC-1** (text ingestion) — all later tests need KB rules to exist
2. **TC-5a/5b/5c** (list/detail/search) — quick, validates TC-1's output; 5c depends on TC-1
3. **TC-5d** (NL search) — independent regression check
4. **TC-2** (URL ingestion) — independent of TC-8
5. **TC-3** (photo) — independent; first test of httpx BUG-04 fix on vision path
6. **TC-4** (PDF) — independent; same vision path
7. **TC-6** (delete) — clean up; independent
8. **TC-7** (AI persona) — independent; quick check
9. **TC-8** (KB → reply citation) — **most important**; requires TC-1 and fresh patient message
10. **TC-9** (teaching loop) — blocked by TC-8; only run if TC-8 passes
11. **TC-10** (reference count) — blocked by TC-8 fresh draft
12. **REG-001–004** — run last, after all TCs

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| TC-8: `cited_knowledge_ids = []` on fresh draft | LLM didn't tag [KB-N] | Check `logs/llm_calls.jsonl` for the draft_reply call; log as FINDING-001/002 |
| TC-8: No fresh draft found after 12s | Background batch hasn't run | Wait 5 more seconds; check `logs/app.log` for batch errors |
| TC-8: Draft `created_at` is before LAST_KB_TIME | Picked a seeded draft by mistake | Dismiss old drafts; re-run TC-8 setup; filter by timestamp |
| TC-3/4: "Connection error" on vision extraction | Proxy still active on LLM client | Restart backend with `NO_PROXY=*`; verify BUG-04 fix in `src/infra/llm/vision.py` |
| TC-9: No "保存为规则？" dialog | BUG-DRAFT-003 not fixed | Check `PatientDetail.jsx` — `teach_prompt` return value handling |
| TC-9: save-as-rule returns 500 | BUG-DRAFT-004 not fixed | Check if rule was still created in DB despite 500; report both |
| REG-004: NL search returns empty | BUG-06 not fixed | Check `db/crud/patient.py:search_patients_nl` gender filter; verify `_gender_variants` dict |
