# Doctor Interview Mode — Unified Record Collection (v2)

> Date: 2026-03-20 | Revised after Codex code audit (1.1M tokens)

## Problem

Doctor creates records via free-text chat → ReAct agent → `create_record` tool.
Fields get missed, extraction is unreliable, no progress tracking.

The patient interview pipeline already solves this with structured collection,
but patient mode is AI-led (AI asks, patient answers). Doctor needs the opposite:
**doctor leads, AI listens and verifies.**

## Solution

Two interaction modes on the same completeness engine:

| | Patient Mode (existing) | Doctor Mode (new) |
|---|---|---|
| **Who leads** | AI asks questions | Doctor dictates freely |
| **AI role** | Interviewer | Listener/verifier |
| **Pace** | One field at a time | Bulk input, multiple fields per message |
| **AI output** | Next question | "已采集 X/7：✓主诉 ✓现病史 ✓既往史。还缺：家族史、个人史" |
| **Tone** | "您有什么不舒服？" | "收到。还缺家族史。" |

Doctor mode AI does NOT:
- Ask probing questions like a patient interviewer
- Repeat back what was said
- Explain medical terms
- Initiate conversation

Doctor mode AI DOES:
- Extract all recognizable fields from whatever the doctor says
- Show a checklist of what's captured vs. missing
- Accept "无"/"不详" to mark a field as done
- Prompt for confirmation when all 7 fields are present

## Architecture: Separate Endpoint, Not Chat Piggyback

Codex audit found that piggybacking on `/api/records/chat` creates collisions
with pending-record fast paths, action hints, agent memory, and archive writes.
Doctor interview gets its own endpoint.

### New endpoint: `POST /api/records/interview/turn`

```python
class DoctorInterviewInput(BaseModel):
    text: str = Field(..., max_length=8000)
    session_id: Optional[str] = None  # None = create new session
    patient_name: Optional[str] = None  # for first turn: resolve/create patient
    patient_gender: Optional[str] = None
    patient_age: Optional[int] = None

class DoctorInterviewResponse(BaseModel):
    session_id: str
    reply: str                        # AI's brief response
    collected: Dict[str, str]         # current field values
    progress: Dict[str, int]          # {filled: 5, total: 7}
    missing: List[str]                # ["family_history", "personal_history"]
    status: str                       # interviewing | ready_for_confirm | confirmed
    patient_id: Optional[int] = None  # resolved patient ID
```

### New endpoint: `POST /api/records/interview/confirm`

```python
class InterviewConfirmInput(BaseModel):
    session_id: str

# Returns the created MedicalRecord
```

### Flow

```
1. Doctor clicks "新增病历" chip
   Frontend: sets activeInterview state (no backend call yet)

2. Doctor types: "张三，男45岁，头痛三天伴恶心呕吐，既往高血压10年服药"
   Frontend: POST /api/records/interview/turn
     { text: "...", session_id: null, patient_name: "张三", patient_gender: "男", patient_age: 45 }

3. Backend:
   a) resolve("张三") → find or create patient → patient_id
   b) create_session(doctor_id, patient_id, mode="doctor")
   c) interview_turn(session_id, text) → LLM extracts fields
   d) Return: {
        session_id: "abc123",
        reply: "收到。已采集 4/7：✓主诉 ✓现病史 ✓既往史 ✓过敏史。还缺：个人史、婚育史、家族史。",
        collected: {chief_complaint: "头痛三天", present_illness: "...", ...},
        progress: {filled: 4, total: 7},
        missing: ["personal_history", "marital_reproductive", "family_history"],
        patient_id: 42
      }

4. Doctor types: "个人史无特殊，未婚未育，家族史无特殊"
   Frontend: POST /api/records/interview/turn
     { text: "...", session_id: "abc123" }

5. Backend:
   Return: {
     reply: "已采集 7/7，全部完成。请确认生成病历。",
     progress: {filled: 7, total: 7},
     missing: [],
     status: "ready_for_confirm"
   }

6. Doctor clicks "确认"
   Frontend: POST /api/records/interview/confirm { session_id: "abc123" }
   Backend: generate full medical record (not just 7-field summary),
            return record_id
```

## Key Differences from Patient Interview

### 1. Full medical record, not interview summary

Codex correctly flagged: patient `confirm_interview()` creates `record_type="interview_summary"`
with only 7 fields. Doctor mode must create a **full medical record** through the
existing `structure_medical_record()` pipeline, which produces the 14-field
outpatient standard (chief_complaint through orders_followup).

```python
async def confirm_doctor_interview(session_id: str) -> dict:
    session = await load_session(session_id)
    # Combine collected fields into clinical text
    clinical_text = _build_clinical_text(session.collected)
    # Use the SAME structuring pipeline as create_record
    medical_record = await structure_medical_record(clinical_text, doctor_id=session.doctor_id)
    # Save as pending draft (same as create_record tool)
    result = await _create_pending_record(
        session.doctor_id, session.patient_id, patient_name,
        clinical_text=clinical_text,
    )
    session.status = "confirmed"
    await save_session(session)
    return result  # {status: "pending_confirmation", preview: ..., pending_id: ...}
```

