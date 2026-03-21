# Doctor Interview Mode Implementation Plan

> **Status: ✅ DONE** — implementation complete, merged to main.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a doctor interview mode that provides structured record collection (listener/verifier pattern) through the same completeness engine as patient interviews, with multi-modal input support and all creation paths consolidated.

**Architecture:** Add `mode` field to existing interview session. New `/api/records/interview/` router with 3 endpoints (turn/confirm/cancel). Doctor-mode prompt is listener-style (extracts fields, shows progress, doesn't ask questions). Remove `create_record` from ReAct agent tools — all creation goes through interview.

**Tech Stack:** Python/FastAPI (backend), React/MUI (frontend), existing LLM pipeline, existing OCR/PDF extraction

**Spec:** `docs/superpowers/specs/2026-03-20-doctor-interview-mode-design.md` (v4)

---

### Task 1: Add `mode` field to InterviewSession model + persistence

**Files:**
- Modify: `src/db/models/interview_session.py`
- Modify: `src/domain/patients/interview_session.py`
- Test: `tests/core/test_interview_session_mode.py`

- [ ] **Step 1: Write the test**

```python
# tests/core/test_interview_session_mode.py
"""Interview session mode field — doctor vs patient mode."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from db.models.interview_session import InterviewStatus


@pytest.mark.asyncio
async def test_create_session_with_doctor_mode():
    with patch("domain.patients.interview_session.AsyncSessionLocal") as mock_cls:
        mock_db = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from domain.patients.interview_session import create_session
        session = await create_session("dr_test", 1, mode="doctor")

    assert session.mode == "doctor"
    assert session.doctor_id == "dr_test"
    assert session.patient_id == 1


@pytest.mark.asyncio
async def test_create_session_defaults_to_patient_mode():
    with patch("domain.patients.interview_session.AsyncSessionLocal") as mock_cls:
        mock_db = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from domain.patients.interview_session import create_session
        session = await create_session("dr_test", 1)

    assert session.mode == "patient"


def test_interview_status_has_draft_created():
    assert hasattr(InterviewStatus, "draft_created")
    assert InterviewStatus.draft_created == "draft_created"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_interview_session_mode.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `create_session` doesn't accept `mode`, no `draft_created` status

- [ ] **Step 3: Update InterviewStatus enum**

In `src/db/models/interview_session.py`, add `draft_created` to `InterviewStatus`:

```python
class InterviewStatus(str, Enum):
    interviewing = "interviewing"
    reviewing = "reviewing"
    confirmed = "confirmed"
    abandoned = "abandoned"
    draft_created = "draft_created"  # ← new
```

Add `mode` column to `InterviewSessionDB`:

```python
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="patient")
```

- [ ] **Step 4: Update all 4 persistence functions**

In `src/domain/patients/interview_session.py`:

**InterviewSession dataclass** — add `mode`:
```python
@dataclass
class InterviewSession:
    id: str
    doctor_id: str
    patient_id: int
    mode: str = "patient"  # ← new
    status: str = InterviewStatus.interviewing
    collected: Dict[str, str] = field(default_factory=dict)
    conversation: List[Dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
```

**create_session** — add `mode` param:
```python
async def create_session(doctor_id: str, patient_id: int, mode: str = "patient") -> InterviewSession:
    # ... existing code ...
    db_row = InterviewSessionDB(
        # ... existing fields ...
        mode=mode,  # ← new
    )
    # ...
    return InterviewSession(id=session_id, doctor_id=doctor_id, patient_id=patient_id, mode=mode)
```

**load_session** — read `mode`:
```python
    return InterviewSession(
        id=row.id,
        doctor_id=row.doctor_id,
        patient_id=row.patient_id,
        mode=row.mode,  # ← new
        status=row.status,
        # ... rest unchanged
    )
```

**save_session** — write `mode`:
```python
    row.mode = session.mode  # ← new (after row.status = ...)
```

**get_active_session** — read `mode`:
```python
    return InterviewSession(
        id=row.id,
        doctor_id=row.doctor_id,
        patient_id=row.patient_id,
        mode=row.mode,  # ← new
        # ... rest unchanged
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_interview_session_mode.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/db/models/interview_session.py src/domain/patients/interview_session.py tests/core/test_interview_session_mode.py
git commit -m "feat: add mode field to InterviewSession (doctor/patient)"
```

---

### Task 2: Doctor interview prompt + mode-aware prompt loading

**Files:**
- Create: `src/agent/prompts/doctor-interview.md`
- Modify: `src/domain/patients/interview_turn.py`
- Test: `tests/core/test_interview_prompt_mode.py`

- [ ] **Step 1: Create the doctor-interview prompt**

Write `src/agent/prompts/doctor-interview.md` with the listener-style prompt from the spec (Section: "Doctor-Mode Prompt"). Include `/no_think` tag for Qwen3 compatibility (same pattern as patient-interview.md).

- [ ] **Step 2: Write the test**

```python
# tests/core/test_interview_prompt_mode.py
"""Interview prompt loading — mode-aware."""
import pytest
from unittest.mock import patch, MagicMock
from domain.patients.interview_turn import _get_prompt


def test_get_prompt_patient_mode():
    with patch("domain.patients.interview_turn.get_prompt_sync", return_value="patient prompt"):
        result = _get_prompt("patient")
    assert result == "patient prompt"


def test_get_prompt_doctor_mode():
    with patch("domain.patients.interview_turn.get_prompt_sync", return_value="doctor prompt"):
        result = _get_prompt("doctor")
    assert result == "doctor prompt"


def test_get_prompt_doctor_mode_calls_correct_prompt_name():
    with patch("domain.patients.interview_turn.get_prompt_sync") as mock:
        mock.return_value = "test"
        _get_prompt("doctor")
    mock.assert_called_with("doctor-interview")


def test_get_prompt_patient_mode_calls_correct_prompt_name():
    with patch("domain.patients.interview_turn.get_prompt_sync") as mock:
        mock.return_value = "test"
        _get_prompt("patient")
    mock.assert_called_with("patient-interview")
```

- [ ] **Step 3: Run test to verify it fails**

Expected: FAIL — `_get_prompt` doesn't accept mode argument

- [ ] **Step 4: Update `_get_prompt` and propagate mode through call chain**

In `src/domain/patients/interview_turn.py`:

Replace the global `_INTERVIEW_PROMPT` cache and `_get_prompt()`:
```python
# Remove: _INTERVIEW_PROMPT: Optional[str] = None
# Remove: old _get_prompt()

def _get_prompt(mode: str = "patient") -> str:
    prompt_name = "doctor-interview" if mode == "doctor" else "patient-interview"
    return get_prompt_sync(prompt_name)
```

Update `_call_interview_llm` signature to accept `mode`:
```python
async def _call_interview_llm(
    conversation, collected, patient_info,
    previous_history=None, mode="patient",  # ← new
) -> Dict[str, Any]:
    # ... existing code ...
    prompt_template = _get_prompt(mode)  # ← pass mode
    # ... rest unchanged
```

Update `interview_turn` to pass `session.mode`:
```python
async def interview_turn(session_id: str, patient_text: str) -> InterviewResponse:
    session = await load_session(session_id)
    # ... existing code ...
    llm_response = await _call_interview_llm(
        conversation=session.conversation,
        collected=session.collected,
        patient_info=patient_info,
        previous_history=previous_history,
        mode=session.mode,  # ← new
    )
```

- [ ] **Step 5: Run test to verify it passes**

Expected: 4 PASSED

- [ ] **Step 6: Run existing interview tests for regression**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -k interview`

- [ ] **Step 7: Commit**

```bash
git add src/agent/prompts/doctor-interview.md src/domain/patients/interview_turn.py tests/core/test_interview_prompt_mode.py
git commit -m "feat: doctor-interview prompt + mode-aware prompt loading"
```

---

### Task 3: Doctor interview router (3 endpoints)

**Files:**
- Create: `src/channels/web/doctor_interview.py`
- Modify: `src/main.py` (or wherever routers are registered)
- Test: `tests/core/test_doctor_interview_endpoints.py`

- [ ] **Step 1: Write the router**

Create `src/channels/web/doctor_interview.py` with:

```python
"""Doctor interview endpoints — structured record collection."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from utils.log import log

router = APIRouter(prefix="/api/records/interview", tags=["doctor-interview"])


# ── Pydantic models ──────────────────────────────────────────────

class DoctorInterviewResponse(BaseModel):
    session_id: str
    reply: str
    collected: Dict[str, str]
    progress: Dict[str, int]
    missing: List[str]
    missing_required: List[str]
    status: str
    patient_id: Optional[int] = None
    pending_id: Optional[str] = None


class InterviewConfirmResponse(BaseModel):
    status: str
    preview: Optional[str] = None
    pending_id: Optional[str] = None


# ── Helper ───────────────────────────────────────────────────────

async def _resolve_doctor_id(
    doctor_id: str, authorization: Optional[str],
) -> str:
    return resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )


async def _verify_session(session_id: str, doctor_id: str):
    from domain.patients.interview_session import load_session
    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "Interview session not found")
    if session.doctor_id != doctor_id:
        raise HTTPException(403, "Not your session")
    return session


# ── POST /turn ───────────────────────────────────────────────────

@router.post("/turn", response_model=DoctorInterviewResponse)
async def interview_turn_endpoint(
    text: str = Form(...),
    session_id: Optional[str] = Form(default=None),
    patient_name: Optional[str] = Form(default=None),
    patient_gender: Optional[str] = Form(default=None),
    patient_age: Optional[int] = Form(default=None),
    doctor_id: str = Form(default=""),
    file: Optional[UploadFile] = File(default=None),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor, scope="records.interview")

    # If file uploaded, extract text and merge
    extra_text = ""
    if file:
        extra_text = await _extract_file_text(file)

    merged_text = f"{text}\n{extra_text}".strip() if extra_text else text

    if not session_id:
        # First turn — create session
        if not patient_name:
            raise HTTPException(422, "请提供患者姓名")
        return await _first_turn(
            resolved_doctor, merged_text,
            patient_name, patient_gender, patient_age,
        )
    else:
        # Continue existing session
        session = await _verify_session(session_id, resolved_doctor)
        return await _continue_turn(session, merged_text)


async def _extract_file_text(file: UploadFile) -> str:
    """Extract text from uploaded image or PDF."""
    content_type = (file.content_type or "").split(";")[0].strip()
    raw = await file.read()

    if content_type.startswith("image/"):
        from infra.llm.vision import extract_text_from_image
        result = await extract_text_from_image(raw)
        return result.get("text", "") if isinstance(result, dict) else str(result)
    elif content_type == "application/pdf" or (file.filename or "").endswith(".pdf"):
        from domain.knowledge.pdf_extract import extract_text_from_pdf_smart
        return extract_text_from_pdf_smart(raw)
    return ""


async def _first_turn(
    doctor_id: str, text: str,
    patient_name: str, patient_gender: Optional[str], patient_age: Optional[int],
) -> DoctorInterviewResponse:
    from agent.tools.resolve import resolve
    from domain.patients.interview_session import create_session
    from domain.patients.interview_turn import interview_turn
    from domain.patients.completeness import check_completeness, count_filled, TOTAL_FIELDS

    # Resolve or create patient
    resolved = await resolve(patient_name, doctor_id, auto_create=True,
                              gender=patient_gender, age=patient_age)
    if "status" in resolved and resolved.get("status") == "error":
        raise HTTPException(422, resolved.get("message", "Patient resolution failed"))

    patient_id = resolved["patient_id"]

    # Create interview session in doctor mode
    session = await create_session(doctor_id, patient_id, mode="doctor")

    # Run first turn
    response = await interview_turn(session.id, text)

    missing = check_completeness(response.collected)
    missing_req = [f for f in ("chief_complaint", "present_illness") if not response.collected.get(f)]

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=response.reply,
        collected=response.collected,
        progress={"filled": count_filled(response.collected), "total": TOTAL_FIELDS},
        missing=missing,
        missing_required=missing_req,
        status="ready_for_confirm" if not missing else "interviewing",
        patient_id=patient_id,
    )


async def _continue_turn(session, text: str) -> DoctorInterviewResponse:
    from domain.patients.interview_turn import interview_turn
    from domain.patients.completeness import check_completeness, count_filled, TOTAL_FIELDS

    response = await interview_turn(session.id, text)

    missing = check_completeness(response.collected)
    missing_req = [f for f in ("chief_complaint", "present_illness") if not response.collected.get(f)]

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=response.reply,
        collected=response.collected,
        progress={"filled": count_filled(response.collected), "total": TOTAL_FIELDS},
        missing=missing,
        missing_required=missing_req,
        status="ready_for_confirm" if not missing else "interviewing",
        patient_id=session.patient_id,
    )


# ── POST /confirm ────────────────────────────────────────────────

@router.post("/confirm", response_model=InterviewConfirmResponse)
async def interview_confirm_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor)

    if session.status != "interviewing":
        raise HTTPException(400, f"Session status is {session.status}, cannot confirm")

    from domain.patients.interview_session import save_session
    from domain.records.structuring import structure_medical_record
    from agent.tools.doctor import _create_pending_record
    from db.models.interview_session import InterviewStatus

    # Build clinical text from collected fields
    clinical_text = _build_clinical_text(session.collected)

    # Create pending draft via same pipeline as create_record tool
    result = await _create_pending_record(
        resolved_doctor, session.patient_id, "",
        clinical_text=clinical_text,
    )

    session.status = InterviewStatus.draft_created
    await save_session(session)

    return InterviewConfirmResponse(
        status=result.get("status", "pending_confirmation"),
        preview=result.get("preview"),
        pending_id=result.get("pending_id"),
    )


def _build_clinical_text(collected: Dict[str, str]) -> str:
    """Combine collected interview fields into a clinical text block."""
    from domain.patients.interview_turn import FIELD_LABELS
    parts = []
    for key, label in FIELD_LABELS.items():
        value = collected.get(key, "")
        if value:
            parts.append(f"{label}：{value}")
    return "\n".join(parts)


# ── POST /cancel ─────────────────────────────────────────────────

@router.post("/cancel")
async def interview_cancel_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor)

    from domain.patients.interview_session import save_session
    from db.models.interview_session import InterviewStatus

    session.status = InterviewStatus.abandoned
    await save_session(session)

    return {"status": "abandoned"}
```

- [ ] **Step 2: Register the router**

Find where routers are registered (likely `src/main.py` or `src/channels/web/__init__.py`) and add:
```python
from channels.web.doctor_interview import router as doctor_interview_router
app.include_router(doctor_interview_router)
```

- [ ] **Step 3: Write endpoint tests**

```python
# tests/core/test_doctor_interview_endpoints.py
"""Doctor interview endpoint contracts."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_first_turn_requires_patient_name():
    """POST /turn without patient_name and no session_id → 422."""
    from channels.web.doctor_interview import interview_turn_endpoint
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await interview_turn_endpoint(
            text="头痛三天", session_id=None, patient_name=None,
            doctor_id="dr_test", authorization=None,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_verify_session_wrong_doctor():
    """Loading another doctor's session → 403."""
    from channels.web.doctor_interview import _verify_session
    from fastapi import HTTPException
    from domain.patients.interview_session import InterviewSession

    mock_session = InterviewSession(
        id="s1", doctor_id="dr_other", patient_id=1, mode="doctor",
    )
    with patch("channels.web.doctor_interview.load_session", new_callable=AsyncMock, return_value=mock_session):
        with pytest.raises(HTTPException) as exc:
            await _verify_session("s1", "dr_test")
    assert exc.value.status_code == 403
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_doctor_interview_endpoints.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/doctor_interview.py tests/core/test_doctor_interview_endpoints.py
git commit -m "feat: doctor interview router — turn/confirm/cancel endpoints"
```

---

### Task 4: Remove `create_record` from agent + update dispatch

**Files:**
- Modify: `src/agent/tools/doctor.py` (remove from DOCTOR_TOOLS)
- Modify: `src/agent/handle_turn.py` (update create_record dispatch)
- Modify: `src/agent/prompts/doctor-agent.md` (update prompt)
- Test: `tests/core/test_action_dispatch.py` (update existing test)

- [ ] **Step 1: Update `_dispatch_action_hint` for create_record**

In `src/agent/handle_turn.py`, change the `Action.create_record` handler:
```python
    if action == Action.create_record:
        return "请使用「新增病历」功能来采集患者信息，AI将帮您结构化记录。"
```

- [ ] **Step 2: Remove `create_record` from DOCTOR_TOOLS**

In `src/agent/tools/doctor.py`, remove `create_record` from the list:
```python
DOCTOR_TOOLS = [
    query_records, list_patients, list_tasks,
    update_record, create_task,  # create_record removed
]
```

- [ ] **Step 3: Update doctor agent prompt**

In `src/agent/prompts/doctor-agent.md`, add a rule:
```
## 创建病历
不要使用 create_record 工具。当医生想要创建新病历时，回复：
"请使用「新增病历」功能来采集患者信息，AI将帮您结构化记录。"
```

- [ ] **Step 4: Update existing test**

In `tests/core/test_action_dispatch.py`, update `test_create_record_falls_through_to_agent`:
```python
@pytest.mark.asyncio
async def test_create_record_returns_redirect_message():
    """create_record → returns redirect message to use interview mode."""
    from agent.handle_turn import _dispatch_action_hint
    reply = await _dispatch_action_hint(Action.create_record, "张三", "dr_test", agent=None)
    assert "新增病历" in reply
```

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_action_dispatch.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASSED

- [ ] **Step 6: Commit**

```bash
git add src/agent/tools/doctor.py src/agent/handle_turn.py src/agent/prompts/doctor-agent.md tests/core/test_action_dispatch.py
git commit -m "feat: remove create_record from agent, redirect to interview mode"
```

---

### Task 5: Frontend — interview mode in ChatSection

**Files:**
- Modify: `frontend/web/src/pages/doctor/ChatSection.jsx`
- Modify: `frontend/web/src/api.js`

- [ ] **Step 1: Add API functions**

In `frontend/web/src/api.js`, add:
```js
export async function interviewTurn(formData) {
  return request("/api/records/interview/turn", {
    method: "POST",
    body: formData,  // FormData for multipart (supports file upload)
    _timeout: 120000,
  });
}

export async function interviewConfirm(sessionId, doctorId) {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  if (doctorId) formData.append("doctor_id", doctorId);
  return request("/api/records/interview/confirm", {
    method: "POST",
    body: formData,
    _timeout: 120000,
  });
}

export async function interviewCancel(sessionId, doctorId) {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  if (doctorId) formData.append("doctor_id", doctorId);
  return request("/api/records/interview/cancel", {
    method: "POST",
    body: formData,
  });
}
```

- [ ] **Step 2: Add `activeInterview` state to ChatSection**

In `ChatSection.jsx`, add localStorage-persisted state:
```js
const [activeInterview, setActiveInterview] = useState(() => {
    const saved = localStorage.getItem(`active_interview:${doctorId}`);
    try { return saved ? JSON.parse(saved) : null; } catch { return null; }
});

useEffect(() => {
    if (activeInterview) {
        localStorage.setItem(`active_interview:${doctorId}`, JSON.stringify(activeInterview));
    } else {
        localStorage.removeItem(`active_interview:${doctorId}`);
    }
}, [activeInterview, doctorId]);
```

- [ ] **Step 3: Update "新增病历" chip handler**

Change `handleCommandSelect` for `create_record`:
```js
function handleCommandSelect(cmd) {
    if (cmd.key === Action.CREATE_RECORD) {
        // Enter interview mode instead of normal chip
        setActiveInterview({ sessionId: null, progress: { filled: 0, total: 7 } });
        setActiveChip(null);
        return;
    }
    // ... rest unchanged
}
```

- [ ] **Step 4: Route messages during active interview**

When `activeInterview` is set, send to interview endpoint:
```js
async function handleInterviewSend() {
    const text = input.trim();
    if (!text) return;

    setMessages(prev => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setLoading(true);

    try {
        const formData = new FormData();
        formData.append("text", text);
        formData.append("doctor_id", doctorId);

        if (!activeInterview.sessionId) {
            // First turn — extract patient name from text (simplified: use full text)
            formData.append("patient_name", text.split("，")[0].replace(/[新患者]/g, "").trim() || text);
        } else {
            formData.append("session_id", activeInterview.sessionId);
        }

        const data = await interviewTurn(formData);

        setActiveInterview({
            sessionId: data.session_id,
            progress: data.progress,
            status: data.status,
            patientId: data.patient_id,
        });

        const progressText = `（${data.progress.filled}/${data.progress.total}）`;
        setMessages(prev => [...prev, {
            role: "assistant", content: data.reply, ts: nowTs(),
            interviewProgress: data.progress,
        }]);

    } catch (error) {
        setMessages(prev => [...prev, {
            role: "assistant",
            content: `采集出错：${error.message}`,
            ts: nowTs(),
        }]);
    } finally {
        setLoading(false);
    }
}
```

- [ ] **Step 5: Show progress indicator and confirm/cancel buttons**

Add above the input bar when interview is active:
```jsx
{activeInterview && (
    <Box sx={{ px: 1.5, py: 0.8, borderTop: "1px solid #e0e0e0", bgcolor: "#f0f9f0",
        display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="caption" sx={{ color: "#2e7d32" }}>
            病历采集中 {activeInterview.progress?.filled}/{activeInterview.progress?.total}
        </Typography>
        <Box sx={{ display: "flex", gap: 1 }}>
            {activeInterview.status === "ready_for_confirm" && (
                <Button size="small" variant="contained" color="success"
                    onClick={handleInterviewConfirm}>
                    确认生成
                </Button>
            )}
            <Button size="small" variant="text" color="error"
                onClick={handleInterviewCancel}>
                取消
            </Button>
        </Box>
    </Box>
)}
```

- [ ] **Step 6: Implement confirm and cancel handlers**

```js
async function handleInterviewConfirm() {
    if (!activeInterview?.sessionId) return;
    setLoading(true);
    try {
        const data = await interviewConfirm(activeInterview.sessionId, doctorId);
        setMessages(prev => [...prev, {
            role: "assistant",
            content: `病历草稿已生成。${data.preview ? '\n\n' + data.preview : ''}`,
            ts: nowTs(),
        }]);
        setActiveInterview(null);
    } catch (error) {
        setMessages(prev => [...prev, {
            role: "assistant", content: `生成失败：${error.message}`, ts: nowTs(),
        }]);
    } finally {
        setLoading(false);
    }
}

async function handleInterviewCancel() {
    if (activeInterview?.sessionId) {
        try { await interviewCancel(activeInterview.sessionId, doctorId); } catch {}
    }
    setActiveInterview(null);
    setMessages(prev => [...prev, {
        role: "assistant", content: "病历采集已取消。", ts: nowTs(),
    }]);
}
```

- [ ] **Step 7: Wire send button to interview handler when active**

Update `handleChipSend` or the send button onClick:
```js
// In the send button / Enter handler:
if (activeInterview) {
    handleInterviewSend();
} else {
    handleChipSend();
}
```

- [ ] **Step 8: Verify frontend builds**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npx vite build --mode development 2>&1 | tail -3`
Expected: Build succeeds

- [ ] **Step 9: Commit**

```bash
git add frontend/web/src/pages/doctor/ChatSection.jsx frontend/web/src/api.js
git commit -m "feat: frontend interview mode — progress indicator, confirm/cancel, file upload"
```

---

### Task 6: Patient interview ownership fix (pre-existing bug)

**Files:**
- Modify: `src/channels/web/patient_interview_routes.py`
- Test: `tests/core/test_patient_interview_ownership.py`

- [ ] **Step 1: Add ownership check to patient `/turn` endpoint**

In `src/channels/web/patient_interview_routes.py`, in the `/turn` handler,
after loading the session, verify patient_id:

```python
# After: session = await load_session(session_id)
# Add:
if session.patient_id != patient_id:  # patient_id from auth
    raise HTTPException(403, "Not your session")
```

- [ ] **Step 2: Write test**

```python
# tests/core/test_patient_interview_ownership.py
"""Patient interview session ownership verification."""
# Test that a patient cannot write to another patient's session
```

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/patient_interview_routes.py tests/core/test_patient_interview_ownership.py
git commit -m "fix: add patient_id ownership check to interview /turn endpoint"
```

---

### Task 7: Integration test + manual QA

- [ ] **Step 1: Start dev servers and test the full flow**

1. Start backend: `.venv/bin/python -m uvicorn main:app --reload --port 8000`
2. Start frontend: `cd frontend/web && npx vite --port 5173`
3. Open browser, test:
   - Click "新增病历" → interview mode activates
   - Type "张三，男45岁，头痛三天伴恶心" → fields extracted, progress shown
   - Type "既往高血压10年，无过敏，家族史无特殊，个人史无特殊" → more fields filled
   - Progress reaches 6/7 → "确认生成" button appears
   - Click confirm → pending draft created
   - Verify existing chat (no chip) still works normally
   - Verify "取消" abandons interview

- [ ] **Step 2: Test edge cases**

   - Type "新患者张三头痛" in normal chat → agent redirects to interview mode
   - Upload an image during interview → OCR extracts + merges
   - Refresh page during interview → state restored from localStorage
   - Click "新增病历" while interview active → old abandoned, new started

- [ ] **Step 3: Run full test suite**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All tests pass
