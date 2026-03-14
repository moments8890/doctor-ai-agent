# ADR 0012: Architecture Diagram

Companion diagram for
[ADR 0012](./0012-understand-execute-compose-pipeline.md).

## Full Pipeline Flow

```mermaid
flowchart TD
    input["user_input + DoctorCtx<br/>(already deduped by channel layer)"]

    %% Pre-pipeline guards
    input --> det{"Deterministic action?<br/>(button click, 确认/取消)"}
    det -->|yes| det_handler["Deterministic handler → template reply"]
    det -->|no| pending{"Pending guard<br/>pending_draft_id or<br/>pending_action_id set?"}

    pending -->|"confirm/abandon regex"| commit_or_discard["Commit or discard pending → template reply"]
    pending -->|"read-only regex"| understand
    pending -->|"other input"| blocked_reply["Blocked template reply"]
    pending -->|"no pending"| understand

    %% Understand phase
    understand["<b>UNDERSTAND</b><br/>LLM → UnderstandResult<br/>(structured, no prose for operational turns)"]

    understand -->|"action_type = none"| direct_reply["Return chat_reply directly<br/><i>1 LLM call</i>"]
    understand -->|"clarification set"| clarify_compose["Compose clarification<br/>(template or suggested_question)"]
    understand -->|"parse failure"| error_template["Generic error template"]
    understand -->|"operational action"| resolve

    %% Execute phase - Resolve
    resolve["<b>RESOLVE</b><br/>Patient DB lookup, binding,<br/>date normalization"]

    resolve -->|"clarification<br/>(not_found, ambiguous,<br/>blocked, missing_field,<br/>invalid_time)"| clarify_compose
    resolve -->|"resolved"| dispatch{"Action<br/>classification"}

    dispatch -->|"READ_ACTIONS<br/>{query_records, list_patients}"| read_engine
    dispatch -->|"WRITE_ACTIONS<br/>{schedule_task, select_patient,<br/>create_patient, create_draft}"| commit_engine

    %% Read engine
    read_engine["<b>READ ENGINE</b><br/>SELECT only, no durable writes<br/>→ ReadResult"]

    %% Commit engine
    commit_engine["<b>COMMIT ENGINE</b><br/>Durable writes, pending state<br/>→ CommitResult"]

    %% Compose phase
    read_engine --> compose_llm["<b>COMPOSE (LLM)</b><br/>Summarize fetched data<br/><i>2 LLM calls total</i>"]
    commit_engine --> compose_template["<b>COMPOSE (template)</b><br/>Format confirmation or success<br/><i>1 LLM call total</i>"]

    det_handler --> turn_result["TurnResult<br/>(reply + optional view_payload)"]
    commit_or_discard --> turn_result
    blocked_reply --> turn_result
    compose_llm --> turn_result
    compose_template --> turn_result
    clarify_compose --> turn_result
    direct_reply --> turn_result
    error_template --> turn_result

    %% Styling
    style understand fill:#4a90d9,color:#fff
    style resolve fill:#7b68ee,color:#fff
    style read_engine fill:#2ecc71,color:#fff
    style commit_engine fill:#e74c3c,color:#fff
    style compose_llm fill:#f39c12,color:#fff
    style compose_template fill:#f39c12,color:#fff
    style turn_result fill:#333,color:#fff
```

## Data Flow: Read Query Path

```mermaid
sequenceDiagram
    participant D as Doctor
    participant PG as Pending Guard
    participant U as Understand (LLM)
    participant R as Resolve
    participant RE as Read Engine
    participant C as Compose (LLM)

    D->>PG: "查张三的病历"
    PG->>U: pass through (read-looking)
    U->>R: UnderstandResult{action_type: query_records, args: {patient_name: "张三"}}
    R->>R: DB lookup "张三" → found (id=42)
    R->>R: Reads scope, no context switch
    R->>RE: ResolvedAction{patient_id: 42, limit: 5}
    RE->>RE: SELECT records WHERE patient_id=42 LIMIT 5
    RE->>C: ReadResult{status: ok, data: [...], total_count: 23, truncated: true}
    C->>D: "张三共有23条病历记录，最近5条：..."
```

