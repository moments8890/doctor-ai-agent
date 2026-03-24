# LLM Prompt Inventory (2026-03-23, post-LangGPT rewrite)

Architecture: **Plan-and-Act pipeline**.
Flow: `handle_turn()` → `route()` (routing LLM) → `dispatch()` → intent handler → optional compose LLM.

All prompts use **LangGPT structure** with unified persona (医生AI临床助手).
Output schemas enforced by **Instructor + Pydantic** (not in prompts).

---

## System Prompts (8 active + 4 deferred)

### Pipeline Prompts (loaded from `src/agent/prompts/*.md`)

| # | File | Tier | Pydantic Model | Instructor? | Few-Shot | Purpose |
|---|------|------|---------------|-------------|----------|---------|
| 1 | `routing.md` | Compact | `RoutingResult` | Yes | 6 | Classify doctor message into 6 intents |
| 2 | `compose.md` | Compact | None (prose) | No | 1 | Generate natural-language summary |
| 3 | `vision-ocr.md` | Compact | None (plain text) | No | 0 | OCR for clinical document images |
| 4 | `vision-import.md` | Medium | `OutpatientRecord` | Yes | 1 | Structured extraction from medical record photos |
| 5 | `doctor-interview.md` | Full | `InterviewLLMResponse` | Yes | 2 | Doctor intake — 14 SOAP field collection |
| 6 | `patient-interview.md` | Full | `InterviewLLMResponse` | Yes | 3 | Patient pre-consultation interview |
| 7 | `structuring.md` | Full | `StructuringLLMResponse` | Yes | 3 | Conversation → structured SOAP record |
| 8 | `diagnosis.md` | Full | `DiagnosisLLMResponse` | Yes | 2 | Differential diagnosis from SOAP fields |

### Inline Prompts — Deferred (not yet rewritten)

| # | File:Line | Purpose |
|---|-----------|---------|
| 9 | `domain/patient_lifecycle/triage.py:258` | Classify patient messages (5 categories) |
| 10 | `domain/patient_lifecycle/triage.py:338` | Handle informational patient questions |
| 11 | `domain/patient_lifecycle/triage.py:416` | Generate escalation summary for doctor |
| 12 | `domain/patient_lifecycle/upload_matcher.py:80` | Match uploaded files to pending tasks |

### Deleted

| File | Reason |
|------|--------|
| `report-extract.md` | Dead after SOAP column migration — LLM fallback unreachable |
| `doctor-agent.md` | Removed in ReAct → Plan-and-Act migration |
| `patient-agent.md` | Removed in ReAct → Plan-and-Act migration |

---

## Persona

All 8 active prompts share:
```
# Role: 医生AI临床助手
## Profile
- 定位：主治医生的智能临床工具，所有操作均在医生授权下进行
- 不独立提供医疗建议，不替代医生判断
```

Patient-facing prompts (patient-interview) add:
```
- 患者交互定位：你是"医生的助手"，帮助患者为就诊做准备
```

---

## Template Tiers

| Tier | Sections | Target Size | Prompts |
|------|----------|-------------|---------|
| Compact | Role, Rules, Constraints, Examples | ~1K | routing, compose, vision-ocr |
| Medium | + Profile | ~2K | vision-import |
| Full | + Background, Init | ~3-4K | doctor-interview, patient-interview, structuring, diagnosis |
