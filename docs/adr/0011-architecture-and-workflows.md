# ADR 0011 — Architecture Overview and Key Workflows

This document is a companion to
[ADR 0011](0011-thread-centric-conversation-runtime-and-deterministic-commits.md).
It visualizes the MVP target architecture and traces the key workflows through
the runtime.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Channel Adapters                            │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                      │
│  │   Web     │   │  WeChat  │   │  Voice   │                      │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘                      │
│       │              │              │                              │
│       └──────────────┴──────────────┘                              │
│                      │                                             │
│            normalize input + message ID                            │
└──────────────────────┬─────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Conversation Runtime                             │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  1. De-dup check (message ID)                              │    │
│  │     duplicate? → return prior result                       │    │
│  └────────────────────────────┬───────────────────────────────┘    │
│                               │                                    │
│  ┌────────────────────────────▼───────────────────────────────┐    │
│  │  2. Load doctor_context                                    │    │
│  │     workflow: patient_id, pending_draft_id                 │    │
│  │     memory: candidate_patient, working_note, summary       │    │
│  └────────────────────────────┬───────────────────────────────┘    │
│                               │                                    │
│  ┌────────────────────────────▼───────────────────────────────┐    │
│  │  3. Draft Guard                                            │    │
│  │     pending_draft_id set + confirm? → commit, done         │    │
│  │     pending_draft_id set + abandon? → discard, done        │    │
│  │     pending_draft_id set + other? → re-prompt, done        │    │
│  └────────────────────────────┬───────────────────────────────┘    │
│                               │ (no pending draft)                 │
│  ┌────────────────────────────▼───────────────────────────────┐    │
│  │  4. Conversation Model (1 call per turn)                   │    │
│  │     input: doctor_context + recent chat_archive turns      │    │
│  │     output: {reply, memory_patch, action_request?}         │    │
│  └────────────────────────────┬───────────────────────────────┘    │
│                               │                                    │
│  ┌────────────────────────────▼───────────────────────────────┐    │
│  │  5. Commit Engine                                          │    │
│  │     validate action_request + patient binding              │    │
│  │     if create_draft → structuring step → pending_draft     │    │
│  │     execute: create patient / bind / create draft / etc.   │    │
│  └────────────────────────────┬───────────────────────────────┘    │
│                               │                                    │
│  ┌────────────────────────────▼───────────────────────────────┐    │
│  │  6. Persist                                                │    │
│  │     apply memory_patch → save doctor_context               │    │
│  │     append turns to chat_archive                           │    │
│  └────────────────────────────┬───────────────────────────────┘    │
│                               │                                    │
│                          return reply                               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       Durable Stores                               │
│                                                                    │
│  doctor_context     one mutable row per doctor (workflow + memory) │
│  chat_archive       append-only turn log (existing)                │
│  patients           committed artifact (existing)                  │
│  pending_drafts     committed artifact (existing)                  │
│  medical_records    committed artifact (existing)                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Context State (per doctor)

```
doctor_context
├── workflow (deterministic, code-owned)
│   ├── patient_id
│   ├── patient_name (display cache)
│   └── pending_draft_id
└── memory (provisional, LLM-facing)
    ├── candidate_patient
    ├── working_note
    └── summary
```

---

## Key Workflows

### 1. First-turn new patient with note (WeChat)

Doctor dictates a new patient case. No prior context exists.

```
Doctor (WeChat): "新建患者张三，男，45岁，主诉头痛三天"

  de-dup: new message ID → proceed
  load context: empty (no patient, no draft)
  draft guard: no pending_draft_id → pass through

  conversation model:
    input:  empty context + single turn
    output: {
      reply: "正在为张三建档并生成病历草稿...",
      memory_patch: {
        candidate_patient: {name: "张三", gender: "男", age: 45},
        working_note: "主诉头痛三天"
      },
      action_request: {type: "create_patient_and_draft", patient: {name: "张三", ...}}
    }

  commit engine:
    1. create patient "张三"
    2. set context patient_id + patient_name
    3. structuring step: raw turn → formatted note
    4. create pending draft → set pending_draft_id

  persist: save context, append turns to chat_archive

Doctor receives: "已为张三建档。病历草稿如下：
                  【主诉】头痛三天...
                  确认保存？"
```

