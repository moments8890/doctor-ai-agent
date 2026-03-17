# Patient Pre-Consultation Interview — Design Spec

> Date: 2026-03-17
> Status: Draft
> ADR: 0016 (to be created from this spec)

## Goal

Patients complete a structured pre-consultation interview via web UI before
seeing the doctor. The AI conducts the interview like a junior doctor, collects
clinical history, and delivers a structured record to the doctor's task queue.

## Decisions

| Decision | Choice |
|----------|--------|
| Channel | Web first, WeChat mini-program deferred |
| Patient entry | Public URL `/patient`, select doctor via search |
| Registration | Name + gender + year_of_birth + phone |
| Auth | Phone + year_of_birth, scoped per doctor |
| Patient UI | WeChat-style chat, single column, mobile-first |
| Interview approach | Hybrid: free-form + completeness check |
| Pipeline | New interview pipeline (not UEC) |
| LLM strategy | Single prompt per turn with full context |
| After confirmation | MedicalRecord + DoctorTask (general) |
| Patient-doctor model | Keep patient.doctor_id FK (one record per doctor) |
| Clinical intelligence | None in v1; schema ready for Phase 2 |

---

## 1. Patient Entry & Registration

### Flow

```
Patient visits /patient
  → First time:
      1. Select doctor (search by name, filtered by accepting_patients=true)
      2. Registration form: name, gender, year_of_birth, phone
      3. Submit → link or create patient (see Linking below) → auto-login → home
  → Returning:
      1. Login: phone + year_of_birth
      2. If linked to one doctor → home
      3. If linked to multiple → doctor picker → home
```

### Doctor Selection

Doctors opt in via `accepting_patients` flag (default false). Patient sees
name + department. Search filters by name prefix.

### Auth Model

- Login: `phone + year_of_birth` validated against
  `WHERE doctor_id = ? AND phone = ? AND year_of_birth = ?`
- Returns JWT token (24h TTL) with patient_id + doctor_id
- Rate limit: 5 failed attempts per phone per 10 minutes
- Same phone can exist under different doctors (separate patient records)

### Linking to Doctor-Created Records

Registration matches by `(doctor_id, name)`. Name is assumed unique per doctor
for MVP. If a record exists, non-null fields are validated — mismatch rejects
with "信息与已有记录不符，请联系医生确认". Null fields are backfilled from
registration input.

```python
patient = await db.execute(
    select(Patient).where(
        Patient.doctor_id == doctor_id,
        Patient.name == name,
    )
).scalar_one_or_none()

if patient:
    # Conflict: non-null fields must not disagree
    if patient.gender and patient.gender != gender:
        raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
    if patient.year_of_birth and patient.year_of_birth != year_of_birth:
        raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
    if patient.phone and patient.phone != phone:
        raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
    # Backfill missing fields
    patient.gender = patient.gender or gender
    patient.year_of_birth = patient.year_of_birth or year_of_birth
    patient.phone = patient.phone or phone
    await db.flush()
    return issue_jwt(patient)
else:
    # Create new patient
    patient = Patient(doctor_id=doctor_id, name=name, ...)
```

### Schema Changes

```sql
-- doctors table
ALTER TABLE doctors ADD COLUMN accepting_patients BOOLEAN DEFAULT false;
ALTER TABLE doctors ADD COLUMN department VARCHAR(64);

-- patients table: ensure phone is indexed per doctor
CREATE INDEX ix_patients_doctor_phone ON patients(doctor_id, phone);
```

No changes to patient.doctor_id FK. Patient visiting multiple doctors gets
separate patient records (one per doctor).

---

## 2. Patient Home Page

Mobile-first, single entry point for all patient capabilities.

```
┌────────────────────────────┐
│  患者主页 — 王芳            │
├────────────────────────────┤
│  📋 开始预问诊    [新问诊]  │
│  📄 我的病历      (3条)     │
│  💬 给医生留言              │
│  📎 上传资料（照片/文件）    │
└────────────────────────────┘
```

