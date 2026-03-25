# Scenario Coverage Analysis

**Status:** Draft for review
**Date:** 2026-03-25
**Related:** [Unified Scenario Runner Design](unified-scenario-runner-design.md)

## Purpose

Map every testable pipeline, workflow, and edge case against existing scenarios.
Identify gaps. Propose new scenarios to fill them. Inform what the unified runner
infrastructure must support beyond extraction accuracy testing.

---

## System Pipelines (from prompts/README.md)

| # | Pipeline | Prompts Used | Entrypoints |
|---|----------|-------------|-------------|
| 1 | Doctor Chat (routing) | routing.md → intent handler | `POST /api/records/chat` |
| 2 | Doctor Interview | interview.md, doctor-extract.md | `POST /api/records/interview/turn`, `/confirm`, `/cancel`, `/session/{id}`, `/carry-forward-confirm` |
| 3 | Patient Interview | patient-interview.md, patient-extract.md | `POST /api/patient/interview/chat` |
| 4 | Patient Triage Chat | (triage module, no prompt file) | `POST /api/patient/chat` |
| 5 | Diagnosis | diagnosis.md | `POST /api/records/diagnosis` (UI button) |
| 6 | Vision OCR | vision-ocr.md | File upload in interview turn |
| 7 | Query (3 sub-types) | query.md | Routed from chat |
| 8 | General/Greeting | general.md | Routed from chat |

---

## Pipeline 1: Doctor Chat (Routing → Intent Handlers)

### 7 Intents (IntentType enum)

| Intent | Existing Scenarios | Count |
|--------|--------------------|-------|
| `create_record` | d1-d8, stemi, stroke, copd, depression, dermatology, orthopedics, gastro, nephrology, oncology, endocrine, neurology, general_medicine, ds_*, gm_*, direct_save_no_confirm, create_with_clinical_content | ~30 |
| `query_record` | cardiology_followup_query, stroke_clinic_query, oncology_note_query, cardiology_specialty_query | 4 |
| `query_task` | large_task_id | 1 |
| `create_task` | schedule_followup | 1 |
| `query_patient` | list_all_patients | 1 |
| `daily_summary` | — | **0** |
| `general` | greeting_no_action, help_request, repeated_greeting | 3 |

### Routing Edge Cases

| Scenario | Existing | Gap? |
|----------|----------|------|
| Numeric-only input ("12345") | numeric_only_input | — |
| Special chars ("（）") | special_chars_parens | — |
| Short ambiguous query ("查") | short_query_default | — |
| Greeting mixed with query | greeting_mixed_query | — |
| Empty string input | — | **GAP** |
| Very long input (>4000 chars) | — | **GAP** |
| Mixed intent ("查张三病历，顺便建个新患者李四") | — | **GAP** |
| Intent with no patient name ("建个病历") | noname_blocked_write | — |
| Non-Chinese input (English/gibberish) | — | **GAP** |

### Clarification / Error Handling

| Scenario | Existing | Gap? |
|----------|----------|------|
| Missing patient name → clarify | clarify_missing_name | — |
| Ambiguous patient (multiple matches) | clarify_ambiguous_patient | — |
| Ambiguous intent | clarify_ambiguous_intent | — |
| Query non-existent patient | query_nonexistent_patient | — |
| Correct record without prior record | correct_without_prior | — |

### Proposed New Scenarios — Doctor Chat

| ID | Title | Group | What It Tests |
|----|-------|-------|---------------|
| `empty_input` | 空消息 | edge_case | Empty string → should not crash, return helpful message |
| `long_input_paste` | 超长粘贴（>4000字） | edge_case | Very long input routed correctly, no truncation |
| `mixed_intent_two_patients` | 混合意图：查+建 | edge_case | "查张三的病历，再帮我建个李四" → handle one, clarify other |
| `daily_summary_request` | 今日小结 | daily_summary | "今天的工作小结" → daily_summary intent |
| `english_input` | 英文输入 | edge_case | "Create a record for patient Zhang" → handled or clarified |
| `query_task_empty` | 查询任务（无任务） | query_task | "我的任务" when no tasks exist → empty-state reply |
| `query_patient_partial_name` | 部分姓名查患者 | query_patient | "查一下姓张的" → fuzzy match or clarify |

---

## Pipeline 2: Doctor Interview (core extraction pipeline)

### Existing Coverage

