# Prompt Rewrite: LangGPT + Instructor Migration

**Date**: 2026-03-23
**Status**: Draft
**Scope**: 8 LLM prompts → structured LangGPT templates + Pydantic/Instructor output schemas

---

## 1. Problem

Current prompts are ad-hoc: inconsistent structure, no shared persona, zero to minimal
few-shot examples, output format instructions duplicated in prose when they should be
enforced by Instructor. Quality issues across routing, extraction, and interview flows.

## 2. Design Principles

1. **Single persona**: All prompts share one identity — the doctor's AI clinical assistant,
   operating under doctor authority. Patient-facing prompts frame it as "your doctor's
   assistant helping prepare for your visit."
2. **Prompt handles reasoning, Instructor handles structure**: Prompts define *how to think*.
   Pydantic models define *what to output*. No JSON format specs in prompts.
3. **Tiered complexity**: Simple tasks get compact prompts (~1K chars), complex tasks get
   full LangGPT treatment (~3-4K chars).
4. **Few-shot from fixtures first**: Use existing test data (`patient_interview_benchmark.json`,
   `seed_data.json`) as v1 examples. Refine with production data later.

## 3. Unified Persona

Every prompt opens with:

```markdown
# Role: 医生AI临床助手

## Profile
- 定位：主治医生的智能临床工具，所有操作均在医生授权下进行
- 不独立提供医疗建议，不替代医生判断
- 语言：中文
- 风格：专业、简洁、循证
```

Patient-facing prompts append:
```markdown
- 患者交互定位：你是"医生的助手"，帮助患者为就诊做准备
```

## 4. Template Tiers

### 4.1 Compact (~1K) — routing, compose, vision-ocr

```markdown
# Role
## Rules (numbered)
## Constraints
## Examples (1-2)
```

### 4.2 Medium (~2K) — vision-import

```markdown
# Role
## Profile
## Rules (numbered, prioritized)
## Constraints
## Examples (2-3)
```

### 4.3 Full (~3-4K) — doctor-interview, patient-interview, structuring, diagnosis

```markdown
# Role
## Profile
## Background (task context, when this prompt is called)
## Rules (numbered, prioritized — how to reason)
## Constraints (hard no's — no hallucination, escalate when uncertain)
## Examples (3-5, input/output pairs from fixtures)
## Init (opening behavior for first turn)
```

## 5. Instructor / Pydantic Status (Verified 2026-03-23)

### Current State

| Prompt | Pydantic Model | Call Style | Status |
|--------|---------------|------------|--------|
| routing | `RoutingResult` | `structured_call` | **Done** |
| doctor-interview | `InterviewLLMResponse` | `structured_call` | **Done** |
| patient-interview | `InterviewLLMResponse` | `structured_call` | **Done** |
| structuring | `StructuringLLMResponse` | `structured_call` | **Done** |
| diagnosis | `DiagnosisLLMResponse` | `structured_call` | **Done** |
| compose | None | `llm_call` (raw text) | **Keep raw** — returns prose, not structured data |
| vision-ocr | None | raw OpenAI | **Keep raw** — returns plain text, no structure needed |
| vision-import | `OutpatientRecord` (exists, manual JSON parse) | raw OpenAI | **Migrate** to `structured_call` |

### Summary

- **5/8 already migrated** to `structured_call` + Pydantic
- **2/8 intentionally raw** (compose returns prose, vision-ocr returns plain text)
- **1/8 needs migration** (vision-import has the Pydantic model but parses JSON manually)

### Remaining Migration Work

Only `vision-import` needs to switch from raw OpenAI + `json.loads()` to
`structured_call(response_model=OutpatientRecord, ...)`. The `OutpatientRecord`
Pydantic model already exists in `domain/records/schema.py`.

### What to Remove from Prompts

For the 5 prompts already using Instructor, delete:
- `## 输出格式` / `## Output Format` sections
- Inline JSON schema examples (`{"intent": "...", ...}`)
- "严格输出JSON" / "不要输出其他内容" instructions
- Field-by-field type annotations

Keep only: `输出JSON。` (one line, as a reminder)

## 6. Prompt-Level Audit (Verified 2026-03-23)

