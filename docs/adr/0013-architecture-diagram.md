# ADR 0013: Architecture Diagram

Companion diagram for
[ADR 0013](./0013-action-type-simplification.md).

## Full Pipeline Flow (ADR 0013)

```mermaid
flowchart TD
    input["user_input + DoctorCtx + chat_archive"]

    %% Pre-pipeline deterministic handler
    input --> det{"Deterministic?<br/>(greeting, help,<br/>确认/取消)"}
    det -->|yes| det_handler["Deterministic handler<br/>→ template reply"]
    det -->|no| understand

    %% Understand phase
    understand["<b>UNDERSTAND</b><br/>LLM → 1 of 5 action types<br/>(none, query, record, update, task)"]

    understand -->|"none"| direct_reply["Return chat_reply directly<br/><i>1 LLM call</i>"]
    understand -->|"clarification"| clarify_compose["Compose clarification<br/>(template)"]
    understand -->|"parse failure"| error_template["Generic error template"]
    understand -->|"query / record /<br/>update / task"| resolve

    %% Execute phase - Resolve
    resolve["<b>RESOLVE</b><br/>Patient lookup + context bind<br/>(uniform: all actions bind)"]

    resolve -->|"clarification<br/>(not_found, ambiguous,<br/>blocked, missing_field)"| clarify_compose
    resolve -->|"resolved"| dispatch{"Read or Write?"}

    dispatch -->|"READ<br/>{query}"| read_engine
    dispatch -->|"WRITE<br/>{record, update, task}"| commit_engine

    %% Read engine
    read_engine["<b>READ ENGINE</b><br/>target-based dispatch:<br/>records / patients / tasks"]

    %% Commit engine
    commit_engine["<b>COMMIT ENGINE</b><br/>record (+ demographics-only),<br/>update, task"]

    %% Compose phase
    read_engine --> compose_llm["<b>COMPOSE (LLM)</b><br/>Summarize fetched data"]
    commit_engine --> compose_template["<b>COMPOSE (template)</b><br/>Success confirmation"]

    %% Context bind (unconditional)
    compose_llm --> bind["Context bind<br/>(if patient_id → switch)"]
    compose_template --> bind

    det_handler --> turn_result["TurnResult"]
    bind --> turn_result
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
    style bind fill:#333,color:#fff
    style turn_result fill:#333,color:#fff
```

## Action Type Overview (ADR 0013)

```mermaid
graph LR
    subgraph "ActionType (5 values)"
        none["none<br/>(chitchat)"]
        query["query<br/>(target: records /<br/>patients / tasks)"]
        record["record<br/>(clinical content /<br/>demographics-only)"]
        update["update<br/>(modify record)"]
        task["task<br/>(create task)"]
    end

    subgraph "Response Mode"
        dr["direct_reply"]
        lc["llm_compose"]
        tp["template"]
    end

    subgraph Engine
        re["read_engine"]
        ce["commit_engine"]
    end

    none --> dr
    query --> lc
    record --> tp
    update --> tp
    task --> tp

    query --> re
    record --> ce
    update --> ce
    task --> ce

    style none fill:#95a5a6,color:#fff
    style query fill:#2ecc71,color:#fff
    style record fill:#e74c3c,color:#fff
    style update fill:#e74c3c,color:#fff
    style task fill:#e74c3c,color:#fff
    style re fill:#2ecc71,color:#fff
    style ce fill:#e74c3c,color:#fff
```

## Data Flow: Read Query (records)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant RE as Read Engine
    participant C as Compose (LLM)
    participant T as Turn (context bind)

    D->>U: "查张三的病历"
    U->>R: {action_type: query, args: {target: records, patient_name: "张三"}}
    R->>R: DB lookup "张三" → found (id=42)
    R->>RE: ResolvedAction{patient_id: 42, limit: 5}
    RE->>RE: SELECT records WHERE patient_id=42 LIMIT 5
    RE->>C: ReadResult{data: [...], total_count: 23}
    C->>T: "张三共有23条病历记录..."
    T->>T: Bind context → patient=张三
    T->>D: reply + context switched
```

## Data Flow: Record with Clinical Content

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant CE as Commit Engine
    participant S as Structuring LLM
    participant Co as Compose (template)

    D->>U: "张三头痛3天伴恶心"
    U->>R: {action_type: record, args: {patient_name: "张三"}}
    R->>R: _ensure_patient → found 张三 (id=42), bind context
    R->>CE: ResolvedAction{patient_id: 42}
    CE->>CE: Collect clinical text from chat_archive
    CE->>S: Raw text → structured record
    CE->>CE: Save to medical_records
    CE->>Co: CommitResult{preview: "主诉：头痛3天..."}
    Co->>D: "已为张三保存病历：主诉：头痛3天..."
```

## Data Flow: Demographics-Only (new patient)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant CE as Commit Engine
    participant Co as Compose (template)

    D->>U: "新患者王芳，女30岁"
    U->>R: {action_type: record, args: {patient_name: "王芳", gender: "女", age: 30}}
    R->>R: _ensure_patient → not found → auto-create (id=99)
    R->>R: Bind context → patient=王芳
    R->>CE: ResolvedAction{patient_id: 99}
    CE->>CE: Collect clinical text → empty
    CE->>Co: CommitResult{patient_only: true, name: "王芳"}
    Co->>D: "已建档【王芳】。"
```

## Data Flow: Task Creation

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant CE as Commit Engine
    participant Co as Compose (template)

    D->>U: "张三3个月后复查"
    U->>R: {action_type: task, args: {patient_name: "张三", title: "3个月复查", scheduled_for: "2026-06-16T12:00"}}
    R->>R: Resolve patient → found 张三 (id=42)
    R->>CE: ResolvedAction{patient_id: 42}
    CE->>CE: task_type = "general" (always)
    CE->>CE: Create DoctorTask row
    CE->>Co: CommitResult{title: "3个月复查", datetime_display: "6月16日"}
    Co->>D: "已为【张三】创建任务：3个月复查，时间：6月16日中午12点。"
```

## Patient Context Binding (ADR 0013)

**Uniform rule: all patient-scoped actions bind context.**

No `scoped_only` flag. No asymmetry between reads and writes.

```mermaid
flowchart LR
    A["Any action with<br/>resolved patient_id"] --> B["Bind to<br/>ctx.workflow"]
    B --> C["patient_id = resolved.patient_id<br/>patient_name = resolved.patient_name"]

    style A fill:#4a90d9,color:#fff
    style B fill:#333,color:#fff
    style C fill:#2ecc71,color:#fff
```

Replaces ADR 0012 §10 "binding asymmetry" (reads scope, writes switch).
