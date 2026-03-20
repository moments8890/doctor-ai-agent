# P3: Doctor Dashboard & Review Workflow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a review workflow so doctors can review, edit, and confirm structured medical records from patient interviews, integrated into the existing Tasks tab.

**Architecture:** New `review_queue` table tracks pending/reviewed status independently from `medical_records`. Four REST endpoints handle list/detail/confirm/edit. Frontend extends `TasksSection.jsx` with a 3rd segment and adds a `ReviewDetail.jsx` drill-down screen.

**Tech Stack:** Python 3.9 / FastAPI / SQLAlchemy async / React 19 / MUI 7 / Zustand

**Spec:** `docs/superpowers/specs/2026-03-20-p3-doctor-dashboard-review-design.md`

**Testing policy (per AGENTS.md):** No unit tests unless explicitly requested. Integration tests not required for non-safety-critical modules. P3 is a CRUD + UI feature, not a diagnosis pipeline, so no tests in this plan.

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `src/db/models/review_queue.py` | ReviewQueue ORM model |
| `src/db/crud/review.py` | CRUD: list, get detail, confirm, update field |
| `src/channels/web/ui/review_handlers.py` | 4 REST endpoints |
| `frontend/web/src/pages/doctor/ReviewDetail.jsx` | Drill-down review screen |

### Modified files
| File | Change |
|------|--------|
| `src/db/models/records.py` | Add `old_structured` column to `MedicalRecordVersion` |
| `src/db/models/__init__.py` | Import `ReviewQueue` |
| `src/channels/web/ui/__init__.py` | Include review router |
| `src/domain/patients/interview_summary.py` | Replace DoctorTask with ReviewQueue insert in `confirm_interview()` |
| `frontend/web/src/api.js` | Add 4 API functions |
| `frontend/web/src/pages/doctor/constants.jsx` | Add review-related constants |
| `frontend/web/src/pages/doctor/TasksSection.jsx` | Add 3rd segment, review item rendering, review detail drill-down |
| `frontend/web/src/pages/DoctorPage.jsx` | Badge count includes pending reviews |

---

### Task 1: ReviewQueue ORM Model

**Files:**
- Create: `src/db/models/review_queue.py`
- Modify: `src/db/models/__init__.py`

- [ ] **Step 1: Create the ReviewQueue model**

```python
# src/db/models/review_queue.py
"""Review queue for patient interview records awaiting doctor review."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("medical_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    doctor_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending_review",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_review_queue_doctor_status_created", "doctor_id", "status", "created_at"),
    )
```

- [ ] **Step 2: Add `old_structured` to MedicalRecordVersion**

In `src/db/models/records.py`, add after `old_record_type` (line 54):

```python
old_structured: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict
```

- [ ] **Step 3: Register in model registry**

In `src/db/models/__init__.py`, add import and __all__ entry:

```python
from db.models.review_queue import ReviewQueue
```

Add `"ReviewQueue"` to the `__all__` list.

- [ ] **Step 4: Verify table creation**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -c "from db.models.review_queue import ReviewQueue; print('OK:', ReviewQueue.__tablename__)"`

Expected: `OK: review_queue`

- [ ] **Step 5: Commit**

```bash
git add src/db/models/review_queue.py src/db/models/__init__.py src/db/models/records.py
git commit -m "feat(p3): add ReviewQueue model and old_structured audit column"
```

---

### Task 2: Review CRUD Operations

**Files:**
- Create: `src/db/crud/review.py`

**Reference patterns:** `src/db/crud/records.py` (save_record, save_record_version), `src/db/crud/tasks.py`

- [ ] **Step 1: Create the CRUD module**

```python
# src/db/crud/review.py
"""CRUD operations for the review queue."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MedicalRecordDB, MedicalRecordVersion, Patient
from db.models.interview_session import InterviewSessionDB
from db.models.review_queue import ReviewQueue
from db.models.base import _utcnow
from domain.records.schema import FIELD_KEYS


async def create_review(
    session: AsyncSession,
    record_id: int,
    doctor_id: str,
    patient_id: Optional[int],
) -> ReviewQueue:
    """Insert a new review queue entry."""
    entry = ReviewQueue(
        record_id=record_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        status="pending_review",
        created_at=_utcnow(),
    )
    session.add(entry)
    return entry


async def list_reviews(
    session: AsyncSession,
    doctor_id: str,
    status: str = "pending_review",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List review queue entries with patient name and chief complaint."""
    q = (
        select(ReviewQueue, Patient.name, MedicalRecordDB.structured, MedicalRecordDB.created_at)
        .outerjoin(Patient, ReviewQueue.patient_id == Patient.id)
        .join(MedicalRecordDB, ReviewQueue.record_id == MedicalRecordDB.id)
        .where(ReviewQueue.doctor_id == doctor_id, ReviewQueue.status == status)
    )
    if status == "reviewed":
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        q = q.where(ReviewQueue.reviewed_at >= cutoff)
    q = q.order_by(ReviewQueue.created_at.desc()).limit(limit)
    result = await session.execute(q)
    rows = result.all()
    items = []
    for rq, patient_name, structured_json, record_created_at in rows:
        structured = json.loads(structured_json) if structured_json else {}
        chief = structured.get("chief_complaint", "")
        items.append({
            "id": rq.id,
            "record_id": rq.record_id,
            "patient_id": rq.patient_id,
            "patient_name": patient_name or "",
            "chief_complaint": chief[:60] if chief else "",
            "status": rq.status,
            "created_at": rq.created_at.isoformat() if rq.created_at else None,
            "reviewed_at": rq.reviewed_at.isoformat() if rq.reviewed_at else None,
        })
    return items