- "开始预问诊" resumes active session if one exists, otherwise creates new
- "我的病历" reuses existing patient record view
- "给医生留言" reuses existing patient messaging
- "上传资料" extends existing import to patient context (deferred to v1.1)

---

## 3. Interview Chat UI

WeChat-style single column, mobile-first.

```
┌────────────────────────────┐
│  ← 退出  预问诊 — 张医生 [摘要 3/7]│
├────────────────────────────┤
│                            │
│  ┌──────────────────┐      │
│  │ 您好！请问您有什么│      │
│  │ 不舒服？         │      │
│  └──────────────────┘      │
│                            │
│      ┌──────────────────┐  │
│      │ 我头痛3天了       │  │
│      └──────────────────┘  │
│                            │
│  ┌──────────────────┐      │
│  │ 头痛是持续性的还是│      │
│  │ 间歇性的？       │      │
│  └──────────────────┘      │
│                            │
├────────────────────────────┤
│  [输入框............] [发送]│
└────────────────────────────┘
```

**Top bar:** "退出" button + doctor name + summary badge ("摘要 3/7"). Tap badge
opens summary sheet as a bottom overlay.

**Exit behavior:** "退出" shows a confirm dialog with two options:
- "保存退出" → session stays `interviewing`, return to home (resumes next visit)
- "放弃重来" → session → `abandoned`, return to home (next start creates fresh)

**Summary sheet:**

```
┌────────────────────────────┐
│  已收集信息          [关闭] │
├────────────────────────────┤
│  ✅ 主诉：头痛3天          │
│  🔄 现病史：收集中...       │
│  ⬜ 既往史                 │
│  ⬜ 过敏史                 │
│  ⬜ 个人史                 │
│  ⬜ 家族史                 │
│                            │
│  [确认提交]  (disabled)     │
└────────────────────────────┘
```

Confirm button enables when completeness check passes. On confirm, patient
reviews full summary and submits.

---

## 4. Interview Pipeline Architecture

Separate from UEC pipeline. Shares LLM providers, DB models, notification
system, prompt loader.

```
┌─────────────────────────────────────────────────┐
│              Shared Infrastructure               │
│  LLM providers · DB models · Notifications       │
│  Prompt loader · Medical record schema           │
└──────────┬──────────────────────┬────────────────┘
           │                      │
   ┌───────▼───────┐    ┌────────▼─────────┐
   │  UEC Pipeline  │    │ Interview Pipeline│
   │  (doctor-side) │    │  (patient-side)   │
   │                │    │                   │
   │ understand     │    │ session manager   │
   │ resolve        │    │ interview LLM     │
   │ commit/read    │    │ field extractor   │
   │ compose        │    │ completeness check│
   └───────▲───────┘    └────────▲──────────┘
           │                      │
     Doctor UI/WeChat      Patient Web UI
```

**Handoff:** Interview pipeline creates MedicalRecord + DoctorTask. Doctor
interacts with it through normal UEC pipeline.

---

## 5. Interview Session Model

```sql
CREATE TABLE interview_sessions (
    id              VARCHAR(36) PRIMARY KEY,  -- UUID
    doctor_id       VARCHAR(64) NOT NULL REFERENCES doctors(doctor_id),
    patient_id      INTEGER NOT NULL REFERENCES patients(id),
    status          VARCHAR(16) NOT NULL DEFAULT 'interviewing',
        -- interviewing | reviewing | confirmed | abandoned
    collected       TEXT,       -- JSON dict of extracted fields
    conversation    TEXT,       -- JSON array [{role, content, timestamp}, ...]
    turn_count      INTEGER DEFAULT 0,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
);

CREATE INDEX ix_interview_patient ON interview_sessions(patient_id, status);
CREATE INDEX ix_interview_doctor ON interview_sessions(doctor_id, status);
```

Status transitions: `interviewing → reviewing → confirmed`
Patient can also: `interviewing → abandoned` (via exit button).
No session expiry — abandoned sessions stay for record-keeping; cleanup
can be added later if needed.

---

## 6. Turn Handler (Core Loop)

