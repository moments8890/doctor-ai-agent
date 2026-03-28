# Session Summary: Prompt Engineering Review & Migration (2026-03-27)

## What Was Done

### 1. Prompting Guide Created
**File:** `docs/guides/llm-prompting-guide.md`

Comprehensive 14-section guide synthesized from Anthropic, OpenAI, and Google prompt engineering docs, adapted to our 6-layer prompt stack. Covers architecture, universal principles, structural patterns, output control, few-shot examples, medical domain rules, conversation vs single-turn, extraction prompts, thinking/reasoning, safety, testing, anti-patterns, checklist, and quick reference templates.

### 2. All 14 Prompts Reviewed
**File:** `docs/guides/prompt-review-side-by-side.html`

Side-by-side comparison (original left, suggested right) for every prompt. Key findings:

| Prompt | Grade | Key Issues |
|--------|-------|------------|
| `common/base.md` | A | No changes needed |
| `doctor-extract.md` | A+ | Gold standard — other prompts should model after this |
| `patient-extract.md` | A+ | No changes needed |
| `diagnosis.md` | A | Pseudo-JSON examples → should be valid JSON |
| `general.md` | A- | Missing role header, example annotations |
| `routing.md` | B | Missing `## Constraints` (semantic only — instructor handles schema) |
| `patient-interview.md` | B | Missing `## 输出格式` (uses llm_call, no instructor) |
| `interview.md` | C+ | Missing constraints, abnormal handling, output schema, edge case examples |
| `query.md` | D+ | Zero examples, no role header |
| `vision-ocr.md` | C+ | Zero examples |
| `triage: classify` | C | Zero examples, embedded in Python |
| `triage: informational` | C+ | Zero examples, embedded in Python |
| `triage: escalation` | C | Zero examples, no constraints, embedded in Python |

### 3. Instructor vs llm_call Analysis

Discovered that `## 输出格式` is redundant for prompts using `structured_call()` (instructor + Pydantic enforces schema at code level). Only prompts using raw `llm_call()` need output schema in the prompt.

| Call Path | Needs 输出格式 in prompt? |
|-----------|--------------------------|
| `structured_call(PydanticModel)` | No — code enforces |
| `llm_call(json_mode=True)` | Yes — no schema enforcement |
| `llm_call()` (free text) | N/A — not JSON |

### 4. Migrated 4 Call Sites to structured_call()

**triage.py** — 3 migrations:

- `classify()`: `_call_triage_llm()` + `json.loads()` → `structured_call(ClassifyLLMResponse)`
  - `ClassifyLLMResponse`: category (TriageCategory enum) + confidence (0.0-1.0)
- `handle_informational()`: → `structured_call(InformationalLLMResponse)`
  - `InformationalLLMResponse`: reply (str)
- `handle_escalation()`: → `structured_call(EscalationLLMResponse)`
  - `EscalationLLMResponse`: 5 string fields (patient_question, conversation_context, patient_status, reason_for_escalation, suggested_action)

Removed ~90 lines of dead triage LLM infrastructure: `_TRIAGE_CLIENT_CACHE`, `_resolve_provider`, `_get_triage_client`, `_make_llm_caller`, `_call_triage_llm`, unused imports (`re`, `AsyncOpenAI`, `_get_providers`, `call_with_retry_and_fallback`, `trace_block`).

Added `_triage_env_var()` helper to preserve `TRIAGE_LLM → ROUTING_LLM → groq` fallback chain.

Removed `## 输出格式` sections from all 3 triage system prompts. Added `## Constraints` to escalation prompt.

**from_record.py** — 1 migration:

- `_extract_tasks_via_llm()`: `llm_call(json_mode=True)` + `json.loads()` → `structured_call(TaskExtractionResponse)`
  - `TaskType` enum: follow_up, medication, checkup, general
  - `ExtractedTask`: title, task_type, due_days, content
  - `TaskExtractionResponse`: wraps `List[ExtractedTask]` in object (instructor requires root object)
  - Uses `model_dump(mode="json")` to serialize enums as strings for consumer compatibility

---

## Still TODO (Not Started)

These are the remaining prompt improvements from the review that were NOT implemented:

### P0 — High Impact, Low Effort
- [ ] Add 3 examples to `query.md` (multi-record, empty, single)
- [ ] Add 3 examples to `vision-ocr.md` (lab, prescription, handwritten)
- [ ] Add examples to triage system prompts (now that they're in Python strings still — extracting to `.md` files is P2)

### P1 — Safety & Schema
- [ ] Add semantic `## Constraints` to `routing.md` (no-guess, no-fabricate)
- [ ] Add `## Constraints` + `## 输出格式` + `## 异常处理` to `interview.md` (uses llm_call, needs prompt-level schema)
- [ ] Add `## 输出格式` to `patient-interview.md` (uses llm_call, needs prompt-level schema)

### P2 — Consistency & Testability
- [ ] Standardize `# Role:` headers across all prompts (5 files)
- [ ] Extract triage prompts from Python strings to `.md` files (3 new files + refactor load path)
- [ ] Add edge case examples to `interview.md` (correction, off-topic)
- [ ] Convert pseudo-JSON to valid JSON in `diagnosis.md` examples

### P3 — Nice to Have
- [ ] Add parenthetical annotations to `general.md` examples
- [ ] Add `## 作用` section to `domain/neurology.md`

---

## Files Changed This Session

```
docs/guides/llm-prompting-guide.md          ← NEW: prompting guide
docs/guides/prompt-review-side-by-side.md   ← NEW: review report (markdown)
docs/guides/prompt-review-side-by-side.html ← NEW: review report (HTML, viewable)
src/domain/patient_lifecycle/triage.py      ← MODIFIED: 3x structured_call migration
src/domain/tasks/from_record.py             ← MODIFIED: 1x structured_call migration
```

## Current LLM Call Path Map (Post-Migration)

| Call Site | Call Path | Response Model |
|-----------|-----------|---------------|
| `router.py` | `structured_call(RoutingResult)` | RoutingResult |
| `diagnosis.py` | `structured_call(DiagnosisLLMResponse)` | DiagnosisLLMResponse |
| `interview_turn.py` | `structured_call(InterviewLLMResponse)` | InterviewLLMResponse |
| `interview_summary.py` | `structured_call(...)` | (extraction model) |
| `structuring.py` | `structured_call(...)` | (extraction model) |
| `vision_import.py` | `structured_call(...)` | (extraction model) |
| `triage.py: classify` | `structured_call(ClassifyLLMResponse)` | ClassifyLLMResponse |
| `triage.py: informational` | `structured_call(InformationalLLMResponse)` | InformationalLLMResponse |
| `triage.py: escalation` | `structured_call(EscalationLLMResponse)` | EscalationLLMResponse |
| `from_record.py` | `structured_call(TaskExtractionResponse)` | TaskExtractionResponse |
| `query_record.py` | `llm_call()` — free text | N/A |
| `query_task.py` | `llm_call()` — free text | N/A |
| `general.py` | `llm_call()` — free text | N/A |
| `doctor_knowledge.py` | `llm_call()` — free text | N/A |

**Rule:** `structured_call` for all JSON outputs. `llm_call` for all free-text outputs.