## Data Flow: Write Confirmation Path (schedule_task)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant PG as Pending Guard
    participant U as Understand (LLM)
    participant R as Resolve
    participant CE as Commit Engine
    participant Co as Compose (template)

    D->>PG: "帮张三约下周三复诊"
    PG->>U: pass through (no pending)
    U->>R: UnderstandResult{action_type: schedule_task, args: {patient_name: "张三", task_type: appointment, scheduled_for: "下周三"}}
    R->>R: DB lookup "张三" → found
    R->>R: Normalize "下周三" → 2026-03-18T12:00 (date-only → noon default)
    R->>R: Default remind_at → 2026-03-18T11:00 (1 hour before)
    R->>R: Write action → switch context to 张三
    R->>CE: ResolvedAction{patient_id: 42, scheduled_for: "2026-03-18T12:00", remind_at: "2026-03-18T11:00"}
    CE->>CE: Create pending_action row (TTL)
    CE->>CE: Set ctx.workflow.pending_action_id
    CE->>Co: CommitResult{status: pending_confirmation, data: {...}}
    Co->>D: "确认为张三创建复诊预约，时间：3月18日中午12点？"

    D->>PG: "确认"
    PG->>PG: pending_action_id set + confirm regex
    PG->>PG: Create DoctorTask row, clear pending_action_id
    PG->>D: "已为张三创建复诊预约，时间：3月18日中午12点"
```

## Data Flow: Clarification Path

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant Co as Compose (template)

    D->>U: "帮张约个复诊"
    U->>R: UnderstandResult{action_type: schedule_task, args: {patient_name: "张"}}
    R->>R: DB lookup "张" → prefix match: 张三, 张三丰
    R->>Co: Clarification{kind: ambiguous_patient, options: [{name: "张三", id: 1}, {name: "张三丰", id: 2}]}
    Co->>D: "找到多位匹配的患者，请确认：1. 张三  2. 张三丰"
```

## Action Type Overview

```mermaid
graph LR
    subgraph ActionType Enum
        none["none<br/>(chitchat)"]
        qr["query_records"]
        lp["list_patients"]
        st["schedule_task"]
        sp["select_patient"]
        cp["create_patient"]
        cd["create_draft"]
    end

    subgraph Response Mode
        dr["direct_reply"]
        lc["llm_compose"]
        tp["template"]
    end

    subgraph Engine
        re["read_engine"]
        ce["commit_engine"]
    end

    none --> dr
    qr --> lc
    lp --> lc
    st --> tp
    sp --> tp
    cp --> tp
    cd --> tp

    qr --> re
    lp --> re
    st --> ce
    sp --> ce
    cp --> ce
    cd --> ce

    style none fill:#95a5a6,color:#fff
    style qr fill:#2ecc71,color:#fff
    style lp fill:#2ecc71,color:#fff
    style st fill:#e74c3c,color:#fff
    style sp fill:#e74c3c,color:#fff
    style cp fill:#e74c3c,color:#fff
    style cd fill:#e74c3c,color:#fff
    style re fill:#2ecc71,color:#fff
    style ce fill:#e74c3c,color:#fff
```

## Pending State Machine

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> PendingDraft: create_draft / create confirmed
    Idle --> PendingAction: schedule_task / action prepared
    PendingDraft --> Idle: 确认 (confirm) → save record
    PendingDraft --> Idle: 取消 (cancel) → discard
    PendingDraft --> Idle: TTL expired → auto-discard
    PendingAction --> Idle: 确认 (confirm) → create DoctorTask
    PendingAction --> Idle: 取消 (cancel) → discard
    PendingAction --> Idle: TTL expired → auto-discard

    note right of PendingDraft: pending_draft_id set
    note right of PendingAction: pending_action_id set
    note left of Idle: Both null (mutex enforced)
```

## memory_patch Application Rules

```mermaid
flowchart TD
    patch["memory_patch in UnderstandResult"]

    patch --> check_action{"action_type?"}
    check_action -->|"none"| apply_always["Apply unconditionally"]
    check_action -->|"operational"| check_clarify{"Understand<br/>clarification?"}

    check_clarify -->|yes| discard1["Discard patch"]
    check_clarify -->|no| check_resolve{"Resolve<br/>clarification<br/>or error?"}

    check_resolve -->|yes| discard2["Discard patch"]
    check_resolve -->|no| check_compose{"Compose<br/>failure?"}

    check_compose -->|yes| apply_compose["Apply patch<br/>(state change is real)"]
    check_compose -->|no| apply_success["Apply patch<br/>(full success)"]

    style apply_always fill:#2ecc71,color:#fff
    style apply_compose fill:#2ecc71,color:#fff
    style apply_success fill:#2ecc71,color:#fff
    style discard1 fill:#e74c3c,color:#fff
    style discard2 fill:#e74c3c,color:#fff
```