| Category | Scenarios | Count |
|----------|----------|-------|
| Single-turn dictation | D1 (verbose), D2 (telegraphic) | 2 |
| Multi-turn dictation | D4 (3-turn) | 1 |
| OCR/paste input | D3 | 1 |
| Bilingual mix | D5 | 1 |
| Negation cluster | D6 | 1 |
| Copy-paste conflict | D7 | 1 |
| Template fill | D8 | 1 |
| Specialty-specific extraction | 15+ (stemi, stroke, nephrology, oncology, etc.) | ~15 |

### Session Lifecycle Gaps

| Workflow | Existing | Gap? | Priority |
|----------|----------|------|----------|
| Start → turns → confirm → record saved | Implicit in create_save | — | |
| Start → turns → cancel → status=abandoned | — | **GAP** | High |
| Start → 2 turns → sign out → sign in → resume → confirm | — | **GAP** | High |
| GET /session/{id} returns correct collected state | — | **GAP** | High |
| Confirm with only CC+PI (minimum viable) → status=pending_review | — | **GAP** | Medium |
| Confirm with all 14 fields → status=completed | — | **GAP** | Medium |
| Confirm with no collected data → 400 error | — | **GAP** | Medium |
| Confirm when patient_id is null → deferred patient creation | — | **GAP** | High |
| Confirm when session already confirmed → 400 error | — | **GAP** | Medium |

### Carry-Forward Gaps

| Workflow | Existing | Gap? |
|----------|----------|------|
| Returning patient: carry-forward offered on first turn | — | **GAP** |
| Doctor confirms carry-forward field → injected into collected | — | **GAP** |
| Doctor dismisses carry-forward field → not injected | — | **GAP** |
| New patient: no carry-forward offered | — | **GAP** |

### Interview Turn Edge Cases

| Scenario | Existing | Gap? |
|----------|----------|------|
| Same message sent twice (duplicate) | — | **GAP** |
| Empty turn text after first turn | — | **GAP** |
| Turn after session already confirmed | — | **GAP** |
| Very long single turn (>4000 chars) | — | **GAP** |
| Turn with only corrections ("把主诉改成...") | same_turn_correction | — |
| Turn with file upload (image) | — | **GAP** |
| Turn with file upload (PDF) | — | **GAP** |
| 5+ turns incrementally building record | — | **GAP** |
| Turn says "完了" or "就这些" (natural completion signal) | — | **GAP** |

### Auto-Task Generation at Confirm

| Scenario | Existing | Gap? |
|----------|----------|------|
| orders_followup has "1个月复查" → task created | — | **GAP** |
| No orders_followup → no tasks | — | **GAP** |
| treatment_plan has "每周复查" → task created | — | **GAP** |

### Proposed New Scenarios — Doctor Interview

| ID | Title | Group | What It Tests |
|----|-------|-------|---------------|
| `interview_cancel` | 取消问诊 | session_lifecycle | Start interview → cancel → status=abandoned, no record |
| `interview_resume` | 中断恢复 | session_lifecycle | 2 turns → GET session → resume → confirm |
| `interview_confirm_minimal` | 最小确认（仅CC+PI） | session_lifecycle | Confirm with only chief_complaint + present_illness → pending_review |
| `interview_confirm_complete` | 完整确认（14字段） | session_lifecycle | All fields filled → confirmed → status=completed |
| `interview_confirm_empty` | 空数据确认 | error_handling | Confirm with empty collected → 400 |
| `interview_confirm_double` | 重复确认 | error_handling | Confirm same session twice → 400 |
| `interview_deferred_patient` | 延迟创建患者 | session_lifecycle | No patient_id during turns → created at confirm |
| `interview_duplicate_message` | 重复消息 | edge_case | Same text sent twice → no double extraction |
| `interview_5_turn_incremental` | 5轮递增补充 | multi_turn | 5 turns each adding 2-3 fields → all merged correctly |
| `interview_natural_completion` | 自然结束信号 | edge_case | Doctor says "就这些了" → system recognizes completion |
| `carry_forward_confirm` | 带入历史-确认 | carry_forward | Returning patient → history field offered → confirmed |
| `carry_forward_dismiss` | 带入历史-拒绝 | carry_forward | Returning patient → history field offered → dismissed |
| `interview_file_upload_image` | 图片上传OCR | file_upload | Image upload → OCR → pre-populate fields |
| `interview_auto_task` | 确认后自动建任务 | task_generation | orders_followup → follow-up task auto-created |

---

## Pipeline 3: Patient Interview

### Existing Coverage

