# Workflow 15 — Persona teach-by-example

Ship gate for the **教AI新偏好** flow where a doctor pastes a sample
reply and the AI extracts style rules from it. Extracted rules are added
to the pending review queue for the doctor to confirm or reject. This is
the primary way doctors teach their AI new preferences from real-world
reply examples.

This workflow targets `TeachByExampleSubpage.jsx`, reachable from the
persona settings tree at `/doctor/settings/persona/teach`.

**Area:** `src/pages/doctor/subpages/TeachByExampleSubpage.jsx`, teach
API (`POST /api/manage/persona/teach?doctor_id=` with
`{ example_text }` body — see `frontend/web/src/api.js:704-711`),
`QK.personaPending(doctorId)` cache key (invalidated on success)
**Spec:** `frontend/web/tests/e2e/15-persona-teach.spec.ts`
**Estimated runtime:** ~3 min manual / ~20 s automated

---

## Scope

**In scope**

- Instructional text explaining the flow ("粘贴一段你满意的回复...").
- Multiline TextField with placeholder, 2000 char max, character counter.
- "开始分析" button: disabled when text empty or whitespace-only.
- Loading state: button shows "分析中…" with spinner; TextField disabled.
- Success with extracted rules: count text ("发现 N 条偏好，已添加到
  待确认队列："), each rule with CheckCircle icon, field label, rule text.
- Success with no rules: "未发现明显的风格偏好，请尝试粘贴更完整的回复".
- Error state: "分析失败，请重试" in danger color.
- Cache invalidation: `QK.personaPending(doctorId)` invalidated when
  `result.count > 0`.
- Multiple submissions: previous results cleared on re-submit.

**Out of scope**

- Reviewing extracted rules in the pending queue — covered in
  [13-persona-pending.md](13-persona-pending.md).
- Persona rules CRUD — covered in
  [04-persona-rules.md](04-persona-rules.md).
- How the backend AI extracts rules — not a UI workflow.

---

## Pre-flight

Shared pre-flight lives in [`README.md`](README.md#shared-pre-flight).
This workflow needs:

- A registered doctor (standard fixture).
- The backend `/api/manage/persona/teach` endpoint must be functional
  (it calls the LLM to extract rules from text).
- For deterministic spec testing, the endpoint can be intercepted to
  return a canned response.

---

## Steps

### 1. Page shell

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/settings/persona/teach` (or via 人设 → 教AI新偏好) | `PageSkeleton` header "教AI新偏好"; back arrow top-left |
| 1.2 | Instructional text | "粘贴一段你满意的回复，AI会自动分析其中的风格偏好，添加到待确认队列。" visible |
| 1.3 | TextField | Multiline, placeholder "粘贴一段你满意的回复示例…", empty |
| 1.4 | Character counter | "0 / 2000" shown below TextField |
| 1.5 | Submit button | "开始分析" button visible and disabled |

### 2. Input validation

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Type spaces only into TextField | "开始分析" button remains disabled |
| 2.2 | Type "你好，这是一段测试回复" | Button becomes enabled; counter updates to show current length |
| 2.3 | Clear the text | Button returns to disabled; counter resets to "0 / 2000" |

### 3. Successful analysis with extracted rules

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Paste a realistic reply text and tap "开始分析" | Button changes to "分析中…" with loading spinner; TextField becomes disabled |
| 3.2 | API responds with extracted rules | Loading resets; "发现 N 条偏好，已添加到待确认队列：" text visible; N rules listed below, each with CheckCircle icon (green), field label (caption), and rule text |
| 3.3 | Navigate to `/doctor/settings/persona/pending` | The extracted rules appear in the pending queue |

### 4. Analysis with no rules found

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Submit very short/generic text (intercept API to return `{ extracted: [], count: 0 }`) | "未发现明显的风格偏好，请尝试粘贴更完整的回复" visible |
| 4.2 | No pending queue invalidation | Cache invalidation should NOT fire (count is 0) |

### 5. Error handling

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Intercept API to return 500, submit text | Loading state appears then resets; "分析失败，请重试" text visible in danger color; TextField re-enabled; button re-enabled |
| 5.2 | Fix intercept, submit again | Success result replaces error text |

### 6. Re-submit clears previous results

| # | Action | Verify |
|---|--------|--------|
| 6.1 | After a successful analysis showing N rules, modify text and tap "开始分析" again | Previous extracted rules disappear during loading; new results replace them |

---

## Edge cases

- **2000-char text** — counter shows "2000 / 2000"; `maxLength` on the
  input prevents typing beyond 2000.
- **Paste exceeding 2000 chars** — input truncates at 2000;
  `maxLength` enforced by the DOM.
- **Submit with only newlines/whitespace** — `text.trim()` is empty so
  `handleSubmit` early-returns; button should be disabled anyway.
- **Rapid double-tap "开始分析"** — `loading` state disables the button
  on first click; second tap is a no-op.
- **Navigate away mid-request** — component unmounts; no error shown.
  The API call completes but setState on unmounted component is a no-op
  in React 18+ (no warning).

---

## Known issues

No open bugs as of 2026-04-11. This page is new on the
`feat/persona-phase1` branch.

---

## Failure modes & debug tips

- **TextField doesn't accept input** — check that `disabled={loading}`
  only applies during API call, not permanently.
- **"开始分析" permanently disabled** — `!text.trim()` condition. Verify
  `text` state updates on `onChange`.
- **Results never appear** — verify
  `POST /api/manage/persona/teach?doctor_id=` returns
  `{ extracted: [...], count: N }`. The component reads
  `result.extracted` and `result.count`.
- **Pending queue not updated after success** — check that
  `queryClient.invalidateQueries({ queryKey: QK.personaPending(doctorId) })`
  fires only when `result.count > 0`.
- **Character counter off by one** — `text.length` in JSX should match
  the controlled input value. If `maxLength` truncates on paste, the
  counter may show the truncated length.
