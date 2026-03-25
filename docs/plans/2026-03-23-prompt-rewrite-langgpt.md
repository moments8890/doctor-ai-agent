# Prompt Rewrite: LangGPT + Instructor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite all 8 in-scope prompts with consistent LangGPT structure, unified persona, and few-shot examples; migrate vision-import to structured_call.

**Architecture:** Each prompt gets a tiered LangGPT template (compact/medium/full) with a shared persona header. Output format sections are removed from prompts that use Instructor/Pydantic. Few-shot examples are extracted from existing test fixtures.

**Tech Stack:** Markdown prompts, Pydantic models, `structured_call` (Instructor), existing test fixtures

**Spec:** `docs/specs/2026-03-23-prompt-rewrite-langgpt-instructor-design.md`

---

## File Map

### Prompt files (rewrite)
- `src/agent/prompts/routing.md` — compact tier
- `src/agent/prompts/compose.md` — compact tier
- `src/agent/prompts/vision-ocr.md` — compact tier
- `src/agent/prompts/vision-import.md` — medium tier
- `src/agent/prompts/doctor-interview.md` — full tier
- `src/agent/prompts/patient-interview.md` — full tier
- `src/agent/prompts/structuring.md` — full tier
- `src/agent/prompts/diagnosis.md` — full tier

### Code files (modify)
- `src/domain/records/vision_import.py` — migrate to `structured_call`

### Code files (cleanup)
- `src/agent/prompts/report-extract.md` — delete
- `src/domain/records/outpatient_report.py` — remove LLM fallback code

### Fixture files (read-only, extract examples from)
- `tests/fixtures/data/patient_interview_benchmark.json`
- `tests/fixtures/data/seed_data.json`
- `scripts/seed_ui_data.py`

---

## Task 1: Migrate vision-import to structured_call

**Files:**
- Modify: `src/domain/records/vision_import.py`

- [ ] **Step 1: Read vision_import.py and identify the raw OpenAI call**

The function that calls the LLM is around line 179+. It does:
```python
client.chat.completions.create(model=..., messages=[...], response_format={"type": "json_object"})
```
Then manually parses JSON. Find the exact function and understand its signature.

- [ ] **Step 2: Replace raw call with structured_call**

Replace the manual `client.chat.completions.create()` + `json.loads()` with:
```python
from agent.llm import structured_call
from domain.records.schema import OutpatientRecord

result = await structured_call(
    response_model=OutpatientRecord,
    messages=messages,
    op_name="vision_import",
    env_var="STRUCTURING_LLM",
    temperature=0.1,
    max_tokens=2000,
)
```

Remove the manual JSON parsing, client construction, and retry logic (structured_call handles all of that).

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/ --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -q --ignore=tests/core/test_multi_gateway_e2e.py --ignore=tests/wechat/test_wechat_kf_e2e.py --ignore=tests/core/test_patient_interview_ownership.py --ignore=tests/wechat/test_wechat_multi_input_e2e.py`
Expected: 47 passed (same as before)

- [ ] **Step 4: Commit**

```bash
git add src/domain/records/vision_import.py
git commit -m "refactor: migrate vision-import to structured_call + Pydantic"
```

---

## Task 2: Rewrite compact-tier prompts (routing, compose, vision-ocr)

**Files:**
- Modify: `src/agent/prompts/routing.md`
- Modify: `src/agent/prompts/compose.md`
- Modify: `src/agent/prompts/vision-ocr.md`

### Template for compact tier:
```markdown
# Role: 医生AI临床助手

## Profile
- 定位：主治医生的智能临床工具，所有操作均在医生授权下进行
- 不独立提供医疗建议，不替代医生判断

## Rules
(numbered rules)

## Constraints
(hard boundaries)

## Examples
(1-2 inline)
```

- [ ] **Step 1: Rewrite routing.md**

Add persona header. Keep the 6 existing examples (they're good). Keep the priority order rules.
Remove the `## 输出格式` and `## 参数说明` sections (Instructor + `RoutingResult` handles this).
Target: ~1.5K chars.

- [ ] **Step 2: Rewrite compose.md**

