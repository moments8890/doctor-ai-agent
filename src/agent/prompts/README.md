# Prompts

LLM prompt files — one `.md` file per prompt. Edit directly to tune behavior.

## How it works

- `utils/prompt_loader.py` reads files by key: `get_prompt("structuring")` → `prompts/structuring.md`
- Files are cached in memory on first read; call `invalidate()` to reload
- Agent prompts (`agent-doctor.md`, `agent-patient.md`) are loaded by `build_prompt(role)` and injected into the LangChain `ChatPromptTemplate`
- Tool-internal prompts (`structuring.md`, `patient-interview.md`) are loaded inside `@tool` functions for specialized LLM calls

## Architecture

### Agent Pipeline

```mermaid
flowchart TD
    subgraph Channels
        WEB[Web Channel]
        WX[WeChat Channel]
    end

    HT["handle_turn(text, role, identity)"]
    FP{"Fast path?<br/>greeting / confirm"}
    FR["Fast reply<br/>0 LLM calls"]

    WEB --> HT
    WX --> HT
    HT --> FP
    FP -- yes --> FR

    subgraph Doctor Agent
        DA["AgentExecutor<br/>agent-doctor.md"]
        DA --> QR[query_records]
        DA --> LP[list_patients]
        DA --> LT[list_tasks]
        DA --> CR[create_record]
        DA --> UR[update_record]
        DA --> CT[create_task]
    end

    subgraph Patient Agent
        PA["AgentExecutor<br/>agent-patient.md"]
        PA --> AI[advance_interview]
    end

    FP -- "role=doctor" --> DA
    FP -- "role=patient" --> PA

    DA -- reply --> HT
    PA -- reply --> HT
```

### Internal LLM Calls (inside tools)

```mermaid
flowchart LR
    subgraph "create_record / update_record"
        SH["Session History<br/>via ContextVar"] --> SL["Structuring LLM<br/>structuring.md"]
        SL --> SP["Structured Preview"]
    end

    subgraph advance_interview
        DB[("interview_sessions DB")] --> IL["Interview LLM<br/>patient-interview.md"]
        IL --> ER["extracted fields +<br/>suggested_reply"]
    end
```

### Standalone Prompts (not in agent pipeline)

```mermaid
flowchart LR
    IMG["Medical Image"] --> OCR["Vision LLM<br/>vision-ocr.md"]
    OCR --> TXT["Plain Text"]

    IMG2["Record Photo"] --> VI["Vision LLM<br/>vision-import.md"]
    VI --> SF["Structured Fields<br/>+ Patient Info"]

    REC["Stored Records"] --> RE["Report LLM<br/>report-extract.md"]
    RE --> RPT["Outpatient Report<br/>Fields"]
```

## Prompt Index

### Agent System Prompts

| File | Role | Template vars | Description |
|------|------|---------------|-------------|
| `agent-doctor.md` | Doctor | `{current_date}`, `{timezone}`, `{tools_section}` | Doctor agent system prompt — clinical collection, tool usage rules, examples |
| `agent-patient.md` | Patient | `{current_date}`, `{timezone}` | Patient agent system prompt — interview orchestration, off-topic handling, scope boundaries |

### Tool-Internal Prompts

| File | Called by | Template vars | Description |
|------|----------|---------------|-------------|
| `structuring.md` | `create_record`, `update_record` | _(receives session history)_ | Conversation → structured medical record (content + structured JSON) |
| `patient-interview.md` | `advance_interview` | `{name}`, `{gender}`, `{age}`, `{previous_history}`, `{collected_json}`, `{missing_fields}` | Clinical field extraction + next-question suggestion for patient pre-consultation |

### Standalone Prompts

| File | Used by | Template vars | Description |
|------|---------|---------------|-------------|
| `report-extract.md` | `services/export/outpatient_report.py` | `{records_text}` | Extract outpatient report fields from stored records |
| `vision-import.md` | `services/record_import/vision_import.py` | _(image input)_ | Extract structured fields + patient info from medical record photos |
| `vision-ocr.md` | `services/ai/vision.py` | _(image input)_ | Plain-text OCR for medical documents |
| `patient-chat.md` | `channels/wechat/patient_pipeline.py` | _(conversation history)_ | Legacy — used by WeChat patient pipeline until migrated to agent |

### Deprecated (delete after migration)

| File | Replaced by | Reason |
|------|------------|--------|
| ~~`understand.md`~~ | `agent-doctor.md` + LangChain agent | Agent LLM handles intent reasoning directly |
