# Doctor Interview Mode — Unified Record Collection (v3)

> Date: 2026-03-20 | v3: fixes 6 issues from Codex v2 code audit

## Problem

Doctor creates records via free-text chat → ReAct agent → `create_record` tool.
Fields get missed, extraction is unreliable, no progress tracking.

The patient interview pipeline already solves this with structured collection,
but patient mode is AI-led (AI asks, patient answers). Doctor needs the opposite:
**doctor leads, AI listens and verifies.**

## Solution

Two interaction modes on the same completeness engine:

- **Patient mode** (existing): AI leads, asks questions, patient answers
- **Doctor mode** (new): Doctor dictates, AI listens, extracts, shows what's missing

## Architecture: Separate Endpoints

### Endpoints (3 total)

```python
# POST /api/records/interview/turn — create or continue interview
class DoctorInterviewInput(BaseModel):
    text: str = Field(..., max_length=8000)
    session_id: Optional[str] = None  # None = create new session
    patient_name: Optional[str] = None
    patient_gender: Optional[str] = None
    patient_age: Optional[int] = None

class DoctorInterviewResponse(BaseModel):
    session_id: str
    reply: str
    collected: Dict[str, str]
    progress: Dict[str, int]           # {filled: 5, total: 7}
    missing: List[str]                 # field names still needed
    missing_required: List[str]        # only required fields still needed
    status: str                        # interviewing | ready_for_confirm
    patient_id: Optional[int] = None
    pending_id: Optional[str] = None   # set after confirm

# POST /api/records/interview/confirm — finalize → pending draft
class InterviewConfirmInput(BaseModel):
    session_id: str
# Returns: {status: "pending_confirmation", preview: ..., pending_id: ...}
# This is the SAME output as create_record tool — a pending draft that
# the doctor then confirms/abandons via the existing PendingRecord flow.

# POST /api/records/interview/cancel — abandon session
class InterviewCancelInput(BaseModel):
    session_id: str
# Returns: {status: "abandoned"}
```

### Two-step confirm flow

Interview confirm does NOT directly create a final record. It creates a
**pending draft** (same as `create_record` tool), which the doctor then
previews and confirms/abandons via the existing PendingRecord flow:

```
Interview collected 7 fields → doctor clicks "确认生成"
  → POST /api/records/interview/confirm
  → _build_clinical_text(collected) → structure_medical_record()
  → _create_pending_record() → returns {pending_id, preview}
  → Interview session status → "draft_created" (not "confirmed")
  → Frontend shows pending draft preview
  → Doctor confirms draft via existing "确认"/"取消" flow
  → PendingRecord saved → Interview session status → "confirmed"
```

Session status lifecycle:
```
interviewing → draft_created → confirmed (via PendingRecord confirm)
                             → abandoned (via PendingRecord cancel or interview cancel)
```

### Flow

```
1. Doctor clicks "新增病历" chip
   Frontend: sets activeInterview state (no backend call yet)

2. Doctor types: "张三，男45岁，头痛三天伴恶心呕吐，既往高血压10年服药"
   Frontend: POST /api/records/interview/turn
     { text: "...", session_id: null, patient_name: "张三",
       patient_gender: "男", patient_age: 45 }

3. Backend:
   a) resolve("张三", auto_create=True, gender="男", age=45)
      → find or create patient → patient_id
      NOTE: if multiple patients named "张三" exist, resolve()
      returns the first match (existing limitation, same as create_record tool).
      Doctor can disambiguate by providing more context.
   b) create_session(doctor_id, patient_id, mode="doctor")
   c) interview_turn(session_id, text) → LLM extracts fields
   d) Return DoctorInterviewResponse

4. Doctor types: "个人史无特殊，未婚未育，家族史无特殊"
   Frontend: POST /api/records/interview/turn
     { text: "...", session_id: "abc123" }

5. Backend returns: status="ready_for_confirm", all fields filled

6. Doctor clicks "确认生成"
   Frontend: POST /api/records/interview/confirm { session_id: "abc123" }
   Backend: creates pending draft → returns {pending_id, preview}
   Frontend: shows draft preview with existing confirm/cancel buttons
```

## Session Ownership Verification

Every endpoint verifies ownership:

```python
# In doctor_interview.py router
async def _verify_doctor_session(session_id: str, doctor_id: str) -> InterviewSession:
    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.doctor_id != doctor_id:
        raise HTTPException(403, "Not your session")
    return session
```

Additionally, the **patient interview endpoint** (`/api/patient/interview/turn`)
must also verify that the session's `patient_id` matches the authenticated patient.
This is a pre-existing bug that should be fixed alongside this feature:

```python
# In patient_interview_routes.py — add to existing /turn endpoint
if session.patient_id != authenticated_patient_id:
    raise HTTPException(403, "Not your session")
```

## Completeness: Required vs. Optional Fields

`completeness.py` defines `marital_reproductive` as OPTIONAL. The spec aligns:

- `ready_for_confirm` triggers when all REQUIRED + ASK_AT_LEAST fields are filled
  (5/7 minimum: chief_complaint, present_illness + past_history, allergy_history,
  family_history, personal_history)
- OPTIONAL fields (marital_reproductive) can be empty
- Progress display distinguishes: "已采集 5/7（必填已完成）。可选：婚育史（未填）"
- Doctor can still fill optional fields before confirming, or skip them

