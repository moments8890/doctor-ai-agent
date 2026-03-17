# Patient Pre-Consultation Interview — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Patients complete an AI-guided pre-consultation interview via web, producing a structured medical record delivered to the doctor's task queue.

**Architecture:** New interview pipeline (separate from UEC) sharing LLM providers, DB models, and notification system. Patient self-registers with phone + year_of_birth, selects a doctor, completes multi-turn interview, confirms summary. Creates MedicalRecord + DoctorTask on confirmation.

**Tech Stack:** Python 3.9+ / FastAPI / SQLAlchemy async / OpenAI-compatible LLM / React (Material-UI) frontend

**Spec:** `docs/superpowers/specs/2026-03-17-patient-pre-consultation-design.md`
**ADR:** `docs/adr/0016-patient-pre-consultation-interview.md`

---

### Task 1: Schema Changes (Doctor + Patient + InterviewSession)

**Files:**
- Modify: `src/db/models/doctor.py:87-106` — add `accepting_patients`, `department`
- Create: `src/db/models/interview_session.py` — InterviewSessionDB model
- Modify: `src/db/models/__init__.py` — export new model
- Modify: `src/db/models/patient.py:50-55` — add phone index

- [ ] **Step 1: Add columns to Doctor model**

In `src/db/models/doctor.py`, add after `created_at`/`updated_at` fields (around line 98):

```python
accepting_patients: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

Import `Boolean` if not already imported.

- [ ] **Step 2: Create InterviewSessionDB model**

Create `src/db/models/interview_session.py`:

```python
"""Interview session for patient pre-consultation (ADR 0016)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class InterviewSessionDB(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="interviewing")
    collected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict
    conversation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_interview_patient", "patient_id", "status"),
        Index("ix_interview_doctor", "doctor_id", "status"),
    )
```

- [ ] **Step 3: Export new model in `__init__.py`**

In `src/db/models/__init__.py`, add:

```python
from db.models.interview_session import InterviewSessionDB
```

And add `"InterviewSessionDB"` to `__all__` if one exists.

- [ ] **Step 4: Add phone index to Patient model**

In `src/db/models/patient.py`, add to `__table_args__` tuple (around line 50):

```python
Index("ix_patients_doctor_phone", "doctor_id", "phone"),
```

- [ ] **Step 5: Apply schema to dev DB**

```bash
sqlite3 /Volumes/ORICO/Code/doctor-ai-agent/data/patients.db <<'SQL'
ALTER TABLE doctors ADD COLUMN accepting_patients BOOLEAN DEFAULT 0;
ALTER TABLE doctors ADD COLUMN department VARCHAR(64);
CREATE INDEX IF NOT EXISTS ix_patients_doctor_phone ON patients(doctor_id, phone);
SQL
```

The `interview_sessions` table will be created by `create_tables()` on next startup.

- [ ] **Step 6: Commit**

```bash
git add src/db/models/doctor.py src/db/models/interview_session.py src/db/models/__init__.py src/db/models/patient.py
git commit -m "feat: schema for patient interview (ADR 0016)

Add accepting_patients + department to Doctor, InterviewSessionDB model,
phone index on patients table."
```

---

### Task 2: Interview Completeness & Merge Logic

**Files:**
- Create: `src/services/patient_interview/__init__.py`
- Create: `src/services/patient_interview/completeness.py`

- [ ] **Step 1: Create package init**

Create `src/services/patient_interview/__init__.py` (empty file).

- [ ] **Step 2: Create completeness module**

Create `src/services/patient_interview/completeness.py`:

```python
"""Field completeness check and merge logic for patient interview (ADR 0016)."""
from __future__ import annotations

from typing import Dict, List

REQUIRED = ("chief_complaint", "present_illness")
ASK_AT_LEAST = ("past_history", "allergy_history", "family_history", "personal_history")
OPTIONAL = ("marital_reproductive",)

ALL_COLLECTABLE = REQUIRED + ASK_AT_LEAST + OPTIONAL
TOTAL_FIELDS = len(ALL_COLLECTABLE)  # 7

APPENDABLE = frozenset({
    "present_illness", "past_history", "allergy_history",
    "family_history", "personal_history", "marital_reproductive",
})


def check_completeness(collected: Dict[str, str]) -> List[str]:
    """Return list of missing field names. Empty list = ready for review."""
    missing = [f for f in REQUIRED if not collected.get(f)]
    if not missing:
        missing = [f for f in ASK_AT_LEAST if f not in collected]
    return missing


def count_filled(collected: Dict[str, str]) -> int:
    """Count how many of the 7 collectable fields have values."""
    return sum(1 for f in ALL_COLLECTABLE if collected.get(f))


def merge_extracted(collected: Dict[str, str], extracted: Dict[str, str]) -> None:
    """Merge LLM-extracted fields into collected dict. Mutates collected in-place."""
    for field, value in extracted.items():
        if not value or field not in ALL_COLLECTABLE:
            continue
        if field in APPENDABLE:
            existing = collected.get(field, "")
            collected[field] = f"{existing}；{value}".strip("；") if existing else value
        else:
            collected[field] = value
```

- [ ] **Step 3: Commit**

```bash
git add src/services/patient_interview/
git commit -m "feat: interview completeness check and field merge (ADR 0016)"
```

---

### Task 3: Interview Session Manager

**Files:**
- Create: `src/services/patient_interview/session.py`

- [ ] **Step 1: Create session manager**

Create `src/services/patient_interview/session.py`:

```python
"""Interview session persistence (ADR 0016)."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.log import log


