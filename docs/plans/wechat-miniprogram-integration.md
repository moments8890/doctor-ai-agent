# 微信小程序集成探索（基于当前代码库）

## 结论（先说结果）

当前项目已经具备可复用的核心能力：
- 后端业务链路（`/api/records/chat`、患者/病历/任务）完整
- 已有微信生态接入经验（公众号/企微客服路由）
- 数据模型已开始从“纯 openid”向“doctor registry”演进（`doctors` 表）

**最小成本路径**：保留现有 FastAPI 业务后端，新增“小程序登录鉴权层 + 小程序前端层”，避免重写 AI/病历主流程。

---

## 现状与小程序差距

### 已具备
- 多数业务已是 REST 化接口，可直接被小程序调用：
  - `POST /api/records/chat`
  - `GET /api/manage/patients`
  - `GET /api/manage/records`
  - `GET/PATCH /api/tasks`
  - `POST /api/voice/chat`
- 后端内部以 `doctor_id` 做租户隔离，链路统一。

### 关键缺口
- REST 接口当前普遍由客户端直接传 `doctor_id`，缺少服务端身份校验。
- 没有小程序登录态入口（`code -> openid/session` 映射）。
- 通知能力当前偏向公众号客服消息，需要补小程序订阅消息或站内提醒策略。
- 前端是 Vite + React，不可直接当微信小程序运行。

---

## 推荐集成路线

## 路线 A（推荐）：后端保留 + 新建小程序前端

1. 小程序侧：`wx.login` 获取 `code`。
2. 后端新增 `POST /api/auth/wechat-mini/login`：
   - 调微信 `code2session` 换 `openid`（+ 可选 `unionid`）
   - 绑定/创建内部 doctor（建议 canonical `doctor_id`）
   - 签发后端会话 token（JWT 或 server session）
3. 业务 API 改为从 token 解析 doctor 身份，不再信任请求内 `doctor_id`。
4. 小程序页面调用现有业务 API。

优点：
- 改动集中在“鉴权层 + 前端适配层”，风险最低
- AI 和病历主链路几乎不动
- 可保留 Web 前端并行运行

---

## 路线 B：迁移到跨端框架（Taro/uni-app）复用前端逻辑

- 将现有 React 页面迁到跨端框架，以便同时输出 H5 + 小程序。
- 适合长期多端统一，但一次性改造成本更高。

---

## 不建议路线

- 直接把现有 Vite React 页面“硬塞”小程序 WebView：
  - 体验和能力受限（系统 API/登录态/上传能力）
  - 临床录音/任务提醒等能力落地不稳定

---

## 后端改造清单（按优先级）

1. 鉴权基建（P0）
- 新增 `routers/auth.py`：
  - `POST /api/auth/wechat-mini/login`
  - `GET /api/auth/me`
- 新增 token 校验依赖（FastAPI dependency），统一注入 `current_doctor_id`。
- 把以下路由迁移到“服务端 doctor_id”模式：
  - `routers/records.py`
  - `routers/ui.py`
  - `routers/tasks.py`
  - `routers/voice.py`

2. 医生身份映射（P0）
- 复用并强化 `doctors` 表字段：`channel`, `wechat_user_id`。
- 建议规则：
  - 小程序登录后得到 `openid`，仅用于外部身份映射
  - 业务侧统一使用内部 `doctor_id`（避免渠道耦合）

3. 通知通道（P1）
- 在 `services/notification.py` 中新增 provider：`wechat_mini_subscribe`（或统一抽象 channel）。
- 支持两级通知：
  - 站内（小程序任务页红点/列表）
  - 订阅消息（预约、危急提醒）

4. 多媒体接口适配（P1）
- 小程序录音/上传对接：优先复用 `POST /api/voice/chat`。
- 增加上传大小、格式、超时、重试策略与可观测埋点。

---

## 前端（小程序）落地建议

1. MVP 页面
- 登录/初始化页
- AI对话页（文本 + 录音）
- 患者列表页
- 患者详情/病历时间线页
- 任务页（待办 + 完成）

2. API 封装
- 统一 `request()` 自动带 token
- 401 自动刷新或重新登录
- 把现在前端的 `doctorId` 参数模式改成“服务端解析身份”

3. 交互策略
- AI 响应可能较慢：保留“处理中”状态
- 上传语音时显示进度与失败重试
- 高风险任务固定入口（底部 Tab）

---

## 部署与微信侧配置

1. 必备
- HTTPS 公网域名
- 小程序后台配置合法域名（request/upload/websocket）
- 生产环境密钥管理（AppSecret、token 签名密钥）

2. 环境分层
- dev/staging/prod 分离 appid 与后端配置
- 后端 runtime config 增加小程序相关键（appid、secret、token ttl）

---

## 分阶段执行（建议 3 周）

### Week 1（P0）
- 完成小程序登录接口 + token 体系
- REST 全面接入鉴权，移除客户端可伪造 `doctor_id` 路径
- 联调文本聊天链路（`/api/records/chat`）

### Week 2（P1）
- 小程序完成患者/病历/任务页面
- 打通语音上传到 `/api/voice/chat`
- 增加关键可观测指标（鉴权失败率、接口延迟、语音失败率）

### Week 3（P1/P2）
- 通知通道升级（订阅消息 + 站内提醒）
- 回归测试 + 小规模医生试用
- 安全检查（token 失效、越权、重放）

---

## 本项目可直接复用的关键点

- AI dispatch 和结构化病历服务无需重写（`services/agent.py`, `services/structuring.py`）
- `doctors` registry 已有基础，可承接多渠道身份映射
- 任务系统与提醒调度可直接复用，主要补通知出口

---

## 风险与注意事项

- 最大风险不是 AI，而是**身份与权限**：必须优先做服务端鉴权。
- 小程序提醒依赖订阅授权，不能假设消息必达。
- 医疗场景建议保留“确认写入”机制，降低误写病历风险。

---

## 下一步（可立即启动）

1. 先做一个 `auth + chat` 的小程序最小闭环（不含管理页）。
2. 后端先完成统一鉴权依赖，再逐路由迁移。
3. 完成后再决定是否把 Web 前端迁到跨端框架。