| Prompt | Has LangGPT Structure? | Has Few-Shot Examples? | Has Output Format to Remove? |
|--------|----------------------|----------------------|----------------------------|
| routing | Partial (rules + priority order) | Yes (6 examples) | Yes |
| doctor-interview | Yes (role/rules/fields) | **No** | Yes |
| patient-interview | Yes (role/stages/rules) | Yes (3 dialogue examples) | Yes |
| structuring | Yes (rules/filtering/fields) | **No** | Yes |
| diagnosis | Yes (rules/sections) | **No** | Yes |
| compose | Minimal (5 rules only) | **No** | No (returns prose) |
| vision-ocr | Minimal (single line) | **No** | Yes |
| vision-import | Yes (rules/fields) | **No** | Yes |

### Key Gaps

- **doctor-interview, structuring, diagnosis**: No few-shot examples — these are the
  most complex prompts and would benefit the most from examples.
- **compose**: Minimal structure, no examples — low-priority since output is free-form.
- **All 8 prompts**: Missing unified persona header.

## 7. Few-Shot Example Plan

### Sources

| Source File | Contains | Use For |
|-------------|----------|---------|
| `tests/fixtures/data/patient_interview_benchmark.json` | 80+ multi-turn interview cases | interview prompts |
| `tests/fixtures/data/seed_data.json` | 5 patients, 10+ clinical records | structuring, diagnosis |
| `scripts/seed_ui_data.py` | Realistic structured records | structuring, diagnosis |
| New (hand-written) | Intent examples | routing, compose |

### Examples Per Prompt

| Prompt | Current | Target | Source | Example Type |
|--------|---------|--------|--------|-------------|
| routing | 6 | 6 (keep) | Existing | intent classification |
| doctor-interview | 0 | 2 | benchmark.json | doctor input → extracted clinical fields |
| patient-interview | 3 | 3 (keep) | Existing | patient message → reply + extracted |
| structuring | 0 | 3 | seed_data.py | clinical text → content + structured dict |
| diagnosis | 0 | 2 | seed_data.py | clinical fields → differentials + workup |
| compose | 0 | 1 | New | query results → natural Chinese reply |
| vision-ocr | 0 | 0 | — | Keep compact, no examples needed |
| vision-import | 0 | 1 | seed_data.py | image description → structured JSON |

## 8. Prompts to Delete

- **`report-extract.md`** — Dead after clinical column migration. The LLM fallback in
  `outpatient_report.py:extract_outpatient_fields()` is unreachable for new records.
  Delete prompt file + LLM fallback code path.

- **`structuring.md`** — Evaluate: replaced by doctor-interview as the sole record
  creation path (per "2.1 Create Record — Always Interview" rule). WeChat import path
  needs to route through interview or be deprecated.

## 9. Implementation Order

### Phase 1: Migrate vision-import to structured_call
- Switch `domain/records/vision_import.py` from raw OpenAI + `json.loads()` to
  `structured_call(response_model=OutpatientRecord, ...)`
- Verify tests pass
- **Scope**: 1 file

### Phase 2: Prompt Rewrite (LangGPT structure)
- Add unified persona header to all 8 prompts
- Restructure each prompt per its tier template (compact/medium/full)
- Remove output format sections from the 5 Instructor-backed prompts
- Keep routing's 6 existing examples, patient-interview's 3 existing examples
- **Scope**: 8 prompt files

### Phase 3: Few-Shot Examples
- Extract examples from `patient_interview_benchmark.json` → doctor-interview (2)
- Extract examples from `seed_data.py` → structuring (3), diagnosis (2), vision-import (1)
- Write new examples → compose (1)
- **Scope**: 5 prompt files

### Phase 4: Cleanup
- Delete `report-extract.md` and its LLM fallback code in `outpatient_report.py`
- Evaluate whether `structuring.md` can be deleted (depends on WeChat import decision)
- Update `tmp-prompt-inventory.md`
- **Scope**: 2-3 files

## 10. Success Criteria

- All 8 prompts follow consistent LangGPT structure with shared persona
- vision-import uses `structured_call` + Pydantic (joining the other 5)
- compose and vision-ocr remain raw (intentional — prose/plain-text output)
- doctor-interview, structuring, and diagnosis each have 2+ few-shot examples
- Existing tests pass (47 unit tests, no regressions)
- Token usage per prompt stays within tier budget (compact <1K, medium <2K, full <4K)

## 11. Deferred (Future Phase)

- **Triage prompts** (classify, informational, escalation) — 3 inline prompts in `triage.py`
- **Upload matcher** — inline prompt in `upload_matcher.py`
- These remain as-is with raw `json_mode` calls until the patient lifecycle pipeline is revisited.