@dataclass
class InterviewSession:
    id: str
    doctor_id: str
    patient_id: int
    status: str = "interviewing"  # interviewing | reviewing | confirmed | abandoned
    collected: Dict[str, str] = field(default_factory=dict)
    conversation: List[Dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0


async def create_session(doctor_id: str, patient_id: int) -> InterviewSession:
    """Create a new interview session in the DB."""
    from db.engine import AsyncSessionLocal
    from db.models.interview_session import InterviewSessionDB

    session_id = str(uuid.uuid4())
    now = datetime.utcnow()

    async with AsyncSessionLocal() as db:
        db_row = InterviewSessionDB(
            id=session_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            status="interviewing",
            collected="{}",
            conversation="[]",
            turn_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(db_row)
        await db.commit()

    log(f"[interview] session created id={session_id} patient={patient_id} doctor={doctor_id}")
    return InterviewSession(id=session_id, doctor_id=doctor_id, patient_id=patient_id)


async def load_session(session_id: str) -> Optional[InterviewSession]:
    """Load an interview session from DB. Returns None if not found."""
    from db.engine import AsyncSessionLocal
    from db.models.interview_session import InterviewSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(InterviewSessionDB).where(InterviewSessionDB.id == session_id)
        )).scalar_one_or_none()

        if row is None:
            return None

        return InterviewSession(
            id=row.id,
            doctor_id=row.doctor_id,
            patient_id=row.patient_id,
            status=row.status,
            collected=json.loads(row.collected or "{}"),
            conversation=json.loads(row.conversation or "[]"),
            turn_count=row.turn_count,
        )


async def save_session(session: InterviewSession) -> None:
    """Persist interview session state to DB."""
    from db.engine import AsyncSessionLocal
    from db.models.interview_session import InterviewSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(InterviewSessionDB).where(InterviewSessionDB.id == session.id)
        )).scalar_one_or_none()

        if row is None:
            log(f"[interview] save_session: session {session.id} not found", level="error")
            return

        row.status = session.status
        row.collected = json.dumps(session.collected, ensure_ascii=False)
        row.conversation = json.dumps(session.conversation, ensure_ascii=False)
        row.turn_count = session.turn_count
        row.updated_at = datetime.utcnow()
        await db.commit()


