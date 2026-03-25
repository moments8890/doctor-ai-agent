# Hybrid Extraction Architecture — Per-Turn Draft + Batch Final

**Status:** Planned (discussed with Codex, approved by user)
**Date:** 2026-03-25
**Priority:** P0 — addresses root cause of duplication, extraction misses, and merge bugs

## Problem

Current per-turn extraction does 3 jobs with 1 object (`session.collected`):
1. Steering next question (what to ask next)
2. UI progress tracking (已完成 4/7)
3. Final saved medical record

This coupling causes: duplication across turns, fragile merge logic, reconciliation patches that don't fully work.

## Design

### Per-Turn (DRAFT) — for steering + progress only
```
Patient message → LLM extracts lightweight draft → session.collected (draft)
                → Used for: progress bar, missing-field guidance, next question
                → NOT the final record
```

### Confirm-Time (FINAL) — the only saved truth
```
Full transcript → batch LLM extraction → complete SOAP fields → save to DB
                → One pass, no merge logic, no duplication
                → Replaces draft entirely
```

### Two modes with different confirm-time prompts

**Patient mode** — Extract + normalize:
- LLM reads full transcript
- Outputs clean medical prose for each SOAP field
- Can normalize, reorganize, deduplicate
- Chief complaint: visit-reason-first, ≤20 chars

**Doctor mode** — Deduplicate + reorganize:
- LLM reads full transcript
- Preserves doctor's exact wording (abbreviations, numbers, units)
- Only deduplicates repeated entries and fixes field placement
- Does NOT paraphrase or rewrite

## Implementation Plan

### Phase 1: Batch extractor
- New function `batch_extract_from_transcript(conversation, mode, patient_info)` in `interview_summary.py`
- Patient prompt: full SOAP extraction from transcript
- Doctor prompt: deduplicate + reorganize with original wording preserved
- Returns complete dict of all SOAP fields

### Phase 2: Wire into confirm
- `confirm_interview()` calls `batch_extract_from_transcript()` instead of using `session.collected`
- Replaces the current reconciliation sweep entirely
- The batch result is what gets saved to `medical_records`

### Phase 3: Per-turn becomes draft
- Per-turn extraction stays for progress/steering
- Prompt reframed: "draft preview, not final charting"
- Remove `complete: true` from prompt (response schema doesn't have it)
- `session.collected` is explicitly a draft — not canonical

### Phase 4: Doctor mode
- Doctor per-turn stays unchanged (immediate feedback)
- Add batch extraction at confirm time with "preserve original wording" prompt
- Doctor UI shows draft progress as before

## Files to change

| File | Change |
|------|--------|
| `src/domain/patients/interview_summary.py` | New `batch_extract_from_transcript()`, replace reconciliation |
| `src/domain/patients/interview_turn.py` | Per-turn prompt reframed as draft |
| `src/agent/prompts/patient-interview.md` | Remove `complete: true`, reframe extraction as draft |
| `src/agent/prompts/doctor-interview.md` | Same |
| `src/channels/web/patient_interview_routes.py` | Confirm uses batch result |
| `src/channels/web/doctor_interview.py` | Add batch at confirm |

## Progress UI per mode

### Patient mode — progress bar
Simple percentage + phase label. Patient doesn't see field names.
```
[████████░░░░░░░░] 40% — 正在了解您的病史
```
Computed from: count of non-empty draft fields / total patient fields (7).
Phase label from interview stage: "了解就诊原因" → "了解病史" → "即将完成".

### Doctor mode — NHC field checklist
Doctor sees which fields are filled, grouped by NHC priority:
```
必填: ✓ 主诉  ✓ 现病史  ✗ 既往史  ✗ 过敏史
推荐: ✗ 体格检查  ✗ 诊断  ✗ 治疗方案
已完成 2/7 必填
```

NHC Article 13 outpatient field categories:
- **必填**: 主诉、现病史 (hard requirement)
- **推荐**: 既往史、过敏史、家族史、个人史、体格检查、诊断、治疗方案
- **可选**: 专科检查、辅助检查、婚育史、医嘱及随访

Computed server-side from draft `collected` — no LLM needed.

### API response format
Both modes return structured `progress` metadata in turn response:
```json
{
  "progress": {
    "filled": 4,
    "total": 7,
    "pct": 57,
    "phase": "病史采集",
    "fields": {
      "chief_complaint": {"status": "filled", "priority": "required"},
      "present_illness": {"status": "filled", "priority": "required"},
      "past_history": {"status": "empty", "priority": "recommended"},
      ...
    }
  }
}
```
UI renders differently per mode — patient sees bar, doctor sees checklist.

## Deferred: Async persistence

Currently `save_session()` runs synchronously after every turn (~10 DB writes per interview). With hybrid architecture, per-turn draft doesn't need persistence — only the conversation log matters for recovery.

**Future optimization:**
- Conversation: async flush every 30s or 3 turns (not every message)
- Draft collected: in-memory only, no DB writes
- Final record: one write at confirm
- Reduces DB writes from ~10 to ~3 per interview

Not blocking for Phase 1 — current per-turn save is safe, just suboptimal.

## Risks

- Confirm-time latency increases (one extra LLM call over full transcript)
- If batch extractor fails, need fallback to draft
- Draft and final may diverge — UI should indicate "preview" status
- Long transcripts (20+ turns) may hit token limits

## Evidence

- Duplication bug proven by LLM debug logs (session 2026-03-24)
- 5-analyst review confirmed merge as root cause
- Codex recommended hybrid approach (session ID: 019d20d7...)
- Simulation results: 10/10 pass rate with current fixes, but duplication still occurs in edge cases
