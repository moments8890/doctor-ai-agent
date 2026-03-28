# Diagnosis UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing CDS backend (`run_diagnosis()`) to a new review UI, enabling doctors to trigger AI diagnosis, review suggestions, and confirm/reject/edit items.

**Architecture:** New `ai_suggestions` DB table (one row per AI suggestion item) replaces the `ai_diagnosis`/`doctor_decisions` JSON columns. Backend gets 5 new API endpoints. Frontend gets a review subpage (`/doctor/review/:recordId`) with collapsible diagnosis cards, plus interview confirm dialog changes.

**Tech Stack:** Python 3.9 (FastAPI, SQLAlchemy), React 19 (MUI 7), existing `run_diagnosis()` pipeline, existing theme tokens (COLOR, TYPE, ICON)

**Spec:** `docs/specs/2026-03-25-diagnosis-ui-design.md`

---

## File Structure

### Backend — New files
- `src/db/models/ai_suggestion.py` — AISuggestion model + enums
- `src/db/crud/suggestions.py` — CRUD operations for ai_suggestions table
- `src/channels/web/ui/diagnosis_handlers.py` — 5 API endpoints

### Backend — Modified files
- `src/db/models/__init__.py` — register AISuggestion model
- `src/db/models/records.py` — drop `ai_diagnosis` and `doctor_decisions` columns
- `src/domain/diagnosis.py` — write to ai_suggestions table instead of JSON column
- `src/channels/web/ui/__init__.py` — register diagnosis router

### Frontend — New files
- `frontend/web/src/pages/doctor/ReviewPage.jsx` — review subpage
- `frontend/web/src/pages/doctor/DiagnosisCard.jsx` — collapsible review card
- `frontend/web/src/pages/doctor/InterviewCompleteDialog.jsx` — NHC preview + two buttons

### Frontend — Modified files
- `frontend/web/src/api.js` — add 5 API functions
- `frontend/web/src/App.jsx` — add `/doctor/review/:recordId` route
- `frontend/web/src/pages/DoctorPage.jsx` — render ReviewPage for review route
- `frontend/web/src/pages/doctor/InterviewView.jsx` — rename button, add dialog, collapsible carry-forward
- `frontend/web/src/pages/doctor/TasksSection.jsx` — review tasks navigate to review page
- `frontend/web/src/pages/doctor/PatientDetail.jsx` — pending_review badge, tap → review page

---

## Task 1: AI Suggestions DB Model

Create the new `ai_suggestions` table with enums.

### Files
- Create: `src/db/models/ai_suggestion.py`
- Modify: `src/db/models/__init__.py`

### Steps

- [ ] **1.1** Create `src/db/models/ai_suggestion.py` with the model:

```python
"""AI 诊断建议表 — 每条 AI 建议一行，医生决策直接更新行。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.engine import Base


class SuggestionSection(str, Enum):
    differential = "differential"
    workup = "workup"
    treatment = "treatment"


class SuggestionDecision(str, Enum):
    confirmed = "confirmed"
    rejected = "rejected"
    edited = "edited"
    custom = "custom"


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id"), nullable=False, index=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Classification
    section: Mapped[str] = mapped_column(String(32), nullable=False)

    # AI output
    content: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    urgency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    intervention: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Doctor response
    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
```

- [ ] **1.2** Register model in `src/db/models/__init__.py` — add import:

```python
from src.db.models.ai_suggestion import AISuggestion, SuggestionSection, SuggestionDecision
```