async def get_active_session(patient_id: int, doctor_id: str) -> Optional[InterviewSession]:
    """Find an active (interviewing) session for this patient+doctor."""
    from db.engine import AsyncSessionLocal
    from db.models.interview_session import InterviewSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(InterviewSessionDB).where(
                InterviewSessionDB.patient_id == patient_id,
                InterviewSessionDB.doctor_id == doctor_id,
                InterviewSessionDB.status == "interviewing",
            ).order_by(InterviewSessionDB.created_at.desc()).limit(1)
        )).scalar_one_or_none()

        if row is None:
            return None

        return InterviewSession(
            id=row.id,
            doctor_id=row.doctor_id,
            patient_id=row.patient_id,
            status=row.status,
            collected=json.loads(row.collected or "{}"),
            conversation=json.loads(row.conversation or "[]"),
            turn_count=row.turn_count,
        )
```

- [ ] **Step 2: Commit**

```bash
git add src/services/patient_interview/session.py
git commit -m "feat: interview session manager (ADR 0016)"
```

---

### Task 4: Interview LLM Prompt

**Files:**
- Create: `src/prompts/patient-interview.md`

- [ ] **Step 1: Create interview prompt**

Create `src/prompts/patient-interview.md`:

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

- [ ] **Step 2: Update prompts README**

In `src/prompts/README.md`, add to the index table:

```markdown
| `patient-interview.md` | `services/patient_interview/turn.py` | AI-guided patient pre-consultation interview |
```

- [ ] **Step 3: Commit**

```bash
git add src/prompts/patient-interview.md src/prompts/README.md
git commit -m "feat: patient interview LLM prompt (ADR 0016)"
```

---

### Task 5: Interview Turn Handler

**Files:**
- Create: `src/services/patient_interview/turn.py`

- [ ] **Step 1: Create turn handler**

Create `src/services/patient_interview/turn.py`:

```python
"""Interview turn handler — core loop (ADR 0016)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from services.ai.llm_client import _PROVIDERS
from services.patient_interview.completeness import (
    TOTAL_FIELDS,
    check_completeness,
    count_filled,
    merge_extracted,
)
from services.patient_interview.session import InterviewSession, load_session, save_session
from utils.log import log
from utils.prompt_loader import get_prompt_sync

MAX_TURNS = 30

_INTERVIEW_PROMPT: Optional[str] = None

FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "family_history": "家族史",
    "personal_history": "个人史",
    "marital_reproductive": "婚育史",
}


@dataclass
class InterviewResponse:
    reply: str
    collected: Dict[str, str]
    progress: Dict[str, int]
    status: str


def _get_prompt() -> str:
    global _INTERVIEW_PROMPT
    if _INTERVIEW_PROMPT is None:
        _INTERVIEW_PROMPT = get_prompt_sync("patient-interview")
    return _INTERVIEW_PROMPT


async def _load_patient_info(patient_id: int) -> Dict[str, Any]:
    """Load patient demographics for prompt context."""
    from db.engine import AsyncSessionLocal
    from db.models import Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        patient = (await db.execute(
            select(Patient).where(Patient.id == patient_id)
        )).scalar_one_or_none()

    if patient is None:
        return {"name": "未知", "gender": "未知", "age": "未知"}

    age = "未知"
    if patient.year_of_birth:
        age = str(datetime.now().year - patient.year_of_birth)

    return {
        "name": patient.name or "未知",
        "gender": patient.gender or "未知",
        "age": age,
    }


async def _call_interview_llm(
    conversation: List[Dict[str, str]],
    collected: Dict[str, str],
    patient_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Call LLM with interview prompt. Returns parsed {reply, extracted}."""
    missing = check_completeness(collected)
    missing_labels = [f"{FIELD_LABELS.get(f, f)}" for f in missing]

    prompt_template = _get_prompt()
    system_prompt = (
        prompt_template
        .replace("{name}", patient_info["name"])
        .replace("{gender}", patient_info["gender"])
        .replace("{age}", str(patient_info["age"]))
        .replace("{collected_json}", json.dumps(collected, ensure_ascii=False, indent=2))
        .replace("{missing_fields}", "、".join(missing_labels) if missing_labels else "无（可进入确认）")
        .replace("{conversation}", "")  # conversation goes in messages, not system prompt
    )

    # Build messages: system + conversation history + latest user message
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in conversation[-20:]:  # cap context to last 20 turns
        messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

    provider_name = os.environ.get("CONVERSATION_LLM") or os.environ.get("ROUTING_LLM", "deepseek")
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        provider_name = "deepseek"
        provider = _PROVIDERS["deepseek"]

    extra_headers = {"anthropic-version": "2023-06-01"} if provider_name == "claude" else {}
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        timeout=float(os.environ.get("INTERVIEW_LLM_TIMEOUT", "30")),
        max_retries=0,
        default_headers=extra_headers,
    )

    model_name = provider.get("model", "deepseek-chat")
    _tag = f"[interview:{provider_name}:{model_name}]"
    log(f"{_tag} turn request")

    completion = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.3,
        response_format={"type": "json_object"},
        max_tokens=500,
    )

    raw = completion.choices[0].message.content or ""
    log(f"{_tag} response: {raw[:200]}")

    data = json.loads(raw)
    return {
        "reply": data.get("reply", "请继续描述您的情况。"),
        "extracted": data.get("extracted", {}),
    }