| Category | Scenarios | Count |
|----------|----------|-------|
| Full flow (register → interview → confirm) | simple_headache, abdominal_pain | 2 |
| Multi-field combined answer | combined_answers_multi_field | 1 |
| Negatives extraction | negatives_extraction | 1 |
| Session resume | resume_interrupted_interview | 1 |
| Cancel and restart | cancel_and_restart | 1 |
| Registration linking | registration_links_doctor_patient | 1 |
| Registration rejection | registration_rejects_mismatched_yob, wrong_yob_login_rejected | 2 |
| Confirm → record created | confirm_creates_record | 1 |
| History injection | history_injection_rare_allergy | 1 |

### Gaps

| Scenario | Gap? | Priority |
|----------|------|----------|
| Off-topic question mid-interview ("你是机器人吗？") | **GAP** | Medium |
| Patient says natural completion ("我说完了") | **GAP** | Medium |
| Very terse patient (one-word answers only) | **GAP** | Medium |
| Verbose patient (long paragraphs per answer) | **GAP** | Low |
| Patient self-contradicts ("没过敏" → "对青霉素过敏") | **GAP** | High |
| Patient provides self-diagnosis ("我查了可能是糖尿病") | **GAP** | Medium |
| Patient interview for minor (parent answering) | **GAP** | Low |
| Patient with no symptoms ("就是来体检的") | **GAP** | Medium |

### Proposed New Scenarios — Patient Interview

| ID | Title | Group | What It Tests |
|----|-------|-------|---------------|
| `patient_off_topic` | 患者离题问答 | edge_case | Off-topic question → answer + continue interview |
| `patient_natural_done` | 患者自然结束 | edge_case | "我说完了" → system moves to confirm |
| `patient_terse` | 极简回答患者 | input_style | Every answer is 1-3 words → still extracts correctly |
| `patient_self_contradict` | 患者自我矛盾 | edge_case | Contradicts earlier answer → later answer wins |
| `patient_self_diagnosis` | 患者自我诊断 | edge_case | "我觉得是XX" → goes to present_illness not diagnosis |
| `patient_checkup_only` | 体检患者 | edge_case | No symptoms, just routine → minimal but valid record |

---

## Pipeline 4: Patient Triage Chat

**Completely uncovered.** 0 scenarios.

| Scenario | Priority |
|----------|----------|
| Informational question ("吃完药多久能吃饭？") | High |
| Escalation to doctor ("我想跟医生说") | High |
| Urgent alert ("胸闷气短呼吸困难") | High |
| Follow-up on existing record | Medium |
| Generic greeting | Medium |

### Proposed New Scenarios — Patient Triage

| ID | Title | Group | What It Tests |
|----|-------|-------|---------------|
| `triage_informational` | 信息咨询 | triage | Question answered by AI, no escalation |
| `triage_escalation` | 转接医生 | triage | Patient wants doctor → message forwarded |
| `triage_urgent` | 紧急症状 | triage | Chest pain keywords → urgent alert to doctor |
| `triage_greeting` | 患者问候 | triage | "你好" → greeting + prompt for question |

---

## Pipeline 5: Diagnosis Generation

**Completely uncovered.** 0 scenarios.

| Scenario | Priority |
|----------|----------|
| Standard case → differentials + workup | High |
| Incomplete record → partial diagnosis | Medium |
| Emergency presentation → red flags highlighted | Medium |

### Proposed New Scenarios — Diagnosis

| ID | Title | Group | What It Tests |
|----|-------|-------|---------------|
| `diagnosis_standard` | 标准鉴别诊断 | diagnosis | Complete record → differentials + treatment + followup |
| `diagnosis_incomplete` | 不完整病历诊断 | diagnosis | Only CC+PI filled → partial diagnosis with caveats |
| `diagnosis_emergency` | 急诊红旗征 | diagnosis | STEMI presentation → red flags + urgent workup |

---

## Pipeline 6: Vision OCR

**0 dedicated scenarios.** D3 tests OCR paste but not the actual image upload flow.

| Scenario | Priority |
|----------|----------|
| Clinical photo → text extraction → field population | Medium |
| Lab report image → structured extraction | Medium |
| Blurry/low-quality image → graceful degradation | Low |
| PDF upload → text extraction | Medium |

---

## Cross-Pipeline Extraction Edge Cases

These apply to both doctor-extract.md and patient-extract.md.

| Edge Case | Existing | Gap? |
|-----------|----------|------|
| Drug brand→generic (波立维→氯吡格雷) | Partial in D1-D8 facts | Need explicit |
| All abbreviations (HTN, DM, CHD, PCI, etc.) | D5 partial | **Need comprehensive** |
| Numeric preservation (EF 45%, BP 130/80) | Implicit | **Need explicit assertion** |
| Time expressions (3天, 10年, 1月, qd, bid) | Implicit | **Need explicit assertion** |
| Negation splitting (无发热咳嗽咳痰 → 3 items) | D6 | — |
| CC ≤20 Chinese chars | NHC judges only | **Need deterministic check** |
| Empty transcript → extraction | — | **GAP** |
| All-negatives patient (everything is 否认/无) | — | **GAP** |
| Mixed units (mmHg, μmol/L, mg/dL) | Implicit | **Need explicit** |
| Duplicate information across turns → dedup | D7 partial | Need more |

