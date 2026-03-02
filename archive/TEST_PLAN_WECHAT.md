# WeChat Official Account — Real-World Test Plan

**Scope:** Phase 2 end-to-end manual testing via a real WeChat official account (service account or subscription account with message API enabled).
**Preconditions:**
- Server is running and publicly reachable (ngrok or production domain)
- WeChat backend is configured: server URL, token, AES key
- `.env` has valid `DEEPSEEK_API_KEY` (or `GROQ_API_KEY`) and WeChat credentials
- Tester is following the official account with a real WeChat account

---

## T-00 · Server Health

| Step | Action | Expected |
|------|--------|----------|
| 1 | `GET https://<your-domain>/` | `{"message": "专科医师AI智能体 API", "version": "0.2.0"}` |
| 2 | Check uvicorn logs on startup | `patients` and `medical_records` tables created (no errors) |
| 3 | WeChat backend → "Submit and verify" | Server returns `echostr`, status shows "配置成功" |

---

## T-01 · Menu Tap Responses

*Tap each menu item and verify the bot replies immediately (no LLM call needed).*

| Menu item | Expected reply (partial) |
|-----------|--------------------------|
| 患者 → 我的病历 | 请发送您的姓名，我将为您查询病历记录 |
| 患者 → 咨询医生 | 请直接发送您的问题 |
| 患者 → 使用说明 | 使用说明：… |
| 医生 → 新建患者 | 请发送患者信息，例如：帮我建个新患者 |
| 医生 → 录入病历 | 请发送病历描述 |
| 医生 → 查询病历 | 请发送患者姓名 |

**Pass criteria:** Reply arrives within 1 s; no "处理失败" or empty reply.

---

## T-02 · Create Patient (happy path)

**Send:**
```
帮我建个新患者，李明，45岁男性
```

**Expected reply:**
```
✅ 已为患者【李明】建档，男性，45岁，后续病历将自动关联该患者。
```

**Verify in DB:**
```bash
sqlite3 patients.db "SELECT * FROM patients;"
```
Row exists with `name=李明`, `gender=男`, `age=45`, `doctor_id=<your openid>`.

---

## T-03 · Create Patient — Minimal (name only)

**Send:**
```
新建患者王芳
```

**Expected reply:** Contains `王芳` and `建档`; no age/gender mentioned.

**Verify:** DB row has `gender=NULL`, `age=NULL`.

---

## T-04 · Create Patient — Missing Name

**Send:**
```
帮我建一个新患者
```

**Expected reply:** Contains `⚠️` and asks for a name (e.g., `未能识别患者姓名`).

**Verify:** No new row in `patients` table.

---

## T-05 · Add Medical Record (session patient, no name in message)

*Precondition: T-02 completed — 李明 is the current session patient.*

**Send:**
```
患者头痛两天，无发热，无呕吐。查体：神经系统检查正常。诊断：紧张性头痛。治疗：口服布洛芬400mg每日三次，共三天。一周后随访。
```

**Expected reply:**
```
📌 已关联患者【李明】

📋 结构化病历

【主诉】
头痛两天…
【诊断】
紧张性头痛
【治疗方案】
口服布洛芬…
```

**Verify in DB:**
```bash
sqlite3 patients.db "SELECT patient_id, chief_complaint, diagnosis FROM medical_records;"
```
`patient_id` matches 李明's `id`.

---

## T-06 · Add Medical Record (patient named in message)

*Start fresh session — do NOT send T-02 first.*

**Send:**
```
王芳今天咳嗽三天，低烧37.5°，诊断上呼吸道感染，给予连花清瘟胶囊，嘱多休息多饮水。
```

**Expected reply:** Contains `📌 已关联患者【王芳】` and structured record sections.

**Verify:** `medical_records` row linked to 王芳's patient id.

---

## T-07 · Add Record — No Patient Context

*Start fresh session with a doctor openid that has no patients and no session.*

**Send:**
```
患者发烧38.5度，咽痛，诊断急性咽炎，头孢克肟0.1g每日两次。
```

**Expected reply:** Structured record returned (no 📌 patient line) — record saved with `patient_id=NULL`.

