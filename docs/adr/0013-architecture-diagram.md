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
    resolve["<b>RESOLVE</b><br/>Patient lookup, date validation<br/>(§3 target routing, §5 _validate_task_dates)"]

    resolve -->|"clarification<br/>(not_found, ambiguous,<br/>blocked, missing_field,<br/>invalid_time)"| clarify_compose
    resolve -->|"resolved"| dispatch{"Read or Write?"}

    dispatch -->|"READ<br/>{query}"| read_engine
    dispatch -->|"WRITE<br/>{record, update, task}"| commit_engine

    %% Read engine
    read_engine["<b>READ ENGINE</b><br/>target-based dispatch:<br/>records / patients / tasks<br/>(unknown target → records)"]

    %% Commit engine
    commit_engine["<b>COMMIT ENGINE</b><br/>record (+ demographics-only),<br/>update, task (type=general)"]

    %% Compose phase
    read_engine --> compose_llm["<b>COMPOSE (LLM)</b><br/>Summarize fetched data"]
    commit_engine --> compose_template["<b>COMPOSE (template)</b><br/>Success confirmation"]

    %% Context bind (unconditional — ADR 0013 §2)
    compose_llm --> bind["<b>CONTEXT BIND</b><br/>if patient_id → switch<br/>(unconditional, no scoped_only)"]
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

## Action Type Overview (ADR 0013 §1)

```mermaid
graph LR
    subgraph "ActionType (5 values)"
        none["none<br/>(chitchat)"]
        query["query<br/>(target: records /<br/>patients / tasks)"]
        record["record<br/>(clinical content /<br/>demographics-only)"]
        update["update<br/>(modify record)"]
        task["task<br/>(type=general always)"]
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

## Data Flow: Query Records + Context Switch (ADR 0013 §2, §3)

Also covers "切换到张三" which maps to `query` (ADR 0013 §4).

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant RE as Read Engine
    participant C as Compose (LLM)
    participant T as Turn (context bind)

    D->>U: "查张三的病历" or "切换到张三"
    U->>R: {action_type: query, args: {target: records, patient_name: "张三"}}
    R->>R: target=records → resolve patient
    R->>R: DB lookup "张三" → found (id=42)
    R->>RE: ResolvedAction{patient_id: 42}
    RE->>RE: SELECT records WHERE patient_id=42 LIMIT 5
    RE->>C: ReadResult{data: [...], total_count: 23}
    C->>T: "张三共有23条病历记录..."
    T->>T: Bind context → patient=张三 (unconditional)
    T->>D: reply + context switched
```

## Data Flow: Query Unscoped (patients / tasks)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant RE as Read Engine
    participant C as Compose (LLM)

    D->>U: "我的患者" or "今日任务"
    U->>R: {action_type: query, args: {target: patients}}
    R->>R: target=patients → skip patient resolution
    R->>RE: ResolvedAction (no patient_id)
    RE->>RE: _list_patients() or _list_tasks()
    RE->>C: ReadResult{data: [...]}
    C->>D: "您有12位患者..."
    Note over D: No context change (no patient_id resolved)
```

## Data Flow: Record with Clinical Content (ADR 0013 §4)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant CE as Commit Engine
    participant S as Structuring LLM
    participant Co as Compose (template)
    participant T as Turn (context bind)

    D->>U: "张三头痛3天伴恶心"
    U->>R: {action_type: record, args: {patient_name: "张三"}}
    R->>R: _ensure_patient → found 张三 (id=42)
    R->>CE: ResolvedAction{patient_id: 42}
    CE->>CE: Collect clinical text from chat_archive
    CE->>S: Raw text → structured record
    CE->>CE: Save to medical_records
    CE->>Co: CommitResult{preview: "主诉：头痛3天..."}
    Co->>T: "已为张三保存病历：主诉：头痛3天..."
    T->>T: Bind context → patient=张三 (unconditional)
    T->>D: reply + context switched
```

## Data Flow: Demographics-Only Registration (ADR 0013 §4)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant CE as Commit Engine
    participant Co as Compose (template)
    participant T as Turn (context bind)

    D->>U: "新患者王芳，女30岁"
    U->>R: {action_type: record, args: {patient_name: "王芳", gender: "女", age: 30}}
    R->>R: _ensure_patient → not found → auto-create with gender/age (id=99)
    R->>CE: ResolvedAction{patient_id: 99}
    CE->>CE: Collect clinical text → empty
    CE->>CE: patient_name present → demographics-only path
    CE->>Co: CommitResult{patient_only: true, name: "王芳"}
    Co->>T: "已建档【王芳】。"
    T->>T: Bind context → patient=王芳 (unconditional)
    T->>D: reply + context switched