```python
MAX_TURNS = 30

async def interview_turn(session_id: str, patient_text: str) -> InterviewResponse:
    session = load_session(session_id)
    # Validate: not abandoned, not already confirmed
    session.conversation.append({"role": "user", "content": patient_text})
    session.turn_count += 1

    # Force review if turn limit reached
    if session.turn_count >= MAX_TURNS:
        session.status = "reviewing"
        summary = generate_review_summary(session.collected)
        reply = "我已经收集了足够的信息，请查看摘要并确认。\n\n" + summary
        session.conversation.append({"role": "assistant", "content": reply})
        save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress={"filled": count_filled(session.collected), "total": 7},
            status=session.status,
        )

    # Main LLM call with parse-failure fallback
    try:
        llm_response = await call_interview_llm(
            conversation=session.conversation,
            collected=session.collected,
            patient_info=load_patient_info(session.patient_id),
        )
    except (JSONDecodeError, KeyError):
        reply = "抱歉，我没有理解，请再说一次。"
        session.conversation.append({"role": "assistant", "content": reply})
        save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress={"filled": count_filled(session.collected), "total": 7},
            status=session.status,
        )

    # Merge extracted fields
    merge_extracted(session.collected, llm_response.extracted)

    # Completeness check
    missing = check_completeness(session.collected)

    if not missing:
        session.status = "reviewing"
        summary = generate_review_summary(session.collected)
        reply = f"我已经收集了您的基本信息。请查看摘要确认是否准确。\n\n{summary}"
    else:
        reply = llm_response.reply

    session.conversation.append({"role": "assistant", "content": reply})
    save_session(session)

    return InterviewResponse(
        reply=reply,
        collected=session.collected,
        progress={"filled": count_filled(session.collected), "total": 7},
        status=session.status,
    )
```

---

## 7. Interview LLM Prompt

Single prompt per turn with full context. Located at `src/prompts/patient-interview.md`.

```markdown
# 预问诊助手

你正在帮助患者完成预问诊。像一位耐心的初级医生一样询问。

## 患者信息
姓名：{name}　性别：{gender}　年龄：{age}岁

## 已收集
{collected_json}

## 待收集
{missing_fields}

## 对话历史
{conversation}

## 规则
- 用通俗友善的语言，避免专业术语
- 每次只问1-2个问题
- 从回答中提取临床信息填入对应字段
- 不做诊断，不给处方
- 患者说"没有"或"不知道" → 提取为"无"或"不详"（不要留空），继续下一项
- 主诉收集完后，通过追问完善现病史

## 输出（严格JSON）
{
  "reply": "下一个问题",
  "extracted": {"field_name": "value", ...}
}
```

---

## 8. Field Extraction & Completeness

### Collected Fields

| Priority | Field | Collection | Merge Strategy |
|----------|-------|------------|----------------|
| Required | `chief_complaint` | "有什么不舒服？" | Overwrite |
| Required | `present_illness` | Follow-up questions on symptoms | Append |
| Ask | `past_history` | "以前有什么疾病或手术？" | Append |
| Ask | `allergy_history` | "有药物或食物过敏吗？" | Append |
| Ask | `family_history` | "家里人有类似疾病吗？" | Append |
| Ask | `personal_history` | "有吸烟饮酒习惯吗？" | Append |
| Optional | `marital_reproductive` | Only if contextually relevant | Append |
| Skip | `physical_exam` through `orders_followup` | Doctor fills | N/A |

### Merge Logic

```python
APPENDABLE = {"present_illness", "past_history", "allergy_history",
              "family_history", "personal_history", "marital_reproductive"}

def merge_extracted(collected: dict, extracted: dict):
    for field, value in extracted.items():
        if not value:
            continue
        if field in APPENDABLE:
            existing = collected.get(field, "")
            collected[field] = f"{existing}；{value}".strip("；") if existing else value
        else:
            collected[field] = value
```

### Completeness Check

```python
REQUIRED = {"chief_complaint", "present_illness"}
ASK_AT_LEAST = {"past_history", "allergy_history", "family_history", "personal_history"}

def check_completeness(collected: dict) -> list[str]:
    missing = [f for f in REQUIRED if not collected.get(f)]
    if not missing:
        missing = [f for f in ASK_AT_LEAST if f not in collected]
    return missing
```

