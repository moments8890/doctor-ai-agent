# 数据库表设计文档

> 最后更新：2026-03-08
> 共 26 张表：9 个 MVP 核心表 · 15 个扩展表 · 2 个暂缓表

---

## 目录

1. [核心流程依赖链](#核心流程依赖链)
2. [MVP 核心表（9 张）](#mvp-核心表9-张)
3. [扩展表（15 张）](#扩展表15-张)
4. [暂缓表（2 张）](#暂缓表2-张)

---

## 核心流程依赖链

```
医生语音/文字消息
    ↓
pending_messages        ← 消息入库，防微信 5s 超时丢失
    ↓
system_prompts          ← 调取 LLM 提示词（热更新）
    ↓
pending_records         ← AI 草稿，等待医生确认（TTL 10 分钟）
    ↓
doctor_session_states   ← 记录 pending_record_id，跨实例恢复
    ↓
医生回复"确认"
    ↓
medical_records         ← 正式病历入库
    ↓
patients                ← 患者风险/分类字段自动更新
    ↓
doctor_tasks            ← 可选：自动生成随访提醒
    ↓
chat_archive            ← 全量对话永久存档（训练语料）
scheduler_leases        ← 定时任务互斥锁（多实例部署）
```

---

## MVP 核心表（9 张）

缺少任何一张，核心流程无法运转。

| 表名 | 用途 |
|---|---|
| `doctors` | 医生身份注册 |
| `invite_codes` | 邀请码登录门控 |
| `patients` | 患者注册与风险分级 |
| `medical_records` | 确认后的正式病历 |
| `pending_records` | AI 草稿确认门控（10 分钟 TTL）|
| `pending_messages` | 微信消息持久化收件箱 |
| `doctor_session_states` | 会话状态跨实例恢复 |
| `system_prompts` | LLM 提示词（支持热更新）|
| `scheduler_leases` | 分布式定时任务互斥锁 |

---

### doctors

**文件**：`db/models/doctor.py`
**用途**：医生身份注册表，整个系统的认证根节点。

| 字段 | 类型 | 说明 |
|---|---|---|
| doctor_id | String(64) PK | 规范化 ID（微信 openid 或邮箱）|
| name | String(128) | 医生姓名 |
| specialty | String(64) | 科室专业（登录时填写，注入 Agent 提示词）|
| channel | String(32) | 渠道：app / wechat / wechat_mini |
| wechat_user_id | String(128) | 微信企业号 openid |
| mini_openid | String(128) | 小程序 openid |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**索引**：`(channel, wechat_user_id)` 唯一，`mini_openid` 唯一

---

### invite_codes

**文件**：`db/models/doctor.py`
**用途**：管理员预置的邀请码，医生凭码登录 Web 端。

| 字段 | 类型 | 说明 |
|---|---|---|
| code | String(32) PK | 邀请码 |
| doctor_id | String(64) | 关联医生 ID |
| doctor_name | String(128) | 医生姓名（显示用）|
| active | Integer(bool) | 是否有效（1/0）|
| created_at | DateTime | 创建时间 |

---

### patients

**文件**：`db/models/patient.py`
**用途**：患者注册表，支持风险分级与病历分类自动计算。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| name | String(128) | 患者姓名 |
| gender | String(16) | 性别 |
| year_of_birth | Integer | 出生年份 |
| primary_category | String(32) | 主分类（AI 计算）|
| category_tags | Text JSON | 分类标签列表 |
| primary_risk_level | String(16) | 风险等级：low / medium / high |
| risk_tags | Text JSON | 风险标签列表 |
| risk_score | Integer | 风险评分 |
| follow_up_state | String(16) | 随访状态 |
| created_at | DateTime | 创建时间 |

**索引**：`(doctor_id, primary_category)`，`(doctor_id, primary_risk_level)`

---

### medical_records

**文件**：`db/models/records.py`
**用途**：医生确认后的正式病历，AI 草稿经确认后写入。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| patient_id | Integer FK | 关联患者 |
| doctor_id | String(64) FK | 所属医生 |
| record_type | String(32) | 病历类型（门诊/住院/随访等）|
| content | Text | 病历内容（JSON）|
| tags | Text JSON | 标签列表 |
| encounter_type | String(32) | 就诊类型：first_visit / follow_up / unknown |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**索引**：`(patient_id, created_at)`

---

### pending_records

**文件**：`db/models/pending.py`
**用途**：AI 草稿确认门控。LLM 结构化后先存此表，医生确认后写入 `medical_records`，10 分钟自动过期。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(64) PK | UUID hex |
| doctor_id | String(64) FK | 所属医生 |
| patient_id | Integer FK | 关联患者（可为空）|
| patient_name | String(128) | 患者姓名（无 ID 场景冗余存储）|
| draft_json | Text | AI 草稿 JSON |
| status | String(32) | awaiting / confirmed / abandoned / expired |
| created_at | DateTime | 创建时间 |
| expires_at | DateTime | 过期时间（创建后 10 分钟）|

**索引**：`(doctor_id, status)`，`expires_at`

---

### pending_messages

**文件**：`db/models/pending.py`
**用途**：微信消息持久化收件箱。消息派发后台任务前先入库，处理完成后标记 done，启动时恢复超时未处理的消息（60 秒阈值）。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(64) PK | UUID |
| doctor_id | String(64) FK | 所属医生 |
| raw_content | Text | 原始消息内容 |
| status | String(16) | pending / done / failed |
| created_at | DateTime | 创建时间 |

**索引**：`(status, created_at)`，`doctor_id`

---

### doctor_session_states

**文件**：`db/models/doctor.py`
**用途**：医生轻量会话状态持久化。记录当前患者、待确认草稿 ID 等，重启或多实例切换时可恢复。

| 字段 | 类型 | 说明 |
|---|---|---|
| doctor_id | String(64) PK | 医生 ID |
| current_patient_id | Integer FK | 当前操作患者 |
| pending_create_name | String(128) | 待创建患者姓名 |
| pending_record_id | String(64) | 待确认草稿 ID |
| updated_at | DateTime | 更新时间 |

---

### system_prompts

**文件**：`db/models/system.py`
**用途**：LLM 提示词存储，支持管理员从 Admin UI 热更新，无需重启服务。

| 字段 | 类型 | 说明 |
|---|---|---|
| key | String(64) PK | 提示词键（structuring / agent_routing 等）|
| content | Text | 提示词正文 |
| updated_at | DateTime | 更新时间 |

---

### scheduler_leases

**文件**：`db/models/runtime.py`
**用途**：分布式定时任务互斥锁，多实例部署时防重复执行（过期草稿清理、任务通知等）。

| 字段 | 类型 | 说明 |
|---|---|---|
| lease_key | String(64) PK | 任务键 |
| owner_id | String(128) | 持锁实例 ID |
| lease_until | DateTime | 锁超时时间 |
| updated_at | DateTime | 更新时间 |

---

## 扩展表（15 张）

核心流程已上线后按优先级启用，代码均已完整实现。

| 表名 | 用途 | 优先级 |
|---|---|---|
| `patient_labels` | 医生自定义患者标签 | 高 |
| `patient_label_assignments` | 患者-标签多对多关联 | 高 |
| `doctor_tasks` | 随访提醒 / 紧急任务 / 预约 | 高 |
| `audit_log` | 敏感操作审计日志（合规）| 高 |
| `chat_archive` | 医生对话永久存档（训练语料）| 高 |
| `doctor_contexts` | 会话压缩摘要（跨重启恢复上下文）| 中 |
| `doctor_conversation_turns` | 滚动窗口对话历史（跨节点上下文）| 中 |
| `system_prompt_versions` | 提示词版本历史（支持回滚）| 中 |
| `runtime_config` | 热更新 JSON 配置 | 中 |
| `medical_record_versions` | 病历修改快照（编辑审计）| 中 |
| `medical_record_exports` | PDF 导出日志 | 低 |
| `neuro_cases` | 神经专科结构化病例 | 低 |
| `neuro_cvd_context` | 神经外科脑血管手术专科上下文 | 低 |
| `specialty_scores` | 临床量表评分（NIHSS/mRS 等）| 低 |
| `doctor_knowledge_items` | 医生专属知识库条目 | 低 |

---

### patient_labels / patient_label_assignments

医生自定义标签（如"脑卒中高危""术后随访"）及其患者多对多关联。`patient_labels` 存标签定义，`patient_label_assignments` 存关联关系。

---

### doctor_tasks

随访提醒、紧急任务、预约管理。病历保存时可自动生成（受 `AUTO_FOLLOWUP_TASKS_ENABLED` 控制），也可手动创建。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| patient_id | Integer FK | 关联患者 |
| record_id | Integer FK | 来源病历 |
| task_type | String(32) | follow_up / emergency / appointment |
| title | String(256) | 任务标题 |
| content | Text | 任务详情 |
| status | String(16) | pending / completed / cancelled |
| due_at | DateTime | 到期时间 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

---

### audit_log

敏感操作审计日志（患者增删改查、登录等），合规追溯用。异步写入，不阻塞主请求。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| ts | DateTime | 操作时间 |
| doctor_id | String(64) FK | 操作医生 |
| action | String(16) | READ / WRITE / DELETE / LOGIN |
| resource_type | String(32) | patient / record / task |
| resource_id | String(64) | 资源 ID |
| ip | String(64) | 客户端 IP |
| trace_id | String(64) | 追踪 ID |
| ok | Boolean | 操作是否成功 |

---

### chat_archive

医生↔AI 全量对话永久存档，不截断，不滚动。用于未来词汇扩展、fast_router 覆盖率提升和模型微调。`intent_label` 由人工审核后回填。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| role | String(16) | user / assistant |
| content | Text | 消息内容 |
| intent_label | String(64) | 意图标注（人工审核后填写，初始为空）|
| created_at | DateTime | 创建时间 |

**索引**：`(doctor_id, created_at)`
**与 doctor_conversation_turns 的区别**：conversation_turns 是滚动窗口（最多保留 20 条用于上下文恢复），chat_archive 永久保存所有对话。

---

### doctor_contexts

对话压缩摘要。当对话轮次超过阈值时，LLM 将历史压缩为结构化摘要存入此表，重启后可恢复上下文。

---

### doctor_conversation_turns

历史对话轮次持久化（滚动窗口，最多 20 条），支持多实例间共享对话上下文。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK | 所属医生 |
| role | String(16) | user / assistant / system |
| content | Text | 消息内容 |
| created_at | DateTime | 创建时间 |

---

### system_prompt_versions

提示词版本历史，每次更新前追加旧版本快照，支持从 Admin UI 回滚。

---

### runtime_config

热更新 JSON 配置，管理员可从 Admin UI 修改路由关键词等参数，无需重启。

---

### medical_record_versions

病历修改审计日志，每次内容/类型/标签变更时追加旧值快照，支持回溯与合规审查。

---

### medical_record_exports

PDF 导出审计日志，记录导出时间、格式和文件哈希，防篡改追溯。

---

### neuro_cases

神经专科结构化病例，存储 LLM 从文字中提取的 NeuroCase 结构（影像、诊断、治疗方案等）及提取日志。

---

### neuro_cvd_context

神经外科脑血管疾病专科上下文（ICH 评分、Hunt-Hess 分级、动脉瘤信息、手术方案、mRS/Barthel 预后等）。仅神经外科医生使用。

---

### specialty_scores

从病历文本中自动提取的临床量表评分（NIHSS、mRS、GCS、UPDRS 等），关联到具体病历。

---

### doctor_knowledge_items

医生专属知识库，存储通过 `add_to_knowledge_base` 命令添加的临床经验条目，注入 LLM 提示词以提升个性化响应。

---

## 暂缓表（2 张）

模型已定义，生产路径无实际读写，暂不启用。

| 表名 | 暂缓原因 |
|---|---|
| `doctor_notify_preferences` | MVP 使用固定调度间隔，无需每位医生单独配置 |
| `runtime_tokens` | Token 目前从环境变量读取，未走数据库 |