This means doctor interview → confirm produces the **exact same output** as the
current `create_record` tool: a pending draft that the doctor can preview and
confirm/abandon via the existing flow.

### 2. Doctor-mode prompt: listener, not interviewer

```markdown
# 医生录入采集模式

你是一个医疗AI助手，帮助医生快速录入患者信息。

## 你的角色
- 你是一个听者和验证者，不是提问者
- 医生主动输入信息，你提取并追踪进度
- 不要追问、不要解释、不要重复医生说的话

## 当前已采集
{collected_json}

## 还缺的字段
{missing_fields}

## 患者信息
姓名：{name} | 性别：{gender} | 年龄：{age}

## 规则
1. 从医生输入中提取所有能识别的字段
2. 回复格式固定：
   - 第一行："收到。" 或 "已更新。"
   - 第二行：已采集 X/7：✓字段1 ✓字段2 ...
   - 第三行（如有缺失）：还缺：字段A、字段B
   - 全部完成时：已采集 7/7，全部完成。请确认生成病历。
3. 不要问问题，不要追问细节，不要解释
4. 医生说"无"或"不详"→ 记录为该字段的值，计为已采集
5. 如果医生在补充已有字段的信息，追加而不是覆盖

## 输出格式（JSON）
{
  "reply": "收到。已采集 4/7：✓主诉 ✓现病史 ✓既往史 ✓过敏史。还缺：个人史、婚育史、家族史。",
  "extracted": {
    "chief_complaint": "头痛三天",
    "present_illness": "头痛三天伴恶心呕吐...",
    ...
  }
}
```

### 3. Session ownership verification

```python
async def doctor_interview_turn(session_id, text, doctor_id):
    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.doctor_id != doctor_id:
        raise HTTPException(403, "Not your session")
    # ... proceed
```

### 4. No collision with existing flows

| Existing flow | Doctor interview | Collision? |
|--------------|-----------------|-----------|
| `/api/records/chat` | `/api/records/interview/turn` | **None** — separate endpoint |
| PendingRecord "确认" fast path | Interview confirm endpoint | **None** — different API |
| Action Chip dispatch | Frontend state only | **None** — no backend change to dispatch |
| Agent memory / archive | Not involved | **None** |
| Patient interview endpoints | Unchanged | **None** |

## What Changes

### Backend — new files

- `src/channels/web/doctor_interview.py` — new router with 2 endpoints:
  - `POST /api/records/interview/turn` — create or continue interview
  - `POST /api/records/interview/confirm` — finalize → pending record

### Backend — modify

- `src/db/models/interview_session.py` — add `mode` column
- `src/domain/patients/interview_session.py` — add `mode` to create/load/save
- `src/domain/patients/interview_turn.py` — replace global prompt cache with
  per-mode lookup via `get_prompt_sync()` (no extra cache dict needed, prompt_loader
  already caches). Pass `mode` through call chain.
- `src/agent/prompts/doctor-interview.md` — new prompt file

### Frontend — modify

- `frontend/web/src/pages/doctor/ChatSection.jsx`:
  - `activeInterview` state (localStorage-persisted)
  - "新增病历" chip → set `activeInterview` (no backend call)
  - During interview: send to `/api/records/interview/turn` instead of `/api/records/chat`
  - Show progress indicator ("已采集 5/7")
  - On `status: ready_for_confirm` → show confirm button
  - On confirm → call `/api/records/interview/confirm` → clear interview state
  - On cancel → abandon session → clear interview state
- `frontend/web/src/api.js` — add `interviewTurn()` and `interviewConfirm()` functions

### NOT changed

- `completeness.py` — same 7 fields, same logic
- Patient interview endpoints — unchanged
- `/api/records/chat` — unchanged
- `handle_turn.py` — unchanged (no more piggybacking)
- Action chip dispatch — unchanged (frontend handles the routing)

## Patient Partial → Doctor Completes

Doctor opens a patient's incomplete interview from the dashboard:

1. Dashboard shows records with `review_queue.status = "pending_review"` and
   linked interview `status = "interviewing"` (incomplete)
2. Doctor clicks "继续采集"
3. Frontend: `POST /api/records/interview/turn`
   with existing `session_id` (mode will be switched to "doctor" server-side)
4. Backend: loads session, switches `mode` to `"doctor"`, continues with
   doctor prompt from whatever fields are already collected
5. `get_active_session` filters by `mode` to prevent patient accidentally
   resuming a doctor-mode session

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Doctor dumps everything in one message | LLM extracts all fields, shows checklist |
| Doctor says "无" for a field | Record as "无", count as filled |
| Doctor clicks "新增病历" while interview active | Abandon current, start new |
| Page refresh during interview | `activeInterview` restored from localStorage, session in DB |
| Doctor types "取消" | Session → abandoned, interview state cleared |
| Two doctors edit same patient interview | Second doctor gets new session (one session per doctor) |
| LLM fails to parse response | Return error, session preserved, doctor retries |
| First message has no patient name | Return error: "请提供患者姓名" |

## Success Criteria

- Doctor creates a structured record in <3 minutes
- All 7 fields tracked with visible progress
- Doctor can dump everything in one message
- Confirm produces same output as existing `create_record` (pending draft)
- Existing patient interview and chat flows unaffected
- No collision with pending record confirm/abandon
