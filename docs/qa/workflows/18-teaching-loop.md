# Workflow 18 — Teaching loop round-trip

Cross-workflow integration test for the core product proof: **"AI thinks
like me."** Verifies the full chain from doctor editing a draft, through
rule creation, to the AI citing that rule in its next output. Spans
workflows [04](04-persona-rules.md) (persona/knowledge),
[08](08-review-diagnosis.md) (review diagnosis), and
[09](09-draft-reply.md) (draft reply).

This is the single most important cross-workflow gate. If it fails, the
product's core value proposition is broken.

**Area:** `PatientDetail.jsx` (draft edit + teaching ConfirmDialog),
`/api/manage/drafts/{id}/edit` (teach_prompt detection),
`/api/manage/teaching/create-rule` (rule persistence),
`KnowledgeSubpage.jsx` (rule visible in KB list),
`/api/doctor/records/{id}/suggestions` (citation in next diagnosis)
**Spec:** `frontend/web/tests/e2e/18-teaching-loop.spec.ts`
**Estimated runtime:** ~15 min manual / ~90 s automated (requires real LLM)

---

## Scope

**In scope**

- Patient sends message → AI generates draft reply (workflow 09 setup).
- Doctor edits draft significantly → `teach_prompt=true` returned.
- Teaching ConfirmDialog appears with "保存为知识规则" title.
- Doctor taps "保存" → rule created via `/api/manage/teaching/create-rule`.
- New knowledge item visible in 我的知识库 with `source=teaching`.
- New patient interview with matching keywords → AI generates diagnosis.
- New diagnosis cites the teaching-sourced knowledge rule.
- Minor edit (< 10 changed chars AND > 80% similarity) does NOT trigger
  the teaching prompt.
- "跳过" dismisses the dialog without creating a rule.

**Out of scope**

- Knowledge CRUD (add/edit/delete via UI) — [05](05-knowledge.md).
- Persona rules CRUD (per-field rule manager) — [04](04-persona-rules.md).
- Draft reply send mechanics (confirmation sheet, attribution) —
  [09](09-draft-reply.md).
- Review diagnosis section layout — [08](08-review-diagnosis.md).
- Persona learning (15-edit threshold extraction) —
  `ai-thinks-like-me-qa-plan.md` §5.

---

## Pre-flight