---

## Cross-Cutting Concerns

| Concern | Existing Coverage | Gap? |
|---------|-------------------|------|
| Auth: invalid/expired token | wrong_yob_login_rejected (patient) | **GAP for doctor** |
| Rate limiting | — | **GAP** (unit test level) |
| LLM timeout (>60s response) | — | **GAP** (mock level) |
| LLM returns empty/malformed | — | **GAP** (mock level) |
| WeChat channel (same flows, different transport) | — | **GAP** |
| Idempotency (retry same request) | — | **GAP** |
| Concurrent sessions (same doctor, 2 patients) | — | **GAP** |

---

## Summary: Coverage Heatmap

| Pipeline | Scenarios | Extraction | Workflow | Edge Cases | Overall |
|----------|-----------|-----------|----------|------------|---------|
| Doctor Chat (routing) | 40+ | N/A | Partial | Partial | **70%** |
| Doctor Interview | 30+ | Strong | **Weak** | **Weak** | **50%** |
| Patient Interview | 11 | Moderate | Moderate | **Weak** | **55%** |
| Patient Triage | 0 | N/A | **None** | **None** | **0%** |
| Diagnosis | 0 | N/A | **None** | **None** | **0%** |
| Vision OCR | 0 | N/A | **None** | **None** | **0%** |

### Priority Tiers

**Tier 1 — Must have (blocks regression confidence):**
- Doctor interview session lifecycle (cancel, resume, confirm states)
- Deferred patient creation at confirm
- Carry-forward workflow
- Duplicate message handling
- Multi-turn incremental (5+ turns)

**Tier 2 — Should have (improves coverage significantly):**
- Patient triage (at least 3 basic scenarios)
- Diagnosis generation (1 standard case)
- Daily summary intent
- Auto-task generation at confirm
- Patient self-contradiction

**Tier 3 — Nice to have (completeness):**
- Vision OCR dedicated tests
- WeChat channel parity
- Rate limiting / auth edge cases
- LLM failure modes (mock-level tests, not E2E)

---

## Impact on Unified Runner Infrastructure

The current runner design (unified-scenario-runner-design.md) supports:
- `doctor_extraction` scenario_type only
- Fact-based assertions + generic matchers
- Single entrypoint: interview turn + confirm

To support the full coverage above, the runner needs:

### 1. Additional scenario_types

```
scenario_type: "doctor_extraction"    — existing (turn → confirm → check facts)
scenario_type: "doctor_workflow"      — session lifecycle tests (cancel, resume, carry-forward)
scenario_type: "doctor_chat"          — routing + intent handler tests
scenario_type: "patient_interview"    — patient interview flow
scenario_type: "patient_triage"       — triage classification tests
scenario_type: "diagnosis"            — diagnosis generation tests
```

### 2. Workflow assertions (beyond extraction)

```json
"assertions": [
  {"target": "session.status", "matcher": "eq", "expected": "abandoned"},
  {"target": "response.status_code", "matcher": "eq", "expected": 400},
  {"target": "response.reply", "matcher": "not_empty"},
  {"target": "response.reply", "matcher": "contains", "expected": "姓名"},
  {"target": "db.doctor_tasks.count", "matcher": "eq", "expected": 1},
  {"target": "carry_forward.offered_fields", "matcher": "contains_any", "expected": ["past_history"]},
  {"target": "session.collected.chief_complaint", "matcher": "not_empty"}
]
```

### 3. Multi-step execution

Some scenarios require multiple API calls with state checks between steps:

```json
"execution": {
  "steps": [
    {"action": "interview_turn", "text": "..."},
    {"action": "interview_turn", "text": "..."},
    {"action": "assert", "target": "session.status", "expected": "interviewing"},
    {"action": "interview_cancel"},
    {"action": "assert", "target": "session.status", "expected": "abandoned"},
    {"action": "assert", "target": "db.medical_records.count", "expected": 0}
  ]
}
```

### 4. Setup/teardown for stateful tests

Returning-patient and query scenarios need pre-existing data:

```json
"setup": {
  "patients": [{"name": "张三", "gender": "男", "age": 55}],
  "records": [{"patient_name": "张三", "chief_complaint": "头痛3天", "past_history": "高血压10年"}]
}
```
