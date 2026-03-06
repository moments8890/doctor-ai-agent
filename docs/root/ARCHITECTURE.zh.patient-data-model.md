# 当前患者病历数据模型（中文副本）

本节对应 `ARCHITECTURE.md` 中的 **Current Patient Record Data Model (Canonical)**，用于中文阅读，不替换英文主文档。

## 当前患者病历数据模型（权威版）

本节基于当前线上代码行为整理，来源如下：
- `db/models.py`
- `db/crud.py`
- `routers/records.py`
- `routers/neuro.py`

### 实体关系（按医生隔离）

```text
doctor_id（逻辑租户键）
   ├─ patients（按 doctor_id 1:N）
   │    └─ medical_records（通过 patient_id 1:N，允许为空）
   ├─ medical_records（也可按 doctor_id 直接查询）
   ├─ neuro_cases（按 doctor_id 直接查询；可选关联 patient_id）
   └─ doctor_contexts（按 doctor_id 1:1）
```

### 表结构与字段

`patients`
- `id`（主键，自增）
- `doctor_id`（索引，必填）
- `name`（必填）
- `gender`（可空）
- `age`（可空）
- `created_at`（UTC 时间戳）

`medical_records`
- `id`（主键，自增）
- `patient_id`（外键 -> `patients.id`，可空）
- `doctor_id`（索引，必填）
- `chief_complaint`（数据库层可空；但 Pydantic 入参模型要求必填）
- `history_of_present_illness`（可空）
- `past_medical_history`（可空）
- `physical_examination`（可空）
- `auxiliary_examinations`（可空）
- `diagnosis`（可空）
- `treatment_plan`（可空）
- `follow_up_plan`（可空）
- `created_at`（UTC 时间戳）

`neuro_cases`
- `id`（主键，自增）
- `doctor_id`（索引，必填）
- `patient_id`（外键 -> `patients.id`，可空）
- 提升后的可检索标量字段：
  - `patient_name`（可空）
  - `gender`（可空）
  - `age`（可空）
  - `encounter_type`（可空）
  - `chief_complaint`（可空）
  - `primary_diagnosis`（可空）
  - `nihss`（可空）
- 完整载荷字段：
  - `raw_json`（可空，存储完整结构化病例 JSON）
  - `extraction_log_json`（可空，存储抽取日志 JSON）
- `created_at`（UTC 时间戳）

`doctor_contexts`
- `doctor_id`（主键）
- `summary`（可空）
- `updated_at`（UTC 时间戳）

`system_prompts`
- `key`（主键）
- `content`（必填）
- `updated_at`（UTC 时间戳）

### 运行时写入路径

`POST /api/records/chat`
- `create_patient` 意图：写入 `patients`。
- `add_record` 意图：
  - 先用 (`doctor_id`, `name`) 查找患者；
  - 若不存在则自动新建患者；
  - 再写入 `medical_records`，并带上解析出的 `patient_id`。

`POST /api/records/from-text|from-image|from-audio`
- 仅返回结构化 `MedicalRecord`，当前路由本身不落库。

`POST /api/neuro/from-text`
- 抽取 `NeuroCase` + `ExtractionLog`；
- 写入 `neuro_cases`（当前实现不关联 `patient_id`）。

内存与提示词写入
- `services/memory.py` 更新 `doctor_contexts`。
- 管理后台/UI 的提示词编辑会更新 `system_prompts`。

### 约束与行为说明

- 多租户边界由 `doctor_id` 保障（CRUD 读写均按该字段做逻辑隔离）。
- `medical_records.patient_id` 可空，因此允许存在未关联患者的病历。
- `patients` 当前没有 (`doctor_id`, `name`) 唯一约束，同名重复患者理论上可出现。
- `medical_records.chief_complaint` 在数据库层可空（兼容性考虑），但抽取模型侧期望有值。
- `neuro_cases` 同时保存“可检索标量字段 + 完整 JSON”，用于查询与审计/回放。
