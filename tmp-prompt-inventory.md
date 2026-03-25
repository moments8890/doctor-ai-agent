# LLM Prompt Inventory (2026-03-23, post-composer migration)

Architecture: **Plan-and-Act pipeline** with **6-layer prompt composer**.
Flow: `handle_turn()` → `route()` → `dispatch()` → handler → `compose_messages()` → LLM.

## 6-Layer Prompt Stack

```
┌─────────────────────────────────┐
│ 1. system/base.md               │  Identity, safety, precedence rules
├─────────────────────────────────┤
│ 2. common/{specialty}.md        │  Specialty knowledge (e.g. neurology)
├─────────────────────────────────┤
│ 3. intent/{intent}.md           │  Action-specific rules + examples
├─────────────────────────────────┤
│ 4. <doctor_knowledge> XML tag   │  Per-intent KB slice from DB
├─────────────────────────────────┤
│ 5. <patient_context> XML tag    │  Records, case history from DB
├─────────────────────────────────┤
│ 6. <doctor_request> XML tag     │  Actual doctor/patient message
└─────────────────────────────────┘
Layers 1-3 → system message | Layers 4-6 → user message
Config: src/agent/prompt_config.py (INTENT_LAYERS matrix)
Assembly: src/agent/prompt_composer.py
```

## Prompt Files

### Layer 1 — System Base
| File | Purpose |
|------|---------|
| `prompts/system/base.md` | Identity, safety rules, precedence |

### Layer 2 — Common (Specialty)
| File | Purpose |
|------|---------|
| `prompts/common/neurology.md` | Neurosurgery knowledge, red flags, key tests |

### Layer 3 — Intent Prompts
| # | File | Pydantic Model | Instructor? | Few-Shot | Purpose |
|---|------|---------------|-------------|----------|---------|
| 1 | `intent/routing.md` | `RoutingResult` | Yes | 9 | Classify doctor message into 6 intents |
| 2 | `intent/query.md` | None (prose) | No | 0 | Generate natural-language query summary |
| 3 | `intent/compose.md` | None (prose) | No | 0 | Alternative compose prompt |
| 4 | `intent/interview.md` | `InterviewLLMResponse` | Yes | 4 | Doctor intake — SOAP field collection |
| 5 | `intent/patient-interview.md` | `InterviewLLMResponse` | Yes | 3 | Patient pre-consultation interview |
| 6 | `intent/diagnosis.md` | `DiagnosisLLMResponse` | Yes | 2 | Differential diagnosis from SOAP fields |
| 7 | `intent/structuring.md` | `StructuringLLMResponse` | Yes | 3 | Text → structured SOAP record |
| 8 | `intent/create-task.md` | None | No | 0 | Task creation rules |
| 9 | `intent/general.md` | None | No | 0 | Fallback/chitchat |
| 10 | `intent/vision-ocr.md` | None (plain text) | No | 0 | OCR for clinical images |
| 11 | `intent/vision-import.md` | `OutpatientRecord` | Manual JSON | 0 | Structured extraction from photos |

### Layer Usage Matrix (from prompt_config.py)

Two assembly patterns:
- **single**: Layers 1-3 → system, Layers 4-6 → user message with XML tags
- **convo**: Layers 1-5 → system (KB + context in system), conversation history, Layer 6 → plain user

```
Intent             | Pattern | Common | Intent           | Dr Knowledge                  | Patient Ctx
-------------------|---------|--------|------------------|-------------------------------|------------
routing            | single  |        | routing          | custom                        |
create_record      | convo   |   ✓    | interview        | interview_guide+red_flag+custom|      ✓
query_record       | single  |        | query            | custom                        |      ✓
query_task         | single  |        | query            | custom                        |
create_task        | single  |        | create-task      | custom                        |
query_patient      | single  |        | query            | custom                        |      ✓
general            | single  |        | general          | custom                        |
patient_interview  | convo   |   ✓    | patient-interview| interview_guide+red_flag+custom|      ✓
review/diagnosis   | single  |   ✓    | diagnosis        | diagnosis_rule+red_flag+treatment+custom| ✓
```

### Inline Prompts — Deferred

| # | File:Line | Purpose |
|---|-----------|---------|
| 1 | `domain/patient_lifecycle/triage.py:258` | Classify patient messages (5 categories) |
| 2 | `domain/patient_lifecycle/triage.py:338` | Handle informational patient questions |
| 3 | `domain/patient_lifecycle/triage.py:416` | Generate escalation summary for doctor |
| 4 | `domain/patient_lifecycle/upload_matcher.py:80` | Match uploaded files to pending tasks |

### Deleted

| File | Reason |
|------|--------|
| `report-extract.md` | Dead after SOAP column migration |
| `doctor-agent.md` | Removed in ReAct → Plan-and-Act migration |
| `patient-agent.md` | Removed in ReAct → Plan-and-Act migration |
| `agent-doctor.md` | Dead duplicate |

### Legacy (root prompts/)

Old prompt files remain in `prompts/` root for admin UI backward compatibility.
The composer reads from `prompts/system/`, `prompts/common/`, `prompts/intent/`.
These will be deleted when admin prompt editor is removed.
