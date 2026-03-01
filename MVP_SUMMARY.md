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
| Phase 3 | 规划中 | 认知强化期 | 对话式AI Agent、主动随访、指南整合 |

---

## Phase 1 — 结构化病历（已完成）

**输入** → 医生口述（语音）或文字笔记
**处理** → LLM 自动结构化解析
**输出** → 规范化结构化病历

### 病历字段

| 字段 | 中文 | 必填 |
|------|------|------|
| `chief_complaint` | 主诉 | ✅ |
| `history_of_present_illness` | 现病史 | ✅ |
| `diagnosis` | 诊断 | ✅ |
| `treatment_plan` | 治疗方案 | ✅ |
| `past_medical_history` | 既往史 | 选填 |
| `physical_examination` | 体格检查 | 选填 |
| `auxiliary_examinations` | 辅助检查 | 选填 |
| `follow_up_plan` | 随访计划 | 选填 |

### REST API
- `POST /api/records/from-text` — 文字输入 → 结构化病历
- `POST /api/records/from-audio` — 语音上传 → 转录 → 结构化病历

---

## Phase 2 — 患者管理与微信Bot（已完成）

### 新增功能

**1. 患者档案管理**
- 建立患者档案（姓名、性别、年龄）
- 病历自动关联患者
- 跨消息会话记忆当前患者（in-memory session）

**2. 微信Bot意图识别**

医生直接发送自然语言，系统自动判断意图：

| 消息示例 | 识别意图 | 动作 |
|----------|----------|------|
| 新患者李明，45岁男性 | `create_patient` | 建档 + 设置当前患者 |
| 患者头痛两天，诊断紧张性头痛 | `add_record` | 结构化 + 存入DB |
| 查一下李明的记录 | `query_records` | 查询历史病历 |
| 你好 | `unknown` | 返回使用说明 |

**意图识别方式**（`INTENT_PROVIDER` 配置）：
- `local`（默认）— jieba分词 + 关键词匹配 + 正则，<5ms，无网络依赖
- `ollama` / `deepseek` / `groq` — LLM识别，精度更高

**3. 数据库持久化**（SQLite + SQLAlchemy async）
- `patients` 表 — 患者档案
- `medical_records` 表 — 结构化病历，外键关联患者

**4. 本地LLM（Qwen2.5）**
- 病历结构化默认使用 Ollama + `qwen2.5:7b`
- 数据不离开本地服务器
- 启动时预热模型，避免首次请求超时

**5. 数据库可视化**
- `/admin` — SQLAdmin Web UI（随API同端口启动）
- `bash tools/start_db_ui.sh` — datasette独立UI
- `python tools/db_inspect.py` — 命令行检查工具

### REST API（新增）
- `POST /api/patients` — 创建患者
- `GET /api/patients/{doctor_id}` — 列出患者
- `GET /api/patients/{doctor_id}/{patient_id}/records` — 查询病历

---

## 技术栈

| 层级 | 技术 |
|------|------|
| Web框架 | FastAPI + uvicorn |
| 数据库 | SQLite + SQLAlchemy (async) + aiosqlite |
| 本地LLM | Ollama + Qwen2.5:7b |
| 云端LLM备选 | DeepSeek / Groq |
| 中文NLP | jieba（意图识别） |
| 微信接入 | wechatpy |
| 管理界面 | SQLAdmin + datasette |
| 测试 | pytest + pytest-asyncio（73个测试） |

---

## 注意事项

- `doctor_id` = 微信openid，与 `WECHAT_APP_ID` 绑定。更换AppID需迁移数据库中的doctor_id。
- Session数据存于内存，服务重启后丢失（Phase 3将持久化）。
- 微信消息5秒超时限制 — 本地Qwen2.5需预热后方可稳定响应。