**Verify:** DB row has `patient_id=NULL`.

---

## T-08 · Query Records (patient named in message)

*Precondition: T-05 has been run — 李明 has at least one record.*

**Send:**
```
查一下李明的历史记录
```

**Expected reply:**
```
📂 患者【李明】最近 1 条记录：

1. [2026-02-28] 主诉：头痛两天 | 诊断：紧张性头痛
```

---

## T-09 · Query Records (session patient, no name in message)

*Precondition: T-02 run first to set session patient to 李明.*

**Send:**
```
看看最近的病历
```

**Expected reply:** Same format as T-08, using 李明 from session.

---

## T-10 · Query Records — No Patient, No Session

*Fresh doctor openid with no patients.*

**Send:**
```
查一下病历
```

**Expected reply:** Contains `⚠️` and `未找到患者信息`.

---

## T-11 · Query Records — Patient Has No Records

*Create a patient (T-02) but do NOT send any records.*

**Send:**
```
查询李明的病历
```

**Expected reply:** Contains `暂无历史记录`.

---

## T-12 · Unknown Intent → Fallback Structuring

**Send:**
```
患者张伟，男，52岁。主诉：胸闷气短1周。现病史：1周前无明显诱因出现胸闷，活动后加重。既往高血压病史5年。查体：BP 150/95mmHg，心率82次/分，律齐。辅助检查：心电图示ST段压低。诊断：冠状动脉粥样硬化性心脏病。治疗：硝酸异山梨酯10mg每日三次，阿司匹林100mg每日一次。
```

**Expected reply:** Full structured record with all 8 sections — **no** `📌 已关联患者` header, **no** DB patient row created.

---

## T-13 · Unrelated Text → Fallback with Rejection

**Send:**
```
今天天气怎么样
```

**Expected reply:** Contains `⚠️ 未能识别为有效病历` — the fallback structuring call rejects non-medical content.

---

## T-14 · Session Persistence Within Conversation

**Sequence:**

| # | Send | Expected |
|---|------|---------|
| 1 | `新建患者赵丽，30岁女性` | 建档成功，session → 赵丽 |
| 2 | `发烧两天，诊断病毒性感冒，退烧药治疗` | 记录关联【赵丽】 |
| 3 | `查一下病历` | 显示赵丽的记录 |
| 4 | `新建患者陈强，55岁男性` | session 切换 → 陈强 |
| 5 | `高血压复查，血压140/90，继续原方案` | 记录关联【陈强】，不再是赵丽 |

---

## T-15 · Timeout Behaviour

*Temporarily set an artificially low timeout or saturate the LLM API.*

**Send:** Any long medical note.

**Expected reply (within 5 s):** `⏳ 处理超时，请重新发送消息。`

---

## T-16 · Non-Text Message Types

| Send | Expected |
|------|---------|
| A voice message | `请发送文字病历记录，我将自动生成结构化病历。` |
| An image | Same as above |
| A location share | Same as above |

---

## T-17 · REST API Sanity (curl)

```bash
# Create patient
curl -X POST "https://<domain>/api/patients?doctor_id=test_doc&name=测试患者&gender=男&age=40"

# List patients
curl "https://<domain>/api/patients/test_doc"

# List records (use id returned above)
curl "https://<domain>/api/patients/test_doc/1/records"
```

**Expected:** Valid JSON responses with correct fields.

---

## Pass / Fail Summary Sheet

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| T-00 | Server health | | |
| T-01 | Menu taps | | |
| T-02 | Create patient (full) | | |
| T-03 | Create patient (minimal) | | |
| T-04 | Create patient (no name) | | |
| T-05 | Add record via session | | |
| T-06 | Add record via message name | | |
| T-07 | Add record no patient | | |
| T-08 | Query by name | | |
| T-09 | Query via session | | |
| T-10 | Query no patient | | |
| T-11 | Query empty history | | |
| T-12 | Unknown intent → structuring | | |
| T-13 | Unrelated text → rejection | | |
| T-14 | Session persistence sequence | | |
| T-15 | Timeout | | |
| T-16 | Non-text messages | | |
| T-17 | REST API | | |