def _make_progress(collected: Dict[str, str]) -> Dict[str, int]:
    return {"filled": count_filled(collected), "total": TOTAL_FIELDS}


async def interview_turn(session_id: str, patient_text: str) -> InterviewResponse:
    """Process one patient message in the interview. Core loop."""
    session = await load_session(session_id)
    if session is None:
        return InterviewResponse(
            reply="问诊会话不存在。", collected={},
            progress={"filled": 0, "total": TOTAL_FIELDS}, status="error",
        )
    if session.status not in ("interviewing",):
        return InterviewResponse(
            reply="该问诊已结束。", collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )

    session.conversation.append({
        "role": "user", "content": patient_text,
        "timestamp": datetime.utcnow().isoformat(),
    })
    session.turn_count += 1

    # Force review if turn limit reached
    if session.turn_count >= MAX_TURNS:
        session.status = "reviewing"
        reply = "我已经收集了足够的信息，请查看摘要并确认提交。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )

    # Main LLM call
    try:
        patient_info = await _load_patient_info(session.patient_id)
        llm_response = await _call_interview_llm(
            conversation=session.conversation,
            collected=session.collected,
            patient_info=patient_info,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log(f"[interview] LLM parse error: {e}", level="warning")
        reply = "抱歉，我没有理解，请再说一次。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )
    except Exception as e:
        log(f"[interview] LLM call failed: {e}", level="error")
        reply = "系统暂时繁忙，请稍后再试。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )

    # Merge extracted fields
    merge_extracted(session.collected, llm_response["extracted"])

    # Completeness check
    missing = check_completeness(session.collected)

    if not missing:
        session.status = "reviewing"
        reply = "我已经收集了您的基本信息。请点击「摘要」查看并确认提交。"
    else:
        reply = llm_response["reply"]

    session.conversation.append({"role": "assistant", "content": reply})
    await save_session(session)

    return InterviewResponse(
        reply=reply, collected=session.collected,
        progress=_make_progress(session.collected), status=session.status,
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/services/patient_interview/turn.py
git commit -m "feat: interview turn handler with LLM integration (ADR 0016)"
```

---

### Task 6: Interview Summary & Handoff

**Files:**
- Create: `src/services/patient_interview/summary.py`

- [ ] **Step 1: Create summary module**

Create `src/services/patient_interview/summary.py`:

```python
"""Generate MedicalRecord + DoctorTask from completed interview (ADR 0016)."""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from db.models.medical_record import MedicalRecord
from services.patient_interview.completeness import ALL_COLLECTABLE
from utils.log import log

FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "personal_history": "个人史",
    "marital_reproductive": "婚育史",
    "family_history": "家族史",
}


def generate_content(collected: Dict[str, str]) -> str:
    """Generate prose content string from collected fields."""
    lines: List[str] = []
    for field in ALL_COLLECTABLE:
        value = collected.get(field, "")
        if not value:
            continue
        label = FIELD_LABELS.get(field, field)
        lines.append(f"{label}：{value}")
    return "\n".join(lines) if lines else ""


def generate_structured(collected: Dict[str, str]) -> Dict[str, str]:
    """Map collected fields to the 14-field outpatient schema."""
    from services.medical_record_schema import FIELD_KEYS
    structured: Dict[str, str] = {}
    for key in FIELD_KEYS:
        structured[key] = collected.get(key, "")
    return structured


def extract_tags(collected: Dict[str, str]) -> List[str]:
    """Extract keyword tags from chief_complaint and present_illness."""
    tags: List[str] = []
    for field in ("chief_complaint", "present_illness"):
        value = collected.get(field, "")
        if not value:
            continue
        # Split on common delimiters and take short terms
        parts = re.split(r"[，。；、\s]+", value)
        for part in parts:
            part = part.strip()
            if 1 < len(part) <= 10 and part not in tags:
                tags.append(part)
    return tags[:10]  # cap at 10 tags


def build_medical_record(collected: Dict[str, str]) -> MedicalRecord:
    """Build a MedicalRecord from interview collected fields."""
    content = generate_content(collected)
    if not content:
        content = "预问诊记录（无临床内容）"

    structured = generate_structured(collected)
    tags = extract_tags(collected)

    return MedicalRecord(
        content=content,
        structured=structured,
        tags=tags,
        record_type="interview_summary",
    )


async def confirm_interview(
    session_id: str,
    doctor_id: str,
    patient_id: int,
    patient_name: str,
    collected: Dict[str, str],
) -> Dict[str, int]:
    """Finalize interview: save record + create task. Returns {record_id, task_id}."""
    from db.crud.records import save_record
    from db.engine import AsyncSessionLocal
    from db.repositories.tasks import TaskRepository

    record = build_medical_record(collected)

    async with AsyncSessionLocal() as db:
        # Save medical record
        db_record = await save_record(
            db, doctor_id, record, patient_id,
            needs_review=True, commit=False,
        )

        # Create review task
        repo = TaskRepository(db)
        task = await repo.create(
            doctor_id=doctor_id,
            task_type="general",
            title=f"审阅预问诊：{patient_name}",
            patient_id=patient_id,
            record_id=db_record.id,
        )

        await db.commit()

    log(f"[interview] confirmed session={session_id} record={db_record.id} task={task.id}")
    return {"record_id": db_record.id, "task_id": task.id}
```

- [ ] **Step 2: Commit**

```bash
git add src/services/patient_interview/summary.py
git commit -m "feat: interview summary generation and handoff (ADR 0016)"
```

---

### Task 7: Patient Auth & Doctor Search API

**Files:**
- Modify: `src/channels/web/patient_portal.py` — add register, login-by-phone, doctor search

- [ ] **Step 1: Add doctor search endpoint**

In `src/channels/web/patient_portal.py`, add after existing endpoints:

```python
@router.get("/doctors")
async def list_accepting_doctors():
    """List doctors accepting patients (for patient registration)."""
    from db.models import Doctor
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        stmt = select(Doctor).where(Doctor.accepting_patients == True)
        rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "doctor_id": d.doctor_id,
            "name": d.name or d.doctor_id,
            "department": d.department or "",
        }
        for d in rows
    ]