- [ ] **1.3** Verify table creates by running:

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
.venv/bin/python -c "from src.db.init_db import create_tables; create_tables()"
```

- [ ] **1.4** Commit:

```bash
git add src/db/models/ai_suggestion.py src/db/models/__init__.py
git commit -m "feat: add ai_suggestions table for diagnosis review"
```

---

## Task 2: Suggestions CRUD

CRUD functions for reading/writing ai_suggestions.

### Files
- Create: `src/db/crud/suggestions.py`

### Steps

- [ ] **2.1** Create `src/db/crud/suggestions.py`:

```python
"""CRUD for ai_suggestions table."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models.ai_suggestion import AISuggestion, SuggestionDecision, SuggestionSection


def create_suggestion(
    db: Session,
    *,
    record_id: int,
    doctor_id: str,
    section: SuggestionSection,
    content: str,
    detail: Optional[str] = None,
    confidence: Optional[str] = None,
    urgency: Optional[str] = None,
    intervention: Optional[str] = None,
    is_custom: bool = False,
) -> AISuggestion:
    row = AISuggestion(
        record_id=record_id,
        doctor_id=doctor_id,
        section=section.value,
        content=content,
        detail=detail,
        confidence=confidence,
        urgency=urgency,
        intervention=intervention,
        is_custom=is_custom,
        decision=SuggestionDecision.custom.value if is_custom else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_suggestions_for_record(db: Session, record_id: int) -> List[AISuggestion]:
    stmt = select(AISuggestion).where(AISuggestion.record_id == record_id).order_by(AISuggestion.id)
    return list(db.execute(stmt).scalars().all())


def get_suggestion_by_id(db: Session, suggestion_id: int) -> Optional[AISuggestion]:
    return db.get(AISuggestion, suggestion_id)


def update_decision(
    db: Session,
    suggestion_id: int,
    *,
    decision: SuggestionDecision,
    edited_text: Optional[str] = None,
    reason: Optional[str] = None,
) -> Optional[AISuggestion]:
    row = db.get(AISuggestion, suggestion_id)
    if not row:
        return None
    row.decision = decision.value
    row.edited_text = edited_text
    row.reason = reason
    row.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def has_suggestions(db: Session, record_id: int) -> bool:
    stmt = select(AISuggestion.id).where(AISuggestion.record_id == record_id).limit(1)
    return db.execute(stmt).first() is not None
```

- [ ] **2.2** Commit:

```bash
git add src/db/crud/suggestions.py
git commit -m "feat: add CRUD for ai_suggestions"
```

---

## Task 3: Modify `run_diagnosis()` to Write Suggestions Table

Adapt the existing diagnosis pipeline to insert rows into `ai_suggestions` instead of writing JSON to `ai_diagnosis` column.

### Files
- Modify: `src/domain/diagnosis.py` (lines 520–560 where results are persisted)

### Steps

- [ ] **3.1** At the top of `diagnosis.py`, add import:

```python
from src.db.crud.suggestions import create_suggestion
from src.db.models.ai_suggestion import SuggestionSection
```

- [ ] **3.2** Find the section where `run_diagnosis()` persists results (around line 528 where it writes to `ai_diagnosis`). Replace the JSON column write with row inserts:

For each item in `result["differentials"]`, `result["workup"]`, `result["treatment"]`, call `create_suggestion()` with the appropriate section enum and fields.

The existing code that writes `record.ai_diagnosis = json.dumps(...)` should be replaced with a loop that creates one `AISuggestion` row per item.

- [ ] **3.3** Update the record status to `pending_review` (this likely already happens — verify).

- [ ] **3.4** Verify by running diagnosis manually and checking the DB:

```bash
.venv/bin/python -c "
from src.db.engine import get_db
from src.db.crud.suggestions import get_suggestions_for_record
db = next(get_db())
rows = get_suggestions_for_record(db, record_id=1)
print(f'{len(rows)} suggestions found')
for r in rows: print(f'  {r.section}: {r.content} ({r.confidence or r.urgency or r.intervention})')
"
```

- [ ] **3.5** Commit:

```bash
git add src/domain/diagnosis.py
git commit -m "feat: run_diagnosis writes to ai_suggestions table"
```

---

## Task 4: Backend API Endpoints

5 new endpoints for diagnosis trigger, suggestion fetch, decide, add custom, and finalize.

### Files
- Create: `src/channels/web/ui/diagnosis_handlers.py`
- Modify: `src/channels/web/ui/__init__.py`

### Steps

- [ ] **4.1** Create `src/channels/web/ui/diagnosis_handlers.py`:

```python
"""Diagnosis review API endpoints."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db.engine import get_db
from src.db.crud.suggestions import (
    create_suggestion,
    get_suggestion_by_id,
    get_suggestions_for_record,
    update_decision,
)
from src.db.crud.records import get_record_by_id, update_record_status
from src.db.models.ai_suggestion import SuggestionDecision, SuggestionSection
from src.db.models.records import RecordStatus
from src.domain.diagnosis import run_diagnosis