Add persona header. Add 1 example showing query results → natural Chinese summary.
Currently 290 chars / 5 rules — expand slightly with persona + example.
Keep it compact since compose returns free-form text (no Instructor).
Target: ~800 chars.

- [ ] **Step 3: Rewrite vision-ocr.md**

Add persona header. Currently a single line (226 chars).
Add constraints: preserve all numbers/units/drug names, no interpretation.
Target: ~500 chars.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/ --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -q --ignore=tests/core/test_multi_gateway_e2e.py --ignore=tests/wechat/test_wechat_kf_e2e.py --ignore=tests/core/test_patient_interview_ownership.py --ignore=tests/wechat/test_wechat_multi_input_e2e.py`
Expected: 47 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent/prompts/routing.md src/agent/prompts/compose.md src/agent/prompts/vision-ocr.md
git commit -m "refactor: rewrite compact-tier prompts with LangGPT structure"
```

---

## Task 3: Rewrite medium-tier prompt (vision-import)

**Files:**
- Modify: `src/agent/prompts/vision-import.md`

- [ ] **Step 1: Rewrite vision-import.md**

Add persona header + Profile section. Keep existing field rules.
Remove `## 输出格式` JSON schema section (Instructor + `OutpatientRecord` handles this).
Add 1 example extracted from `scripts/seed_ui_data.py` (a realistic medical record → expected structured output).
Target: ~1.5K chars.

- [ ] **Step 2: Run tests**

Same command as above. Expected: 47 passed.

- [ ] **Step 3: Commit**

```bash
git add src/agent/prompts/vision-import.md
git commit -m "refactor: rewrite vision-import prompt with LangGPT structure"
```

---

## Task 4: Rewrite full-tier prompts — doctor-interview

**Files:**
- Modify: `src/agent/prompts/doctor-interview.md`

### Template for full tier:
```markdown
# Role: 医生AI临床助手

## Profile
- 定位：主治医生的智能临床工具，所有操作均在医生授权下进行
- 不独立提供医疗建议，不替代医生判断
- 语言：中文
- 风格：专业、简洁、循证

## Background
(task context)

## Rules
(numbered, prioritized)

## Constraints
(hard no's)

## Examples
(2-3 from fixtures)

## Init
(opening behavior)
```

- [ ] **Step 1: Rewrite doctor-interview.md**

Add persona + Profile + Background (explains this is the doctor intake mode for clinical field collection).
Keep the existing clinical field tiers (必填/推荐/可选) and rules.
Remove `## 输出格式` JSON section (Instructor + `InterviewLLMResponse` handles this).
Add 2 few-shot examples from `tests/fixtures/data/patient_interview_benchmark.json`:
- Example 1: Doctor provides chief complaint + basic info → extracted fields
- Example 2: Doctor provides multiple fields at once → multi-field extraction
Add Init section: first message behavior (extract name/gender/age, show initial progress).
Target: ~3K chars.

- [ ] **Step 2: Run tests**

Same command. Expected: 47 passed.

- [ ] **Step 3: Commit**

```bash
git add src/agent/prompts/doctor-interview.md
git commit -m "refactor: rewrite doctor-interview prompt with LangGPT + examples"
```

---

## Task 5: Rewrite full-tier prompts — patient-interview

**Files:**
- Modify: `src/agent/prompts/patient-interview.md`

- [ ] **Step 1: Rewrite patient-interview.md**

Add persona + Profile (include patient-facing positioning: "你是医生的助手").
Add Background section explaining pre-consultation context.
Keep the two-phase structure (phase1: chief_complaint + present_illness, phase2: history).
Keep the 3 existing dialogue examples (off-topic handling, history referencing).
Keep emergency escalation rules.
Remove `## 输出格式` section (Instructor + `InterviewLLMResponse` handles this).
Remove `## 字段定义` section (Pydantic model defines this).
Restructure remaining content into Rules / Constraints sections.
Target: ~4K chars (down from current 6.5K by removing format/field sections).

- [ ] **Step 2: Run tests**

Same command. Expected: 47 passed.

- [ ] **Step 3: Commit**

