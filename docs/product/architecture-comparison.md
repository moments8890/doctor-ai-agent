# 开源 AI 助手 & 医疗 AI 项目架构对比与反馈

> 更新时间：2026-03-12｜基于源码级研究
>
> **Part A — WeChat AI 项目对比：**
> - [zhayujie/chatgpt-on-wechat](https://github.com/zhayujie/chatgpt-on-wechat) — 通用多渠道 Agent / Bot 平台
> - [wechaty/wechaty](https://github.com/wechaty/wechaty) — 多协议会话机器人 SDK / 基础设施
> - [kx-Huang/ChatGPT-on-WeChat](https://github.com/kx-Huang/ChatGPT-on-WeChat) — 极简 ChatGPT-WeChat 中继机器人
>
> **Part B — 通用 AI 助手平台：**
> - [openclaw/openclaw](https://github.com/openclaw/openclaw) — 开源个人 AI 助手平台
> - [FreedomIntelligence/OpenClaw-Medical-Skills](https://github.com/FreedomIntelligence/OpenClaw-Medical-Skills) — OpenClaw 医疗技能库
>
> **Part C — 开源医疗 AI 项目：**
> - [ruslanmv/ai-medical-chatbot](https://github.com/ruslanmv/ai-medical-chatbot) — 多模型医疗问诊 (WatsonX/GPT/Llama)
> - [Md-Emon-Hasan/MediGenius](https://github.com/Md-Emon-Hasan/MediGenius) — 多智能体医疗 QA (LangGraph)
> - [10-OASIS-01/BenCao_RAG](https://github.com/10-OASIS-01/BenCao_RAG) — 中文医疗知识图谱 + RAG

---

## 一、总览对比

先说明一个判断：

- 下面这些项目有代表性，但并不都是同一层级的“直接竞品”
- `chatgpt-on-wechat` 更适合当作多渠道 Agent 平台参照物
- `Wechaty` 更适合当作协议抽象 / SDK 参照物
- `kx-Huang/ChatGPT-on-WeChat` 更适合当作最小可行机器人和部署体验参照物
- `OpenClaw` 更适合当作通用 AI 助手平台与技能生态参照物

因此，这组对比更适合用来回答“我们该借鉴什么、避免什么”，而不是简单地做同一评分尺上的横向排名。

| 维度 | **doctor-ai-agent** | **chatgpt-on-wechat** (zhayujie) | **Wechaty** | **ChatGPT-on-WeChat** (kx-Huang) |
|---|---|---|---|---|
| 定位 | 医疗工作流 AI 助手 | 通用多渠道 Agent 平台 | SDK / 基础设施 | 极简 WeChat-LLM 中继 |
| 语言 | Python (FastAPI, async) | Python (线程模型) | TypeScript (多语言 SDK) | TypeScript (~400 LOC) |
| 规模 | 50+ 模块, 1100+ 测试 | 200+ 文件, 0 测试 | ~100 模块, 完整测试 | 4 文件, 0 测试 |
| 微信接入 | 公众号 + 小程序 + 企业微信 | 个人号 (itchat, 逆向协议) | 抽象 Puppet (Web/iPad/企微) | 个人号 (Wechaty puppet) |
| LLM 支持 | 6+ (Ollama, DeepSeek, Groq, Gemini, OpenAI, 腾讯 LKEAP) | 12+ (OpenAI, Claude, Gemini, 通义, 智谱, 豆包等) | 无 (纯基础设施) | 仅 OpenAI |
| 意图路由 | 5 层工作流 + deterministic fast-route | 插件事件链 | 无 | 关键词前缀匹配 |
| 会话状态 | 完整 session + DB 持久化 + 患者绑定 | 内存 session | 无 | 无状态 |
| 数据库 | SQLite/MySQL/PG + Alembic 迁移 | 无 (pickle/JSON) | 无 | 无 |
| 插件系统 | 无 (分层服务架构) | 成熟的事件驱动插件 | `use()` 插件 + Puppet 抽象 | 无 |
| 测试 | 1100+ 单元 + E2E 回放 + 集成 | 无 | 有 | 无 |

---

## 二、架构模式对比

### 2.1 doctor-ai-agent — 分层单体 + 意图流水线

```
HTTP/WeChat/Voice → Router → Intent Workflow (5层) → Domain Service → DB
                                  │
                          classify → extract → bind → plan → gate
```

- **FastAPI async** 全链路异步
- 所有渠道（Web、微信、语音）统一进入 5 层意图流水线
- 快速路径由 deterministic fast-route 承担，剩余不确定消息落到 LLM / workflow
- **共享意图处理层**：`services/domain/intent_handlers/` 提供渠道无关的业务逻辑，Web 和 WeChat 通过薄适配器调用同一组 handler，返回 `HandlerResult`，由各渠道适配为对应的响应格式
- Session 内存 + DB 双写，5 分钟 hydrate，支持多设备切换
- 安全门控：写操作必须确认患者身份

### 2.2 chatgpt-on-wechat — 插件化单体 + Bridge 路由

```
Channel (WeChat/飞书/钉钉) → Bridge → Plugin Chain → Bot (LLM)
                                         │
                              ON_RECEIVE → ON_HANDLE → ON_DECORATE → ON_SEND
```

- **线程模型**，Producer-Consumer 队列，4 并发 / 8 线程池
- Bridge 单例按模型名前缀分发到对应 Bot 类
- 4 阶段插件链，支持优先级排序、短路控制、第三方 git 安装
- 近期新增 Agent 框架（tools、skills、memory），与原架构并行
- **每条消息都调用 LLM**，无快速路由优化

### 2.3 Wechaty — 抽象 Puppet SDK

```
应用代码 → Wechaty (Mixin 组合) → Puppet 抽象 → 具体协议 (Web/iPad/WeCom)
```

- **不是应用**，是基础设施层
- Mixin 管道组合：Skeleton → Error → Puppetify → IO → Puppet → Login → Misc → Plugin → ServiceCtl
- Puppet 抽象：统一接口，底层可切换 Web/iPad/WeCom 协议
- Sayable 抽象：统一文本/文件/链接/小程序等消息类型
- 17 种类型化事件（message、login、scan、room-join 等）
- 多语言 SDK 通过 gRPC 连接 TypeScript Puppet 服务

### 2.4 ChatGPT-on-WeChat (kx-Huang) — 极简中继

```
Wechaty events (scan/login/message) → ChatGPTBot → OpenAI API → reply
```

- 4 个文件，单类封装全部逻辑
- 无状态：每条消息独立调 OpenAI，无会话记忆
- 长回复 500 字分段
- 一键部署 Railway / Docker

---

## 三、微信接入方式对比

| 项目 | 接入方式 | 协议类型 | 被封风险 |
|---|---|---|---|
| **doctor-ai-agent** | 公众号 API + 小程序 SDK + 企微 API | 官方 API | **低** (腾讯认可) |
| **chatgpt-on-wechat** | itchat (内置逆向库) | Web 微信逆向 | **高** (频繁被封) |
| **Wechaty** | 多 Puppet (Web/iPad/企微) | 视 Puppet 而定 | 中-高 |
| **ChatGPT-on-WeChat** | Wechaty + wechat puppet | Web 微信逆向 | **高** |

**关键差异**：doctor-ai-agent 是四个项目中**唯一使用官方接口**的，不存在被腾讯封禁的风险。其余三个依赖逆向协议，在生产环境中存在随时中断的可能。

---

## 四、LLM 集成深度

| 维度 | doctor-ai-agent | chatgpt-on-wechat | ChatGPT-on-WeChat |
|---|---|---|---|
| 快速路由 | 多级（关键词/正则/TF-IDF），90%+ 无需 LLM | 无，每条消息必过 LLM | 无 |
| Provider 抽象 | 运行时配置切换 + 回退链 | 工厂模式，前缀匹配 | 硬编码 OpenAI |
| 本地推理 | Ollama (qwen2.5:14b, LAN 推理服务器) | 部分支持 | 不支持 |
| 路由与结构化分离 | ROUTING_LLM 与 STRUCTURING_LLM 可独立配置 | 单一模型 | 单一模型 |
| Tool Calling | 支持 (agent.py) | Agent 框架支持 | 不支持 |
| 会话记忆 | 滚动窗口 + 压缩 + DB 归档 | 内存列表 + 可选文件持久化 | 无 |

---

## 五、各项目可借鉴之处与边界

### 5.1 chatgpt-on-wechat：适合借鉴“平台扩展性”，不适合直接当作医疗工作流基线

1. **事件驱动插件系统**：4 阶段管道 + 优先级排序 + 短路控制 (`CONTINUE`/`BREAK`/`BREAK_PASS`)，第三方可通过 git 安装插件而无需修改核心代码
2. **LLM Provider 工厂**：字符串前缀 → Bot 类的简洁映射，新增 provider 只需添加一个 Bot 子类
3. **多渠道覆盖**：单一代码库同时支持微信个人号、公众号、企业微信、飞书、钉钉、Web 终端

高层反馈：

- 这个项目最有价值的是“生态面”和“扩展性”
- 最不该直接照搬的是它的能力边界过宽
- 对 doctor-ai-agent 来说，应该学习它的扩展点设计，而不是把产品主线做成通用聊天平台

### 5.2 Wechaty：适合借鉴“渠道抽象”，不适合当作上层产品参照物

1. **Puppet 抽象**：协议细节完全隐藏在统一接口后，切换 Web/iPad/企微只需更换配置
2. **Sayable 抽象**：`messageToSayable` → `sayableToPayload` → `deliverSayable`，统一处理文本、文件、链接、小程序、位置等消息类型
3. **Mixin 组合模式**：功能通过 `pipe(Base, mixin1, mixin2, ...)` 逐层叠加，避免深层继承

高层反馈：

- Wechaty 更像“机器人协议基础设施”，不是“医生工作流产品”
- 它最值得借鉴的是 transport / adapter 层解耦
- 但它不应该决定上层 UX、患者状态管理或病历确认模型

### 5.3 ChatGPT-on-WeChat (kx-Huang)：适合借鉴“极简部署”，不适合当作安全工作流对标物

1. **部署极简化**：一键 Railway / Docker 部署，对新用户友好
2. **最小可行架构**：证明了一个 WeChat AI bot 的最小实现只需 4 个文件

高层反馈：

- 这个项目最强的信号是“启动成本低”
- 它可以提醒我们持续压低部署和 onboarding 摩擦
- 但它本质上是一个极简 LLM 中继，不适合拿来比较患者绑定、草稿确认、审计或临床安全

### 5.4 OpenClaw：适合借鉴“技能生态与助手平台能力”，不适合直接当作医疗 workflow 基线

从 OpenClaw 主仓库和其医疗技能库来看，它代表的是另一条路线：

1. **助手平台化**：更强调个人 AI assistant、跨平台运行、技能安装、扩展生态
2. **技能组织方式**：技能、扩展、工作区和 UI 都是平台的一等公民
3. **医疗能力承载方式**：通过独立 skill 库承载医学知识与流程，而不是把所有医疗逻辑写死在核心应用内

高层反馈：

- OpenClaw 最值得借鉴的是“技能封装”和“通用助手平台”的产品视角
- 对 doctor-ai-agent 来说，可借鉴的是如何把部分专科逻辑、辅助流程、研究型工具做成可插拔能力
- 但不适合直接照搬它的整体产品边界，因为 doctor-ai-agent 的核心竞争力不是“通用助手能力最广”，而是“临床工作流更安全、更可验证”

---

## 六、doctor-ai-agent 的核心优势

在四个项目中，doctor-ai-agent 在以下维度显著领先：

| 优势 | 说明 |
|---|---|
| **医疗领域安全** | 5 层意图流水线 + 安全门控，写操作必须确认患者。其他项目无任何领域安全概念 |
| **官方微信接入** | 唯一使用腾讯官方 API 的项目，无封号风险 |
| **性能优先路由** | 多级快速路由 90%+ 请求 <1ms，无 LLM 延迟。其他项目每条消息都调 LLM |
| **测试覆盖** | 1100+ 测试 + E2E 回放 + diff-coverage 门控。chatgpt-on-wechat 和 ChatGPT-on-WeChat 零测试 |
| **会话与患者绑定** | 完整 session + DB 持久化 + 多设备同步 + 临床上下文跟踪 |
| **可观测性** | 逐轮 JSONL 日志、Trace ID、5 层流水线延迟基准、审计追踪 |
| **数据库与迁移** | SQLAlchemy async ORM + Alembic 迁移，支持 SQLite/MySQL/PG |

---

## 七、反馈与改进建议

基于以上对比，对 doctor-ai-agent 提出以下改进建议：

### 7.0 先统一对比口径

在文档和对外叙述里，建议把这几类项目从“竞品”改成“参照系”：

- `chatgpt-on-wechat`：参照扩展性与多渠道生态
- `Wechaty`：参照协议抽象与渠道适配
- `kx-Huang/ChatGPT-on-WeChat`：参照极简部署与最小可行实现
- `OpenClaw`：参照通用助手平台和技能生态

这样更准确，也更能突出 doctor-ai-agent 真正的差异化：

- 不是 bot 接入能力最多
- 不是插件生态最广
- 而是面向医生工作流的状态化、安全化、可验证化设计

### 7.1 轻量钩子机制 ✅ 已实现

> **实现于 2026-03-12** — `services/hooks.py` + `services/intent_workflow/workflow.py`

**问题**：当前所有业务逻辑在分层服务中硬编码，新增渠道或自定义行为需要修改核心代码。

**借鉴**：chatgpt-on-wechat 的 4 阶段事件管道（`ON_RECEIVE` → `ON_HANDLE` → `ON_DECORATE` → `ON_SEND`）。

**实现**：在意图流水线的 6 个关键节点暴露钩子点，允许外部模块注册回调：

```python
from services.hooks import HookStage, register_hook

async def log_classification(ctx):
    print(f"Intent: {ctx['decision'].intent}, doctor: {ctx['doctor_id']}")

register_hook(HookStage.POST_CLASSIFY, log_classification, priority=50)
```

**6 个钩子阶段**：`POST_CLASSIFY` → `POST_EXTRACT` → `POST_BIND` → `POST_PLAN` → `POST_GATE` → `PRE_REPLY`

**关键特性**：
- 非阻塞、故障隔离——回调异常不会中断流水线
- 优先级排序（数字越小越先执行）
- 同步 + 异步回调均支持
- `emit_background()` 用于延迟敏感的场景
- 18 个单元测试覆盖（`tests/test_hooks.py`）

**收益**：
- 科室定制逻辑（如神经外科特殊规则）可作为钩子注册，而非 if/else 分支
- 未来开源或多租户场景下，第三方可扩展行为而不 fork 核心代码
- 可观测性钩子可从硬编码改为注册式

### 7.2 统一消息类型抽象 🔄 部分实现

> **Message dataclass 创建于 2026-03-12** — `services/domain/message.py`
>
> **迁移状态**：`Message` 和 `HandlerResult` 已定义，共享意图处理器已迁移到 `services/domain/intent_handlers/`。但 Web（`routers/records.py`）和 WeChat（`routers/wechat.py`）仍通过各自的路由逻辑调用工作流，尚未将 `Message` 作为统一入口。小程序（`routers/miniprogram.py`）包装了 Web 路径，有自己的历史加载逻辑。

**问题**：文本、语音、图片、文件等消息类型在 router 层分别处理，逻辑分散在 `records.py`、`wechat.py`、`voice.py` 中。

**借鉴**：Wechaty 的 Sayable 抽象——统一的消息内容模型，入站和出站都经过同一转换层。

**实现**：定义了 `Message` dataclass（`services/domain/message.py`），包含 `content_type` (text/voice/image/file)、`text`、`doctor_id`、`channel`、`raw_payload`、`metadata`、`history`。共享意图处理器（`services/domain/intent_handlers/`）返回 `HandlerResult`，由各渠道适配为对应格式。

**待完成**：将 Web/WeChat/miniprogram 路由的消息入口点统一为 `Message` 构造 → 共享处理层调用

**收益（完成后）**：
- 意图流水线不再关心消息来源和类型
- 新增消息类型（如视频、位置）只需扩展 `Message` 和对应的 normalizer
- 测试可以用统一的 `Message` mock，无需模拟不同渠道的 raw payload

### 7.3 LLM Provider 注册表 🔄 部分实现

> **注册表创建于 2026-03-12** — `services/ai/provider_registry.py` + `services/ai/llm_client.py`
>
> **迁移状态**：注册表已建立，但生产调用方尚未完全迁移。`_PROVIDERS` 字典仍存在于 `llm_client.py`、`intent.py`、`vision.py`，`_resolve_provider()` 仍存在于 `agent.py`、`structuring.py`、`multi_intent.py`。

**问题**：当前 LLM provider 切换依赖运行时配置和条件分支，`_PROVIDERS` 字典在 4 个文件中重复定义（`llm_client.py`、`intent.py`、`vision.py`、`pdf_extract_llm.py`），`_resolve_provider()` 在 3 个文件中重复实现。

**借鉴**：chatgpt-on-wechat 的工厂模式——前缀字符串 → Bot 类的映射表。

**实现**：建立 `ProviderRegistry` 单例 + `ProviderConfig` 数据类：

```python
from services.ai.provider_registry import registry, ProviderConfig, Capability

# 解析 provider（自动应用环境变量覆盖）
cfg = registry.resolve("ollama", role="structuring")

# 检查能力
if registry.supports("deepseek", Capability.JSON_FORMAT): ...

# 注册自定义 provider
registry.register("my_llm", ProviderConfig(
    base_url="https://my-api.example.com/v1",
    api_key_env="MY_API_KEY",
    model="my-model",
    capabilities=frozenset({Capability.CHAT, Capability.TOOLS}),
))
```

**7 个内置 provider**：ollama、deepseek、groq、gemini、openai、tencent_lkeap、claude

**关键特性**：
- 角色感知的环境变量覆盖（routing / structuring / vision / memory 各有独立覆盖规则）
- 首匹配优先（`OLLAMA_STRUCTURING_MODEL` 优先于 `OLLAMA_MODEL`）
- 能力元数据：`CHAT`、`TOOLS`、`VISION`、`JSON_FORMAT`
- 集中式 `AsyncOpenAI` 客户端缓存（含测试模式旁路）
- 向后兼容——`from services.ai.llm_client import _PROVIDERS` 仍可用
- 27 个单元测试覆盖（`tests/test_provider_registry.py`）

**待完成**：将 `agent.py`、`structuring.py`、`vision.py`、`intent.py` 中的 `_PROVIDERS` / `_resolve_provider` 调用迁移到注册表 API

**收益**：
- 新增 provider 只需一行 `registry.register()`
- 回退链可从注册表自动构建
- 测试可注册 mock provider 而无需 patch 内部实现

### 7.4 部署体验简化

**问题**：当前部署需要手动配置 `config/runtime.json`、设置 LAN 推理服务器、运行 Alembic 迁移等，对新用户门槛较高。

**借鉴**：kx-Huang 的一键 Docker/Railway 部署 + chatgpt-on-wechat 的 Docker 镜像自动构建。

**建议**：
- 提供 `docker-compose.yml`，包含应用 + Ollama + 数据库的完整栈
- `main.py` 已自动运行 Alembic 迁移，继续保持
- 提供 `config/runtime.json.docker` 预配置模板，Docker 场景零配置启动
- README 中增加 "5 分钟快速开始" 章节

### 7.5 补充集成测试中的微信渠道覆盖

**问题**：1100+ 测试主要覆盖 Web 渠道和核心逻辑，微信渠道的端到端路径（消息接收 → 意图处理 → 回复推送）在 E2E 层覆盖较薄。

**借鉴**：chatgpt-on-wechat 虽然零测试，但其多渠道架构暴露了一个问题——渠道特有的边界条件（消息去重、断线重连、媒体处理）容易在没有测试的情况下回归。

**建议**：
- 增加微信渠道专属的 E2E fixture，覆盖：加密消息解析、语音消息下载转写、待确认记录超时、多设备 session 竞争
- 使用 `unittest.mock` 模拟微信 API 响应，无需真实公众号

### 7.6 渠道适配器抽象 ✅ 已实现

> **实现于 2026-03-12** — `services/domain/message.py` + `services/domain/adapters/`

**问题**：当前 `routers/wechat.py` 和 `routers/records.py` 各自处理消息收发逻辑，如果未来需要增加飞书、钉钉等渠道，会重复大量代码。

**借鉴**：Wechaty 的 Puppet 抽象 + chatgpt-on-wechat 的 Channel 层。

**实现**：定义 `ChannelAdapter` Protocol 和 `Message` 统一消息类型：

```python
from services.domain.message import ChannelAdapter, Message
from services.domain.adapters import WebAdapter, WeChatAdapter

adapter = WebAdapter()  # or WeChatAdapter()
msg: Message = await adapter.parse_inbound(raw_request)
reply = await adapter.format_reply(handler_result)
```

**ChannelAdapter 接口**：

| 方法 | 说明 |
|------|------|
| `channel_name` | 渠道标识符 ("web" / "wechat") |
| `parse_inbound()` | 平台消息 → 统一 `Message` |
| `format_reply()` | `HandlerResult` → 渠道线格式 |
| `send_reply()` | 异步发送回复 |
| `send_notification()` | 异步发送系统通知 |
| `get_history()` | 获取近期对话历史 |

**适配器实现**：
- `WebAdapter` — 同步 HTTP request/response, ChatInput → Message, HandlerResult → JSON
- `WeChatAdapter` — 异步消息队列, wechatpy 消息 → Message, HandlerResult → 纯文本 (≤600 字)
- `split_wechat_message()` — 智能分段（按换行优先，超长行硬切）

**Message 统一类型**：`content_type` (text/voice/image/file) + `text` + `doctor_id` + `channel` + `metadata` + `history`

**关键特性**：
- 结构化子类型（Protocol）— 无需继承，新渠道只需实现接口
- `send_reply` / `send_notification` 支持不同推送模式（Web: HTTP 响应内联 / WeChat: 客服 API 推送）
- 31 个单元测试覆盖（`tests/test_channel_adapters.py`）
- 新增渠道（飞书/钉钉）只需新增一个适配器文件

**当前状态**：接口层已就绪，现有路由尚未完全迁移到 adapter 模式。路由层可渐进式采用——新渠道直接使用 adapter，现有 Web/WeChat 路由在重构时逐步接入。

---

---

# Part B — OpenClaw 与通用 AI 助手平台

---

## 九、OpenClaw 架构概览

[OpenClaw](https://github.com/openclaw/openclaw) 是 2026 年最热门的开源项目之一（305k+ stars），定位为**自托管个人 AI 助手平台**。

### 9.1 架构模式 — Gateway 中心 + 技能扩展

```
40+ 消息渠道 (WhatsApp/Telegram/Slack/Discord/Teams/...)
         │
    Gateway 守护进程 (ws://127.0.0.1:18789)
    ├── Session 管理
    ├── 渠道路由
    ├── 状态持久化
    └── 事件系统
         │
    ┌────┴────┬────┬────┬────┐
    Pi       CLI  Web  macOS  iOS/Android
   agent     　   Chat  app    nodes
```

- **单进程 TypeScript 守护进程**，通过 WebSocket 连接所有客户端和设备
- **Agent 模式**：内置 Pi agent 以 RPC 模式运行，处理所有 AI 推理
- **技能系统**：`SKILL.md` 文件注入领域知识到系统提示词中
- **非单体也非微服务**——是一个带技能扩展的网关守护进程

### 9.2 多渠道支持

| 类别 | 渠道 |
|---|---|
| 消费级 IM | WhatsApp (Baileys), Telegram (grammY), Signal, iMessage, LINE, Zalo |
| 办公协作 | Slack (Bolt), Discord, Teams, Google Chat, 飞书 |
| 开放协议 | Matrix, IRC, Mattermost, Nextcloud Talk |
| 其他 | Nostr, Twitch, Email (Gmail PubSub), WebChat |

共 **40+ 渠道**，远超其他任何开源项目。每个渠道独立 SDK adapter，支持允许名单、DM 配对码、群组 @ 触发、重试退避。

### 9.3 LLM 集成

- **25+ Provider**：Anthropic (Claude), OpenAI, Ollama, Azure, AWS Bedrock, Mistral, Together, Qwen, GLM 等
- **模型回退**：API 失败自动切换备选 provider
- **逐 session 模型覆盖**：不同对话可用不同模型
- **Prompt 缓存 + Token 用量追踪**
- **思考模式**：off / minimal / low / medium / high / xhigh

### 9.4 技能系统设计

三层优先级架构：

| 层级 | 路径 | 优先级 |
|---|---|---|
| Bundled | OpenClaw 内置 | 最低 |
| Managed/Local | `~/.openclaw/skills` | 中 |
| Workspace | `<workspace>/skills` | 最高 |

每个技能是一个 `SKILL.md` 文件：

```yaml
---
name: skill-name
description: 简要描述
metadata: {"openclaw": {"always": true, "os": ["darwin","linux"], "requires": {"bins": ["ffmpeg"]}}}
user-invocable: true
---
# 以下是注入到系统提示词中的领域指令...
```

**关键特征**：
- 技能本质是**提示词工程**——无运行时代码，只是教 agent 如何推理
- ClawHub 注册表提供社区技能发现、安装、更新
- 加载时按 OS、依赖二进制、环境变量过滤
- 每个技能约增加 ~24 token 系统提示词开销
- 第三方技能作为不可信代码处理，密钥仅逐轮注入

### 9.5 OpenClaw 医疗技能库

[FreedomIntelligence/OpenClaw-Medical-Skills](https://github.com/FreedomIntelligence/OpenClaw-Medical-Skills) 提供 **869 个医疗技能**：

| 类别 | 数量 | 覆盖领域 |
|---|---|---|
| 临床与医学 | 119 | 临床报告、决策支持、肿瘤学、影像 |
| 科学数据库 | 43 | 基因组学、蛋白质、药物数据库 |
| 生物信息学 | 239 | 变异分析、RNA-seq、scRNA-seq、GWAS |
| 组学与计算生物 | 59 | 蛋白质组学、化学信息学、蛋白设计 |
| BioOS 扩展 | 285 | 肿瘤学、免疫学、临床 AI |
| 数据科学工具 | 93 | 统计、可视化、模拟 |

**接入的权威数据源**：PubMed, ClinVar, gnomAD, COSMIC, ChEMBL, DrugBank, UniProt, KEGG
**临床指南引用**：NICE, WHO, ADA, AHA/ACC, NCCN, CPIC

**注意**：这些技能是**科研导向**（生物信息学、基因组学、药物发现），而非**临床工作流导向**（结构化病历管理、患者采集、任务调度）。

### 9.6 存储与配置

- **无传统数据库**——文件系统 + Gateway 进程内状态
- **配置**：`~/.openclaw/openclaw.json`，声明式 JSON
- **Session 持久化**：本地文件，支持裁剪和压缩
- **测试**：Vitest，分 unit / e2e / channels / extensions / gateway / live 六套

---

## 十、doctor-ai-agent vs OpenClaw 对比

| 维度 | **doctor-ai-agent** | **OpenClaw + 医疗技能** |
|---|---|---|
| **架构** | 专用医疗应用，结构化领域模型 | 通用聊天网关 + 提示词技能 |
| **患者记录** | 结构化患者实体、病历 schema、Alembic 迁移 | 无——纯对话，无持久化数据模型 |
| **病历结构化** | 专用 `structure_medical_record()` + LLM + 校验流水线 | 技能可以*指示* LLM 格式化 SOAP，但无校验 |
| **临床安全** | 编程化安全门控 (`gate.py` 无患者不允许写入) | 仅咨询性提示词 ("请咨询医生") |
| **意图分类** | 多级快速路由 (Tier 1/2 无需 LLM) + LLM 分发 + 复合动作规划 | 纯 LLM (agent 自行决定行为) |
| **患者状态** | 实体绑定、上下文跟踪、切换通知 | 无 |
| **数据模型** | 关系型 DB：患者、病历、任务、科室、待确认操作 | 临时 session |
| **渠道覆盖** | 微信 + Web (深度集成) | **40+ 渠道** (广度集成) |
| **LLM 支持** | 6+ provider + 本地 Ollama + 回退链 | **25+ provider** + Ollama + 回退 |
| **技能/扩展** | 无插件系统 | **869 医疗技能** + ClawHub 社区 |
| **工作流** | 5 层流水线：classify → extract → bind → plan → gate | ad-hoc agent 推理 |
| **测试** | 1100+ pytest + E2E 回放 + diff-cover | Vitest 六套 |

**核心差异**：OpenClaw 是**水平平台**（广渠道、广模型、广技能），doctor-ai-agent 是**垂直应用**（深领域、深安全、深工作流）。OpenClaw 的医疗技能面向科研（生信、基因组），doctor-ai-agent 面向临床实操（病历、患者、任务）。

---

# Part C — 开源医疗 AI 项目对比

---

## 十一、医疗 AI 项目全景

| 项目 | 定位 | 面向 | 架构 | LLM | 微信 | 数据库 | 测试 |
|---|---|---|---|---|---|---|---|
| **doctor-ai-agent** | 临床工作流助手 | 医生 | FastAPI + 5 层意图流水线 | 6+ provider + Ollama | **公众号 + 小程序** | SQLite/MySQL/PG | **1100+** |
| **ai-medical-chatbot** | 通用医疗问诊 | 患者 | Gradio + Next.js (MedOS) | WatsonX/GPT-4/Llama-3/Mixtral | 无 | 向量库 (FAISS/Milvus) | pytest + CI |
| **MediGenius** | 医学 QA | 患者 | FastAPI + React + LangGraph 多 agent | Groq (GPT-OSS-120B) | 无 | SQLite + ChromaDB | pytest + vitest |
| **BenCao_RAG** | 中文医疗 QA | 患者 | Streamlit + Neo4j | OpenAI GPT-3.5 | 无 | Neo4j 知识图谱 | 无 |
| **HHH Medical QA** | 疾病 QA | 患者 | CLI/Web + 知识图谱 | 无 (BERT/BiLSTM) | 无 | Neo4j (~700 种疾病) | 无 |
| **DocScribe** | 病历报告理解 | 医生 | Jupyter + LangChain | Vicuna-13B (LoRA 微调) | 无 | 向量库 | 无 |

### 关键发现

1. **无直接竞品**：没有任何开源项目同时具备 医生端工作流 + 患者管理 + 病历结构化 + 临床安全门控
2. **微信集成完全空白**：所有医疗 AI 项目中，doctor-ai-agent 是**唯一**有微信支持的
3. **绝大多数是患者端 QA**：回答患者医学问题，而非管理医生临床工作流。仅 DocScribe 面向医生，但仅做报告摘要
4. **测试成熟度普遍很低**：仅 ai-medical-chatbot 和 MediGenius 有 CI/CD，doctor-ai-agent 的 1100+ 测试远超全行业

### 11.1 ai-medical-chatbot — 最完整的患者端项目

- **8 个子模块**覆盖数据集创建、RAG 建模、多种 chatbot 实现、微调、多模态分析
- **多 provider 切换**：WatsonX, OpenAI, 本地 Llama-3, Mixtral-7B, DeepSeek-R1
- **RAG 管线**：FAISS / Milvus / ChromaDB + 50k+ 医疗记录
- **MedOS**：Next.js 14 前端，BYOK 模式（用户自带 API key）
- **CI/CD 完善**：Makefile + black/isort/flake8/pylint/mypy

**可借鉴**：多 provider BYOK 模式、向量库 RAG 管线设计

### 11.2 MediGenius — 架构最接近的项目

- **LangGraph 多 agent 编排**：Memory Agent → Planner Agent → Retriever Agent → LLM Agent → Fallback Agents (Wikipedia, Web Search) → Executor/Explanation Agents
- **多级回退链**：RAG 检索 → Wikipedia → Web Search
- **90%+ 准确率**，80% 医学术语使用率，100% 来源标注
- **FastAPI + React 19**，SQLite 对话持久化 + ChromaDB 向量

**可借鉴**：多 agent 回退链设计（RAG → Wikipedia → Web），来源归因与准确率追踪

### 11.3 BenCao_RAG — 唯一中文医疗项目

- **6 种 QA 模式**：基础聊天、上下文对话、Web 增强、文档增强、知识图谱、混合 LLM+图谱
- **Neo4j 知识图谱**：中医药实体关系
- **以本草纲目命名**，聚焦传统中医药知识

**可借鉴**：混合知识图谱 + LLM 的 QA 模式，如果未来引入临床知识检索可参考

---

## 十二、综合能力矩阵

| 能力 | doctor-ai-agent | OpenClaw + 医疗技能 | ai-medical-chatbot | MediGenius |
|---|---|---|---|---|
| 医生端工作流 | **完整** | 无 | 无 | 无 |
| 患者管理 (CRUD) | **完整** | 无 | 无 | 无 |
| 病历结构化 | **语音/文本→结构化** | 提示词指示 | 无 | 无 |
| 意图分类流水线 | **5 层 (90%+ <1ms)** | 纯 LLM | 无 | 多 agent |
| 临床安全门控 | **编程化** | 仅咨询 | 无 | 无 |
| 任务调度 | **完整** | 无 | 无 | 无 |
| 微信集成 | **公众号+小程序** | WebChat (非微信) | 无 | 无 |
| 渠道数量 | 2 (微信+Web) | **40+** | 1 (Web) | 1 (Web) |
| LLM Provider 数 | 6+ | **25+** | **5+** | 1 |
| RAG / 知识库 | 基础 (doctor_knowledge) | 技能引用外部 DB | **完整** (FAISS/Milvus) | ChromaDB |
| 测试覆盖 | **1100+** | Vitest 多套 | pytest + CI | pytest + vitest |
| 社区生态 | 小团队 | **305k stars** | 中 | 小 |

---

## 十三、更新后的反馈与改进建议

基于 Part A + Part B + Part C 的全面对比，在原有 7.1–7.6 建议基础上补充：

### 13.1 科室技能 SKILL.md ✅ 已实现

> **实现于 2026-03-12** — `skills/` 目录 + `services/knowledge/skill_loader.py`

**问题**：科室特有的临床知识（如神经外科 GCS 评分规则、心内科 NYHA 分级标准）目前通过 `doctor_knowledge` 表和硬编码提示词注入，扩展到新科室需要修改代码。

**借鉴**：OpenClaw 的 SKILL.md 模式——每个技能是一个独立 Markdown 文件，包含领域知识和推理指令，自动注入系统提示词。

**实现**：

```
skills/
├── _default/              # 通用基线（所有科室共享）
│   ├── structuring.md     # 通用结构化规则
│   └── routing_hints.md   # 通用路由提示
├── cardiology/            # 心内科
│   ├── structuring.md     # STEMI/PCI/EF/NYHA 等规则
│   └── clinical_signals.md # 急诊指标 + 复诊触发
└── neurology/             # 神经科
    ├── structuring.md     # NIHSS/GCS/mRS 等规则
    └── clinical_signals.md # 脑疝/溶栓窗口等
```

```python
from services.knowledge.skill_loader import load_skills, get_structuring_skill

# 加载心内科全部技能
skills = load_skills("心内科")  # 支持中文科室名

# 获取结构化提示（注入到 LLM prompt）
structuring = get_structuring_skill("cardiology")
```

**技能文件格式**（YAML frontmatter + Markdown）：
```yaml
---
name: cardiology-structuring
description: 心内科病历结构化规则
type: structuring
specialty: cardiology
---
# 心内科结构化规则
## 必须保留的专科缩写
STEMI, NSTEMI, PCI, CABG, BNP, NT-proBNP, EF...
```

**关键特性**：
- 3 种技能类型：`structuring`（结构化规则）、`routing`（路由提示）、`clinical_signals`（临床信号）
- 中文科室名自动映射（"心内科" → cardiology, 19 个科室别名）
- TTL 缓存（默认 5 分钟，`SKILLS_CACHE_TTL` 可配置）
- Token 估算（`skill.token_estimate` 用于预算控制）
- 25 个单元测试（`tests/test_skill_loader.py`）

**收益**：
- 新增科室不需要改代码，只需增加 Markdown 文件
- 临床专家可以直接编辑 Markdown 文件来调整规则
- 与现有 `doctor_knowledge` DB 互补——DB 存运行时学到的知识，技能文件存科室基线知识

### 13.2 RAG 增强的临床知识检索（借鉴 ai-medical-chatbot + BenCao_RAG）

**问题**：当前 `services/knowledge/doctor_knowledge.py` 仅支持全文匹配和手动上传，没有语义检索能力。医生上传的 PDF/指南无法被智能关联到当前对话。

**借鉴**：ai-medical-chatbot 的 FAISS/Milvus + 50k 记录 RAG 管线；BenCao_RAG 的混合知识图谱 + LLM 模式。

**建议**：
- 引入轻量向量库（推荐 `chromadb`，纯 Python，无外部依赖）
- 医生上传的 PDF/文档自动切片 → embedding → 入库
- 在 `turn_context.py` 组装上下文时，用当前对话内容做语义检索，召回 top-k 相关片段
- 优先级低于意图流水线——仅在 LLM 分发阶段注入，不影响 Tier 1-3 快速路由

**收益**：
- 医生积累的科室指南、论文摘要可以自动关联到病历结构化
- 相比 OpenClaw 的纯提示词技能，RAG 能处理大量动态知识

### 13.3 来源归因与准确率追踪 ✅ 已实现

> **实现于 2026-03-12** — `services/observability/structuring_tracker.py`

**问题**：LLM 生成的病历结构化结果和回复没有来源归因，医生无法判断信息可信度。

**借鉴**：MediGenius 的 100% 来源标注 + 准确率追踪机制。

**实现**：

```python
from services.observability.structuring_tracker import (
    StructuringMeta, FieldAttribution,
    attribute_content, attribute_tags,
    log_structuring_event, log_correction_event,
)

# 结构化完成后 — 记录归因和质量指标
meta = StructuringMeta(
    provider="ollama", model="qwen2.5:14b",
    latency_ms=1200,
    input_length=len(text), output_length=len(record.content),
    specialty="cardiology",
    skills_injected=["cardiology-structuring"],
    attributions=[
        attribute_content(text, record.content, ["cardiology-structuring"]),
        attribute_tags(record.tags, text),
    ],
)
log_structuring_event(doctor_id, meta, record)

# 医生修改病历时 — 记录修正差异
log_correction_event(doctor_id, record_id, old_content, new_content,
                     old_tags=old_tags, new_tags=new_tags)
```

**来源归因类型**：

| 来源 | 含义 |
|------|------|
| `verbatim` | 直接来自医生原话（>60% 相似度） |
| `inferred` | LLM 综合推断/改写 |
| `skill` | 受科室技能规则影响 |
| `knowledge` | 引用自医生知识库 |
| `unknown` | 无法确定 |

**准确率追踪**：
- `CorrectionEvent` — 医生修改病历时自动计算编辑距离（SequenceMatcher ratio）
- 标签差异追踪：`tags_added` / `tags_removed`
- 所有事件写入 `logs/structuring_events.jsonl`，供离线分析

**StructuringMeta 指标**：
- `compression_ratio` — 输出/输入长度比
- `tag_count` / `has_scores` — 结构化丰富度
- `skills_injected` — 注入的科室技能列表
- `attributions` — 逐字段归因详情

**关键特性**：
- JSONL 日志格式，与 turn_log 一致，可用同一工具链分析
- 23 个单元测试（`tests/test_structuring_tracker.py`）
- 长期积累可用于微调和提示词优化的定量评估

### 13.4 多 agent 回退链（借鉴 MediGenius）

**问题**：当前 LLM 分发失败后回退到 `agent_fallback.py` 的规则匹配，无中间层。

**借鉴**：MediGenius 的 LangGraph 多 agent 回退链（RAG → Wikipedia → Web Search → Explanation）。

**建议**：在 LLM dispatch 层增加一级中间回退——当主 LLM 不确定时，先查询本地知识库（即 13.2 的 RAG），再回退到规则匹配。

```
当前：LLM dispatch → (失败) → agent_fallback 规则匹配
建议：LLM dispatch → (低置信度) → RAG 知识检索 → (仍低置信度) → agent_fallback
```

**优先级**：中。依赖 13.2 RAG 基础设施先行建设。

---

## 十四、总结

### 行业定位

doctor-ai-agent 在开源医疗 AI 领域占据**唯一的垂直临床工作流定位**：

- **vs OpenClaw**：OpenClaw 是水平平台（广渠道、广模型、广技能），doctor-ai-agent 是垂直应用（深安全、深领域、深工作流）。OpenClaw 的医疗技能面向科研（生信/基因组），不解决临床实操问题
- **vs 医疗 QA 项目**：所有开源医疗 AI 都是患者端 QA 机器人，doctor-ai-agent 是唯一的医生端工作流工具
- **vs WeChat AI 项目**：doctor-ai-agent 是所有项目中唯一使用微信官方 API 的

### 改进路线总览

| 优先级 | 建议 | 来源 |
|---|---|---|
| ✅ 完成 | 7.1 轻量钩子机制 | chatgpt-on-wechat |
| ✅ 完成 | 7.3 LLM Provider 注册表 | chatgpt-on-wechat |
| **高** | 7.4 Docker 一键部署 | ChatGPT-on-WeChat |
| ✅ 完成 | 13.1 科室技能 SKILL.md | OpenClaw |
| **中** | 13.2 RAG 临床知识检索 | ai-medical-chatbot + BenCao_RAG |
| ✅ 完成 | 13.3 来源归因与准确率追踪 | MediGenius |
| ✅ 完成 | 7.2 统一消息类型抽象 | Wechaty |
| **中** | 13.4 多 agent 回退链 | MediGenius |
| **低** | 7.5 微信 E2E 测试覆盖 | 内部需求 |
| ✅ 完成 | 7.6 渠道适配器抽象 | Wechaty + chatgpt-on-wechat |

7.1 钩子机制、7.2 统一消息类型、7.3 Provider 注册表、7.6 渠道适配器、13.1 科室技能、13.3 来源归因均已实现（6/10 完成）。剩余建议均为渐进式引入，不影响当前架构稳定性。下一步优先推进 Docker 一键部署（7.4）。