router = APIRouter(prefix="/api/doctor", tags=["diagnosis"])


# --- Request/Response Models ---

class DiagnoseRequest(BaseModel):
    doctor_id: str

class DecideRequest(BaseModel):
    decision: SuggestionDecision
    edited_text: Optional[str] = None
    reason: Optional[str] = None

class AddSuggestionRequest(BaseModel):
    doctor_id: str
    section: SuggestionSection
    content: str
    detail: Optional[str] = None

class FinalizeRequest(BaseModel):
    doctor_id: str


# --- Endpoints ---

@router.post("/records/{record_id}/diagnose", status_code=202)
async def trigger_diagnosis(record_id: int, body: DiagnoseRequest, db: Session = Depends(get_db)):
    record = get_record_by_id(db, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    # Fire and forget — diagnosis runs in background
    asyncio.create_task(run_diagnosis(body.doctor_id, record_id=record_id))
    return {"status": "running", "record_id": record_id}


@router.get("/records/{record_id}/suggestions")
def list_suggestions(record_id: int, db: Session = Depends(get_db)):
    record = get_record_by_id(db, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    rows = get_suggestions_for_record(db, record_id)
    return {
        "status": record.status,
        "suggestions": [
            {
                "id": r.id,
                "section": r.section,
                "content": r.content,
                "detail": r.detail,
                "confidence": r.confidence,
                "urgency": r.urgency,
                "intervention": r.intervention,
                "decision": r.decision,
                "edited_text": r.edited_text,
                "reason": r.reason,
                "is_custom": r.is_custom,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            }
            for r in rows
        ],
    }


@router.post("/suggestions/{suggestion_id}/decide")
def decide_suggestion(suggestion_id: int, body: DecideRequest, db: Session = Depends(get_db)):
    row = update_decision(
        db, suggestion_id,
        decision=body.decision,
        edited_text=body.edited_text,
        reason=body.reason,
    )
    if not row:
        raise HTTPException(404, "Suggestion not found")
    return {"status": "ok", "id": row.id, "decision": row.decision}


@router.post("/records/{record_id}/suggestions")
def add_custom_suggestion(record_id: int, body: AddSuggestionRequest, db: Session = Depends(get_db)):
    record = get_record_by_id(db, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    row = create_suggestion(
        db,
        record_id=record_id,
        doctor_id=body.doctor_id,
        section=body.section,
        content=body.content,
        detail=body.detail,
        is_custom=True,
    )
    return {"status": "ok", "id": row.id}


@router.post("/records/{record_id}/review/finalize")
def finalize_review(record_id: int, body: FinalizeRequest, db: Session = Depends(get_db)):
    record = get_record_by_id(db, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    update_record_status(db, record_id, RecordStatus.completed)
    # TODO: mark associated review task as done
    return {"status": "completed", "record_id": record_id}
```

- [ ] **4.2** Register router in `src/channels/web/ui/__init__.py`:

```python
from src.channels.web.ui.diagnosis_handlers import router as diagnosis_router
# ... add to include_router calls:
router.include_router(diagnosis_router)
```

- [ ] **4.3** Verify endpoints load:

```bash
.venv/bin/python -c "from src.channels.web.ui.diagnosis_handlers import router; print(f'{len(router.routes)} routes registered')"
```

- [ ] **4.4** Commit:

```bash
git add src/channels/web/ui/diagnosis_handlers.py src/channels/web/ui/__init__.py
git commit -m "feat: add diagnosis review API endpoints"
```

---

## Task 5: Frontend API Functions

Add 5 API functions to `api.js`.

### Files
- Modify: `frontend/web/src/api.js`

### Steps

- [ ] **5.1** Add these functions at the end of `api.js` (before the final export block if any):

```javascript
// ── Diagnosis / Review ──

export async function triggerDiagnosis(recordId, doctorId) {
  return request(`/api/doctor/records/${recordId}/diagnose`, {
    method: "POST",
    body: JSON.stringify({ doctor_id: doctorId }),
  });
}

export async function getSuggestions(recordId) {
  return request(`/api/doctor/records/${recordId}/suggestions`);
}

export async function decideSuggestion(suggestionId, decision, opts = {}) {
  return request(`/api/doctor/suggestions/${suggestionId}/decide`, {
    method: "POST",
    body: JSON.stringify({ decision, ...opts }),
  });
}

export async function addSuggestion(recordId, doctorId, section, content, detail) {
  return request(`/api/doctor/records/${recordId}/suggestions`, {
    method: "POST",
    body: JSON.stringify({ doctor_id: doctorId, section, content, detail }),
  });
}

export async function finalizeReview(recordId, doctorId) {
  return request(`/api/doctor/records/${recordId}/review/finalize`, {
    method: "POST",
    body: JSON.stringify({ doctor_id: doctorId }),
  });
}
```

- [ ] **5.2** Commit:

```bash
git add frontend/web/src/api.js
git commit -m "feat: add diagnosis API functions"
```

---

## Task 6: DiagnosisCard Component

Collapsible review card with confirm/reject/edit actions.

### Files
- Create: `frontend/web/src/pages/doctor/DiagnosisCard.jsx`

### Steps

- [ ] **6.1** Create `DiagnosisCard.jsx` — a single collapsible card that handles all 5 states (unreviewed, confirmed, rejected, edited, custom). Reference the visual mockup at `.superpowers/brainstorm/9508-1774478043/review-balanced.html` and use design tokens from `frontend/web/src/theme.js` (COLOR, TYPE).

The component receives:
```javascript
{
  suggestion: { id, section, content, detail, confidence, urgency, intervention, decision, edited_text, reason, is_custom },
  onDecide: (suggestionId, decision, opts) => void,
  expanded: boolean,
  onToggle: () => void,
}
```

Key behaviors:
- Collapsed: one line — content + badge (confidence/urgency/intervention) + status icon
- Expanded: reasoning text + action buttons row (✓ 确认 / ✗ 排除 / ✎ 修改)
- Edit mode: textarea pre-filled with AI text + 保存修改/取消
- Reject mode: optional reason input
- 3px left border indicates state (green=confirmed, gray=rejected, amber=edited, dashed green=custom)

- [ ] **6.2** Commit:

```bash
git add frontend/web/src/pages/doctor/DiagnosisCard.jsx
git commit -m "feat: add DiagnosisCard component"
```

---

## Task 7: ReviewPage Component

Full review subpage at `/doctor/review/:recordId`.

### Files
- Create: `frontend/web/src/pages/doctor/ReviewPage.jsx`
- Modify: `frontend/web/src/App.jsx` (add route)
- Modify: `frontend/web/src/pages/DoctorPage.jsx` (render ReviewPage)

### Steps

- [ ] **7.1** Create `ReviewPage.jsx` — the main review subpage. Structure:
- `SubpageHeader` with "← 诊断审核" and "完成" button (calls `finalizeReview`)
- Collapsible record summary (NHC fields from existing `RecordFields` component)
- If no suggestions and no diagnosis running: show "诊断建议 — 请AI分析此病历" trigger button
- If diagnosis running: show loading skeleton ("AI 正在分析...")
- If suggestions exist: three sections (鉴别诊断, 检查建议, 治疗方向) each with:
  - Section header + progress counter (e.g., "3/4")
  - List of `DiagnosisCard` components
  - "+ 添加" button for custom items
- Sticky bottom bar: progress text + "完成审核" button

Uses: `getSuggestions()`, `decideSuggestion()`, `addSuggestion()`, `finalizeReview()`, `triggerDiagnosis()` from api.js.

Polls `getSuggestions()` every 3 seconds while status is "pending_review" and no suggestions exist (waiting for diagnosis to complete).

- [ ] **7.2** Add route in `App.jsx` — inside the doctor routes section (around line 71-75), add:

```jsx
<Route path="/doctor/review/:recordId" element={<RequireAuth><DoctorPage /></RequireAuth>} />
```

- [ ] **7.3** In `DoctorPage.jsx` — detect the `/doctor/review/:recordId` URL pattern and render `ReviewPage` instead of the normal section content. Add to the `SectionContent` function (around line 103).

- [ ] **7.4** Commit:

```bash
git add frontend/web/src/pages/doctor/ReviewPage.jsx frontend/web/src/App.jsx frontend/web/src/pages/DoctorPage.jsx
git commit -m "feat: add ReviewPage with diagnosis cards and routing"
```

---

## Task 8: InterviewCompleteDialog

Popup shown when doctor clicks "完成" in interview — shows NHC field preview with two buttons.

### Files
- Create: `frontend/web/src/pages/doctor/InterviewCompleteDialog.jsx`
- Modify: `frontend/web/src/pages/doctor/InterviewView.jsx`

### Steps

- [ ] **8.1** Create `InterviewCompleteDialog.jsx`:

Props:
```javascript
{
  open: boolean,
  fields: { chief_complaint, present_illness, past_history, ... },
  fieldCount: { filled: number, total: number },
  onSave: () => void,        // save only
  onSaveAndDiagnose: () => void,  // save + trigger diagnosis + navigate
  onClose: () => void,
}
```

Renders a MUI `Dialog` with:
- Title: "病历预览"
- Body: NHC field label + value pairs (reuse `RecordFields` rendering pattern)
- Field count: "已提取 7/14 字段"
- Footer: `保存` (outlined) + `保存并诊断 →` (green fill)

- [ ] **8.2** Modify `InterviewView.jsx`:
- Rename "确认生成" button text to "完成" (line 244)
- On "完成" click: instead of calling `handleConfirm()` directly, set `showCompleteDialog = true`
- Add `InterviewCompleteDialog` at the bottom of the component
- `onSave` → calls existing `handleConfirm()` logic
- `onSaveAndDiagnose` → calls `handleConfirm()`, then `triggerDiagnosis()`, then `navigate(/doctor/review/${recordId})`

- [ ] **8.3** Make carry-forward section collapsible in `InterviewView.jsx` (around line 281-290):
- Add a `carryForwardCollapsed` state
- Wrap carry-forward cards in a collapsible container
- Toggle on header click (▾/▴)
- Auto-collapse when all items are acted on

- [ ] **8.4** Commit:

```bash
git add frontend/web/src/pages/doctor/InterviewCompleteDialog.jsx frontend/web/src/pages/doctor/InterviewView.jsx
git commit -m "feat: interview complete dialog with save/diagnose options"
```

---

## Task 9: Wire Navigation — Tasks & Patient Detail

Make review tasks and record rows navigate to the review page.

### Files
- Modify: `frontend/web/src/pages/doctor/TasksSection.jsx`
- Modify: `frontend/web/src/pages/doctor/PatientDetail.jsx`

### Steps

- [ ] **9.1** In `TasksSection.jsx` — find `UnifiedTaskItem` (line 101-124). When a task has an associated record_id and is a review-type task, make `onTap` navigate to `/doctor/review/${item.record_id}` instead of showing task detail.

- [ ] **9.2** In `PatientDetail.jsx` — find where `RecordCard` components are rendered. For records with `status === "pending_review"`:
- Add a visual badge (small dot or "待审核" text)
- Make the record row tap navigate to `/doctor/review/${record.id}` instead of expanding inline

- [ ] **9.3** Commit:

```bash
git add frontend/web/src/pages/doctor/TasksSection.jsx frontend/web/src/pages/doctor/PatientDetail.jsx
git commit -m "feat: wire task list and patient detail to review page"
```

---

## Task 10: Drop Old Columns & Clean Up

Remove `ai_diagnosis` and `doctor_decisions` JSON columns. Update any remaining references.

### Files
- Modify: `src/db/models/records.py` (lines 59-60)
- Modify: `src/domain/diagnosis.py` (remove old JSON write if still present)

### Steps

- [ ] **10.1** In `src/db/models/records.py`, comment out or remove lines 59-60:

```python
# DROPPED — replaced by ai_suggestions table
# ai_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
# doctor_decisions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

Note: Since we're not running Alembic migrations, the columns will remain in the DB but won't be used by the ORM. This is safe — SQLAlchemy ignores extra DB columns not mapped in the model.

- [ ] **10.2** Grep for any remaining references to `ai_diagnosis` or `doctor_decisions` in `src/` and `frontend/` and remove them:

```bash
grep -rn "ai_diagnosis\|doctor_decisions" src/ frontend/web/src/ --include="*.py" --include="*.js" --include="*.jsx"
```

- [ ] **10.3** Commit:

```bash
git add src/db/models/records.py src/domain/diagnosis.py
git commit -m "refactor: drop ai_diagnosis/doctor_decisions columns, use ai_suggestions table"
```

---

## Task 11: Integration Test

End-to-end test: trigger diagnosis → fetch suggestions → decide → finalize.

### Files
- Create: `tests/integration/test_diagnosis_review.py`

### Steps

- [ ] **11.1** Write integration test against the running server (port 8001):

```python
"""E2E test: diagnosis trigger → suggestions → decide → finalize."""
import pytest
import httpx

BASE = "http://127.0.0.1:8001"

@pytest.mark.integration
class TestDiagnosisReview:

    async def test_full_review_flow(self):
        async with httpx.AsyncClient(base_url=BASE) as c:
            # 1. Find a record to diagnose
            records = (await c.get("/api/doctor/records", params={"doctor_id": "test_doctor"})).json()
            assert records["items"], "Need at least one record"
            record_id = records["items"][0]["id"]

            # 2. Trigger diagnosis
            resp = await c.post(f"/api/doctor/records/{record_id}/diagnose",
                                json={"doctor_id": "test_doctor"})
            assert resp.status_code == 202

            # 3. Poll for suggestions (wait up to 30s)
            import asyncio
            for _ in range(10):
                await asyncio.sleep(3)
                resp = await c.get(f"/api/doctor/records/{record_id}/suggestions")
                data = resp.json()
                if data["suggestions"]:
                    break
            assert data["suggestions"], "Diagnosis should produce suggestions"

            # 4. Decide on first suggestion
            s_id = data["suggestions"][0]["id"]
            resp = await c.post(f"/api/doctor/suggestions/{s_id}/decide",
                                json={"decision": "confirmed"})
            assert resp.json()["decision"] == "confirmed"

            # 5. Add custom suggestion
            resp = await c.post(f"/api/doctor/records/{record_id}/suggestions",
                                json={"doctor_id": "test_doctor", "section": "differential",
                                      "content": "Test custom", "detail": "Test detail"})
            assert resp.json()["status"] == "ok"

            # 6. Finalize
            resp = await c.post(f"/api/doctor/records/{record_id}/review/finalize",
                                json={"doctor_id": "test_doctor"})
            assert resp.json()["status"] == "completed"
```

- [ ] **11.2** Commit:

```bash
git add tests/integration/test_diagnosis_review.py
git commit -m "test: add diagnosis review integration test"
```
