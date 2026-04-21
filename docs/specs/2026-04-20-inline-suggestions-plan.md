# Inline AI Suggestions — Per-Field Plan

> Date: 2026-04-20
> Status: Draft v3 (Codex + eng-reviewed)
> Supersedes the UI portion of: `docs/specs/2026-03-25-diagnosis-ui-design.md`
> Depends on: existing `AISuggestion` model, `ReviewPage.jsx`, `RecordSummaryCard`
> Visual mockup: `docs/specs/2026-04-20-mockups/inline-suggestions-review.html`

## Problem

Current `ReviewPage` renders AI suggestions as a flat list of 9–15 cards (3–5 per
section across `differential` / `workup` / `treatment`), divorced from the record
structure. A past redesign explicitly flattened categorization to reduce clutter
(`ReviewPage.jsx:243` comment: "No category tags, no urgency chip — all
categorization dropped by design"), but the fatigue problem returned at the
volume level: doctor sees 9–15 cards per record, each demanding
accept / reject / edit.

Product is narrowing to 待回复 + 待审核. Review surface needs to become a
**single decisive recommendation per decision axis**, inline with the record
fields the doctor is already reading.

## Target Experience

Doctor opens `/doctor/review/:recordId`. The record editor shows structured
fields. AI suggestion density is shaped by the nature of each decision axis:

- **诊断 (differential) — 1 suggestion, no cycle.** Single judgment. Accept
  or modify. No alternates shown.
- **治疗方向 (treatment) — 1 suggestion, no cycle.** Single coherent plan.
  Same reasoning.
- **检查建议 (workup) — 1 suggestion at a time with 换一条 cycle.** Backend
  emits 2–4. UI shows one pending candidate; 采纳 collapses it to a ✓ row
  and auto-promotes the next pending; 换一条 skips to the next without
  accepting; accepted suggestions stack as ✓ rows above the current
  pending row. Counter shows `N / total`.

Inline rows under each field:

```
诊断
  [textarea — doctor editable]
  ─ AI 建议：后循环缺血（PCI），伴发作性眩晕          [采纳] 修改

检查建议  (已采纳 1 条 · 还剩 3 条)
  ✓ 已采纳：心电图 + 肌钙蛋白 + BNP                  [展开]
  ─ AI 建议  2/4：急诊冠脉 CTA                       [采纳] 换一条 修改
```

- `采纳` — confirm; current row collapses to ✓, next pending appears
- `修改` — inline edit, then confirm
- `换一条` — workup only; advances to next candidate without accepting
- Last candidate: 换一条 becomes "已看完" (disabled)
- 诊断/治疗 never show 换一条 (no alternates exist in the intended data shape)

No separate suggestion cards. No flat list. Stacked ✓ rows above one
active pending row for workup.

## Design Decisions (revised 2026-04-20)

| Decision | Choice | Rationale |
|---|---|---|
| UI paradigm | Inline-per-field (not cards) | Codex: "separate suggestion cards are a UI artifact, not the doctor's task" |
| 诊断 density | Exactly 1 AI suggestion, no 换一条 | Single judgment; multiple candidates add noise |
| 治疗方向 density | Exactly 1 AI suggestion, no 换一条 | Single coherent plan; same reasoning |
| 检查建议 density | 1 pending at a time + 换一条 cycle; accepted stack as ✓ rows | Workup is a list — doctor builds it up over multiple 采纳 clicks. One-at-a-time keeps focus; 换一条 provides escape hatch. |
| 换一条 persistence | Session-only React state per field; resets on refresh | Not clinical data |
| Top-1 selection (诊断/治疗) | `is_custom` > `not rejected` > LLM output order | Custom (doctor-added) wins over AI-generated |
| Workup pending order | LLM output order, rejected auto-skipped, custom floats to bottom of queue | Model usually emits high-priority tests first |
| Empty section | Show field + "暂无 AI 建议 · 手动填写" | Hiding makes absence ambiguous |
| Custom suggestions | 诊断/治疗 custom replaces the 1 AI; 检查 custom appends to list | Matches the singular-vs-list split |
| Rejected audit | Preserve existing `decision=rejected` rows in DB | No schema change; "show rejected" button deferred |
| Backend in Phase 1 | Unchanged — still emits 3–5 per section | UI filters on render; simplest path |
| Backend in Phase 2 | `differential` → 1 · `treatment` → 1 · `workup` → 2–4 | Prompt trim via `/prompt-surgeon` + eval gate |

## Data Model Mapping

`SuggestionSection` enum has 3 values; record has 4 key fields. Mapping:

| Section | Record field | UI label |
|---|---|---|
| `differential` | `diagnosis` | 诊断 |
| `treatment` | `treatment_plan` | 治疗方案 |
| `workup` | *(UI block only, no DB field in Phase 1)* | 检查建议 |

**Decision (Codex revision)**: `workup` renders as a first-class inline block
with the same AI row, but does NOT add a new record schema field in Phase 1.
Reason: schema churn + migration risk + prompt/extractor touch points turn a
UI simplification into a data migration. If doctors later need persisted
structured workup text, add the field as a separate change.

Record fields `chief_complaint` and `present_illness` have no AI suggestion
section today; they stay as plain editable fields. This is fine — not every
field needs AI.

## Phased Delivery

### Phase 1a — Make record editable (first commit)

Per Beck's "make the change easy, then make the easy change." Ship this
standalone first, validate it doesn't regress the existing card-list flow,
then layer 1b.

**Scope:**
- Convert `RecordSummaryCard` from display-only to editable (textarea per
  field).
- Local React state for field values; persisted via existing
  `finalize_review` writeback (no new per-keystroke save endpoint).
- Cover: doctor edits `diagnosis` / `treatment_plan` directly without
  touching AI → finalize writes edited text.
- Card list continues to render below; no AI flow change.

### Phase 1b — Inline AI rows (second commit, behind flag)

**Scope:**
- Build `FieldWithAI.jsx` component (takes `field`, `label`,
  `sectionSuggestions`, `value`, `onChange`, `onDecide`).
- Replace flat `SuggestionCard` map with one `FieldWithAI` per
  differential / workup / treatment section.
- 换一条 cycle state — per-field React state, session-only.
- Per-section custom add buttons (+ 诊断 / + 检查 / + 治疗). No more
  `treatment` default.
- "✓ 已采纳 AI 建议" collapsed state; "医生已在基础上修改" if field text
  diverges from accepted suggestion.
- "完成审核 · N 条未处理" counter on bottom button.
- **Delete** dead `ChecklistSection` (`ReviewPage.jsx:516+`) and unused
  `SuggestionCard` paths.
- Feature flag `VITE_INLINE_SUGGESTIONS_V2` (build-time env var). Default
  `true` in staging. Falsey → restore existing flat list renderer.

### Phase 1c — Backend finalize-contract update (ships with 1b)

**Scope:**
- Add `implicit_reject=true` param to `POST /records/{id}/review/finalize`
  (`src/channels/web/doctor_dashboard/diagnosis_handlers.py:314`).
- When true, untouched (`decision IS NULL`) rows are marked `rejected` at
  writeback time instead of raising 422.
- v1 dashboard keeps default `implicit_reject=false` (preserves existing
  block-on-undecided contract).
- v2 inline UI always calls with `implicit_reject=true`.

### Backend writeback — workup destination

- Confirmed `workup` suggestions write to existing `orders_followup`
  record field (no schema change).
- Update `finalize_review` writeback: after the existing differential →
  `diagnosis` and treatment → `treatment_plan` blocks, add a workup →
  `orders_followup` block using the same `edited_text`/`content`/`detail`
  concat pattern.

**Out of scope:**
- Prompt-level trim (Phase 2)
- Any `workup_plan` schema field — `orders_followup` is the Phase 1 home
- Rejected-suggestions review UI
- v1 MUI dashboard changes — stays on card list via default
  `implicit_reject=false`

### Phase 2 — Backend prompt trim (separate plan)

- Use `/prompt-surgeon` to change diagnosis LLM to emit exactly 1 per section
- Requires eval coverage on `differential` / `workup` / `treatment` output
  quality (currently 0 scenarios — extraction has 60, diagnosis has none;
  per project memory `project_prompt_guard_before_optimize.md`)
- Blocked on building eval harness for diagnosis output shape

## Files to Change (Phase 1)

Frontend:
- `frontend/web/src/v2/pages/doctor/ReviewPage.jsx` — remove flat suggestion
  map (line 962), delete `SuggestionCard` render path, delete
  `ChecklistSection` (line 516+, already dead), rebuild `RecordSummaryCard`
  to be editable with inline AI rows.
- Possibly a new `InlineSuggestion.jsx` component if extraction clarifies the
  per-field row.

Backend:
- No changes in Phase 1.
- If we add `workup_plan` field: new Alembic migration + model update +
  extractor prompt update. Decide in eng-review.

## Edge Cases

- **Record has no AI suggestions at all** (pending / failed diagnosis) — keep
  existing trigger button ("请 AI 分析此病历") and failure state card. Inline
  rows only appear after suggestions exist.
- **Doctor edits field directly without accepting/rejecting AI** — the AI row
  stays visible as reference. On 完成审核, any unaccepted suggestions count as
  implicit reject? **Open question for eng-review.**
- **Doctor accepts AI then edits the field** — existing `decision=edited` path
  handles this. Inline version needs to match.
- **Section has 0 pending suggestions after cycle exhausts** — show "已查看全部
  AI 建议" inline; no 换一条 button.
- **Teach loop** — existing `setTeachEditId` flow after edit-and-confirm must
  still trigger. Carry over verbatim.

## Decisions Post-Codex (Previously "Open Questions")

1. ~~`workup` field mapping~~ → **Decided**: UI-only block in Phase 1, no
   schema field. Schema change is a separate future plan gated on actual
   need.
2. ~~Unaccepted at 完成审核~~ → **Decided**: **implicit reject** for any
   suggestion never accepted into the record. Implicit confirm would lie
   about the audit trail; block-finalize is too heavy. Bottom button shows
   "完成审核 · N 条未处理" so the count is visible.
3. ~~换一条 state coupling~~ → **Decided**: per-field, session-only React
   state. No cross-field coupling. Resets on refresh.
4. **Test coverage** → State-transition regression is the real risk, not
   pixel polish. Before shipping, verify round-trips for `confirmed` /
   `edited` / `rejected` plus teach-loop trigger after edited-accept. Need
   Playwright or Vitest coverage on these transitions (currently unknown —
   check in eng-review).
5. ~~Rollback plan~~ → **Decided**: feature flag (or at minimum a
   hard-coded branch toggle in `ReviewPage.jsx` top-level) so the flat list
   can be restored in one env-var flip if completion rate drops. "One-commit
   revert" is not a rollback plan — users will already be in the new UI.

## Eng-Review Resolutions (2026-04-20)

- **Finalize contract** → Option C: backend `implicit_reject` param
  (see Phase 1c). v1 keeps old behavior by default; v2 opts in.
- **Phase split** → Yes, 1a (editable record) → 1b (inline AI + delete
  dead paths) → 1c (backend param). Three commits, three PRs.
- **Feature flag** → `VITE_INLINE_SUGGESTIONS_V2` build-time env var at
  top of `ReviewPage.jsx`. Reversible without code deploy via CDN
  config flip.
- **Workup destination** → `orders_followup` existing field.
- **Component extraction** → new `FieldWithAI.jsx`. `ReviewPage.jsx` is
  already 1100 lines.

## Ship Gate — Required Tests (Phase 1b)

All must land before Phase 1b merges. This is the IRON RULE regression
gate from eng-review.

**Critical regressions (must not break):**
1. Teach-loop triggers after edited-accept (`setTeachEditId` path)
2. Cited knowledge map still renders (`citedIds` / `knowledgeMap` flow)
3. Finalize writeback preserves confirmed diagnosis → `diagnosis` field
4. Finalize writeback preserves confirmed treatment → `treatment_plan`

**New behavior E2E:**
5. 采纳 button → collapses to ✓; field reflects suggestion text
6. 诊断 shows exactly 1 AI suggestion (top-1 by precedence rule), no 换一条
7. 治疗方向 shows exactly 1 AI suggestion (same rule), no 换一条
8. 检查建议 shows 1 pending at a time with counter `N/total`;
   采纳 → ✓ row + next pending appears; 换一条 → skips without accepting
9. 检查建议 last candidate: 换一条 button shows "已看完" disabled state
10. Empty section shows "暂无 AI 建议 · 手动填写"
11. 诊断 custom-add replaces the AI suggestion shown; 检查 custom-add appends
    to the pending queue; 治疗 custom-add replaces
12. Per-section custom add buttons write to correct backend `section`
13. Implicit-reject: untouched suggestions at 完成审核 → backend marks
    them `rejected` (not 422); record saves with only accepted text
14. "完成审核 · N 条未处理" counter matches actual undecided count (sum
    across all sections; workup counts pending as undecided)

**Feature-flag smoke:**
15. `VITE_INLINE_SUGGESTIONS_V2=false` → flat list renders (Phase 0
    behavior preserved)

Target: ~8-10 hours of Playwright work (≈ 1 day with CC+gstack).
Extend `tests/e2e/08-review-diagnosis.spec.ts`; don't create a new
file.

## Risks

- **Doctor confusion from paradigm shift**: going from "9 cards with clear
  accept/reject" to "inline row per field" changes mental model. Mitigation:
  feature flag for fast rollback; watch session recordings after deploy.
- **State-transition regressions**: moving decision controls into record
  fields means `confirmed` / `edited` / `rejected` / `custom` semantics must
  still round-trip. Teach-loop trigger after edited-accept is the most
  fragile path. Must have e2e or equivalent coverage before ship.
- **Field-text drift from accepted AI**: once doctor accepts then manually
  edits the field, the final text ≠ original AI suggestion. The "✓ 已采纳 AI
  建议" state must show "医生已在基础上修改" to avoid pretending the field
  still equals the original. See mockup phone 2, 治疗方案.
- **Mobile layout density**: inline rows under editable textarea increase
  vertical height per field. Target is 360px wide — mockup verifies it fits.
- **Custom suggestion bias**: current "+ 添加我的建议" defaults to
  `treatment`. New per-section "+ 诊断 / + 检查 / + 治疗" buttons fix the
  bias by forcing the author to pick an axis. Discoverability risk: three
  smaller buttons less obvious than one big one. Mitigation: visual weight
  + copy tests.
- **Empty vs. loading confusion**: an empty section with "暂无 AI 建议"
  could look like a loading bug if the adjacent section has content.
  Mitigation: always render the placeholder explicitly, never hide the
  section entirely.
- **Teach loop regression**: existing `teach_prompt` / `teach_edit_id` flow
  is tangled with `SuggestionCard`. Careful extraction needed — see Phase 1
  files-to-change list.

## Non-Goals

- Rejecting the 2026-03-25 spec wholesale — only the card-list rendering
  changes. Trigger flow, finalize flow, teach loop, status transitions stay.
- Adding new AI capabilities — same suggestions, different presentation.
- Restyling v2 theme or adding new tokens.