async def get_review_detail(
    session: AsyncSession,
    queue_id: int,
    doctor_id: str,
) -> Optional[Dict[str, Any]]:
    """Get full review detail: structured record + interview chat history."""
    rq = (await session.execute(
        select(ReviewQueue).where(
            ReviewQueue.id == queue_id,
            ReviewQueue.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if rq is None:
        return None

    record = (await session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == rq.record_id)
    )).scalar_one_or_none()
    if record is None:
        return None

    patient = None
    if rq.patient_id:
        patient = (await session.execute(
            select(Patient).where(Patient.id == rq.patient_id)
        )).scalar_one_or_none()

    # Get interview conversation
    conversation = []
    if rq.patient_id:
        interview = (await session.execute(
            select(InterviewSessionDB)
            .where(
                InterviewSessionDB.patient_id == rq.patient_id,
                InterviewSessionDB.doctor_id == doctor_id,
                InterviewSessionDB.status == "completed",
            )
            .order_by(InterviewSessionDB.updated_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if interview and interview.conversation:
            conversation = json.loads(interview.conversation)

    structured = json.loads(record.structured) if record.structured else {}
    tags = json.loads(record.tags) if record.tags else []

    return {
        "id": rq.id,
        "record_id": rq.record_id,
        "status": rq.status,
        "created_at": rq.created_at.isoformat() if rq.created_at else None,
        "reviewed_at": rq.reviewed_at.isoformat() if rq.reviewed_at else None,
        "patient": {
            "id": patient.id if patient else None,
            "name": patient.name if patient else "",
            "gender": patient.gender if patient else None,
            "year_of_birth": patient.year_of_birth if patient else None,
        } if patient else None,
        "record": {
            "id": record.id,
            "record_type": record.record_type,
            "content": record.content,
            "structured": structured,
            "tags": tags,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        },
        "conversation": conversation,
    }


async def confirm_review(
    session: AsyncSession,
    queue_id: int,
    doctor_id: str,
) -> Optional[ReviewQueue]:
    """Mark a review as confirmed."""
    rq = (await session.execute(
        select(ReviewQueue).where(
            ReviewQueue.id == queue_id,
            ReviewQueue.doctor_id == doctor_id,
            ReviewQueue.status == "pending_review",
        )
    )).scalar_one_or_none()
    if rq is None:
        return None
    rq.status = "reviewed"
    rq.reviewed_at = _utcnow()
    return rq


async def update_review_field(
    session: AsyncSession,
    queue_id: int,
    doctor_id: str,
    field: str,
    value: str,
) -> Optional[Dict[str, Any]]:
    """Update a single structured field on the underlying medical record."""
    if field not in FIELD_KEYS:
        return None  # caller should raise 422

    rq = (await session.execute(
        select(ReviewQueue).where(
            ReviewQueue.id == queue_id,
            ReviewQueue.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if rq is None:
        return None

    record = (await session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == rq.record_id)
    )).scalar_one_or_none()
    if record is None:
        return None

    # Snapshot for audit
    version = MedicalRecordVersion(
        record_id=record.id,
        doctor_id=doctor_id,
        old_content=record.content,
        old_tags=record.tags,
        old_record_type=record.record_type,
        old_structured=record.structured,
    )
    session.add(version)

    # Update structured field
    structured = json.loads(record.structured) if record.structured else {}
    structured[field] = value
    record.structured = json.dumps(structured, ensure_ascii=False)
    record.updated_at = _utcnow()

    return {
        "record_id": record.id,
        "structured": structured,
    }
```

- [ ] **Step 2: Verify import**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -c "from db.crud.review import create_review, list_reviews, get_review_detail, confirm_review, update_review_field; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/db/crud/review.py
git commit -m "feat(p3): add review queue CRUD operations"
```

---

### Task 3: Review API Endpoints

**Files:**
- Create: `src/channels/web/ui/review_handlers.py`
- Modify: `src/channels/web/ui/__init__.py`

**Reference pattern:** `src/channels/web/ui/record_edit_handlers.py` (Pydantic models, Query/Header params, `_resolve_ui_doctor_id`)

- [ ] **Step 1: Create the endpoint handler module**

```python
# src/channels/web/ui/review_handlers.py
"""Review queue endpoints: list, detail, confirm, update field."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud.review import (
    list_reviews,
    get_review_detail,
    confirm_review,
    update_review_field,
)
from domain.records.schema import FIELD_KEYS
from infra.observability.audit import audit
from infra.auth.rate_limit import enforce_doctor_rate_limit
from channels.web.ui._utils import _resolve_ui_doctor_id
from utils.log import safe_create_task

router = APIRouter(tags=["ui"], include_in_schema=False)


class FieldUpdate(BaseModel):
    field: str
    value: str


@router.get("/api/manage/review-queue", include_in_schema=True)
async def list_review_queue(
    doctor_id: str = Query(default="web_doctor"),
    status: str = Query(default="pending_review"),
    limit: int = Query(default=50, le=200),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.review.list")
    async with AsyncSessionLocal() as db:
        items = await list_reviews(db, resolved, status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/manage/review-queue/{queue_id}", include_in_schema=True)
async def get_review_detail_endpoint(
    queue_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.review.detail")
    async with AsyncSessionLocal() as db:
        detail = await get_review_detail(db, queue_id, resolved)
    if detail is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return detail


@router.post("/api/manage/review-queue/{queue_id}/confirm", include_in_schema=True)
async def confirm_review_endpoint(
    queue_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.review.confirm")
    async with AsyncSessionLocal() as db:
        rq = await confirm_review(db, queue_id, resolved)
        if rq is None:
            raise HTTPException(status_code=404, detail="Review not found or already confirmed")
        await db.commit()
    safe_create_task(audit(resolved, "review.confirmed", "review", str(rq.record_id)))
    return {"id": rq.id, "status": rq.status, "reviewed_at": rq.reviewed_at.isoformat() if rq.reviewed_at else None}


@router.patch("/api/manage/review-queue/{queue_id}/record", include_in_schema=True)
async def update_review_field_endpoint(
    queue_id: int,
    body: FieldUpdate,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.review.edit")
    if body.field not in FIELD_KEYS:
        raise HTTPException(status_code=422, detail=f"Unknown field: {body.field}")
    async with AsyncSessionLocal() as db:
        result = await update_review_field(db, queue_id, resolved, body.field, body.value)
        if result is None:
            raise HTTPException(status_code=404, detail="Review or record not found")
        await db.commit()
    safe_create_task(audit(resolved, "review.field_edited", "review", str(result["record_id"])))
    return result
```

- [ ] **Step 2: Include router in UI __init__**

In `src/channels/web/ui/__init__.py`, add:

```python
from channels.web.ui.review_handlers import router as _review_router
```

And below the existing `router.include_router` calls:

```python
router.include_router(_review_router)
```

- [ ] **Step 3: Verify endpoint registration**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -c "from channels.web.ui.review_handlers import router; print('Routes:', [r.path for r in router.routes])"`

Expected: Routes listing the 4 paths.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/ui/review_handlers.py src/channels/web/ui/__init__.py
git commit -m "feat(p3): add review queue API endpoints"
```

---

### Task 4: Interview Pipeline Integration

**Files:**
- Modify: `src/domain/patients/interview_summary.py:75-118`

- [ ] **Step 1: Replace DoctorTask with ReviewQueue in `confirm_interview()`**

Replace lines 82-106 of `src/domain/patients/interview_summary.py`:

**Old code (lines 82-106):**
```python
    """Finalize interview: save record + create task. Returns {record_id, task_id}."""
    from db.crud.records import save_record
    from db.engine import AsyncSessionLocal
    from db.repositories.tasks import TaskRepository

    record = build_medical_record(collected)

    async with AsyncSessionLocal() as db:
        db_record = await save_record(
            db, doctor_id, record, patient_id,
            needs_review=True, commit=False,
        )

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
```

**New code:**
```python
    """Finalize interview: save record + create review queue entry. Returns {record_id, review_id}."""
    from db.crud.records import save_record
    from db.crud.review import create_review
    from db.engine import AsyncSessionLocal

    record = build_medical_record(collected)

    async with AsyncSessionLocal() as db:
        db_record = await save_record(
            db, doctor_id, record, patient_id,
            commit=False,
        )

        review = await create_review(
            db,
            record_id=db_record.id,
            doctor_id=doctor_id,
            patient_id=patient_id,
        )

        await db.commit()

    log(f"[interview] confirmed session={session_id} record={db_record.id} review={review.id}")
```

- [ ] **Step 2: Update the return value and notification message**

Replace lines 108-118:

**Old:**
```python
    # Notify doctor (best-effort, don't block on failure)
    try:
        from domain.tasks.notifications import send_doctor_notification
        await send_doctor_notification(
            doctor_id,
            f"患者【{patient_name}】已完成预问诊，请查看待办任务。",
        )
    except Exception as e:
        log(f"[interview] doctor notification failed: {e}", level="warning")

    return {"record_id": db_record.id, "task_id": task.id}
```

**New:**
```python
    # Notify doctor (best-effort, don't block on failure)
    try:
        from domain.tasks.notifications import send_doctor_notification
        await send_doctor_notification(
            doctor_id,
            f"患者【{patient_name}】已完成预问诊，请查看待审核记录。",
        )
    except Exception as e:
        log(f"[interview] doctor notification failed: {e}", level="warning")

    return {"record_id": db_record.id, "review_id": review.id}
```

- [ ] **Step 3: Verify import chain**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -c "from domain.patients.interview_summary import confirm_interview; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/domain/patients/interview_summary.py
git commit -m "feat(p3): replace DoctorTask with ReviewQueue in confirm_interview"
```

---

### Task 5: Frontend API Functions

**Files:**
- Modify: `frontend/web/src/api.js`

- [ ] **Step 1: Add 4 review API functions**

Add at the end of the file, before the final closing (after the last export):

```javascript
// ── Review Queue ──────────────────────────────────────────────────────────────

export async function getReviewQueue(doctorId, status = "pending_review", limit = 50) {
  return request(`/api/manage/review-queue?doctor_id=${doctorId}&status=${status}&limit=${limit}`);
}

export async function getReviewDetail(queueId, doctorId) {
  return request(`/api/manage/review-queue/${queueId}?doctor_id=${doctorId}`);
}

export async function confirmReview(queueId, doctorId) {
  return request(`/api/manage/review-queue/${queueId}/confirm?doctor_id=${doctorId}`, {
    method: "POST",
  });
}

export async function updateReviewField(queueId, doctorId, field, value) {
  return request(`/api/manage/review-queue/${queueId}/record?doctor_id=${doctorId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/api.js
git commit -m "feat(p3): add review queue API client functions"
```

---

### Task 6: Frontend Constants

**Files:**
- Modify: `frontend/web/src/pages/doctor/constants.jsx`

- [ ] **Step 1: Add review-related constants**

Add after the `TASK_STATUS_OPTS` export (around line 94):

```javascript
export const REVIEW_STATUS_LABEL = {
  pending_review: "待审核",
  reviewed: "已审核",
};

export const STRUCTURED_FIELD_LABELS = {
  department: "科别",
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  allergy_history: "过敏史",
  personal_history: "个人史",
  marital_reproductive: "婚育史",
  family_history: "家族史",
  physical_exam: "体格检查",
  specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查",
  diagnosis: "初步诊断",
  treatment_plan: "治疗方案",
  orders_followup: "医嘱及随访",
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/doctor/constants.jsx
git commit -m "feat(p3): add review status labels and structured field labels"
```

---

### Task 7: ReviewDetail Component

**Files:**
- Create: `frontend/web/src/pages/doctor/ReviewDetail.jsx`

**Reference patterns:** `TaskDetailView` in `TasksSection.jsx` (lines 120-237), `MobilePatientDetailView` in `PatientsSection.jsx` (lines 271-284)

- [ ] **Step 1: Create ReviewDetail.jsx**

This is the drill-down screen. It shows:
1. Top bar with back button
2. Patient header (avatar + name + metadata)
3. Structured field cards (tappable for inline edit)
4. Collapsible interview chat history
5. Sticky action bar (confirm / edit toggle)

```jsx
/**
 * 审核详情：结构化病历字段 + 问诊对话记录 + 确认/修改操作。
 * Drill-down from TasksSection review queue items.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, CircularProgress, Collapse, Stack, TextField, Typography,
} from "@mui/material";
import { getReviewDetail, confirmReview, updateReviewField } from "../../api";
import PatientAvatar from "./PatientAvatar";
import { STRUCTURED_FIELD_LABELS } from "./constants";

const FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "personal_history", "marital_reproductive", "family_history",
  "physical_exam", "specialist_exam", "auxiliary_exam", "diagnosis",
  "treatment_plan", "orders_followup",
];

function FieldCard({ fieldKey, value, editing, onStartEdit, onSave, onCancel }) {
  const [draft, setDraft] = useState(value || "");
  const label = STRUCTURED_FIELD_LABELS[fieldKey] || fieldKey;

  useEffect(() => { setDraft(value || ""); }, [value]);

  if (editing) {
    return (
      <Box sx={{ mb: 1, p: "10px 12px", bgcolor: "#fff", borderRadius: "6px", borderLeft: "3px solid #07C160" }}>
        <Typography sx={{ fontSize: 11, color: "#999", mb: 0.5 }}>{label}</Typography>
        <TextField
          fullWidth multiline size="small" value={draft}
          onChange={(e) => setDraft(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { fontSize: 14 } }}
        />
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Box onClick={() => onSave(fieldKey, draft)}
            sx={{ px: 2, py: 0.7, bgcolor: "#07C160", color: "#fff", borderRadius: "4px",
              fontSize: 13, fontWeight: 600, cursor: "pointer", "&:active": { opacity: 0.7 } }}>
            保存
          </Box>
          <Box onClick={onCancel}
            sx={{ px: 2, py: 0.7, bgcolor: "#f5f5f5", color: "#666", borderRadius: "4px",
              fontSize: 13, cursor: "pointer", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
        </Stack>
      </Box>
    );
  }

  return (
    <Box onClick={() => onStartEdit(fieldKey)}
      sx={{ mb: 1, p: "10px 12px", bgcolor: "#f7f7f7", borderRadius: "6px", cursor: "pointer" }}>
      <Typography sx={{ fontSize: 11, color: "#999", mb: 0.3 }}>{label}</Typography>
      {value ? (
        <Typography sx={{ fontSize: 14, color: "#333", lineHeight: 1.6 }}>
          {value} <Typography component="span" sx={{ color: "#ccc", fontSize: 12 }}>✏️</Typography>
        </Typography>
      ) : (
        <Typography sx={{ fontSize: 14, color: "#ccc", fontStyle: "italic" }}>患者未提供</Typography>
      )}
    </Box>
  );
}

function ConversationHistory({ conversation }) {
  const [open, setOpen] = useState(false);
  if (!conversation || conversation.length === 0) return null;
  const turnCount = Math.ceil(conversation.length / 2);

  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1 }}>
      <Box onClick={() => setOpen(!open)} sx={{ display: "flex", alignItems: "center", gap: 0.8, cursor: "pointer" }}>
        <Typography sx={{ fontSize: 12, color: "#999" }}>{open ? "▼" : "▶"}</Typography>
        <Typography sx={{ fontSize: 14, fontWeight: 600, color: "#333" }}>问诊对话记录</Typography>
        <Typography sx={{ fontSize: 12, color: "#bbb" }}>({turnCount}轮)</Typography>
      </Box>
      <Collapse in={open}>
        <Box sx={{ mt: 1.5 }}>
          {conversation.map((msg, i) => (
            <Box key={i} sx={{ mb: 1, display: "flex", flexDirection: "column",
              alignItems: msg.role === "assistant" ? "flex-start" : "flex-end" }}>
              <Typography sx={{ fontSize: 11, color: "#bbb", mb: 0.3 }}>
                {msg.role === "assistant" ? "AI问诊" : "患者"}
              </Typography>
              <Box sx={{
                maxWidth: "85%", p: "8px 12px", borderRadius: "8px", fontSize: 13, lineHeight: 1.6,
                bgcolor: msg.role === "assistant" ? "#f0f0f0" : "#e8f5e9",
                color: "#333",
              }}>
                {msg.content}
              </Box>
            </Box>
          ))}
        </Box>
      </Collapse>
      {!open && (
        <Typography sx={{ fontSize: 13, color: "#999", mt: 0.8 }}>点击展开查看完整对话...</Typography>
      )}
    </Box>
  );
}

export default function ReviewDetail({ queueId, doctorId, onBack, onConfirmed }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [editingField, setEditingField] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError("");
    getReviewDetail(queueId, doctorId)
      .then(setDetail)
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [queueId, doctorId]);

  useEffect(() => { load(); }, [load]);

  async function handleConfirm() {
    setConfirming(true);
    try {
      await confirmReview(queueId, doctorId);
      onConfirmed?.();
      onBack();
    } catch (e) { setError(e.message || "确认失败"); }
    finally { setConfirming(false); }
  }

  async function handleFieldSave(field, value) {
    setSaving(true);
    try {
      const result = await updateReviewField(queueId, doctorId, field, value);
      setDetail((prev) => ({
        ...prev,
        record: { ...prev.record, structured: result.structured },
      }));
      setEditingField(null);
    } catch (e) { setError(e.message || "保存失败"); }
    finally { setSaving(false); }
  }

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
        <CircularProgress size={24} sx={{ color: "#07C160" }} />
      </Box>
    );
  }

  const patient = detail?.patient;
  const structured = detail?.record?.structured || {};
  const age = patient?.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;
  const isReviewed = detail?.status === "reviewed";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      {/* Top bar */}
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff",
        borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3,
          cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>← 返回</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }}>
          审核详情
        </Typography>
      </Box>

      {/* Content */}
      <Box sx={{ flex: 1, overflowY: "auto", p: 1 }}>
        {error && <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError("")}>{error}</Alert>}

        {/* Patient header + structured fields */}
        <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1 }}>
          {patient && (
            <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
              <PatientAvatar name={patient.name} size={44} />
              <Box>
                <Typography sx={{ fontWeight: 600, fontSize: 17 }}>{patient.name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {[
                    patient.gender ? ({ male: "男", female: "女" }[patient.gender] || patient.gender) : null,
                    age ? `${age}岁` : null,
                    "问诊总结",
                  ].filter(Boolean).join(" · ")}
                </Typography>
              </Box>
            </Stack>
          )}

          {FIELD_ORDER.map((key) => (
            <FieldCard
              key={key} fieldKey={key} value={structured[key]}
              editing={editMode && editingField === key}
              onStartEdit={(k) => { if (editMode) setEditingField(k); }}
              onSave={handleFieldSave}
              onCancel={() => setEditingField(null)}
            />
          ))}
        </Box>

        {/* Interview conversation */}
        <ConversationHistory conversation={detail?.conversation} />

        {/* Spacer for action bar */}
        <Box sx={{ height: 80 }} />
      </Box>

      {/* Sticky action bar */}
      {!isReviewed && (
        <Box sx={{ position: "fixed", bottom: 0, left: 0, right: 0, p: "12px 16px",
          bgcolor: "#fff", borderTop: "1px solid #e5e5e5", zIndex: 10 }}>
          <Stack direction="row" spacing={1.5}>
            <Box onClick={!confirming ? handleConfirm : undefined}
              sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: "4px",
                bgcolor: confirming ? "#a5d6a7" : "#07C160", color: "#fff",
                fontWeight: 600, fontSize: 15, cursor: confirming ? "default" : "pointer",
                "&:active": confirming ? {} : { opacity: 0.7 } }}>
              {confirming ? "确认中..." : "✓ 确认审核"}
            </Box>
            <Box onClick={() => { setEditMode(!editMode); setEditingField(null); }}
              sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: "4px",
                bgcolor: editMode ? "#e8f5e9" : "#fff", color: editMode ? "#07C160" : "#666",
                border: editMode ? "1px solid #07C160" : "1px solid #e5e5e5",
                fontWeight: 600, fontSize: 15, cursor: "pointer",
                "&:active": { opacity: 0.7 } }}>
              {editMode ? "退出修改" : "✏️ 修改"}
            </Box>
          </Stack>
        </Box>
      )}
    </Box>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/doctor/ReviewDetail.jsx
git commit -m "feat(p3): add ReviewDetail drill-down component"
```

---

### Task 8: Extend TasksSection with Review Segment

**Files:**
- Modify: `frontend/web/src/pages/doctor/TasksSection.jsx`

This is the largest frontend change. The modifications are:

1. Add 3rd segment "待审核" to the pill toggle
2. Fetch review queue when segment is "review"
3. Render review items with distinct visual style (circle avatar, orange chip)
4. Drill down to ReviewDetail on tap

- [ ] **Step 1: Update SEGMENTS constant**

At the top of `TasksSection.jsx`, replace the `SEGMENTS` constant (line 23-26):

**Old:**
```javascript
const SEGMENTS = [
  { value: "todo", label: "待办" },
  { value: "done", label: "已完成" },
];
```

**New:**
```javascript
const SEGMENTS = [
  { value: "todo", label: "待办" },
  { value: "review", label: "待审核" },
  { value: "done", label: "已完成" },
];
```

- [ ] **Step 2: Add review imports**

Add to the import block at the top:

```javascript
import { getReviewQueue } from "../../api";
import PatientAvatar from "./PatientAvatar";
import ReviewDetail from "./ReviewDetail";
```

- [ ] **Step 3: Add ReviewQueueItem component**

Add before the `export default function TasksSection` component:

```jsx
function ReviewQueueItem({ item }) {
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.4 }}>
      <PatientAvatar name={item.patient_name} size={40} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1 }}>
          <Typography sx={{ fontWeight: 500, fontSize: 15, color: "text.primary",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {item.patient_name || "未知患者"} · 问诊记录
          </Typography>
          <Typography sx={{ fontSize: 11, flexShrink: 0, color: "#fff",
            bgcolor: "#ff9500", px: 0.8, py: 0.1, borderRadius: "3px" }}>
            待审核
          </Typography>
        </Box>
        {item.chief_complaint && (
          <Typography sx={{ fontSize: 13, color: "#999", mt: 0.2,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {item.chief_complaint}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Add review state and loading to `useTasksState` hook**

In the `useTasksState` function, add review state:

After `const [cancelConfirmId, setCancelConfirmId] = useState(null);` add:

```javascript
const [reviews, setReviews] = useState([]);
const [reviewLoading, setReviewLoading] = useState(false);
```

Add a review loading function inside `useTasksState`, after the existing `load` callback:

```javascript
const loadReviews = useCallback(() => {
  setReviewLoading(true);
  getReviewQueue(doctorId, "pending_review")
    .then((d) => setReviews(d.items || []))
    .catch(() => {})
    .finally(() => setReviewLoading(false));
}, [doctorId]);
```

In the existing `useEffect(() => { load(); }, [load]);`, add a parallel review load:

```javascript
useEffect(() => { loadReviews(); }, [loadReviews]);
```

Add `reviews, reviewLoading, loadReviews` to the return object of `useTasksState`.

Also update the destructuring at the call site in `TasksSection` (around line 446):

```javascript
const { tasks, loading, error, setError, segment, setSegment, ..., reviews, reviewLoading, loadReviews } = useTasksState(doctorId);
```

- [ ] **Step 5: Update the `load` callback to merge reviews into "todo" segment**

In the existing `load` callback, for the `segment === "todo"` branch (currently fetches pending tasks), update to also fetch reviews:

The `todo` segment needs to show both tasks and reviews. Modify the `load` callback's `todo` branch:

**Old (inside load):**
```javascript
: getTasks(doctorId, "pending").then((d) => Array.isArray(d) ? d : (d.items || []));
```

**New:**
For the "todo" segment, fetch both tasks and reviews. The simplest approach: tasks are loaded by `load()`, reviews by `loadReviews()`. In the render, merge them when `segment === "todo"`.

Update `loadReviews` to depend on `segment` so it re-fetches when switching tabs:

```javascript
const loadReviews = useCallback(() => {
  setReviewLoading(true);
  getReviewQueue(doctorId, "pending_review")
    .then((d) => setReviews(d.items || []))
    .catch(() => {})
    .finally(() => setReviewLoading(false));
}, [doctorId]);

useEffect(() => { loadReviews(); }, [loadReviews, segment]);
```

The `segment` dependency ensures reviews refresh when the user switches tabs.

- [ ] **Step 6: Add review detail state to the main component**

In the `TasksSection` component body, after `const [detailTask, setDetailTask] = useState(null);` add:

```javascript
const [detailReview, setDetailReview] = useState(null);
```

Add a review detail guard before the task detail guard:

```javascript
if (detailReview) {
  return (
    <ReviewDetail
      queueId={detailReview.id}
      doctorId={doctorId}
      onBack={() => { setDetailReview(null); loadReviews(); }}
      onConfirmed={() => loadReviews()}
    />
  );
}
```

- [ ] **Step 7: Update the list rendering to handle review segment**

In the main render return, after the segment header and before/within the scrollable list area, add conditional rendering:

When `segment === "review"`, render review items only:

```jsx
{segment === "review" && !reviewLoading && reviews.length === 0 && (
  <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1, px: 2 }}>
    <AssignmentOutlinedIcon sx={{ fontSize: 48, color: "#ccc" }} />
    <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 500 }}>暂无待审核记录</Typography>
  </Box>
)}
{segment === "review" && reviews.map((item) => (
  <Box key={`review-${item.id}`} onClick={() => setDetailReview(item)}
    sx={{ borderBottom: "0.5px solid #f0f0f0", cursor: "pointer", bgcolor: "#fff" }}>
    <ReviewQueueItem item={item} />
  </Box>
))}
```

When `segment === "todo"`, reviews and tasks must be interleaved by time (not rendered as separate blocks). Create a merged array:

```jsx
// Inside the render, before the list output, merge reviews + tasks for "todo":
const todoItems = segment === "todo"
  ? [
      ...reviews.map((r) => ({ ...r, _type: "review", _sortTime: r.created_at })),
      ...tasks.map((t) => ({ ...t, _type: "task", _sortTime: t.due_at || t.created_at })),
    ].sort((a, b) => (b._sortTime || "").localeCompare(a._sortTime || ""))
  : [];
```

Then render `todoItems` in a flat list:

```jsx
{segment === "todo" && todoItems.length === 0 && !loading && !reviewLoading && (
  <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1, px: 2 }}>
    <AssignmentOutlinedIcon sx={{ fontSize: 48, color: "#ccc" }} />
    <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 500 }}>暂无待办</Typography>
  </Box>
)}
{segment === "todo" && (
  <Box sx={{ bgcolor: "#fff" }}>
    {todoItems.map((item) =>
      item._type === "review" ? (
        <Box key={`review-${item.id}`} onClick={() => setDetailReview(item)}
          sx={{ borderBottom: "0.5px solid #f0f0f0", cursor: "pointer" }}>
          <ReviewQueueItem item={item} />
        </Box>
      ) : (
        <SwipeableTaskRow key={`task-${item.id}`}
          onSwipeLeft={() => { if (item.status === "pending") handleComplete(item.id, "completed"); }}
          onSwipeRight={() => { if (item.status === "pending") handleCancel(item.id); }}>
          <Box onClick={() => setDetailTask(item)}
            sx={{ borderBottom: "0.5px solid #f0f0f0", cursor: "pointer" }}>
            <TaskRow task={item} isOverdue={false} />
          </Box>
        </SwipeableTaskRow>
      )
    )}
  </Box>
)}
```

When `segment === "done"`, show completed tasks AND reviewed records (last 2 days). Add reviewed-item state and fetching:

In `useTasksState`, add:

```javascript
const [reviewedItems, setReviewedItems] = useState([]);
```

In the `load` callback's `done` branch, also fetch reviewed items:

```javascript
const fetchDone = segment === "done"
  ? Promise.all([
      getTasks(doctorId, "completed"),
      getTasks(doctorId, "cancelled"),
      getReviewQueue(doctorId, "reviewed"),
    ]).then(([c, x, r]) => {
      setReviewedItems(r.items || []);
      return [...(Array.isArray(c) ? c : c.items || []), ...(Array.isArray(x) ? x : x.items || [])]
        .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    })
  : getTasks(doctorId, "pending").then((d) => Array.isArray(d) ? d : (d.items || []));
