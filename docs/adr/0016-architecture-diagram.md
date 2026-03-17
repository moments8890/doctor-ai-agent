# ADR 0016: Architecture Diagram

Companion diagram for
[ADR 0016](./0016-patient-pre-consultation-interview.md).

## System Overview: Two Pipelines

```mermaid
flowchart TD
    subgraph shared["Shared Infrastructure"]
        llm["LLM Providers<br/>(Ollama, DeepSeek, OpenAI, Claude)"]
        db["DB Models<br/>(Patient, MedicalRecord, DoctorTask)"]
        notify["Notification System<br/>(Web badge, WeChat push)"]
        prompt["Prompt Loader"]
        schema["Medical Record Schema<br/>(14-field OutpatientRecord)"]
    end

    subgraph doctor_pipeline["UEC Pipeline (Doctor-Side)"]
        understand["Understand"]
        resolve["Resolve"]
        read_engine["Read Engine"]
        commit_engine["Commit Engine"]
        compose["Compose"]
    end

    subgraph patient_pipeline["Interview Pipeline (Patient-Side)"]
        session_mgr["Session Manager"]
        interview_llm["Interview LLM"]
        field_extract["Field Extractor"]
        completeness["Completeness Check"]
    end

    doctor_ui["Doctor UI / WeChat"]
    patient_ui["Patient Web UI"]

    doctor_ui --> understand
    understand --> resolve
    resolve --> read_engine
    resolve --> commit_engine
    read_engine --> compose
    commit_engine --> compose
    compose --> doctor_ui

    patient_ui --> session_mgr
    session_mgr --> interview_llm
    interview_llm --> field_extract
    field_extract --> completeness
    completeness --> patient_ui

    %% Shared infra connections
    interview_llm -.-> llm
    understand -.-> llm
    compose -.-> llm
    commit_engine -.-> db
    session_mgr -.-> db
    completeness -.->|"on confirm"| db
    completeness -.->|"create task"| notify

    %% Handoff
    completeness ==>|"MedicalRecord +<br/>DoctorTask"| commit_engine

    style shared fill:#f5f5f5,stroke:#ccc
    style doctor_pipeline fill:#e3f2fd,stroke:#4a90d9
    style patient_pipeline fill:#fce4ec,stroke:#e74c3c
    style doctor_ui fill:#4a90d9,color:#fff
    style patient_ui fill:#e74c3c,color:#fff
```

## Patient Entry & Auth Flow

```mermaid
flowchart TD
    visit["/patient"]
    visit --> has_token{"Has JWT<br/>token?"}

    has_token -->|yes| validate["Validate token"]
    validate -->|valid| multi{"Linked to<br/>multiple<br/>doctors?"}
    validate -->|expired| login

    has_token -->|no| login["Login / Register"]

    login --> choice{"First time?"}
    choice -->|returning| auth["Phone + Year of Birth"]
    choice -->|new| register["Select Doctor →<br/>Registration Form<br/>(name, gender, YOB, phone)"]

    register --> link{"Patient record<br/>exists for this<br/>doctor + name?"}
    link -->|yes| validate_fields["Validate non-null fields<br/>(gender, YOB, phone)"]
    validate_fields -->|match| backfill["Backfill nulls → Issue JWT"]
    validate_fields -->|mismatch| reject["信息与已有记录不符<br/>请联系医生确认"]
    link -->|no| create["Create patient → Issue JWT"]

    auth --> lookup["WHERE doctor_id=?<br/>AND phone=?<br/>AND year_of_birth=?"]
    lookup -->|found| multi
    lookup -->|not found| register

    multi -->|one doctor| home["Patient Home"]
    multi -->|multiple| picker["Doctor Picker"] --> home

    backfill --> home
    create --> home

    style visit fill:#e74c3c,color:#fff
    style home fill:#2ecc71,color:#fff
    style reject fill:#e74c3c,color:#fff
```

## Patient Home Page

```mermaid
flowchart TD
    home["Patient Home — 王芳"]

    home --> interview_btn["📋 开始预问诊"]
    home --> records_btn["📄 我的病历 (3条)"]
    home --> message_btn["💬 给医生留言"]
    home --> upload_btn["📎 上传资料<br/>(deferred v1.1)"]

    interview_btn --> has_active{"Active session<br/>exists?"}
    has_active -->|yes| resume["Resume interview"]
    has_active -->|no| start["POST /interview/start<br/>→ new session"]

    records_btn --> records["GET /patient/records"]
    message_btn --> messages["POST /patient/message"]

    resume --> chat["Interview Chat UI"]
    start --> chat

    style home fill:#2ecc71,color:#fff
    style chat fill:#f39c12,color:#fff
    style upload_btn fill:#ccc,color:#666
```

## Interview Turn Flow

