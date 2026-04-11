# Workflow 04 — Persona rules CRUD

Ship gate for **AI人设** — the per-field rule manager where doctors
configure how their AI speaks. Rules here directly shape every LLM
prompt, so adding, editing, or deleting a rule must be reflected in the
next AI output.

This workflow targets the new `PersonaSubpage` introduced on
`feat/persona-phase1` (commits `607b4053`, `a09376a5`, `eaa8dfa0`).

**Area:** `src/pages/doctor/subpages/PersonaSubpage.jsx`, persona API
(`api.addPersonaRule` / `updatePersonaRule` / `deletePersonaRule`),
`usePersona()` hook, `QK.persona(doctorId)` cache key
**Spec:** `frontend/web/tests/e2e/04-persona-rules.spec.ts`
**Estimated runtime:** ~5 min manual / ~30 s automated

---

## Scope

**In scope**

- Render 5 field sections (`reply_style`, `closing`, `structure`,
  `avoid`, `edits`) with correct Chinese labels and hint placeholders.
- Add rule via `+` icon on each field header → `SheetDialog` → submit.
- Edit rule via pencil icon → `SheetDialog` pre-filled → submit.
- Delete rule via trash icon → `ConfirmDialog` → confirm.
- Source badge per rule (`手动` / `引导` / `学习` / `示例` / `迁移`).
- Usage count (`使用 N 次`) rendered when > 0.
- Stats row at the bottom: `规则总数` + `学习获得`.
- Empty field state: hint placeholder in italic text4 color.
- Invalid add/edit (empty / whitespace only) blocks submit button.
- Optimistic UI + query invalidation after mutation.

**Out of scope**

- The persona preview card on MyAIPage — [03](03-my-ai-overview.md).
- How persona rules influence LLM output — eval suite, not Playwright.
- Teaching loop that auto-saves edits back as `source=edit` rules —
  tracked in `ai-thinks-like-me-qa-plan.md`.

---

## Pre-flight

Standard pre-flight. No seed needed — the spec starts from an empty
persona and creates rules through the UI. A separate test case seeds
via `seed.addPersonaRule` to verify render of existing rules.

---

## Steps

### 1. Page shell

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/settings/persona` (directly, or via 我的AI → 编辑人设) | `PageSkeleton` header "AI 人设"; back arrow `‹` top-left; bottom nav hidden |
| 1.2 | Observe 5 field sections | In order: 回复风格 → 常用结尾语 → 回复结构 → 回避内容 → 常见修改 |
| 1.3 | Each field header | Title left, `+` circle icon right in `COLOR.primary` |
| 1.4 | Empty field body | Italic hint text in text4 color, e.g. "例：口语化回复，像微信聊天" for 回复风格 |
| 1.5 | Stats section at bottom | Section label "统计"; two StatColumns: `规则总数` and `学习获得` |

### 2. Add rule

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Tap `+` icon on 回复风格 header | `SheetDialog` opens titled "添加回复风格"; 3-line multiline TextField auto-focused with placeholder "例：口语化回复，像微信聊天" |
| 2.2 | Leave field empty → look at footer | `添加` button disabled (grey); `取消` enabled |
| 2.3 | Type "口语化，像朋友聊天" | `添加` button becomes enabled (primary green) |
| 2.4 | Tap `添加` | Button shows "添加中…" loading state; sheet closes; the rule appears under 回复风格 with source badge "手动" |
| 2.5 | Stats row updates | `规则总数` increments by 1 |
| 2.6 | Cancel variant: open dialog, type text, tap 取消 | Dialog closes with no API call; rule count unchanged |

### 3. Edit rule

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap pencil icon on any rule | `SheetDialog` opens titled "编辑规则"; TextField pre-filled with existing rule text; "保存" button right, "取消" button left |
| 3.2 | Clear text → footer | `保存` disabled |
| 3.3 | Type new text "口语化回复，不要太正式" → 保存 | Sheet closes; rule text updates in place; no duplicate row |
| 3.4 | Source badge unchanged | Still "手动" (edits don't change source) |

### 4. Delete rule

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Tap trash icon on any rule | `ConfirmDialog` opens: title "确认删除"; message "删除后该规则将不再影响 AI 行为，确定要删除吗？"; cancel button labeled `保留` LEFT grey; confirm button labeled `删除` RIGHT red (danger tone) |
| 4.2 | Tap `保留` | Dialog closes; rule still present |
| 4.3 | Tap trash again → `删除` | Dialog closes; rule removed from list; 规则总数 decrements |

### 5. Multiple fields, rule ordering, source labels

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Add one rule to each of the 5 fields | Each appears under its own section; cross-section ordering preserved |
| 5.2 | For a seeded rule with `source=onboarding` | Badge reads "引导" (in accent color) |
| 5.3 | For a seeded rule with `source=edit` | Badge reads "学习" — this is what the teaching loop produces |
| 5.4 | For a seeded rule with `usage_count=5` | Caption "使用 5 次" shown below the rule text |
| 5.5 | Stats `学习获得` value | Equals the count of `edits` field rules where `source=edit` |

### 6. Query cache invalidation

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Open network tab, add a rule | Two requests fire: POST `/api/doctor/persona/<field>/rules`, then GET `/api/doctor/persona` (cache invalidation) |
| 6.2 | Navigate back to 我的AI | Persona preview card reflects the new rule within 1 s (no hard reload) |

---

## Edge cases

- **Very long rule text (~500 chars)** — word-breaks within the card, no
  horizontal scroll.
- **Server 500 on add** — dialog stays open; "添加中…" resets; no toast
  yet (see code: `catch {} // stay open on error`). Consider adding
  user-facing error feedback.
- **Deleting the last rule of a field** — field collapses back to the
  empty-hint placeholder.
- **Rapid double-tap on `+`** — only one SheetDialog should open
  (state guard).
- **Deleting a rule that the LLM cited recently** — the ai-thinks-like-me
  plan covers verifying the next diagnosis no longer cites it; not
  automated here.

---

## Known issues

No open bugs as of 2026-04-11. This page is new on the
`feat/persona-phase1` branch; it will pick up the standard
`hero-path-qa-plan.md` §Known Issues registry once merged.

---

## Failure modes & debug tips

- **Rules don't appear after add** — check query invalidation fires for
  `QK.persona(doctorId)` and that `usePersona()` returns the new shape.
  The effect is in `invalidate()` helper in PersonaSubpage.jsx.
- **Edit dialog shows empty text** — the `setEditText(rule.text)` may not
  run if `rule` prop is undefined. Log the `openEdit` args.
- **`规则总数` stuck at 0** — the reduce in lines 139-142 counts
  `fields[f.key]?.length`. If the API returns `fields: { reply_style: {...}
  }` instead of an array, totals break. Verify the API shape.
- **Delete confirm dialog shows wrong labels** — `ConfirmDialog` props:
  `cancelLabel="保留"`, `confirmLabel="删除"`, `confirmTone="danger"`.
  Standard MUI confirm layout; cancel LEFT, primary RIGHT.
