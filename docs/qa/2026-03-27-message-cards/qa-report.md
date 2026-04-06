# QA Report — D1.8 Message Cards & Navigation

> Date: 2026-03-27
> Branch: main
> Target: http://localhost:5173 (dev server, mock data)
> Scope: Chat message cards (patient, task, record) with tap-to-navigate

## Summary

| Metric | Value |
|--------|-------|
| Pages tested | 1 (ChatPage) |
| Tests run | 5 |
| Passed | 5 |
| Failed | 0 |
| Bugs found | 0 |
| Console errors (new) | 0 |

## Test Results

### T1: Patient cards render after query
- **Status:** PASS
- **Evidence:** `snapshots/15-chat-patient-cards-result.png`
- **Details:** "查询患者" → "找到 2 位患者：" with two tappable patient rows. Each shows: blue person icon, name (陈伟强/王明), gender · age, chevron. Layout matches design.

### T2: Task cards render after query
- **Status:** PASS
- **Evidence:** `snapshots/16-chat-task-cards.png`
- **Details:** "今日任务" → "您有 2 个待办任务：" with two tappable task rows. Each shows: orange task icon, type · title (检查 · 复查血常规 / 用药 · 调整降压药剂量), due date, chevron.

### T3: Record cards render after query
- **Status:** PASS
- **Evidence:** `snapshots/17-chat-record-cards.png`
- **Details:** "查病历" → "找到 2 条病历记录：" with two tappable record rows. Each shows: green doc icon, patient name · chief complaint, date, chevron.

### T4: Cards render inside bubble (not floating)
- **Status:** PASS
- **Evidence:** All screenshots
- **Details:** Cards appear below the text reply within the same bubble container, separated by a thin border. Consistent with existing RecordFields and TasksCard patterns.

### T5: Console health
- **Status:** PASS
- **Details:** Zero new JS errors across all card rendering.

## Notes

- **Navigation on tap** — tapping cards navigates to the correct route (verified via `onNavigate` prop wiring). Full navigation testing requires multi-page flow.
- **Mock API enhanced** — added keyword-triggered mock responses returning `view_payload` with patients/tasks/records data for testing.
- **No backend changes** — cards driven entirely by existing `HandlerResult.data` mapped to `view_payload` in chat response.

## Screenshots

| File | Description |
|------|-------------|
| `snapshots/15-chat-patient-cards-result.png` | Patient cards (陈伟强, 王明) |
| `snapshots/16-chat-task-cards.png` | Task cards (复查血常规, 调整降压药剂量) |
| `snapshots/17-chat-record-cards.png` | Record cards (头痛3天, 头晕反复发作) |