```bash
git add src/agent/prompts/patient-interview.md
git commit -m "refactor: rewrite patient-interview prompt with LangGPT structure"
```

---

## Task 6: Rewrite full-tier prompts — structuring

**Files:**
- Modify: `src/agent/prompts/structuring.md`

- [ ] **Step 1: Rewrite structuring.md**

Add persona + Profile + Background (explains this converts raw clinical text to structured clinical record).
Keep the no-fabrication constraints (严禁虚构).
Keep information filtering rules.
Remove `## 输出格式` JSON section (Instructor + `StructuringLLMResponse` handles this).
Remove `## 字段定义` section (Pydantic model defines this).
Add 3 few-shot examples from `scripts/seed_ui_data.py`:
- Example 1: Simple outpatient note → structured fields
- Example 2: Voice transcription with noise → cleaned structured fields
- Example 3: No clinical content → empty response
Target: ~3K chars.

- [ ] **Step 2: Run tests**

Same command. Expected: 47 passed.

- [ ] **Step 3: Commit**

```bash
git add src/agent/prompts/structuring.md
git commit -m "refactor: rewrite structuring prompt with LangGPT + examples"
```

---

## Task 7: Rewrite full-tier prompts — diagnosis

**Files:**
- Modify: `src/agent/prompts/diagnosis.md`

- [ ] **Step 1: Rewrite diagnosis.md**

Add persona + Profile + Background (explains this generates differential diagnosis from structured record).
Keep confidence level rules (高/中/低).
Keep the dual-audience format (doctor_brief + patient_note).
Remove `## 输出格式` JSON section (Instructor + `DiagnosisLLMResponse` handles this).
Remove field-by-field type definitions (Pydantic handles this).
Add 2 few-shot examples from `scripts/seed_ui_data.py`:
- Example 1: Headache + hypertension → meningioma differential
- Example 2: Insufficient data → conservative response with "insufficient evidence" note
Target: ~3.5K chars (down from current 4.8K).

- [ ] **Step 2: Run tests**

Same command. Expected: 47 passed.

- [ ] **Step 3: Commit**

```bash
git add src/agent/prompts/diagnosis.md
git commit -m "refactor: rewrite diagnosis prompt with LangGPT + examples"
```

---

## Task 8: Cleanup — delete report-extract and LLM fallback

**Files:**
- Delete: `src/agent/prompts/report-extract.md`
- Modify: `src/domain/records/outpatient_report.py`

- [ ] **Step 1: Delete report-extract.md**

```bash
rm src/agent/prompts/report-extract.md
```

- [ ] **Step 2: Remove LLM fallback in outpatient_report.py**

In `extract_outpatient_fields()`, the LLM fallback path (after `_merge_structured_fields` returns None) is now unreachable since the write path always populates clinical columns. Remove:
- The `_build_extraction_prompt()` function
- The `_get_llm_client()` function and `_CLIENT_CACHE`
- The LLM call block in `extract_outpatient_fields()`
- The `ExtractionError` class
- The `_get_custom_template()` function

Keep:
- `_merge_structured_fields()` — this is the active path
- `extract_outpatient_fields()` — but simplified to just call `_merge_structured_fields()` and raise if None
- `export_as_json()` — unchanged

- [ ] **Step 3: Run tests**

Same command. Expected: 47 passed.

- [ ] **Step 4: Commit**

```bash
git add -A src/agent/prompts/report-extract.md src/domain/records/outpatient_report.py
git commit -m "chore: delete report-extract prompt and LLM fallback (clinical columns are authoritative)"
```

---

## Task 9: Update prompt inventory

**Files:**
- Modify: `tmp-prompt-inventory.md`

- [ ] **Step 1: Update tmp-prompt-inventory.md**

Reflect current state after rewrite:
- 8 active prompts with LangGPT structure
- report-extract.md deleted
- structuring.md status (kept or deleted depending on WeChat import decision)
- Note which prompts use Instructor vs raw text

- [ ] **Step 2: Commit**

```bash
git add tmp-prompt-inventory.md
git commit -m "docs: update prompt inventory after LangGPT rewrite"
```
