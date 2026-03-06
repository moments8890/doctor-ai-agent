# 专科医师AI智能体 — MVP 可行性报告摘要

## 背景

现有医疗AI分两类，均不以专科医师为中心：
- **机构级**（如科大讯飞）：嵌入HIS/EMR，专注院内流程合规
- **平台级**（如平安健康）：患者端问诊，专注泛化健康咨询

**缺口**：以专科医师为核心、深入临床业务的闭环管理工具。

---

## 四大结构性痛点

1. **管理超载** — 医生时间固定，患者规模持续增加
2. **反馈被动** — 出院后管理断裂，复查靠自觉，失访风险高
3. **沟通低效** — 碎片化重复咨询耗时，医患数据零散难转化
4. **知识迭代** — 缺乏将最新指南实时映射到具体病程的辅助机制

---

## 三阶段路线图

| 阶段 | 状态 | 重点 | 核心功能 |
|------|------|------|----------|
| **Phase 1** | ✅ 完成 | 效率建立期 | 语音/文字录入 → 结构化病历生成 |
| **Phase 2** | ✅ 完成 | 能力扩展期 | 患者管理、数据库持久化、微信Bot意图识别 |
| **Phase 3** | 🔄 进行中 | 认知强化期 | LLM Agent调度、对话记忆、专科语料、本地语音 |

---

## Phase 1 — 结构化病历（已完成）

**输入** → 医生口述（语音）或文字笔记
**处理** → LLM 自动结构化解析
**输出** → 规范化结构化病历

### 病历字段（符合卫医政发〔2010〕11号规范）

| 字段 | 中文 | 必填 |
|------|------|------|
| `chief_complaint` | 主诉 | ✅ |
| `history_of_present_illness` | 现病史 | ✅ |
| `diagnosis` | 诊断 | 尽量填 |
| `treatment_plan` | 治疗方案 | 尽量填 |
| `past_medical_history` | 既往史 | 选填 |
| `physical_examination` | 体格检查 | 选填 |
| `auxiliary_examinations` | 辅助检查 | 选填 |
| `follow_up_plan` | 随访计划 | 选填 |

---

## Phase 2 — 患者管理与微信Bot（已完成）

- 患者建档（姓名、性别、年龄），病历自动关联
- 跨消息会话记忆当前患者（in-memory session）
- 数据库持久化（SQLite + SQLAlchemy async）
- 本地LLM（Ollama + Qwen2.5:7b），数据不离开服务器
- 数据库可视化（SQLAdmin + datasette + CLI工具）

---

## Phase 3 — LLM Agent 与专科增强（进行中）

### 3.1 LLM Function-Calling Agent（已完成）

弃用基于规则的意图识别，改用 **LLM 工具调用（function calling）** 作为主要调度路径：

| 工具 | 触发条件 |
|------|----------|
| `add_medical_record` | 任何临床内容：症状、体征、检查、诊断、用药、专科操作 |
| `create_patient` | 明确建档请求（无临床内容） |
| `query_records` | 查询历史病历 |
| `list_patients` | 查看患者列表 |
| 无工具调用 | 普通对话 → 直接返回 chat_reply |

**决策依据**：规则匹配无法覆盖心血管/肿瘤专科术语（EGFR、HER2、化疗周期、CEA趋势等），LLM工具调用可通过工具描述扩展覆盖范围，无需维护关键词列表。

### 3.2 对话记忆与上下文压缩（已完成）

- 每位医生维护最近 **10轮** 对话滚动窗口
- 窗口满（10轮）或空闲超过30分钟时，LLM自动压缩为120字摘要并持久化到DB
- 新会话开始时注入摘要为系统消息，实现跨会话上下文延续

### 3.3 专科语料支持（已完成）

结构化提示词（`services/structuring.py`）针对专科输入优化：
- **心血管**：STEMI/NSTEMI、PCI/CABG术后、消融术后、BNP/EF趋势、Holter、NYHA分级、LDL-C达标
- **肿瘤**：化疗周期、肿瘤标志物趋势（CEA/CA199）、靶向药（奥希替尼/曲妥珠单抗）、EGFR/HER2/T790M、ANC/G-CSF
- **趋势数据**：`auxiliary_examinations` 字段包含数值变化（如"BNP 980 pg/mL（上次600，升高）"）
- **鉴别诊断**：`diagnosis` 支持"考虑：XX；待排：YY"格式
- `max_tokens` 从 800 提升至 1500，支持复杂多诊断病历

### 3.4 本地语音识别（已完成）

**决策**：采用本地 faster-whisper 替代 OpenAI Whisper API。

| 方案 | 优点 | 缺点 |
|------|------|------|
| OpenAI Whisper API | 简单，无需本地资源 | 网络延迟，按量收费，医学术语准确率有限 |
| **faster-whisper（选用）** | 离线，零调用成本，可注入医学词汇提示 | 需本地 ~1.5 GB 模型 |
| 讯飞/阿里云医疗ASR | 医学领域准确率最高 | 额外依赖，有费用 |

**实现要点**：
- `initial_prompt` 注入常见药名、实验室指标、诊断名称，显著提升专科术语转录准确率
- 模型懒加载（首次调用时加载），不阻塞启动
- 线程池执行，不阻塞异步事件循环
- `faster-whisper` 未安装时自动回退到 OpenAI API

### 3.5 引导式问诊（已完成）

7步结构化问诊流程（菜单触发或发送"开始问诊"）：
患者姓名 → 主诉 → 持续时间 → 严重程度 → 伴随症状 → 既往史 → 体格检查

全程支持语音输入，完成后自动生成并保存结构化病历。

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| Web框架 | FastAPI + uvicorn | |
| 数据库 | SQLite + SQLAlchemy (async) + aiosqlite | |
| 本地LLM | Ollama + Qwen2.5:7b | 病历结构化、Agent调度 |
| 云端LLM备选 | DeepSeek / Groq | 按需切换 |
| 本地语音识别 | faster-whisper large-v3 | 含医学词汇提示词 |
| 中文NLP | jieba | 辅助实体提取（规则模块） |
| 微信接入 | wechatpy | |
| 管理界面 | SQLAdmin + datasette | |
| 测试 | pytest + pytest-asyncio | |

---

## 注意事项

- `doctor_id` = 微信openid，与 `WECHAT_APP_ID` 绑定。更换AppID需迁移DB中的doctor_id。
- Session 对话历史存于内存，服务重启后丢失，但 **DoctorContext 摘要已持久化到DB**。
- 微信消息5秒超时限制 — 所有LLM调用均在后台执行，结果通过客服消息API推送。
- faster-whisper large-v3 约占 1.5 GB 内存；低配服务器可改用 `WHISPER_MODEL=medium`。