Shared pre-flight lives in [`README.md`](README.md#shared-pre-flight).
This workflow additionally needs:

- **LLM-enabled backend:** `NO_PROXY=* no_proxy=*` on startup. Without
  this, draft generation and diagnosis both fail silently.
- The Playwright spec seeds its own data via `fixtures/seed.ts` helpers:
  `addKnowledgeText`, `completePatientInterview`, `sendPatientMessage`,
  `waitForDraft`, `waitForSuggestions`.
- No manual seed data required — everything is created per-test.

**Important:** This test makes real LLM calls. Expect ~60-90 s total
runtime. The spec uses `test.slow()` to triple the default timeout.

---

## Steps

### Phase 1 — Draft generation (workflow 09)

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Seed: add knowledge text "高血压患者建议优先使用ARB类降压药" | `POST /api/manage/knowledge` returns 200 with `id` |
| 1.2 | Seed: complete patient interview (hypertension symptoms) | Record created; `record_id` returned |
| 1.3 | Seed: patient sends follow-up message "血压控制不好，是否需要调整用药方案？" | Message created |
| 1.4 | Wait for AI draft | `waitForDraft` returns within 30 s; draft exists for this patient |

### Phase 2 — Significant edit triggers teaching prompt (workflow 09)

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Navigate to `/doctor/review?tab=pending_reply` | Patient name visible in the queue |
| 2.2 | Tap patient card → open chat view | URL contains `view=chat`; draft bubble visible with "AI起草回复 · 待你确认" header |
| 2.3 | Tap "修改" button | "正在编辑AI草稿" banner visible |
| 2.4 | Replace draft text with substantially different content: "根据你的情况，我建议调整为ARB类药物（如缬沙坦），每日一次，早晨空腹服用。同时建议每天早晚各测一次血压并记录。两周后复查。" | Text area contains the new text |
| 2.5 | Tap send button | Confirmation sheet "确认发送回复" appears |
| 2.6 | Confirm send | Reply sent; ConfirmDialog "保存为知识规则" appears with message "你的修改有价值！是否保存为知识规则，帮助 AI 更好地理解你的风格？" |
| 2.7 | Verify dialog buttons | "跳过" on LEFT, "保存" on RIGHT |

### Phase 3 — Save as rule (workflow 09 → 04/05)

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap "保存" in the teaching dialog | Button shows "保存中…" loading state; dialog closes |
| 3.2 | Navigate to `/doctor/myai` → 我的知识库 | Knowledge list loads |
| 3.3 | Find the new knowledge item | Item with content matching the edited reply text exists in the list |

### Phase 4 — Round-trip citation (workflow 08)

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Seed: register a second patient with same doctor | New patient created |
| 4.2 | Seed: complete interview for second patient with ARB-related symptoms: "最近头晕，血压偏高，想了解ARB类药物是否适合我" | New record created |
| 4.3 | Wait for AI diagnosis suggestions | `waitForSuggestions` returns within 30 s |
| 4.4 | Navigate to review page for new record | Review page loads with 鉴别诊断/检查建议/治疗方向 sections |
| 4.5 | Check suggestion text | At least one suggestion references ARB or the content from the teaching rule |
| 4.6 | No raw `[KB-N]` citations | Body text contains zero literal `[KB-N]` strings |

### Phase 5 — Edge case: minor edit does NOT trigger prompt

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Seed: send another patient message → wait for draft | New draft generated |
| 5.2 | Edit draft with minor change (1-2 characters, e.g. append "。") | `PUT /api/manage/drafts/{id}/edit` returns `teach_prompt=false` |
| 5.3 | No teaching dialog appears | ConfirmDialog with "保存为知识规则" is NOT visible |

### Phase 6 — Edge case: skip does NOT create rule

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Trigger a significant edit on a new draft (same as Phase 2 flow) | Teaching ConfirmDialog appears |
| 6.2 | Tap "跳过" | Dialog closes |
| 6.3 | Check knowledge list | No new item was created (count unchanged) |

---

## Edge cases

- **Edit too small to trigger teaching** — changing 1-2 characters with
  > 80% similarity returns `teach_prompt=false`. No dialog, no rule.
  (Verified in Phase 5.)
- **Duplicate rule text** — if the doctor saves the exact same edit
  twice, `save_knowledge_item` may return the existing item rather than
  creating a duplicate (API returns 200 with existing ID — see
  FINDING-QA01 in `ai-thinks-like-me-qa-plan.md`).
- **Doctor dismisses (skips) the prompt** — tapping "跳过" closes the
  dialog without calling `createRuleFromEdit`. No knowledge item created.
  (Verified in Phase 6.)
- **Doctor edits then discards without sending** — no teaching prompt
  appears because `should_prompt_teaching` is only evaluated on the
  `PUT /edit` call, and the ConfirmDialog only triggers after the edit
  API returns `teach_prompt=true`.
- **LLM timeout during draft generation** — `waitForDraft` times out
  after 30 s. The spec fails with a clear timeout message. No false
  positive.
- **LLM timeout during diagnosis** — `waitForSuggestions` times out.
  Same behavior.

---

## Known issues

See `docs/qa/ai-thinks-like-me-qa-plan.md` §Known Issues. Bugs
specifically affecting this workflow:

- FINDING-001 — Citation tagging unreliable; the teaching rule may not
  always be cited even when symptoms match. Phase 4.5 uses a soft
  content check rather than requiring an exact citation chip.
- BUG-DRAFT-003 — Teaching loop ConfirmDialog may not appear. Believed
  fixed as of 2026-04-09 QA run.

---

## Failure modes & debug tips

- **Draft never appears (Phase 1.4 timeout)** — check `NO_PROXY=*` is
  set. Check backend logs for LLM errors. The draft pipeline is async
  and fires on `sendPatientMessage`.
- **Teaching dialog never appears (Phase 2.6)** — verify the edit is
  large enough: `should_prompt_teaching` requires either >= 10 changed
  chars or <= 80% similarity. Check the `PUT /edit` response for
  `teach_prompt` and `edit_id`.
- **Rule not created (Phase 3.1)** — check `POST /api/manage/teaching/create-rule`
  response. 404 means the `edit_id` was not found or doctor mismatch.
- **Diagnosis doesn't cite the rule (Phase 4.5)** — knowledge retrieval
  uses token-overlap scoring (top 5). If the interview text doesn't
  share enough keywords with the rule, it won't be retrieved. Ensure the
  seeded interview mentions "ARB" explicitly.
- **Suggestion text contains `[KB-N]` (Phase 4.6)** — server-side
  citation extraction failed. Check `extract_citations()` in
  `diagnosis_handlers.py`.
