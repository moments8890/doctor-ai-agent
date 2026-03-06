# 专科医师AI智能体 — 测试手册

> Last updated: 2026-03-01 · Phase 2

---

## 一、自动化测试

```bash
cd app
.venv/bin/pytest -v          # 97 tests, all passing
.venv/bin/pytest -v -k crud  # only DB tests
.venv/bin/pytest -v -k intent_rules  # only rule-based intent tests
```

| 测试文件 | 数量 | 覆盖范围 |
|----------|------|----------|
| `test_crud.py` | 18 | 数据库 CRUD、隔离性、排序 |
| `test_session.py` | 7 | 内存会话逻辑 |
| `test_intent.py` | 7 | LLM 意图路径（已 mock） |
| `test_intent_rules.py` | 31 | 规则引擎：意图、实体、心内科词库、急救、CV 指标 |
| `test_patients_api.py` | 6 | REST 接口 |
| `test_wechat_intent.py` | 28 | 完整分发链：建档/记录/查询/急救/格式化/消息分块 |

所有 DB 测试使用内存 SQLite，所有 LLM 调用已 mock，**无需网络即可运行**。

---

## 二、手动测试前置条件

```bash
# 1. 启动 Ollama（本地 LLM）
ollama serve                        # 保持后台运行
ollama pull qwen2.5:7b              # 首次需要

# 2. 确认 .env 配置
cat .env
# LLM_PROVIDER=ollama
# INTENT_PROVIDER=local
# WECHAT_TOKEN=...
# WECHAT_APP_ID=...
# WECHAT_APP_SECRET=...

# 3. 启动 API
.venv/bin/uvicorn main:app --reload

# 4. 开启 ngrok（WeChat 回调需要 HTTPS）
ngrok http 8000
# 复制 https://xxxx.ngrok-free.app 填入微信公众平台 → 开发 → 基本配置
```

### 验证服务正常

```bash
curl http://localhost:8000/
# {"message":"专科医师AI智能体 API","version":"0.2.0"}
```

---

## 三、手动测试用例

### T1 — 新建患者（明确建档关键词）

**输入**
```
帮我建个新患者，李明，45岁男性
```

**预期回复**
```
✅ 已为患者【李明】建档，男性，45岁，后续病历将自动关联该患者。
```

**验证**
```bash
python scripts/db_inspect.py patients
# 应看到 李明 | 男 | 45
```

---

### T2 — 新建患者（无年龄/性别）

**输入**
```
新患者王芳
```

**预期回复**
```
✅ 已为患者【王芳】建档，后续病历将自动关联该患者。
```

---

### T3 — 病历记录（明确姓名，患者已存在）

> 前提：先完成 T1，李明已在库中

**输入**
```
李明今天头痛三天，诊断紧张性头痛，给予布洛芬口服
```

**预期**（约 5 秒后客服消息推送）
```
📌 已关联患者【李明】

📋 结构化病历

【主诉】
头痛三天

【现病史】
头痛持续三天

【诊断】
紧张性头痛

【治疗方案】
布洛芬口服
```

**验证**
```bash
python scripts/db_inspect.py patient 1  # 替换为李明的 id
```

---

### T4 — 病历记录（姓名未建档，自动建档）

> 前提：数据库中没有"赵雷"

**输入**
```
赵雷，发烧两天，37.8°，诊断上呼吸道感染，嘱多休息多饮水
```

**预期**（客服消息）
```
✅ 已为【赵雷】新建档并保存病历

📋 结构化病历
...
```

**验证**：数据库新增赵雷 + 一条病历记录。

---

### T5 — 病历记录（无姓名，沿用会话患者）

> 前提：先完成 T1（李明已建档，且是当前会话患者）

**输入**（不含姓名）
```
患者咳嗽五天，低烧37.5，诊断支气管炎，给予阿莫西林
```

**预期**（客服消息）
```
📌 已关联患者【李明】

📋 结构化病历
...
```

---

### T6 — 病历记录（无结构内容，Ollama 无法解析）

**输入**
```
王芳下午来了
```

**预期**
```
⚠️ 未能识别为有效病历，请发送完整的病历描述（包含主诉、诊断等信息）。
```

---

### T7 — 查询病历（指定患者）

> 前提：T3 完成，李明有一条病历

**输入**
```
查一下李明的记录
```

**预期**
```
📂 患者【李明】最近 1 条记录：

1. [2026-03-01] 主诉：头痛三天 | 诊断：紧张性头痛
```

---

### T8 — 查询病历（不指定患者，显示所有）

**输入**
```
查看历史记录
```

**预期**
```
📂 所有患者最近 N 条记录：

1. 【李明】[2026-03-01] 主诉：头痛三天 | 诊断：...
2. 【赵雷】[2026-03-01] 主诉：发烧两天 | 诊断：...
```