```mermaid
flowchart TD
    input["Patient sends message"]
    input --> validate{"Session valid?<br/>(not abandoned,<br/>not confirmed)"}
    validate -->|no| error["Error: session closed"]

    validate -->|yes| append["Append to conversation<br/>turn_count += 1"]

    append --> turn_limit{"turn_count<br/>≥ MAX_TURNS?"}
    turn_limit -->|yes| force_review["Force transition<br/>to reviewing"]

    turn_limit -->|no| emergency{"Emergency<br/>keywords?"}
    emergency -->|yes| warn["⚠️ 建议拨打120<br/>(continue allowed)"]

    emergency -->|no| llm_call["Call Interview LLM<br/>(full context +<br/>collected + missing)"]

    llm_call --> parse{"JSON parse<br/>OK?"}
    parse -->|no| fallback["抱歉，请再说一次"]

    parse -->|yes| merge["Merge extracted<br/>fields into collected"]

    merge --> complete{"Completeness<br/>check"}

    complete -->|"missing fields"| reply["Return LLM reply<br/>status: interviewing"]
    complete -->|"all filled"| review["Generate summary<br/>status: reviewing"]

    force_review --> response["InterviewResponse<br/>{reply, collected,<br/>progress, status}"]
    warn --> response
    fallback --> response
    reply --> response
    review --> response

    response --> save["Save session to DB"]
    save --> patient_ui["→ Patient UI"]

    style input fill:#e74c3c,color:#fff
    style llm_call fill:#4a90d9,color:#fff
    style review fill:#2ecc71,color:#fff
    style force_review fill:#f39c12,color:#fff
    style warn fill:#f39c12,color:#fff
    style error fill:#999,color:#fff
```

## Field Extraction & Merge

```mermaid
graph LR
    subgraph "LLM Output"
        extracted["extracted: {<br/>chief_complaint: '头痛3天',<br/>present_illness: '持续性，伴恶心'<br/>}"]
    end

    subgraph "Merge Strategy"
        overwrite["Overwrite<br/>(chief_complaint)"]
        append["Append with ；<br/>(present_illness,<br/>past_history,<br/>allergy_history,<br/>family_history,<br/>personal_history,<br/>marital_reproductive)"]
    end

    subgraph "Collected (after merge)"
        result["collected: {<br/>chief_complaint: '头痛3天',<br/>present_illness: '持续性头痛；伴恶心'<br/>}"]
    end

    extracted --> overwrite --> result
    extracted --> append --> result

    style extracted fill:#4a90d9,color:#fff
    style overwrite fill:#e74c3c,color:#fff
    style append fill:#2ecc71,color:#fff
    style result fill:#f39c12,color:#fff
```

## Completeness Check

```mermaid
flowchart TD
    check["check_completeness(collected)"]

    check --> req{"Required filled?<br/>chief_complaint<br/>present_illness"}
    req -->|no| missing_req["Return missing<br/>required fields"]

    req -->|yes| ask{"Ask-at-least filled?<br/>past_history<br/>allergy_history<br/>family_history<br/>personal_history"}

    ask -->|"any not in collected"| missing_ask["Return missing<br/>ask-at-least fields"]
    ask -->|"all present<br/>(incl. '无'/'不详')"| done["Return []<br/>→ transition to reviewing"]

    style check fill:#4a90d9,color:#fff
    style done fill:#2ecc71,color:#fff
    style missing_req fill:#e74c3c,color:#fff
    style missing_ask fill:#f39c12,color:#fff
```

## Handoff: Patient Confirm → Doctor Task

```mermaid
sequenceDiagram
    participant P as Patient
    participant I as Interview Pipeline
    participant DB as Database
    participant N as Notification
    participant D as Doctor

    P->>I: POST /interview/confirm

    I->>I: Generate prose content<br/>from collected fields
    I->>I: Build structured dict<br/>(14-field schema)
    I->>I: Extract tags from<br/>chief_complaint + present_illness

    I->>DB: INSERT medical_records<br/>(record_type="interview_summary",<br/>needs_review=true)
    DB-->>I: record_id

    I->>DB: INSERT doctor_tasks<br/>(task_type="general",<br/>title="审阅预问诊：王芳",<br/>record_id=record_id)

    I->>DB: UPDATE interview_sessions<br/>status → "confirmed"

    I->>N: Notify doctor<br/>(web badge + WeChat)

    I->>P: "已提交给张医生，<br/>请等待医生审阅"

    Note over D: Doctor opens task list
    D->>DB: Query task → get record_id
    D->>DB: Query medical_records<br/>WHERE id = record_id

    Note over D: Reviews structured record<br/>via normal UEC pipeline

    D->>DB: UPDATE (add diagnosis,<br/>treatment plan, etc.)
    D->>DB: Mark task complete
```

## Interview Chat UI Layout