```

## Data Flow: Task Creation (ADR 0013 §5)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant CE as Commit Engine
    participant Co as Compose (template)
    participant T as Turn (context bind)

    D->>U: "张三3个月后复查"
    U->>R: {action_type: task, args: {patient_name: "张三", title: "3个月复查", scheduled_for: "2026-06-16T12:00"}}
    R->>R: _validate_task_dates → OK (not past, <1 year)
    R->>R: _resolve_patient_scoped → found 张三 (id=42)
    R->>CE: ResolvedAction{patient_id: 42}
    CE->>CE: task_type = "general" (always hardcoded)
    CE->>CE: Create DoctorTask row
    CE->>Co: CommitResult{title: "3个月复查", datetime_display: "6月16日"}
    Co->>T: "已为【张三】创建任务：3个月复查，时间：6月16日中午12点。"
    T->>T: Bind context → patient=张三 (unconditional)
    T->>D: reply + context switched
```

## Data Flow: Clarification (ambiguous patient)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant Co as Compose (template)

    D->>U: "帮张约个复诊"
    U->>R: {action_type: task, args: {patient_name: "张", title: "复诊"}}
    R->>R: _validate_task_dates → OK
    R->>R: DB lookup "张" → prefix match: 张三, 张三丰
    R->>Co: Clarification{kind: ambiguous_patient, options: [{name: "张三"}, {name: "张三丰"}]}
    Co->>D: "找到多位匹配的患者，请确认：1. 张三  2. 张三丰"
    Note over D: No context change (clarification, not resolved)
```

## Data Flow: Task Date Validation Failure (ADR 0013 §5)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant Co as Compose (template)

    D->>U: "张三去年3月复查"
    U->>R: {action_type: task, args: {patient_name: "张三", scheduled_for: "2025-03-16T12:00"}}
    R->>R: _validate_task_dates → FAIL (date in past)
    R->>Co: Clarification{kind: invalid_time, message_key: "clarify_invalid_time"}
    Co->>D: "时间无效：请检查日期和时间。请重新指定时间。"
    Note over D: No context change (clarification, not resolved)
```

## Patient Context Binding (ADR 0013 §2)

**Uniform rule: all patient-scoped actions bind context unconditionally.**

No `scoped_only` flag. No asymmetry between reads and writes.

```mermaid
flowchart LR
    A["Any action with<br/>resolved patient_id"] --> B["turn.py: unconditional bind"]
    B --> C["ctx.workflow.patient_id = resolved.patient_id<br/>ctx.workflow.patient_name = resolved.patient_name"]

    style A fill:#4a90d9,color:#fff
    style B fill:#333,color:#fff
    style C fill:#2ecc71,color:#fff
```

Replaces ADR 0012 §10 "binding asymmetry" (reads scope, writes switch).
In practice, `scoped_only` only affected `query_records` — `list_patients`
and `list_tasks` never resolved a patient_id, so the flag was irrelevant
for them (see ADR 0013 §2 note).

## Multi-Action Example (ADR 0013 §1)

```mermaid
sequenceDiagram
    participant D as Doctor
    participant U as Understand (LLM)
    participant R as Resolve
    participant CE as Commit Engine
    participant RE as Read Engine
    participant T as Turn

    D->>U: "李淑芳，血压135/85，3个月复查"
    U->>T: {actions: [{type: record, args: {patient_name: "李淑芳"}}, {type: task, args: {patient_name: "李淑芳", title: "3个月复查"}}]}

    Note over T: Action 1: record
    T->>R: resolve(record, {patient_name: "李淑芳"})
    R->>R: _ensure_patient → found/created
    R->>CE: ResolvedAction{patient_id: N}
    CE->>CE: Structure + save record
    CE->>T: CommitResult → "已为李淑芳保存病历..."

    Note over T: Action 2: task
    T->>R: resolve(task, {patient_name: "李淑芳"})
    R->>R: _validate_task_dates → OK
    R->>R: _resolve_patient_scoped → found
    R->>CE: ResolvedAction{patient_id: N}
    CE->>CE: Create DoctorTask (type=general)
    CE->>T: CommitResult → "已为李淑芳创建任务..."

    T->>T: Bind context → patient=李淑芳
    T->>D: combined reply
```