---

### T9 — 查询空记录

> 前提：T2 中王芳已建档，但无病历

**输入**
```
查一下王芳的病历
```

**预期**
```
📂 患者【王芳】暂无历史记录。
```

---

### T10 — 列出所有患者

**输入**
```
所有患者
```
或
```
我的患者列表
```

**预期**
```
👥 共 3 位患者：

1. 李明（男、45岁）
2. 王芳
3. 赵雷（...）

发送「查询[姓名]」查看病历
```

---

### T11 — 心内科病历（含 CV 指标）

**输入**
```
张伟，65岁男性，胸痛2小时，血压160/100，心率95，心电图ST段抬高，诊断STEMI，立即PCI，双抗治疗
```

**预期**（客服消息，含完整心内科字段）
```
✅ 已为【张伟】新建档并保存病历

📋 结构化病历

【主诉】
胸痛2小时

【现病史】
血压160/100，心率95，心电图ST段抬高

【诊断】
STEMI（急性ST段抬高型心肌梗死）

【治疗方案】
立即行PCI，双联抗血小板治疗
```

**后台日志应显示**
```
[WeChat] cv_metrics={'bp_systolic': 160, 'bp_diastolic': 100, 'heart_rate': 95}
```

---

### T12 — 急救场景（紧急标记）

**输入**
```
3床室颤，立即除颤
```

**预期**（客服消息）
```
🚨 【紧急记录已保存】

📋 结构化病历

【主诉】
室颤

【治疗方案】
立即除颤
```

**后台日志**
```
[WeChat msg] peek intent=Intent.add_record
[WeChat] cv_metrics={}
```

---

### T13 — 未知意图（help 消息）

**输入**
```
你好
```
或
```
今天天气真好
```

**预期**（同步回复，无 LLM 调用）
```
您好！我是医生助手，请发送以下内容：

📋 病历记录 — 直接描述症状、诊断和治疗
👤 新建患者 — 例如：新患者李明，45岁男性
🔍 查询病历 — 例如：查一下李明的记录
👥 所有病人 — 查看患者列表
```

---

## 四、心内科专项测试

以下消息应全部被识别为 `add_record`（可在服务日志中确认）：

| 输入 | 应识别 intent | 备注 |
|------|--------------|------|
| `患者胸痛两小时，心电图ST段抬高` | add_record | STEMI 典型表现 |
| `老李房颤，心率120，准备射频消融` | add_record | 含心率指标 |
| `EF值只有35%，气短加重，调整利尿剂` | add_record | EF指标 |
| `双抗治疗中，今天牙龈出血` | add_record | 抗凝出血风险 |
| `BNP 800，心衰加重，加用托拉塞米` | add_record | BNP + 心衰 |
| `冠脉造影结果，三支病变，建议搭桥` | add_record | CAG + CABG |
| `患者心跳停止，立即心肺复苏` | add_record (🚨) | 触发急救标记 |

---

## 五、边界条件测试

| 场景 | 输入 | 预期 |
|------|------|------|
| 建档无姓名 | `帮我建个新患者` | ⚠️ 未能识别患者姓名 |
| 纯数字 | `123456` | help 消息 |
| 空消息 | （空白） | 请发送文字病历记录 |
| 超长病历 | >600 字符的病历 | 分多条客服消息发送 |
| 重复建档 | 对同名患者再次 `新患者李明` | 建新档（当前不去重） |

---

## 六、数据库验证

```bash
# Web UI（推荐）
open http://localhost:8000/admin

# CLI 快查
python scripts/db_inspect.py patients          # 所有患者
python scripts/db_inspect.py records           # 最近10条病历
python scripts/db_inspect.py patient <id>      # 指定患者详情
python scripts/db_inspect.py record <id>       # 指定病历详情

# 原始 SQL
sqlite3 -column -header patients.db "SELECT id,name,gender,age FROM patients;"
sqlite3 -column -header patients.db "SELECT id,patient_id,chief_complaint,diagnosis FROM medical_records;"
```

---

## 七、常见问题排查

| 现象 | 可能原因 | 解决 |
|------|----------|------|
| 病历无回复（>10 秒） | Ollama 未启动 | `ollama serve` |
| 病历结构化失败 | Qwen2.5 未下载 | `ollama pull qwen2.5:7b` |
| 微信验证失败 | Token/ngrok URL 不匹配 | 检查 `.env` + 微信平台配置 |
| 查询患者返回空 | doctor_id (openid) 不匹配 | 检查 `WECHAT_APP_ID` 是否变更 |
| 首条病历超时 | Ollama 冷启动 | 已有 warmup，重启后第一条可能仍稍慢 |
| 客服消息未送达 | access_token 失效 | 检查日志 `[WeChat token]`，自动刷新 |