```mermaid
flowchart TD
    subgraph topbar["Top Bar"]
        exit["← 退出"]
        title["预问诊 — 张医生"]
        badge["摘要 3/7"]
    end

    subgraph chat["Chat Area (scrollable)"]
        ai1["🤖 您好！请问您有什么不舒服？"]
        user1["👤 我头痛3天了"]
        ai2["🤖 头痛是持续性的还是间歇性的？"]
        user2["👤 持续的，还有点恶心"]
        ai3["🤖 以前有过类似的头痛吗？"]
    end

    subgraph input_bar["Input Bar"]
        textbox["输入框..."]
        send["发送"]
    end

    subgraph summary_sheet["Summary Sheet (overlay on badge tap)"]
        s1["✅ 主诉：头痛3天"]
        s2["🔄 现病史：收集中..."]
        s3["⬜ 既往史"]
        s4["⬜ 过敏史"]
        s5["⬜ 个人史"]
        s6["⬜ 家族史"]
        s7["⬜ 婚育史"]
        confirm["[确认提交] (disabled)"]
    end

    badge -.->|tap| summary_sheet

    style topbar fill:#f5f5f5,stroke:#ccc
    style chat fill:#fff,stroke:#ccc
    style input_bar fill:#f5f5f5,stroke:#ccc
    style summary_sheet fill:#fff,stroke:#f39c12
    style ai1 fill:#e3f2fd,stroke:#4a90d9
    style ai2 fill:#e3f2fd,stroke:#4a90d9
    style ai3 fill:#e3f2fd,stroke:#4a90d9
    style user1 fill:#dcf8c6,stroke:#2ecc71
    style user2 fill:#dcf8c6,stroke:#2ecc71
    style confirm fill:#ccc,color:#666
```

## Exit Behavior

```mermaid
flowchart TD
    exit["Patient taps ← 退出"]
    exit --> dialog["Confirm Dialog"]

    dialog --> save["保存退出"]
    dialog --> abandon["放弃重来"]

    save --> keep["Session stays<br/>status: interviewing"]
    keep --> home["→ Patient Home<br/>(resume next visit)"]

    abandon --> mark["Session →<br/>status: abandoned"]
    mark --> home2["→ Patient Home<br/>(next start = fresh)"]

    style exit fill:#e74c3c,color:#fff
    style save fill:#2ecc71,color:#fff
    style abandon fill:#f39c12,color:#fff
```

## End-to-End Data Flow

```mermaid
sequenceDiagram
    participant P as Patient
    participant Web as Patient Web UI
    participant Auth as Auth API
    participant Int as Interview Pipeline
    participant LLM as Interview LLM
    participant DB as Database
    participant Task as Task System
    participant Doc as Doctor

    Note over P,Doc: Phase 1: Registration

    P->>Web: Visit /patient
    Web->>Auth: GET /doctors (accepting=true)
    Auth-->>Web: [张医生-神经外科, 李医生-神经内科]
    P->>Web: Select 张医生
    P->>Auth: POST /register (name, gender, YOB, phone)
    Auth->>DB: Create/link patient
    Auth-->>Web: JWT token
    Web-->>P: Patient Home

    Note over P,Doc: Phase 2: Interview

    P->>Web: Tap "开始预问诊"
    Web->>Int: POST /interview/start
    Int->>DB: Create interview_session
    Int-->>Web: {session_id, greeting}
    Web-->>P: "您好！请问您有什么不舒服？"

    loop Each turn (up to 30)
        P->>Web: Type message
        Web->>Int: POST /interview/turn
        Int->>LLM: System prompt + conversation + collected + missing
        LLM-->>Int: {reply, extracted}
        Int->>Int: merge_extracted()
        Int->>Int: check_completeness()
        Int->>DB: Save session
        Int-->>Web: {reply, collected, progress, status}
        Web-->>P: AI reply + updated summary
    end

    Note over P,Doc: Phase 3: Confirm & Handoff

    Web-->>P: "请查看摘要确认" (status: reviewing)
    P->>Web: Tap "确认提交"
    Web->>Int: POST /interview/confirm
    Int->>Int: Generate content + structured + tags
    Int->>DB: INSERT medical_records (interview_summary)
    Int->>DB: INSERT doctor_tasks (审阅预问诊：王芳)
    Int->>Task: Notify doctor
    Int->>DB: Session → confirmed
    Int-->>Web: "已提交给张医生"
    Web-->>P: Confirmation + record in "我的病历"

    Note over P,Doc: Phase 4: Doctor Review

    Task-->>Doc: 🔴 新任务：审阅预问诊：王芳
    Doc->>DB: Open record (via UEC query)
    Doc->>Doc: Review, edit, add diagnosis
    Doc->>DB: Update record (via UEC update)
    Doc->>DB: Mark task complete
```