The prompt says "X/7" for total progress but indicates which remaining fields
are required vs. optional:

```
收到。已采集 5/7：✓主诉 ✓现病史 ✓既往史 ✓过敏史 ✓家族史。
必填已完成，可确认生成病历。可选未填：个人史、婚育史。
```

## Doctor-Mode Prompt: Listener, Not Interviewer

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
   - 第三行（如有缺失必填）：还缺（必填）：字段A、字段B
   - 第四行（如有可选未填）：可选未填：字段C
   - 必填全部完成时：必填已完成，可确认生成病历。
3. 不要问问题，不要追问细节，不要解释
4. 医生说"无"或"不详"→ 记录为该字段的值，计为已采集
5. 如果医生在补充已有字段的信息，追加而不是覆盖
6. 第一条消息通常包含患者姓名/性别/年龄，一并提取

## 输出格式（JSON）
{
  "reply": "收到。已采集 4/7：✓主诉 ✓现病史 ✓既往史 ✓过敏史。还缺（必填）：家族史、个人史。可选未填：婚育史。",
  "extracted": { ... }
}
```

## Patient Partial → Doctor Completes

Deferred to Phase 2 (dashboard implementation). Reason: the current dashboard
does not list interview sessions, and `review_queue` has no `interview_session_id`
column. This requires:
1. A new query: `GET /api/records/interview/incomplete` — list sessions with
   `status=interviewing` for this doctor's patients
2. Dashboard UI to show these and let doctor click "继续采集"
3. `review_queue` schema change to link to interview sessions

For now, doctor can only create new interviews. Patient-to-doctor resume
is a Phase 2 feature.

## What Changes

### Backend — new files

- `src/channels/web/doctor_interview.py` — new router with 3 endpoints:
  - `POST /api/records/interview/turn` — create or continue
  - `POST /api/records/interview/confirm` — finalize → pending draft
  - `POST /api/records/interview/cancel` — abandon session

### Backend — modify

- `src/db/models/interview_session.py` — add `mode` column (String, default "patient"),
  add `draft_created` to InterviewStatus enum
- `src/domain/patients/interview_session.py` — add `mode` to create/load/save/get_active
- `src/domain/patients/interview_turn.py` — pass `mode` through call chain,
  use `get_prompt_sync(prompt_name)` directly (prompt_loader already caches)
- `src/channels/web/patient_interview_routes.py` — add `patient_id` ownership check
  to existing `/turn` endpoint (pre-existing bug fix)
- `src/agent/prompts/doctor-interview.md` — new prompt file

### Frontend — modify

- `frontend/web/src/pages/doctor/ChatSection.jsx`:
  - `activeInterview` state (localStorage-persisted)
  - "新增病历" chip → set activeInterview (no backend call)
  - During interview: send to `/api/records/interview/turn`
  - Show progress indicator ("已采集 5/7")
  - On `status: ready_for_confirm` → show "确认生成" button
  - On confirm → `/api/records/interview/confirm` → show pending draft preview
  - On cancel → `/api/records/interview/cancel` → clear interview state
- `frontend/web/src/api.js` — add `interviewTurn()`, `interviewConfirm()`,
  `interviewCancel()` functions

### NOT changed

- `completeness.py` — same fields, same required/optional logic
- Patient interview endpoints — unchanged (except ownership fix)
- `/api/records/chat` — unchanged
- `handle_turn.py` — unchanged
- Action chip dispatch — unchanged (frontend handles routing)

## No Collision with Existing Flows

| Existing flow | Doctor interview | Collision? |
|--------------|-----------------|-----------|
| `/api/records/chat` | `/api/records/interview/turn` | **None** — separate endpoint |
| PendingRecord "确认" fast path | Interview creates pending draft → existing confirm flow | **None** — sequential, not parallel |
| Action Chip dispatch | Frontend state only | **None** |
| Agent memory / archive | Not involved | **None** |
| Patient interview endpoints | Unchanged (+ ownership fix) | **None** |

## Known Limitations

1. **Duplicate patient names:** `resolve()` returns first `LIMIT 1` match.
   Same limitation as current `create_record` tool. Doctor can disambiguate
   by checking after creation. Future: add disambiguation prompt.

2. **Patient partial → doctor resume:** Deferred to Phase 2. Requires
   dashboard changes and `review_queue` schema update.

3. **Concurrent edits:** `save_session` overwrites JSON blobs without locking.
   Acceptable for single-doctor-per-session model. If team editing is needed
   later, add optimistic locking.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Doctor dumps everything in one message | LLM extracts all fields, shows checklist |
| Doctor says "无" for a field | Record as "无", count as filled |
| Doctor clicks "新增病历" while interview active | Abandon current, start new |
| Page refresh during interview | `activeInterview` restored from localStorage |
| Doctor clicks "取消" | `POST /api/records/interview/cancel` → session abandoned |
| LLM fails to parse response | Return error, session preserved, doctor retries |
| First message has no patient name | Return error: "请提供患者姓名" |
| Optional fields skipped | Doctor can confirm with 5/7 (required complete) |
| Doctor types "确认" in text | Not intercepted — must click confirm button |

## Success Criteria

- Doctor creates a structured record in <3 minutes via interview mode
- Required fields (5/7) guaranteed present before confirm
- Doctor can dump everything in one message and AI extracts correctly
- Confirm produces same pending draft as existing `create_record` tool
- Existing patient interview and chat flows unaffected