```

- [ ] **Step 2: Add patient registration endpoint**

```python
@router.post("/register")
async def register_patient(
    doctor_id: str = Body(...),
    name: str = Body(...),
    gender: str = Body(None),
    year_of_birth: int = Body(...),
    phone: str = Body(...),
):
    """Patient self-registration. Links to existing record if name matches."""
    from db.models import Patient, Doctor
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Validate doctor exists and is accepting
        doctor = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == doctor_id)
        )).scalar_one_or_none()
        if doctor is None or not doctor.accepting_patients:
            raise HTTPException(404, "未找到该医生")

        # Check for existing patient record
        patient = (await db.execute(
            select(Patient).where(
                Patient.doctor_id == doctor_id,
                Patient.name == name,
            )
        )).scalar_one_or_none()

        if patient:
            # Validate non-null fields don't conflict
            if patient.gender and gender and patient.gender != gender:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            if patient.year_of_birth and patient.year_of_birth != year_of_birth:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            if patient.phone and patient.phone != phone:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            # Backfill nulls
            if not patient.gender and gender:
                patient.gender = gender
            if not patient.year_of_birth:
                patient.year_of_birth = year_of_birth
            if not patient.phone:
                patient.phone = phone
            await db.commit()
        else:
            # Create new patient
            patient = Patient(
                doctor_id=doctor_id,
                name=name,
                gender=gender,
                year_of_birth=year_of_birth,
                phone=phone,
            )
            db.add(patient)
            await db.commit()
            await db.refresh(patient)

    token = _issue_patient_token(patient.id, doctor_id, getattr(patient, "access_code_version", 0))
    return {"token": token, "patient_id": patient.id, "patient_name": patient.name}
