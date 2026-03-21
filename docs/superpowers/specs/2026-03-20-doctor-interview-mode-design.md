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

### Entry Point Consolidation

**所有创建患者/病历的路径都归入 doctor interview session。不再有自由文本创建。**

```
Before (multiple paths, unreliable):
  "新增病历" chip   → ReAct agent → create_record tool → free-text extraction
  Free text          → ReAct agent → create_record tool → free-text extraction
  Patient tab        → manual form

After (one path, guaranteed structured):
  "新增病历" chip   ─┐
  Free text intent  ─┼→ Doctor Interview Session → structured collection → pending draft
  Patient tab "添加" ─┘
```

**具体变更：**
1. **"新增病历" Action Chip** → 直接进入 interview mode（前端状态切换）
2. **Free text 创建意图** → ReAct agent 检测到创建意图后，不再调用 `create_record` tool，
   而是返回"已为您开启病历采集模式"并启动 interview session。
   **第一条消息的内容自动作为 interview 的第一轮输入**，医生不需要重复。
3. **Patient tab "添加患者"** → 同样进入 interview mode
4. **`create_record` tool 从 agent 工具列表中移除** — 不再有自由文本创建路径

### Multi-Modal Input During Interview

Interview session 支持多种输入方式，所有提取的内容都进入同一个 completeness engine：

```
Doctor interview session accepts:
├── 文字/语音 → LLM 提取字段
├── 图片（病历照片/检查报告）→ OCR → 提取文本 → LLM 提取字段
├── PDF/文档 → 提取文本 → LLM 提取字段
└── 混合（先发照片，再补充文字）→ 合并提取
```

实现方式：interview turn endpoint 增加可选的 `file` 参数。如果有文件，先走现有的
OCR/PDF 提取 pipeline（`vision_import.py` / `pdf_extract.py`），提取文本后与 `text`
合并，作为一条 interview turn 输入。

### Flow

```
1. Doctor clicks "新增病历" chip (or free text triggers creation intent)
   Frontend: enters interview mode (sets activeInterview state)
   If triggered by free text: auto-feed the text as first message

2. Doctor types/dictates: "张三，男45岁，头痛三天伴恶心呕吐，既往高血压10年服药"
   (or uploads a photo of a referral letter, or sends a PDF report)
   Frontend: POST /api/records/interview/turn
     { text: "...", session_id: null, patient_name: "张三",
       patient_gender: "男", patient_age: 45 }
     (or multipart with file attachment)

3. Backend:
   a) If file attached: OCR/PDF extract → merge text
   b) resolve("张三", auto_create=True, gender="男", age=45)
      → find or create patient → patient_id
   c) create_session(doctor_id, patient_id, mode="doctor")
   d) interview_turn(session_id, merged_text) → LLM extracts fields
   e) Return DoctorInterviewResponse

4. Doctor adds more info (text, voice, or another document)
   Frontend: POST /api/records/interview/turn
     { text: "...", session_id: "abc123" }

5. Backend returns: status="ready_for_confirm", required fields filled

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

Confirm threshold follows `completeness.py` exactly:

- **REQUIRED (2):** chief_complaint, present_illness — must be filled
- **ASK_AT_LEAST (4):** past_history, allergy_history, family_history, personal_history — must be filled
- **OPTIONAL (1):** marital_reproductive — can be empty

`ready_for_confirm` triggers when `check_completeness()` returns empty list
= all 6 REQUIRED + ASK_AT_LEAST fields filled. OPTIONAL (婚育史) can be skipped.

Progress display:
```
收到，已记录。
✓ 主诉 ✓ 现病史 ✓ 既往史 ✓ 过敏史 ✓ 家族史 ✓ 个人史（6/7）
全部必填已完成，可以生成初步病历了。（婚育史未填，可跳过）
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
2. 回复简洁友好，格式如下：
   - 开头："收到，已记录。"
   - 进度清单：✓ 字段1 ✓ 字段2 ...（X/7）
   - 如有必填未完成：还需要：字段A、字段B
   - 如有可选未填：（婚育史未填，可跳过）
   - 全部必填完成时：全部必填已完成，可以生成初步病历了。
3. 不要问问题，不要追问细节，不要解释
4. 医生说"无"或"不详"→ 记录为该字段的值，计为已采集
5. 如果医生在补充已有字段的信息，追加而不是覆盖
6. 第一条消息通常包含患者姓名/性别/年龄，一并提取

## 输出格式（JSON）
{
  "reply": "收到，已记录。\n✓ 主诉 ✓ 现病史 ✓ 既往史 ✓ 过敏史（4/7）\n还需要：家族史、个人史",
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
- `src/agent/tools/doctor.py` — **remove `create_record` from `DOCTOR_TOOLS` list**.
  Agent can no longer create records via free-text. If agent detects creation intent,
  it returns a message directing the doctor to use interview mode.
- `src/agent/handle_turn.py` — update `_dispatch_action_hint` for `Action.create_record`:
  return a redirect message instead of calling `agent.handle()`
- `src/channels/web/patient_interview_routes.py` — add `patient_id` ownership check
  to existing `/turn` endpoint (pre-existing bug fix)
- `src/agent/prompts/doctor-interview.md` — new prompt file
- `src/agent/prompts/doctor-agent.md` — update system prompt: when user wants to
  create a record/patient, respond with "请使用「新增病历」功能来采集患者信息" instead
  of calling create_record tool

### Frontend — modify

- `frontend/web/src/pages/doctor/ChatSection.jsx`:
  - `activeInterview` state (localStorage-persisted)
  - "新增病历" chip → set activeInterview (no backend call)
  - Free text creation intent detected by agent → frontend enters interview mode,
    auto-feeds the original message as first interview turn
  - During interview: send to `/api/records/interview/turn` (supports file upload)
  - Show progress indicator ("已采集 5/7")
  - On `status: ready_for_confirm` → show "确认生成" button
  - On confirm → `/api/records/interview/confirm` → show pending draft preview
  - On cancel → `/api/records/interview/cancel` → clear interview state
  - Patient tab "添加患者" → same interview mode entry
- `frontend/web/src/api.js` — add `interviewTurn()`, `interviewConfirm()`,
  `interviewCancel()` functions (interviewTurn supports multipart for file upload)

### NOT changed

- `completeness.py` — same fields, same required/optional logic
- Patient interview endpoints — unchanged (except ownership fix)
- `/api/records/chat` — unchanged (but agent no longer creates records via this path)
- Existing OCR/PDF extraction pipeline — reused as-is for document upload in interview

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
| Optional fields skipped | Doctor can confirm with 6/7 (REQUIRED + ASK_AT_LEAST), 婚育史 is optional |
| Doctor types "确认" in text | Not intercepted — must click confirm button |
| Doctor types "新患者张三..." in free chat | Agent detects intent → returns redirect message → frontend enters interview mode, auto-feeds text |
| Doctor uploads photo during interview | OCR extract → merge with text → LLM extracts fields |
| Doctor uploads PDF during interview | PDF extract → merge with text → LLM extracts fields |
| Patient tab "添加患者" click | Enters same interview mode |
| Doctor tries to use old create_record via chat | Agent responds: "请使用「新增病历」功能来采集患者信息" |

## Success Criteria

- Doctor creates a structured record in <3 minutes via interview mode
- Required fields (6/7) guaranteed present before confirm (婚育史 optional)
- Doctor can dump everything in one message and AI extracts correctly
- Confirm produces same pending draft as existing `create_record` tool
- Existing patient interview and chat flows unaffected
