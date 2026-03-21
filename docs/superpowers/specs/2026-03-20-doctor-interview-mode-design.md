# Doctor Interview Mode — Unified Record Collection

> Date: 2026-03-20

## Problem

Currently the doctor creates records via free-text chat → ReAct agent → `create_record`
tool → LLM extracts fields from unstructured input. This is unreliable:
- Fields get missed (doctor forgets to mention family history)
- LLM extraction is hit-or-miss on complex multi-field input
- No progress tracking (doctor doesn't know what's been captured vs. missing)

The patient interview pipeline (`domain/patients/interview_turn.py`) already solves
this problem with structured multi-turn collection, completeness tracking, and
confirm-before-save flow. But it only works for patients.

## Solution

Add a `mode` field to the existing interview session. Same engine, different prompt:

- **Patient mode** (existing): gentle tone, explains terms, slow pace, one field at a time
- **Doctor mode** (new): professional terminology, fast pace, accepts bulk input, asks
  only for missing fields

The "新增病历" Action Chip triggers doctor interview mode instead of free-text
`create_record`.

## What Changes

### 1. InterviewSession — add `mode` field

```python
# interview_session.py
@dataclass
class InterviewSession:
    id: str
    doctor_id: str
    patient_id: int
    mode: str = "patient"  # "patient" | "doctor"
    status: str = InterviewStatus.interviewing
    collected: Dict[str, str] = field(default_factory=dict)
    conversation: List[Dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
```

DB model (`InterviewSessionDB`) gets `mode` column (String, default `"patient"`).

**All persistence functions must propagate `mode`:**
- `create_session(doctor_id, patient_id, mode="patient")` — accept and write mode
- `load_session(session_id)` — read `mode` from DB row into dataclass
- `save_session(session)` — write `mode` back to DB
- `get_active_session(patient_id, doctor_id)` — include `mode` in returned dataclass

### 2. Interview prompt — load by mode (per-mode cache)

The current global `_INTERVIEW_PROMPT` cache must be replaced with a per-mode cache,
otherwise whichever mode loads first will be used for both.

```python
# interview_turn.py
_PROMPTS: Dict[str, str] = {}  # replaces single _INTERVIEW_PROMPT global

def _get_prompt(mode: str = "patient") -> str:
    if mode not in _PROMPTS:
        prompt_name = "doctor-interview" if mode == "doctor" else "patient-interview"
        loaded = get_prompt_sync(prompt_name)
        if not loaded:
            raise ValueError(f"Interview prompt '{prompt_name}' not found")
        _PROMPTS[mode] = loaded
    return _PROMPTS[mode]
```

**Propagation through call chain:**
- `interview_turn(session_id, text)` loads session → gets `session.mode`
- Passes `mode` to `_call_interview_llm(..., mode=session.mode)`
- `_call_interview_llm` calls `_get_prompt(mode)` instead of `_get_prompt()`

The `doctor-interview` prompt instructs the LLM to:
- Use professional medical terminology (not layman language)
- Accept bulk input ("张三，男45岁，头痛三天伴恶心，既往高血压10年" → extract all at once)
- Only ask for specifically missing fields ("已采集5/7。还缺：家族史、个人史。")
- Be concise — no explanations, no reassurance
- Support voice dictation style (run-on sentences, no punctuation)

### 3. "新增病历" Action Chip → interview mode

Currently: doctor clicks "新增病历" → types text → ReAct agent → `create_record` tool

#### Patient creation flow

The doctor's first message typically includes the patient name ("张三，男45岁，头痛").
Rather than creating a "placeholder patient", the flow is:

1. Doctor clicks "新增病历"
2. Frontend sets `activeInterview` state (no backend call yet)
3. Doctor types/dictates patient info
4. First `interview_turn` call:
   - LLM extracts patient name/gender/age from the message
   - If name found: `resolve()` to find or auto-create patient
   - Create interview session with `mode="doctor"` and real `patient_id`
   - Return first response with extracted fields + progress
5. Subsequent messages continue the interview
6. When 7/7 fields collected: "已采集完整，确认生成病历？"
7. Doctor confirms → record created

This avoids the "placeholder patient" problem — patient is created from the
first message, same as the current `create_record` tool's `resolve()` flow.

#### API routing

Doctor interview turns go through the **existing chat endpoint** (`/api/records/chat`)
with a new `interview_session_id` field:

```python
class ChatInput(BaseModel):
    text: str = Field(..., max_length=8000)
    history: List[HistoryMessage] = Field(default_factory=list)
    doctor_id: str = ""
    action_hint: Optional[Action] = None
    interview_session_id: Optional[str] = None  # ← new
```

In `handle_turn`:
```python
# Before agent dispatch, check for active interview
if interview_session_id:
    return await interview_turn(interview_session_id, text)
```

This avoids needing a separate endpoint and reuses existing auth/rate-limiting.

### 4. Patient partial → doctor completes

If a patient already did pre-consultation (filled 4/7 fields), doctor opens the
patient's incomplete interview from the dashboard:

- Dashboard shows "待审核" records with incomplete interviews
- Doctor clicks "继续采集" → API: `POST /api/records/interview/resume`
  with `session_id` + switches `mode` to `"doctor"`
- Frontend enters interview mode with existing `collected` fields
- Doctor only gets asked about missing fields

### 5. Session lifecycle in doctor chat

During an active doctor interview:

- Frontend tracks `activeInterview` state (persisted to `localStorage` for refresh recovery)
- Messages include `interview_session_id` → routed to `interview_turn()`
- Chat shows progress indicator ("已采集 5/7 字段")
- Doctor can cancel anytime ("取消" → session abandoned, return to normal chat)
- On completion → record created → `activeInterview` cleared

```js
const [activeInterview, setActiveInterview] = useState(() => {
    // Restore from localStorage on mount
    const saved = localStorage.getItem(`active_interview:${doctorId}`);
    return saved ? JSON.parse(saved) : null;
});
// { sessionId: "...", progress: {filled: 5, total: 7} } or null
```

#### Conflict with "确认" fast path

The existing fast path in `handle_turn.py` intercepts "确认" to confirm a
`PendingRecord`. When an interview is active, "确认" should confirm the
interview instead. Resolution: if `interview_session_id` is present, skip
the `PendingRecord` fast path — interview routing takes precedence.

## What Doesn't Change

- `completeness.py` — same 7 fields, same required/optional split, same merge logic
- Patient interview endpoints — unchanged, still work as before
- Interview prompt output format — same `{reply, extracted}` JSON

## What Changes in interview_summary

`confirm_interview()` currently:
1. Creates a `MedicalRecord`
2. Creates a `ReviewQueue` entry
3. Creates a `DoctorTask` ("患者预问诊")
4. Sends doctor notification

For doctor-initiated interviews (mode="doctor"):
- Step 1: Same (create record)
- Step 2: **Skip** review queue (doctor is the author, no need to self-review)
- Step 3: **Skip** task creation (doctor already knows)
- Step 4: **Skip** notification (doctor is already here)

```python
async def confirm_interview(session_id: str) -> dict:
    session = await load_session(session_id)
    record = await _create_medical_record(session)
    if session.mode == "patient":
        await _create_review_queue_entry(record)
        await _create_doctor_task(session)
        await _send_doctor_notification(session)
    return {"status": "confirmed", "record_id": record.id}
```

## Files to Modify

### Backend

- `src/db/models/interview_session.py` — add `mode` column (String, default "patient")
- `src/domain/patients/interview_session.py` — add `mode` param to all 4 persistence
  functions (`create_session`, `load_session`, `save_session`, `get_active_session`)
- `src/domain/patients/interview_turn.py` — replace global prompt cache with per-mode
  dict, propagate `mode` through `interview_turn` → `_call_interview_llm` → `_get_prompt`
- `src/domain/patients/interview_summary.py` — skip review queue/task/notification
  when `mode="doctor"`
- `src/channels/web/chat.py` — add `interview_session_id` to `ChatInput`
- `src/agent/handle_turn.py` — route to `interview_turn` when `interview_session_id`
  is present (before fast path and agent dispatch)

### Frontend

- `frontend/web/src/pages/doctor/ChatSection.jsx` — `activeInterview` state
  (localStorage-persisted), route messages with `interview_session_id`, show
  progress indicator, handle confirm/cancel
- `frontend/web/src/api.js` — `sendChat` already passes payload through, no change

### New Files

- `src/agent/prompts/doctor-interview.md` — doctor-mode interview prompt

## Doctor Interview Prompt Design

```markdown
# 医生问诊采集模式

你是一个医疗AI助手，正在帮助医生快速录入患者信息。

## 你的角色
- 高效采集患者信息，使用专业医学术语
- 医生可能一次说完所有信息，也可能分多次补充
- 只追问缺失的字段，不重复已有信息

## 采集字段
{collected_json}

## 缺失字段
{missing_fields}

## 患者信息
姓名：{name} | 性别：{gender} | 年龄：{age}

## 规则
1. 从医生输入中提取所有能识别的字段，一次提取多个
2. 只针对缺失字段追问，已有字段不再重复
3. 追问时简洁直接："家族史？" 而不是 "请问患者的家族史情况如何？"
4. 如果医生说"无"或"不详"，记录为该字段的值
5. 所有7个字段采集完成后，提示医生确认
6. 第一条消息通常包含患者姓名/性别/年龄，一并提取

## 输出格式（JSON）
{
  "reply": "已采集5/7。家族史？个人史？",
  "extracted": {
    "chief_complaint": "头痛三天",
    "present_illness": "...",
    ...
  }
}
```

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Doctor types everything in one message | LLM extracts all fields, asks for missing |
| Doctor says "无" for a field | Record as "无", count as filled |
| Doctor says "跳过" or "不知道" | Record as "不详", count as filled |
| Doctor cancels mid-interview | Session → abandoned, no record created |
| Doctor clicks "新增病历" while interview active | Abandon current, start new |
| Doctor types "确认" during interview | Confirms interview (not PendingRecord) |
| Patient already has partial interview | Doctor opens it, mode→"doctor", completes remaining |
| Network error during interview | Session in DB, `activeInterview` in localStorage, resumable |
| Doctor sends image/PDF during interview | OCR text inserted into input field, doctor sends it, LLM extracts fields |
| Page refresh during interview | `activeInterview` restored from localStorage, session resumed from DB |
| MAX_TURNS reached (doctor mode) | Same cap (30), but message uses professional tone: "已达到轮次上限，请确认当前采集内容" |

## Success Criteria

- Doctor can create a 7-field structured record in <3 minutes via interview mode
- All 7 fields guaranteed present (vs. current free-text where fields are often missing)
- Doctor can dump everything in one message and AI extracts correctly
- Existing patient interview flow unchanged
- Patient partial → doctor complete works seamlessly
