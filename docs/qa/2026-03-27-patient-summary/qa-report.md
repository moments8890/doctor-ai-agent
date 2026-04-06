# QA Report — D1.6 Per-Patient Clinical Summary

> Date: 2026-03-27
> Branch: main
> Target: http://localhost:5173 (dev server, mock data)
> Scope: "总结{患者名}" chat command producing structured clinical summary

## Summary

| Metric | Value |
|--------|-------|
| Pages tested | 1 (ChatPage) |
| Tests run | 3 |
| Passed | 3 |
| Failed | 0 |
| Bugs found | 0 |
| Console errors (new) | 0 |

## Test Results

### T1: "总结陈伟强" produces structured clinical summary
- **Status:** PASS
- **Evidence:** `snapshots/18-patient-summary.png`
- **Details:** Response renders structured Markdown with: **基本信息** (男，42岁), **主要诊断** (2 entries with dates), **治疗经过** (氨氯地平5mg qd), **当前状态** (血压控制尚可), **注意事项** (⚠ 需复查血常规). Matches the prompt template structure.

### T2: Record cards render below summary
- **Status:** PASS
- **Evidence:** `snapshots/18-patient-summary.png`
- **Details:** Two record cards below summary text: 陈伟强·头痛3天伴恶心呕吐 (2026-03-26) and 陈伟强·头晕反复发作1月 (2026-03-19). Tappable with chevrons.

### T3: Console health
- **Status:** PASS
- **Details:** Zero new errors.

## What Changed

- `routing.md` — added "总结", "最近情况", "就诊历史" as query_record triggers
- `query.md` — structured clinical summary format for per-patient queries (基本信息→主要诊断→治疗经过→当前状态→注意事项)
- `mockApi.js` — added mock response for "总结" keyword with realistic clinical summary

## Limitations

- Mock data only — real LLM output format verified by prompt design, not live execution. Requires running backend + LLM for end-to-end verification.

## Screenshots

| File | Description |
|------|-------------|
| `snapshots/18-patient-summary.png` | Clinical summary for 陈伟强 with structured sections + record cards |
