# 数据库表设计文档

> 最后更新：2026-03-13
> 共 26 张表：9 个 MVP 核心表 · 14 个扩展表 · 3 个暂缓表

---

## 目录

1. [核心流程依赖链](#核心流程依赖链)
2. [MVP 核心表（9 张）](#mvp-核心表9-张)
3. [扩展表（14 张）](#扩展表14-张)
4. [暂缓表（3 张）](#暂缓表3-张)

---

## 核心流程依赖链

```
医生语音/文字消息
    ↓
pending_messages        ← 消息入库，防微信 5s 超时丢失
    ↓
system_prompts          ← 调取 LLM 提示词（热更新）
    ↓
pending_records         ← AI 草稿，等待医生确认（expires_at 控制过期）
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
| doctor_id | String(64) FK→doctors SET NULL | 关联医生 ID |
| doctor_name | String(128) | 医生姓名（显示用）|
| active | Boolean | 是否有效 |
| created_at | DateTime | 创建时间 |
| expires_at | DateTime | 过期时间（可选）|
| max_uses | Integer | 最大使用次数（默认 1）|
| used_count | Integer | 已使用次数（默认 0）|

---

### patients

**文件**：`db/models/patient.py`
**用途**：患者注册表，支持风险分级与病历分类自动计算。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK→doctors CASCADE | 所属医生 |
| name | String(128) | 患者姓名 |
| gender | String(16) | 性别 |
| year_of_birth | Integer | 出生年份 |
| primary_category | String(32) | 主分类（AI 计算）|
| category_tags | Text JSON | 分类标签列表 |
| phone | String(20) | 手机号（可选）|
| patient_id_number | String(18) | 身份证号（可选）|
| access_code | String(160) | 患者门户访问码（PBKDF2-SHA256 哈希，NULL = 仅姓名登录）|
| access_code_version | Integer | 访问码版本计数器（旋转时递增，使旧 JWT 失效）|
| created_at | DateTime | 创建时间 |

**索引**：`(doctor_id, created_at)`、`(doctor_id, primary_category)`
**唯一约束**：`(id, doctor_id)`、`(doctor_id, name)`

> **注**：`primary_risk_level`、`risk_tags`、`risk_score`、`follow_up_state` 字段尚未映射到模型（MVP 不需要）。计算逻辑保留在 `services/patient/patient_risk.py`，可按需添加列后启用。

---

### medical_records

**文件**：`db/models/records.py`
**用途**：医生确认后的正式病历，AI 草稿经确认后写入。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| patient_id | Integer FK | 关联患者 |
| doctor_id | String(64) FK | 所属医生 |
| record_type | String(32) | 病历类型：visit / dictation / import / neuro_case 等 |
| content | Text | 病历内容（LLM 整理后的自由文本，非 JSON）|
| tags | Text JSON | 关键词标签列表 |
| encounter_type | String(32) | 就诊类型：first_visit / follow_up / unknown |
| neuro_patient_name | String(128) | 神经科病例患者姓名（record_type=neuro_case 时使用）|
| nihss | Integer | NIHSS 评分（已弃用，改用 specialty_scores）|
| neuro_raw_json | Text | 神经科原始提取 JSON |
| neuro_extraction_log_json | Text | 神经科提取日志 JSON |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**索引**：`(patient_id, created_at)`、`(doctor_id, created_at)`、`(doctor_id, record_type, created_at)`

---

### pending_records

**文件**：`db/models/pending.py`
**用途**：AI 草稿确认门控。LLM 结构化后先存此表，医生确认后写入 `medical_records`。过期时间由 `expires_at` 字段控制（通常 10 分钟，启动时可自动保存过期草稿）。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(64) PK | UUID hex |
| doctor_id | String(64) FK→doctors CASCADE | 所属医生 |
| patient_id | Integer FK→patients **SET NULL** | 关联患者（患者删除时置 NULL，不阻断已有草稿）|
| patient_name | String(128) | 患者姓名（冗余存储，patient_id 为 NULL 时仍可显示）|
| draft_json | Text | AI 草稿 JSON |
| status | String(32) | awaiting / confirmed / abandoned / expired |
| created_at | DateTime | 创建时间 |
| expires_at | DateTime | 过期时间（创建后 10 分钟）|

**索引**：`(doctor_id, status)`，`expires_at`

---

### pending_messages

**文件**：`db/models/pending.py`
**用途**：微信消息持久化收件箱。消息派发后台任务前先入库，处理完成后标记 done，启动时恢复超时未处理的消息（60 秒阈值）。刻意精简——只保留恢复所需的最少字段。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(64) PK | UUID |
| doctor_id | String(64) FK→doctors CASCADE | 所属医生 |
| raw_content | Text | 原始消息内容 |
| status | String(16) | pending / processing / done / dead |
| attempt_count | Integer | 处理尝试次数（默认 0，超过阈值转入 dead）|
| created_at | DateTime | 创建时间 |

**索引**：`(status, created_at)`，`doctor_id`

---

### doctor_session_states

**文件**：`db/models/doctor.py`
**用途**：医生轻量会话状态持久化。记录当前患者、待确认草稿 ID 等，重启或多实例切换时可恢复。

| 字段 | 类型 | 说明 |
|---|---|---|
| doctor_id | String(64) PK FK→doctors CASCADE | 医生 ID |
| current_patient_id | Integer FK→patients SET NULL | 当前操作患者 |
| pending_create_name | String(128) | 待创建患者姓名 |
| pending_record_id | String(64) FK→pending_records SET NULL | 待确认草稿 ID |
| interview_json | Text | CVD 量表追问状态（JSON，服务重启时可恢复）|
| blocked_write_json | Text | 阻塞写入上下文（ADR 0007，等待患者姓名）|
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

## 扩展表（14 张）

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
| `neuro_cvd_context` | 神经外科脑血管专科上下文（**试点核心**，实时写入）| **高** |
| `specialty_scores` | 临床量表评分 per-score 置信度存档（与 neuro_cvd_context 双写）| 中 |
| `neuro_cases` | 结构化病例批量导入（非实时微信流程）| 低 |

---

### patient_labels / patient_label_assignments

医生自定义标签（如"脑卒中高危""术后随访"）及其患者多对多关联。`patient_labels` 存标签定义，`patient_label_assignments` 存关联关系。

---

### doctor_tasks

随访提醒、紧急任务、预约管理。病历保存时可自动生成（受 `AUTO_FOLLOWUP_TASKS_ENABLED` 控制），也可手动创建。APScheduler 每分钟调用 `run_due_task_cycle()` 推送到期任务。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增主键 |
| doctor_id | String(64) FK→doctors CASCADE | 所属医生 |
| patient_id | Integer FK→patients CASCADE | 关联患者（患者删除时任务级联删除）|
| record_id | Integer FK→medical_records **SET NULL** | 来源病历（病历删除时置 NULL，不阻断）|
| task_type | String(32) | follow_up / emergency / appointment / general |
| title | String(256) | 任务标题 |
| content | Text | 任务详情 |
| status | String(32) | pending / completed / cancelled |
| due_at | DateTime | 到期时间（可为空，紧急任务立即执行）|
| created_at | DateTime | 创建时间 |
| updated_at | DateTime? | 更新时间（nullable）|

**索引**：
- `ix_tasks_doctor_status_due (doctor_id, status, due_at)` — 医生维度任务查询
- `ix_tasks_status_due (status, due_at)` — 调度器跨医生到期任务扫描（`list_due_unnotified()` 无 doctor_id 过滤）

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

### neuro_cvd_context

**神经外科脑血管试点核心表**。实时写入（微信流程确认病历后后台异步提取）。

存储字段：ICH Score（0–6）、Hunt-Hess（1–5）、Fisher/改良 Fisher、WFNS、动脉瘤位置/大小/颈宽/形态、Spetzler-Martin（1–5）、GCS（3–15）、PHASES Score（0–12）、血管痉挛状态、脑积水、烟雾病铃木分期、手术类型/日期/状态、mRS（0–6）、Barthel 指数。`updated_at`（最后字段更新时间，`upsert_cvd_field()` 写入时自动更新）。

**与 specialty_scores 的关系**：两表**独立写入**，触发条件不同——并非保证双写同一病历。
- `specialty_scores`：当 `detect_score_keywords()` 检测到量表关键词时写入（关键词驱动）
- `neuro_cvd_context`：当 Agent 提取到 CVD 上下文（inline）或 `_detect_cvd_keywords()` 命中（后台任务）时写入

`neuro_cvd_context` 是完整临床上下文的查询主表；`specialty_scores` 是 per-score 的置信度/验证状态审计表。如两表同一字段值不一致，以 `neuro_cvd_context` 为准。

---

### specialty_scores

从病历文本中自动提取的临床量表 per-score 存档（NIHSS、mRS、GCS、Hunt-Hess 等），每条记录保含 `confidence_score` 和 `validation_status`（pending/confirmed/rejected），用于量表提取质量追踪和人工审核。**注意**：对于神经外科脑血管病种，相同字段同时写入 `neuro_cvd_context`，后者是查询/展示的主表。

---

### neuro_cases

**⚠️ 批量导入专用，非实时微信流程表。**

`extract_neuro_case()` 返回 `(NeuroCase, ExtractionLog, NeuroCVDSurgicalContext)` 三元组，但实时微信流程只将 `NeuroCVDSurgicalContext` 存入 `neuro_cvd_context`——`NeuroCase` 部分被丢弃，`neuro_cases` 表不参与实时流程。

`routers/neuro.py` 提供单独的 `/neuro/` 导入端点，供批量导入既有病历时写入此表。字段：`nihss`（已提升为列）+ `raw_json`（完整提取结构）+ `extraction_log_json`。

---

## 暂缓表（3 张）

模型已定义，生产路径无实际读写，暂不启用。

| 表名 | 暂缓原因 |
|---|---|
| `doctor_notify_preferences` | MVP 使用固定调度间隔，无需每位医生单独配置 |
| `runtime_tokens` | Token 目前从环境变量读取，未走数据库 |
| `doctor_knowledge_items` | 服务（`services/knowledge/doctor_knowledge.py`）和测试已实现，但尚未接入 `dispatch()` 提示词注入——待下一迭代：将医生知识条目注入 Agent 系统提示词，提升神经外科个性化响应（如"本院 ICH 手术指征"等个人协议）|
