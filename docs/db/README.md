# 数据库表设计文档

> 最后更新：2026-03-08
> 共 25 张表，分为 9 个必要表（MVP 核心）、14 个实用表（上线后增量）、2 个暂缓表。

---

## 目录

1. [核心流程依赖链](#核心流程依赖链)
2. [必要表（MVP 核心）](#必要表mvp-核心)
3. [实用表（上线后增量）](#实用表上线后增量)
4. [暂缓表](#暂缓表)
5. [各表详情](#各表详情)

---

## 核心流程依赖链

```
医生语音/文字
    ↓
PendingMessage（消息入库，防丢失）
    ↓
SystemPrompt（调取 LLM 提示词）
    ↓
PendingRecord（AI 草稿，等待医生确认）
    ↓
DoctorSessionState（记录 pending_record_id，跨实例恢复）
    ↓
医生回复"确认"
    ↓
MedicalRecordDB（正式入库）
    ↓
Patient（患者分类/风险字段更新）
    ↓
DoctorTask（可选：自动生成随访提醒）
```

---

## 必要表（MVP 核心）

共 9 张，缺少任何一张核心流程无法运转。

| 表名 | 说明 |
|---|---|
| `doctors` | 医生身份注册表 |
| `invite_codes` | 邀请码登录门控 |
| `patients` | 患者注册表 |
| `medical_records` | 确认后的正式病历 |
| `pending_records` | AI 草稿确认门控（10 分钟 TTL）|
| `pending_messages` | 微信消息持久化收件箱 |
| `doctor_session_states` | 会话状态持久化（跨实例恢复）|
| `system_prompts` | LLM 提示词（支持热更新）|
| `scheduler_leases` | 分布式定时任务锁 |

---

## 实用表（上线后增量）

共 14 张，已有完整代码，非阻塞性功能，MVP 上线后按优先级开启。

| 表名 | 说明 | 优先级 |
|---|---|---|
| `patient_labels` | 医生自定义患者标签 | 高 |
| `patient_label_assignments` | 患者-标签多对多关联 | 高 |
| `doctor_tasks` | 随访提醒 / 紧急任务 | 高 |
| `audit_log` | 敏感操作审计日志（合规）| 高 |
| `doctor_contexts` | 会话压缩摘要（跨重启恢复上下文）| 中 |
| `doctor_conversation_turns` | 历史对话轮次持久化 | 中 |
| `system_prompt_versions` | 提示词版本历史（支持回滚）| 中 |
| `runtime_config` | 热更新 JSON 配置 | 中 |
| `medical_record_versions` | 病历修改记录（编辑审计）| 中 |
| `medical_record_exports` | PDF 导出日志 | 低 |
| `neuro_cases` | 神经专科结构化病例 | 低 |
| `neuro_cvd_context` | 神经外科脑血管手术上下文 | 低 |
| `specialty_scores` | 临床量表评分（NIHSS/mRS 等）| 低 |
| `runtime_cursors` | WeCom KF 消息同步游标 | 低 |
| `doctor_knowledge_items` | 医生专属知识库条目 | 低 |

---

## 暂缓表

共 2 张，模型已定义但生产路径无实际读写，暂不启用。

| 表名 | 说明 | 暂缓原因 |
|---|---|---|
| `doctor_notify_preferences` | 医生个性化通知调度配置 | MVP 使用固定调度间隔，无需每医生单独配置 |
| `runtime_tokens` | 通用 Token 缓存 | Token 目前从环境变量读取，未走数据库 |

---

## 各表详情

### doctors

**文件**：`db/models/doctor.py`
**用途**：医生身份注册表，是整个系统的认证根节点。每位医生首次消息到达时自动创建，或由管理员通过邀请码注册。

| 字段 | 类型 | 说明 |
|---|---|---|
| doctor_id | String(64) PK | 规范化 ID（微信 openid 或邮箱）|
| name | String(128) | 医生姓名 |
| specialty | String(64) | 专科（可选）|
| channel | String(32) | 渠道：app / wechat / wechat_mini |
| wechat_user_id | String(128) | 微信 openid |
| mini_openid | String(128) | 小程序 openid |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**索引**：`(channel, wechat_user_id)` 唯一，`mini_openid` 唯一
**MVP 级别**：必要

---

### invite_codes

**文件**：`db/models/doctor.py`
**用途**：管理员预置的邀请码，医生凭码登录 Web 端。支持自定义格式（4-32 位字母数字下划线连字符）。

| 字段 | 类型 | 说明 |
|---|---|---|
| code | String(32) PK | 邀请码 |
| doctor_id | String(64) | 关联医生 ID |
| doctor_name | String(128) | 医生姓名（显示用）|
| active | Integer | 是否有效（1/0）|
| created_at | DateTime | 创建时间 |

**MVP 级别**：必要

---

### patients

**文件**：`db/models/patient.py`
**用途**：患者注册表。与医生绑定，支持风险分级和病历分类的自动计算字段。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| name | String(128) | 患者姓名 |
| gender | String(8) | 性别 |
| year_of_birth | Integer | 出生年份 |
| primary_category | String(64) | 主分类（AI 计算）|
| category_tags | Text (JSON) | 分类标签列表 |
| primary_risk_level | String(16) | 风险等级：low/medium/high |
| risk_tags | Text (JSON) | 风险标签列表 |
| risk_score | Float | 风险评分 |
| follow_up_state | String(32) | 随访状态 |
| created_at | DateTime | 创建时间 |

**MVP 级别**：必要

---

### medical_records

**文件**：`db/models/records.py`
**用途**：医生确认后的正式病历表。AI 结构化草稿经医生确认后写入此表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| patient_id | Integer FK | 关联患者 |
| doctor_id | String(64) FK | 所属医生 |
| record_type | String(32) | 病历类型（门诊/住院/随访等）|
| content | Text | 病历内容（JSON）|
| tags | Text (JSON) | 标签列表 |
| source_message_id | String(64) | 来源消息 ID |
| encounter_type | String(32) | 就诊类型 |
| is_signed_off | Boolean | 是否已签核 |
| signed_off_at | DateTime | 签核时间 |
| doctor_signature | String(256) | 医生签名 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：必要

---

### pending_records

**文件**：`db/models/pending.py`
**用途**：AI 草稿确认门控。LLM 结构化后先存入此表，医生回复"确认"后才正式写入 `medical_records`，有效期 10 分钟。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(64) PK | UUID hex |
| doctor_id | String(64) FK | 所属医生 |
| patient_id | Integer FK | 关联患者（可选）|
| patient_name | String(128) | 患者姓名（冗余，用于无 ID 场景）|
| draft_json | Text | AI 草稿 JSON |
| raw_input | Text | 原始语音/文字输入 |
| status | String(32) | awaiting / confirmed / abandoned / expired |
| created_at | DateTime | 创建时间 |
| expires_at | DateTime | 过期时间（创建后 10 分钟）|

**索引**：`(doctor_id, status)`，`expires_at`
**MVP 级别**：必要

---

### pending_messages

**文件**：`db/models/pending.py`
**用途**：微信消息持久化收件箱。每条消息在派发后台任务前先入库，处理完成后标记 done，启动时恢复超时未处理的消息（60 秒阈值），防止因微信 5 秒超时导致丢消息。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(64) PK | UUID |
| doctor_id | String(64) FK | 所属医生 |
| raw_content | Text | 原始消息内容 |
| msg_type | String(16) | text / voice / image |
| status | String(16) | pending / done / failed |
| error | Text | 错误信息（可选）|
| created_at | DateTime | 创建时间 |
| processed_at | DateTime | 处理完成时间 |

**索引**：`(status, created_at)`，`doctor_id`
**MVP 级别**：必要

---

### doctor_session_states

**文件**：`db/models/doctor.py`
**用途**：医生会话状态持久化。记录当前患者、待确认记录 ID 等轻量状态，重启或多实例切换时可恢复。

| 字段 | 类型 | 说明 |
|---|---|---|
| doctor_id | String(64) PK | 医生 ID |
| current_patient_id | Integer FK | 当前操作患者 |
| pending_create_name | String(128) | 待创建患者姓名 |
| pending_record_id | String(64) | 待确认草稿 ID |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：必要

---

### system_prompts

**文件**：`db/models/system.py`
**用途**：LLM 提示词存储，支持管理员从 Admin UI 热更新，无需重启服务。

| 字段 | 类型 | 说明 |
|---|---|---|
| key | String(64) PK | 提示词键（structuring / agent_routing 等）|
| content | Text | 提示词正文 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：必要

---

### scheduler_leases

**文件**：`db/models/runtime.py`
**用途**：分布式定时任务互斥锁。多实例部署时防止重复执行定时任务（如过期草稿清理、任务通知）。

| 字段 | 类型 | 说明 |
|---|---|---|
| lease_key | String(64) PK | 任务键 |
| owner_id | String(64) | 持锁实例 ID |
| lease_until | DateTime | 锁超时时间 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：必要

---

### patient_labels

**文件**：`db/models/patient.py`
**用途**：医生自定义患者标签（如"脑卒中高危""术后随访"），每位医生独立管理。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| name | String(64) | 标签名称 |
| color | String(16) | 颜色（十六进制）|
| created_at | DateTime | 创建时间 |

**MVP 级别**：实用

---

### patient_label_assignments

**文件**：`db/models/patient.py`
**用途**：患者与标签的多对多关联表。

| 字段 | 类型 | 说明 |
|---|---|---|
| patient_id | Integer FK | 患者 ID（联合主键）|
| label_id | Integer FK | 标签 ID（联合主键）|

**MVP 级别**：实用

---

### medical_record_versions

**文件**：`db/models/records.py`
**用途**：病历修改审计日志。每次病历内容/类型/标签变更时追加一条旧值快照，支持回溯与合规审查。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| record_id | Integer FK | 关联病历 |
| doctor_id | String(64) FK | 操作医生 |
| old_content | Text | 修改前内容 |
| old_tags | Text (JSON) | 修改前标签 |
| old_record_type | String(32) | 修改前类型 |
| changed_at | DateTime | 修改时间 |

**MVP 级别**：实用

---

### medical_record_exports

**文件**：`db/models/records.py`
**用途**：PDF 导出审计日志。记录导出时间、格式和文件哈希，防篡改追溯。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| record_id | Integer FK | 关联病历 |
| doctor_id | String(64) FK | 导出医生 |
| export_format | String(16) | pdf / docx |
| exported_at | DateTime | 导出时间 |
| pdf_hash | String(64) | 文件 SHA256 |
| created_at | DateTime | 记录创建时间 |

**MVP 级别**：实用

---

### neuro_cases

**文件**：`db/models/records.py`
**用途**：神经专科结构化病例，存储 LLM 从文字中提取的 NeuroCase 结构（含患者信息、影像、诊断、治疗方案等）及提取日志。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| patient_id | Integer FK | 关联患者 |
| patient_name | String(128) | 患者姓名（冗余）|
| nihss | Integer | NIHSS 评分（提升字段，便于查询）|
| raw_json | Text | 完整 NeuroCase JSON |
| extraction_log_json | Text | 提取日志 JSON |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：实用

---

### neuro_cvd_context

**文件**：`db/models/specialty.py`
**用途**：神经外科脑血管疾病专科上下文。每条病历对应一行，存储 ICH 评分、Hunt-Hess 分级、Fisher 分级、Spetzler-Martin 分级、动脉瘤信息、手术方案、功能预后（mRS/Barthel）等结构化字段。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| record_id | Integer FK | 关联病历 |
| patient_id | Integer FK | 关联患者 |
| doctor_id | String(64) FK | 所属医生 |
| diagnosis_subtype | String(32) | ICH/SAH/缺血性/AVM/动脉瘤/其他 |
| hemorrhage_location | String(64) | 出血部位 |
| ich_score | Integer | ICH 评分（0-6）|
| ich_volume_ml | Float | 出血量（ml）|
| hunt_hess_grade | Integer | Hunt-Hess 分级（1-5）|
| fisher_grade | Integer | Fisher 分级（1-4）|
| spetzler_martin_grade | Integer | Spetzler-Martin 分级（1-5）|
| gcs_score | Integer | GCS 评分（3-15）|
| aneurysm_location | String(64) | 动脉瘤位置 |
| aneurysm_size_mm | Float | 动脉瘤大小（mm）|
| aneurysm_morphology | String(32) | 囊状/梭形/其他 |
| aneurysm_treatment | String(32) | 夹闭/弹簧圈/Pipeline/保守 |
| surgery_type | String(64) | 手术类型 |
| surgery_date | String(16) | 手术日期（YYYY-MM-DD）|
| surgery_status | String(16) | planned/done/cancelled/conservative |
| surgical_approach | String(64) | 手术入路 |
| mrs_score | Integer | mRS 评分（0-6）|
| barthel_index | Integer | Barthel 指数（0-100）|
| source | String(16) | 来源：chat/voice/import |
| created_at | DateTime | 创建时间 |

**索引**：`(doctor_id, patient_id)`，`(patient_id, created_at)`
**MVP 级别**：实用

---

### specialty_scores

**文件**：`db/models/scores.py`
**用途**：从病历文本中自动提取的临床量表评分（NIHSS、mRS、UPDRS 等），关联到具体病历。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| record_id | Integer FK | 关联病历 |
| doctor_id | String(64) FK | 所属医生 |
| patient_id | Integer FK | 关联患者 |
| score_type | String(32) | 量表类型（NIHSS/mRS/GCS 等）|
| score_value | Float | 评分值 |
| raw_text | String(256) | 原文片段 |
| details_json | Text | 详细解析 JSON |
| source | String(16) | chat/import/manual |
| confidence_score | Float | 置信度（0-1）|
| validation_status | String(16) | pending/validated/rejected |
| extracted_at | DateTime | 提取时间 |
| created_at | DateTime | 创建时间 |

**MVP 级别**：实用

---

### doctor_tasks

**文件**：`db/models/tasks.py`
**用途**：随访提醒、紧急任务、预约管理。病历保存时可自动触发生成（受环境变量 `AUTO_FOLLOWUP_TASKS_ENABLED` 控制），也可手动创建。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| patient_id | Integer FK | 关联患者 |
| record_id | Integer FK | 来源病历 |
| task_type | String(32) | follow_up/emergency/appointment |
| title | String(256) | 任务标题 |
| content | Text | 任务详情 |
| status | String(16) | pending/completed/cancelled |
| due_at | DateTime | 到期时间 |
| notified_at | DateTime | 最后通知时间 |
| trigger_source | String(32) | manual/risk_engine/timeline_rule |
| trigger_reason | Text | 触发原因 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：实用

---

### doctor_contexts

**文件**：`db/models/doctor.py`
**用途**：对话压缩摘要。当对话轮次超过阈值时，LLM 将历史压缩为结构化摘要存入此表，重启后可恢复上下文。

| 字段 | 类型 | 说明 |
|---|---|---|
| doctor_id | String(64) PK | 医生 ID |
| summary | Text | 压缩摘要文本 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：实用

---

### doctor_conversation_turns

**文件**：`db/models/doctor.py`
**用途**：历史对话轮次持久化，支持多实例间共享对话上下文。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| role | String(16) | user/assistant/system |
| content | Text | 消息内容 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**索引**：`(doctor_id, created_at)`
**MVP 级别**：实用

---

### doctor_knowledge_items

**文件**：`db/models/doctor.py`
**用途**：医生专属知识库，存储医生通过 `add_to_knowledge_base` 命令添加的临床经验条目，注入 LLM 提示词以提升个性化响应。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| content | Text | 知识条目内容 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：实用

---

### system_prompt_versions

**文件**：`db/models/system.py`
**用途**：提示词版本历史，每次更新前追加旧版本快照，支持从 Admin UI 回滚。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| prompt_key | String(64) | 提示词键 |
| content | Text | 历史内容 |
| changed_by | String(64) | 操作人 |
| changed_at | DateTime | 变更时间 |

**MVP 级别**：实用

---

### runtime_config

**文件**：`db/models/runtime.py`
**用途**：热更新 JSON 配置。管理员可通过 Admin UI 修改路由关键词、fast_router 参数等配置，无需重启。

| 字段 | 类型 | 说明 |
|---|---|---|
| config_key | String(64) PK | 配置键 |
| content_json | Text | JSON 配置内容 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：实用

---

### runtime_cursors

**文件**：`db/models/runtime.py`
**用途**：通用游标存储，当前用于 WeCom KF 消息同步游标，防止多实例重复拉取同一批消息。

| 字段 | 类型 | 说明 |
|---|---|---|
| cursor_key | String(64) PK | 游标键 |
| cursor_value | String(256) | 游标值 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：实用

---

### audit_log

**文件**：`db/models/audit.py`
**用途**：敏感操作审计日志，记录患者数据增删改查、登录等操作，合规追溯用。异步写入，不阻塞主请求。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| ts | DateTime | 操作时间 |
| doctor_id | String(64) FK | 操作医生 |
| action | String(16) | READ/WRITE/DELETE/LOGIN |
| resource_type | String(32) | patient/record/task |
| resource_id | String(64) | 资源 ID |
| ip | String(64) | 客户端 IP |
| trace_id | String(64) | 追踪 ID |
| ok | Boolean | 操作是否成功 |

**MVP 级别**：实用

---

### doctor_notify_preferences

**文件**：`db/models/doctor.py`
**用途**：医生个性化通知调度配置（自动/手动、间隔/定时等）。当前 MVP 使用固定调度，此表暂未激活。

| 字段 | 类型 | 说明 |
|---|---|---|
| doctor_id | String(64) PK | 医生 ID |
| notify_mode | String(16) | auto/manual |
| schedule_type | String(16) | immediate/interval/cron |
| interval_minutes | Integer | 间隔分钟数 |
| cron_expr | String(64) | Cron 表达式 |
| last_auto_run_at | DateTime | 上次自动执行时间 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：暂缓

---

### runtime_tokens

**文件**：`db/models/runtime.py`
**用途**：通用 Token 缓存（如微信 access_token）。当前 Token 从环境变量读取，此表未启用。

| 字段 | 类型 | 说明 |
|---|---|---|
| token_key | String(64) PK | Token 键 |
| token_value | Text | Token 值 |
| expires_at | DateTime | 过期时间 |
| updated_at | DateTime | 更新时间 |

**MVP 级别**：暂缓