### 2. Multi-turn note assembly with draft confirmation

Doctor provides clinical details across several turns before saving.

```
Turn 1: "说一下王芳的情况"
  draft guard: no pending draft → model
  model: {action: select_patient, patient_name: "王芳"}
  commit engine: look up 王芳 → set patient_id
  reply: "已选择患者王芳，请继续。"

Turn 2: "血压150/95，心率88"
  draft guard: no pending draft → model
  model: {memory_patch: {working_note: "BP 150/95, HR 88"}, action: none}
  reply: "已记录。还有其他内容吗？"

Turn 3: "开了氨氯地平5mg，每日一次"
  draft guard: no pending draft → model
  model: {memory_patch: {working_note: "BP 150/95, HR 88; 氨氯地平5mg qd"}, action: none}
  reply: "已记录处方。需要保存病历吗？"

Turn 4: "保存"
  draft guard: no pending draft → model
  model: {action: create_draft}
  commit engine:
    structuring step: raw turns from chat_archive → formatted note
    create pending draft → set pending_draft_id
  reply: "病历草稿：\n【...】\n确认保存？"

Turn 5: "确认"
  draft guard: pending_draft_id set, input = confirm → handle
    commit engine: confirm draft → medical_record
    clear pending_draft_id
  reply: "王芳的病历已保存。"
  (model not called)
```

### 3. Note first, patient name second

Doctor dictates clinical content without naming the patient. The model
handles clarification as a normal turn.

```
Turn 1: "记录一下，患者头晕两周，伴恶心呕吐"
  draft guard: no pending draft → model
  model: {
    action: clarify,
    reply: "请问这是哪位患者的记录？",
    memory_patch: {working_note: "头晕两周，伴恶心呕吐"}
  }
  commit engine: action is clarify → no durable write
  reply: "请问这是哪位患者的记录？"

Turn 2: "赵六"
  draft guard: no pending draft → model
  model: {action: select_patient, patient_name: "赵六"}
  commit engine: look up "赵六" → found → set patient_id
  reply: "已选择赵六。需要保存病历吗？"

Turn 3: "保存"
  draft guard: no pending draft → model
  model: {action: create_draft}
  commit engine:
    structuring step: raw turns (including turn 1 content) → formatted note
    create pending draft → set pending_draft_id
  reply: "病历草稿：\n【主诉】头晕两周，伴恶心呕吐...\n确认保存？"

Turn 4: "确认"
  draft guard: pending_draft_id set, input = confirm → handle
    confirm draft → medical_record
    clear pending_draft_id
  reply: "赵六的病历已保存。"
  (model not called)
```

### 4. Patient switch with warning

Doctor switches patients while working_note has content but no draft.

```
State: patient_id = 王芳, working_note = "BP 150/95, HR 88", no pending_draft_id

Doctor: "接下来看李明"
  draft guard: no pending draft → model
  model: {action: select_patient, patient_name: "李明"}
  commit engine:
    current patient is 王芳, working_note is non-empty
    → proceed with switch, clear context + memory
    → look up 李明 → set patient_id
  reply: "注意：关于王芳的未保存记录已清除。已切换到李明。"
```

### 5. Patient switch blocked by pending draft

Doctor tries to switch while a draft is awaiting confirmation.

```
State: patient_id = 王芳, pending_draft_id = draft_123

Doctor: "看一下李明"
  draft guard: pending_draft_id set, input is not confirm/abandon → re-prompt
  reply: "您有王芳的待确认草稿。请先确认保存或放弃草稿，然后再切换患者。"
  (model not called)
```

### 6. Duplicate delivery (WeChat retry)

```
Delivery 1: MsgId = "wx_msg_abc123"
  → de-dup check: not seen → full processing → reply stored

Delivery 2 (retry): MsgId = "wx_msg_abc123"
  → de-dup check: already processed → return prior reply
  → no model call, no side effects
```