```

- [ ] **Step 3: Add login-by-phone endpoint**

```python
@router.post("/login")
async def login_by_phone(
    phone: str = Body(...),
    year_of_birth: int = Body(...),
    doctor_id: str = Body(None),
):
    """Patient login with phone + year_of_birth."""
    from db.models import Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        if doctor_id:
            # Direct login to specific doctor
            patient = (await db.execute(
                select(Patient).where(
                    Patient.doctor_id == doctor_id,
                    Patient.phone == phone,
                    Patient.year_of_birth == year_of_birth,
                )
            )).scalar_one_or_none()
            if patient is None:
                raise HTTPException(401, "手机号或出生年份不正确")
            token = _issue_patient_token(patient.id, doctor_id, getattr(patient, "access_code_version", 0))
            return {"token": token, "patient_id": patient.id, "patient_name": patient.name, "doctor_id": doctor_id}
        else:
            # Find all patient records for this phone+yob
            patients = (await db.execute(
                select(Patient).where(
                    Patient.phone == phone,
                    Patient.year_of_birth == year_of_birth,
                )
            )).scalars().all()
            if not patients:
                raise HTTPException(401, "手机号或出生年份不正确")
            if len(patients) == 1:
                p = patients[0]
                token = _issue_patient_token(p.id, p.doctor_id, getattr(p, "access_code_version", 0))
                return {"token": token, "patient_id": p.id, "patient_name": p.name, "doctor_id": p.doctor_id}
            # Multiple doctors — return list for picker
            return {
                "needs_doctor_selection": True,
                "doctors": [
                    {"doctor_id": p.doctor_id, "patient_name": p.name}
                    for p in patients
                ],
            }
```

- [ ] **Step 4: Add `Body` import if missing**

Ensure `from fastapi import Body` is in the imports at top of file.

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/patient_portal.py
git commit -m "feat: patient register, login-by-phone, doctor search API (ADR 0016)"
```

---

### Task 8: Interview API Endpoints

**Files:**
- Create: `src/channels/web/patient_interview_routes.py`
- Modify: `src/main.py` — mount the new router

- [ ] **Step 1: Create interview routes**

Create `src/channels/web/patient_interview_routes.py`:

```python
"""Patient interview API endpoints (ADR 0016)."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from channels.web.patient_portal import _authenticate_patient
from services.patient_interview.session import (
    create_session,
    get_active_session,
    load_session,
    save_session,
)
from services.patient_interview.summary import confirm_interview
from services.patient_interview.turn import interview_turn
from utils.log import log

router = APIRouter(prefix="/api/patient/interview", tags=["patient-interview"])

_GREETING = "您好！我是您的预问诊助手。请问您有什么不舒服？"


@router.post("/start")
async def start_interview(
    authorization: str = "",
):
    """Create or resume an interview session."""
    patient = await _authenticate_patient(authorization)

    # Check for existing active session
    active = await get_active_session(patient["patient_id"], patient["doctor_id"])
    if active:
        return {
            "session_id": active.id,
            "reply": "欢迎回来！我们继续之前的问诊。",
            "collected": active.collected,
            "progress": {"filled": _count(active.collected), "total": 7},
            "status": active.status,
            "resumed": True,
        }

    session = await create_session(patient["doctor_id"], patient["patient_id"])
    return {
        "session_id": session.id,
        "reply": _GREETING,
        "collected": {},
        "progress": {"filled": 0, "total": 7},
        "status": "interviewing",
        "resumed": False,
    }


@router.post("/turn")
async def turn(
    session_id: str = Body(...),
    text: str = Body(...),
    authorization: str = "",
):
    """Send a patient message and get AI reply."""
    await _authenticate_patient(authorization)

    if not text.strip():
        raise HTTPException(400, "消息不能为空")
    if len(text) > 2000:
        raise HTTPException(400, "消息过长")

    response = await interview_turn(session_id, text.strip())

    if response.status == "error":
        raise HTTPException(404, response.reply)

    return {
        "reply": response.reply,
        "collected": response.collected,
        "progress": response.progress,
        "status": response.status,
    }


@router.get("/current")
async def current_session(
    authorization: str = "",
):
    """Get active interview session state, or null."""
    patient = await _authenticate_patient(authorization)
    active = await get_active_session(patient["patient_id"], patient["doctor_id"])

    if active is None:
        return None

    return {
        "session_id": active.id,
        "collected": active.collected,
        "conversation": active.conversation,
        "progress": {"filled": _count(active.collected), "total": 7},
        "status": active.status,
    }


@router.post("/confirm")
async def confirm(
    session_id: str = Body(...),
    authorization: str = "",
):
    """Patient confirms interview summary → creates record + task."""
    patient = await _authenticate_patient(authorization)

    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "问诊会话不存在")
    if session.patient_id != patient["patient_id"]:
        raise HTTPException(403, "无权操作")
    if session.status not in ("reviewing", "interviewing"):
        raise HTTPException(400, "该问诊已结束")

    # Perform handoff
    result = await confirm_interview(
        session_id=session.id,
        doctor_id=session.doctor_id,
        patient_id=session.patient_id,
        patient_name=patient.get("patient_name", ""),
        collected=session.collected,
    )

    # Mark session confirmed
    session.status = "confirmed"
    await save_session(session)

    return {
        "status": "confirmed",
        "record_id": result["record_id"],
        "task_id": result["task_id"],
        "message": "您的预问诊信息已提交给医生，请等待医生审阅。",
    }


@router.post("/cancel")
async def cancel(
    session_id: str = Body(...),
    authorization: str = "",
):
    """Abandon interview session."""
    patient = await _authenticate_patient(authorization)

    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "问诊会话不存在")
    if session.patient_id != patient["patient_id"]:
        raise HTTPException(403, "无权操作")
    if session.status not in ("interviewing", "reviewing"):
        raise HTTPException(400, "该问诊已结束")

    session.status = "abandoned"
    await save_session(session)

    return {"status": "abandoned"}


def _count(collected: dict) -> int:
    from services.patient_interview.completeness import count_filled
    return count_filled(collected)
```

- [ ] **Step 2: Mount router in main.py**

In `src/main.py`, add import (around line 46):

```python
from channels.web.patient_interview_routes import router as patient_interview_router
```

Add include (around line 678):

```python
app.include_router(patient_interview_router)
```

- [ ] **Step 3: Fix `_authenticate_patient` to accept authorization param**