Transition to reviewing when `missing` is empty.

### Progress Total

Progress reports `total: 7` — the 7 patient-collectable fields (2 required + 4 ask +
1 optional). `marital_reproductive` counts toward displayed progress but does not
block the completeness gate.

---

## 9. Handoff to Doctor

When patient confirms:

1. **Generate MedicalRecord:**
   - `content`: prose narrative from collected fields
   - `structured`: collected fields dict (maps directly to 14-field schema)
   - `tags`: extracted from chief_complaint + present_illness
   - `record_type`: `"interview_summary"`
   - `needs_review`: `true`

2. **Create DoctorTask:**
   - `task_type`: `"general"`
   - `title`: `"审阅预问诊：{patient_name}"`
   - `patient_id`: linked patient
   - `record_id`: the new record (title + record_type carry interview semantics)
   - `status`: `"pending"`

3. **Notify doctor** via existing notification system (web badge + WeChat push)

4. **Patient sees:** confirmation message, record appears in "我的病历"

5. **Doctor workflow:** task appears in task list → opens record → reviews/edits
   via normal UEC pipeline (query, update) → marks task complete

---

## 10. File Structure

### New Files

```
src/
  channels/web/
    patient_ui.py                  — patient web routes (login, home, interview pages)
  services/patient_interview/
    __init__.py
    session.py                     — InterviewSession: load, save, abandon
    turn.py                        — interview_turn() core loop
    completeness.py                — check_completeness(), merge_extracted()
    summary.py                     — generate prose + structured from collected
  prompts/
    patient-interview.md           — interview LLM prompt
  db/models/
    interview_session.py           — InterviewSessionDB SQLAlchemy model
```

### Modified Files

```
src/
  channels/web/patient_portal.py   — add register-by-phone, login-by-phone, doctor search
  db/models/doctor.py              — add accepting_patients, department columns
frontend/src/pages/
  PatientPage.jsx                — rewrite: login, home, doctor picker, interview chat
```

### Not Touched

- UEC pipeline (services/runtime/) — unchanged
- Structuring service — not used during interview
- WeChat channel — deferred to mini-program phase

---

## 11. API Endpoints

```
# Patient auth (extend existing patient_portal.py)
POST   /api/patient/register          — name, gender, year_of_birth, phone, doctor_id
POST   /api/patient/login             — phone + year_of_birth (+ doctor_id if multi)
GET    /api/patient/doctors           — list doctors accepting patients (name, department)

# Interview (new)
POST   /api/patient/interview/start   — create session → session_id + greeting
POST   /api/patient/interview/turn    — session_id + text → reply + collected + progress
GET    /api/patient/interview/current — active session state (or null)
POST   /api/patient/interview/confirm — finalize → creates record + task
POST   /api/patient/interview/cancel  — abandon session (save-exit keeps interviewing status)

# Rate limits (uses existing enforce_doctor_rate_limit helper)
#   /interview/start    — 3 per hour per patient   (prevent session spam)
#   /interview/turn     — 10 per minute per session (each call triggers LLM inference)
#   /interview/confirm  — 2 per hour per patient   (prevent duplicate submissions)

# Existing (unchanged)
GET    /api/patient/me
GET    /api/patient/records
POST   /api/patient/message
```

---

## 12. Scope Boundaries

### In Scope (v1)

- Patient self-registration and login (web)
- Doctor selection (search/dropdown)
- AI-guided interview (hybrid: free-form + completeness)
- Live summary during interview
- Patient confirmation and submission
- Doctor notification via task queue
- Patient home page (interview, records, messaging)

### Deferred

- Emergency keyword detection + 120 guidance
- Voice input (requires STT integration)
- WeChat mini-program
- Patient file/photo upload during interview
- AI diagnostic suggestions (Phase 2)
- Automated re-interview on doctor request
- Multi-doctor patient record (keep per-doctor FK)
- SMS verification
- Neurology-specific knowledge base