```

Add `reviewedItems` to the return object. In the render, when `segment === "done"`, render reviewed items at the top with a "已审核" section header before the existing task groups:

```jsx
{segment === "done" && reviewedItems.length > 0 && (
  <>
    <Box sx={{ px: 2, py: 0.6, pt: 1.2 }}>
      <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>已审核记录</Typography>
    </Box>
    <Box sx={{ bgcolor: "#fff" }}>
      {reviewedItems.map((item) => (
        <Box key={`reviewed-${item.id}`} onClick={() => setDetailReview(item)}
          sx={{ borderBottom: "0.5px solid #f0f0f0", cursor: "pointer" }}>
          <ReviewQueueItem item={item} reviewed />
        </Box>
      ))}
    </Box>
  </>
)}
```

Update `ReviewQueueItem` to accept a `reviewed` prop and show "已审核" chip (green) instead of "待审核" (orange):

```jsx
function ReviewQueueItem({ item, reviewed }) {
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.4 }}>
      <PatientAvatar name={item.patient_name} size={40} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1 }}>
          <Typography sx={{ fontWeight: 500, fontSize: 15, color: "text.primary",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {item.patient_name || "未知患者"} · 问诊记录
          </Typography>
          <Typography sx={{ fontSize: 11, flexShrink: 0, color: "#fff",
            bgcolor: reviewed ? "#07C160" : "#ff9500", px: 0.8, py: 0.1, borderRadius: "3px" }}>
            {reviewed ? "已审核" : "待审核"}
          </Typography>
        </Box>
        {item.chief_complaint && (
          <Typography sx={{ fontSize: 13, color: "#999", mt: 0.2,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {item.chief_complaint}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 8: Commit**

```bash
git add frontend/web/src/pages/doctor/TasksSection.jsx
git commit -m "feat(p3): add review segment and queue rendering in TasksSection"
```

---

### Task 9: Badge Count Update

**Files:**
- Modify: `frontend/web/src/pages/DoctorPage.jsx`

- [ ] **Step 1: Fetch pending review count**

In `useDoctorPageState`, add review count state and effect:

After `const [pendingTaskCount, setPendingTaskCount] = useState(0);` add:

```javascript
const [pendingReviewCount, setPendingReviewCount] = useState(0);
```

Add the import at the top of the file:

```javascript
import { getReviewQueue } from "../api";
```

Add effect after the existing task count effect:

```javascript
useEffect(() => {
  if (!doctorId) return;
  getReviewQueue(doctorId, "pending_review", 200)
    .then((d) => setPendingReviewCount((d.items || []).length))
    .catch(() => {});
}, [doctorId]);
```

Add `pendingReviewCount` to the return object.

- [ ] **Step 2: Update badge to show combined count**

In the `DesktopSidebar` usage and `MobileBottomNav` usage, update the badge value.

In `DoctorPage` render, where `navBadge` is passed to `DesktopSidebar`:

**Old:**
```javascript
navBadge={{ tasks: pendingTaskCount, chat: pendingRecord ? 1 : 0 }}
```

**New:**
```javascript
navBadge={{ tasks: pendingTaskCount + pendingReviewCount, chat: pendingRecord ? 1 : 0 }}
```

In `MobileBottomNav`, update the tasks badge — currently it uses `pendingTaskCount` directly. Pass the combined count:

The `MobileBottomNav` component receives `pendingTaskCount` as a prop. Update the prop value in the render:

**Old:**
```javascript
<MobileBottomNav activeSection={activeSection} pendingTaskCount={pendingTaskCount} ...
```

**New:**
```javascript
<MobileBottomNav activeSection={activeSection} pendingTaskCount={pendingTaskCount + pendingReviewCount} ...
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/DoctorPage.jsx
git commit -m "feat(p3): badge count includes pending reviews"
```

---

### Task 10: Manual Verification

- [ ] **Step 1: Start backend**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -m uvicorn main:app --port 8000 --reload`

Verify no import errors on startup.

- [ ] **Step 2: Verify review_queue table created**

Check the SQLite database has the `review_queue` table and `medical_record_versions` has the new `old_structured` column.

- [ ] **Step 3: Test API endpoints with curl**

```bash
# List (should return empty)
curl "http://localhost:8000/api/manage/review-queue?doctor_id=test_doctor"

# Verify 404 on missing detail
curl "http://localhost:8000/api/manage/review-queue/999?doctor_id=test_doctor"
```

- [ ] **Step 4: Start frontend**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npm run dev`

Open in browser. Navigate to Tasks tab. Verify 3-segment pill toggle renders (待办 | 待审核 | 已完成). Verify 待审核 tab shows empty state.

- [ ] **Step 5: Final commit**

If any fixes were needed during verification:

```bash
git add -A
git commit -m "fix(p3): address issues found during manual verification"
```