The existing `_authenticate_patient` reads from `Header`. The interview routes need to pass the authorization string. Check if the function signature supports this or if you need to pass the header value through. Adapt as needed — the key is that interview routes validate the patient JWT before processing.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/patient_interview_routes.py src/main.py
git commit -m "feat: interview API endpoints — start, turn, confirm, cancel (ADR 0016)"
```

---

### Task 9: Frontend — Patient Login & Home

**Files:**
- Modify: `frontend/src/pages/PatientPage.jsx` — rewrite with login, doctor picker, home
- Modify: `frontend/src/api.js` — add new API functions

- [ ] **Step 1: Add API helpers**

In `frontend/src/api.js`, add patient interview functions:

```javascript
// Patient interview API
export async function listDoctors() {
  const res = await fetch(`${BASE}/api/patient/doctors`);
  return res.json();
}

export async function patientRegister(doctorId, name, gender, yearOfBirth, phone) {
  const res = await fetch(`${BASE}/api/patient/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doctor_id: doctorId, name, gender, year_of_birth: yearOfBirth, phone }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || '注册失败');
  return res.json();
}

export async function patientLogin(phone, yearOfBirth, doctorId) {
  const res = await fetch(`${BASE}/api/patient/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, year_of_birth: yearOfBirth, doctor_id: doctorId || undefined }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || '登录失败');
  return res.json();
}

export async function interviewStart(token) {
  return patientRequest('/api/patient/interview/start', token, { method: 'POST' });
}

export async function interviewTurn(token, sessionId, text) {
  return patientRequest('/api/patient/interview/turn', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, text }),
  });
}

export async function interviewCurrent(token) {
  return patientRequest('/api/patient/interview/current', token);
}

export async function interviewConfirm(token, sessionId) {
  return patientRequest('/api/patient/interview/confirm', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function interviewCancel(token, sessionId) {
  return patientRequest('/api/patient/interview/cancel', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
}
```

- [ ] **Step 2: Rewrite PatientPage.jsx**

Rewrite `frontend/src/pages/PatientPage.jsx` with three views:
1. **LoginView** — phone + year_of_birth login, or register (with doctor picker)
2. **HomeView** — patient home: start interview, view records, send message
3. **InterviewView** — WeChat-style chat with summary overlay

This is the largest frontend task. Follow the existing Material-UI patterns in the codebase. Key components:

- `LoginView`: phone input, YOB input, login button. "首次使用？" link to registration form with doctor dropdown.
- `HomeView`: card-based layout with 3 action buttons. Shows active interview banner if one exists.
- `InterviewView`: scrollable chat bubbles (AI left, patient right), input bar at bottom, summary badge in header.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/PatientPage.jsx frontend/src/api.js
git commit -m "feat: patient login, home, and interview chat UI (ADR 0016)"
```

---

### Task 10: Integration Test & End-to-End Verification

**Files:**
- Modify: dev DB — set a test doctor as accepting_patients

- [ ] **Step 1: Enable a test doctor for patient access**

```bash
sqlite3 /Volumes/ORICO/Code/doctor-ai-agent/data/patients.db \
  "UPDATE doctors SET accepting_patients=1, department='神经外科' WHERE doctor_id='test_doctor';"
```

- [ ] **Step 2: Manual E2E test**

1. Start server: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -m uvicorn main:app --port 8000 --reload`
2. Open browser: `http://localhost:8000/patient`
3. Test registration flow: select doctor → fill form → submit
4. Test interview: start → answer 5-6 questions → check summary badge
5. Test confirm: verify record appears in doctor's task list
6. Test login: close browser → reopen → login with phone + YOB

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: patient pre-consultation interview system (ADR 0016)

Complete implementation of patient-side pre-consultation interview.
Patients self-register, AI conducts structured clinical interview,
delivers record to doctor's task queue on confirmation."
```

- [ ] **Step 4: Push**

```bash
git push origin main
git push gitee main
```
