# Admin & Debug Dashboard Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate two overlapping debug pages into one standalone HTML debug dashboard at `/debug`, and redesign the React admin page for beta ops monitoring with overview stats, doctor drill-down, and grouped raw data.

**Architecture:** 4 independent tasks: (1) debug route consolidation + cleanup, (2) admin overview API endpoints, (3) admin overview frontend, (4) admin doctor drill-down frontend. Each task produces a working commit.

**Tech Stack:** FastAPI (backend), React + MUI (admin frontend), standalone HTML + vanilla JS (debug frontend), SQLAlchemy async queries

**Spec:** `docs/specs/2026-03-30-admin-debug-consolidation-design.md`
**Mockup:** `docs/specs/2026-03-30-admin-debug-mockup.html`

---

### Task 1: Debug Dashboard — Route Consolidation & Cleanup

**Files:**
- Modify: `src/channels/web/doctor_dashboard/debug_handlers.py` (add `/debug` route)
- Modify: `src/channels/web/doctor_dashboard/debug.html` (remove Requests, Errors, Health tabs; merge Logs tab)
- Delete: `frontend/web/src/pages/admin/DebugPage.jsx`
- Modify: `frontend/web/src/App.jsx` (remove `/debug` and `/debug/:section` routes, keep `/debug/doctor`, `/debug/patient`, `/debug/components`)

- [ ] **Step 1: Add `/debug` route in backend**

In `src/channels/web/doctor_dashboard/debug_handlers.py`, add a new route right after the existing `/api/debug/dashboard` route:

```python
@router.get("/debug", include_in_schema=False)
async def debug_page_short(token: str = Query(..., description="Debug access token")):
    """Serve debug dashboard at short URL."""
    _require_ui_debug_access(token)
    return FileResponse(
        Path(__file__).parent / "debug.html",
        media_type="text/html",
    )
```

- [ ] **Step 2: Remove Requests, Health tabs from debug.html**

In `src/channels/web/doctor_dashboard/debug.html`:

1. Remove the tab buttons for `requests` and `health` from the tab bar (keep `llm`, `benchmark`, `errors`)
2. Remove the entire `<!-- TAB: REQUESTS -->` panel div (`id="panel-requests"`)
3. Remove the entire `<!-- TAB: HEALTH -->` panel div (`id="panel-health"`)
4. Remove their JS functions (`loadRequests`, `renderRequests`, `loadHealth`, etc.)
5. Update `validTabs` array to `['llm', 'benchmark', 'errors']`

- [ ] **Step 3: Rename Errors tab to Logs, add source/level filters**

In `debug.html`:

1. Rename the tab button text from `Errors` to `Logs`
2. Rename `data-tab="errors"` to `data-tab="logs"` and `id="panel-errors"` to `id="panel-logs"`
3. Add a level filter dropdown (ALL/DEBUG/INFO/WARNING/ERROR/CRITICAL) next to the existing source filter
4. Update the fetch call to pass the level parameter: `/api/debug/logs?source=${source}&level=${level}&limit=200`
5. Update `validTabs` to `['llm', 'benchmark', 'logs']`
6. Update `loadCurrentTab` to call `loadLogs()` when tab is `logs`

- [ ] **Step 4: Delete DebugPage.jsx and remove routes from App.jsx**

Delete `frontend/web/src/pages/admin/DebugPage.jsx`.

In `frontend/web/src/App.jsx`, remove:
```jsx
import DebugPage from "./pages/admin/DebugPage";
```
And remove these two Route elements:
```jsx
<Route path="/debug" element={<DebugPage />} />
<Route path="/debug/:section" element={<DebugPage />} />
```
Keep the `/debug/components`, `/debug/doctor`, `/debug/patient` routes — those are mock app previews, not the debug console.

- [ ] **Step 5: Verify and commit**

Run: `cd frontend/web && npx biome check --fix src/App.jsx`

```bash
git add src/channels/web/doctor_dashboard/debug_handlers.py \
  src/channels/web/doctor_dashboard/debug.html \
  frontend/web/src/App.jsx
git rm frontend/web/src/pages/admin/DebugPage.jsx
git commit -m "refactor: consolidate debug to /debug, remove React DebugPage"
```

---

### Task 2: Admin Overview API Endpoints

**Files:**
- Create: `src/channels/web/doctor_dashboard/admin_overview.py`
- Modify: `src/channels/web/doctor_dashboard/__init__.py` (include new router)

- [ ] **Step 1: Create admin_overview.py with overview endpoint**

Create `src/channels/web/doctor_dashboard/admin_overview.py`:

```python
"""Admin overview API — aggregated stats and alerts for beta monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import (
    AISuggestion, SuggestionDecision,
    Doctor,
    DoctorKnowledgeItem,
    DoctorTask, TaskStatus,
    InterviewSessionDB,
    MedicalRecordDB,
    MessageDraft,
    Patient,
    PatientMessage,
)
from channels.web.doctor_dashboard.filters import _fmt_ts, apply_exclude_test_doctors

router = APIRouter(tags=["admin-overview"], include_in_schema=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/api/admin/overview")
async def admin_overview(db: AsyncSession = Depends(get_db)):
    """Aggregated stats + alerts for the overview dashboard."""
    now = _utcnow()
    day_ago = now - timedelta(hours=24)
    hour_ago = now - timedelta(hours=1)
    three_days = now - timedelta(days=3)

    # ── Doctors ──
    docs_q = apply_exclude_test_doctors(select(Doctor), Doctor.doctor_id)
    all_docs = (await db.execute(docs_q)).scalars().all()
    active_today = sum(1 for d in all_docs if d.updated_at and d.updated_at >= day_ago)
    inactive_docs = [
        {"doctor_id": d.doctor_id, "name": d.name or d.doctor_id,
         "last_active": _fmt_ts(d.updated_at)}
        for d in all_docs if not d.updated_at or d.updated_at < three_days
    ]

    # ── Patient messages 24h ──
    msg_total = (await db.execute(
        select(func.count()).select_from(PatientMessage)
        .where(PatientMessage.created_at >= day_ago)
    )).scalar() or 0

    # ── Medical records 24h ──
    rec_total = (await db.execute(
        select(func.count()).select_from(MedicalRecordDB)
        .where(MedicalRecordDB.created_at >= day_ago)
    )).scalar() or 0

    # ── AI suggestions 24h ──
    sugg_rows = (await db.execute(
        select(AISuggestion).where(AISuggestion.created_at >= day_ago)
    )).scalars().all()
    sugg_total = len(sugg_rows)
    sugg_accepted = sum(1 for s in sugg_rows if s.decision == SuggestionDecision.ACCEPTED)
    sugg_edited = sum(1 for s in sugg_rows if s.decision == SuggestionDecision.EDITED)
    sugg_rejected = sum(1 for s in sugg_rows if s.decision == SuggestionDecision.REJECTED)

    # ── Tasks ──
    pending_tasks = (await db.execute(
        select(DoctorTask).where(DoctorTask.status.in_([
            TaskStatus.PENDING, TaskStatus.IN_PROGRESS,
        ]))
    )).scalars().all()
    overdue = [
        {"doctor_id": t.doctor_id, "patient_id": t.patient_id,
         "title": t.title, "created_at": _fmt_ts(t.created_at)}
        for t in pending_tasks
        if t.created_at and t.created_at < day_ago
    ]

    return {
        "doctors": {"active": active_today, "total": len(all_docs)},
        "messages_24h": {"total": msg_total},
        "records_24h": {"total": rec_total},
        "suggestions_24h": {
            "total": sugg_total, "accepted": sugg_accepted,
            "edited": sugg_edited, "rejected": sugg_rejected,
        },
        "tasks": {"pending": len(pending_tasks), "overdue": len(overdue)},
        "alerts": {
            "overdue_tasks": overdue,
            "inactive_doctors": inactive_docs,
        },
    }


@router.get("/api/admin/doctors")
async def admin_doctors(db: AsyncSession = Depends(get_db)):
    """Doctor list with activity metrics for the overview table."""
    now = _utcnow()
    day_ago = now - timedelta(hours=24)

    docs_q = apply_exclude_test_doctors(select(Doctor), Doctor.doctor_id)
    all_docs = (await db.execute(docs_q)).scalars().all()

    result = []
    for d in all_docs:
        did = d.doctor_id

        patient_count = (await db.execute(
            select(func.count()).select_from(Patient).where(Patient.doctor_id == did)
        )).scalar() or 0

        msg_today = (await db.execute(
            select(func.count()).select_from(PatientMessage)
            .where(and_(PatientMessage.doctor_id == did, PatientMessage.created_at >= day_ago))
        )).scalar() or 0

        kb_count = (await db.execute(
            select(func.count()).select_from(DoctorKnowledgeItem)
            .where(DoctorKnowledgeItem.doctor_id == did)
        )).scalar() or 0

        # AI adoption rate
        suggestions = (await db.execute(
            select(AISuggestion).where(and_(
                AISuggestion.doctor_id == did, AISuggestion.decision.isnot(None),
            ))
        )).scalars().all()
        total_decided = len(suggestions)
        accepted = sum(1 for s in suggestions if s.decision == SuggestionDecision.ACCEPTED)
        adoption = round(accepted / total_decided * 100) if total_decided else None

        # Pending items
        pending = (await db.execute(
            select(func.count()).select_from(DoctorTask)
            .where(and_(DoctorTask.doctor_id == did, DoctorTask.status.in_([
                TaskStatus.PENDING, TaskStatus.IN_PROGRESS,
            ])))
        )).scalar() or 0

        result.append({
            "doctor_id": did,
            "name": d.name or did,
            "department": d.department or "",
            "patient_count": patient_count,
            "msg_today": msg_today,
            "ai_adoption": adoption,
            "pending_tasks": pending,
            "kb_count": kb_count,
            "last_active": _fmt_ts(d.updated_at),
        })
    return {"doctors": result}


@router.get("/api/admin/activity")
async def admin_activity(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Recent activity feed — merges suggestions, records, tasks, messages."""
    now = _utcnow()
    day_ago = now - timedelta(hours=24)
    events: list[dict] = []

    # AI suggestions
    suggs = (await db.execute(
        select(AISuggestion).where(AISuggestion.created_at >= day_ago)
        .order_by(AISuggestion.created_at.desc()).limit(limit)
    )).scalars().all()
    for s in suggs:
        events.append({
            "time": _fmt_ts(s.created_at), "doctor_id": s.doctor_id,
            "type": "ai_suggestion", "detail": s.section or "",
            "patient_id": s.record_id,  # closest FK
            "status": s.decision.value if s.decision else "pending",
        })

    # Records
    recs = (await db.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.created_at >= day_ago)
        .order_by(MedicalRecordDB.created_at.desc()).limit(limit)
    )).scalars().all()
    for r in recs:
        events.append({
            "time": _fmt_ts(r.created_at), "doctor_id": r.doctor_id,
            "type": "record", "detail": r.chief_complaint or "",
            "patient_id": r.patient_id,
            "status": r.status.value if r.status else "draft",
        })

    # Tasks
    tasks = (await db.execute(
        select(DoctorTask).where(DoctorTask.updated_at >= day_ago)
        .order_by(DoctorTask.updated_at.desc()).limit(limit)
    )).scalars().all()
    for t in tasks:
        events.append({
            "time": _fmt_ts(t.updated_at), "doctor_id": t.doctor_id,
            "type": "task", "detail": t.title or "",
            "patient_id": t.patient_id,
            "status": t.status.value if t.status else "pending",
        })

    # Sort all by time descending, take top N
    events.sort(key=lambda e: e["time"] or "", reverse=True)
    return {"events": events[:limit]}


@router.get("/api/admin/doctors/{doctor_id}")
async def admin_doctor_detail(
    doctor_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Doctor detail: profile, setup checklist, 7-day stats."""
    now = _utcnow()
    week_ago = now - timedelta(days=7)

    doc = (await db.execute(
        select(Doctor).where(Doctor.doctor_id == doctor_id)
    )).scalar_one_or_none()
    if not doc:
        return {"error": "not found"}

    # Setup checklist
    kb_count = (await db.execute(
        select(func.count()).select_from(DoctorKnowledgeItem)
        .where(DoctorKnowledgeItem.doctor_id == doctor_id)
    )).scalar() or 0

    patient_count = (await db.execute(
        select(func.count()).select_from(Patient)
        .where(Patient.doctor_id == doctor_id)
    )).scalar() or 0

    first_record = (await db.execute(
        select(func.count()).select_from(MedicalRecordDB)
        .where(MedicalRecordDB.doctor_id == doctor_id)
    )).scalar() or 0

    first_suggestion = (await db.execute(
        select(func.count()).select_from(AISuggestion)
        .where(AISuggestion.doctor_id == doctor_id)
    )).scalar() or 0

    # 7-day stats
    msgs_7d = (await db.execute(
        select(func.count()).select_from(PatientMessage)
        .where(and_(PatientMessage.doctor_id == doctor_id, PatientMessage.created_at >= week_ago))
    )).scalar() or 0

    recs_7d = (await db.execute(
        select(func.count()).select_from(MedicalRecordDB)
        .where(and_(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.created_at >= week_ago))
    )).scalar() or 0

    suggs_7d = (await db.execute(
        select(AISuggestion).where(and_(
            AISuggestion.doctor_id == doctor_id, AISuggestion.created_at >= week_ago,
        ))
    )).scalars().all()
    decided = [s for s in suggs_7d if s.decision]
    accepted = sum(1 for s in decided if s.decision == SuggestionDecision.ACCEPTED)
    adoption = round(accepted / len(decided) * 100) if decided else None

    tasks_7d = (await db.execute(
        select(DoctorTask).where(and_(
            DoctorTask.doctor_id == doctor_id, DoctorTask.created_at >= week_ago,
        ))
    )).scalars().all()
    tasks_done = sum(1 for t in tasks_7d if t.status == TaskStatus.COMPLETED)

    return {
        "doctor_id": doctor_id,
        "name": doc.name or doctor_id,
        "department": doc.department or "",
        "created_at": _fmt_ts(doc.created_at),
        "last_active": _fmt_ts(doc.updated_at),
        "setup": {
            "kb_count": kb_count,
            "has_patients": patient_count > 0,
            "has_records": first_record > 0,
            "has_ai_usage": first_suggestion > 0,
        },
        "stats_7d": {
            "patients": patient_count,
            "messages": msgs_7d,
            "records": recs_7d,
            "ai_adoption": adoption,
            "ai_accepted": accepted,
            "ai_edited": sum(1 for s in decided if s.decision == SuggestionDecision.EDITED),
            "ai_rejected": sum(1 for s in decided if s.decision == SuggestionDecision.REJECTED),
            "tasks_total": len(tasks_7d),
            "tasks_done": tasks_done,
        },
    }


@router.get("/api/admin/doctors/{doctor_id}/patients")
async def admin_doctor_patients(
    doctor_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Patient list for a specific doctor with status indicators."""
    patients = (await db.execute(
        select(Patient).where(Patient.doctor_id == doctor_id)
        .order_by(Patient.created_at.desc())
    )).scalars().all()

    result = []
    for p in patients:
        pid = p.id

        msg_count = (await db.execute(
            select(func.count()).select_from(PatientMessage)
            .where(PatientMessage.patient_id == pid)
        )).scalar() or 0

        rec_count = (await db.execute(
            select(func.count()).select_from(MedicalRecordDB)
            .where(MedicalRecordDB.patient_id == pid)
        )).scalar() or 0

        pending_tasks = (await db.execute(
            select(func.count()).select_from(DoctorTask)
            .where(and_(DoctorTask.patient_id == pid, DoctorTask.status.in_([
                TaskStatus.PENDING, TaskStatus.IN_PROGRESS,
            ])))
        )).scalar() or 0

        # Last message time
        last_msg = (await db.execute(
            select(PatientMessage.created_at)
            .where(PatientMessage.patient_id == pid)
            .order_by(PatientMessage.created_at.desc()).limit(1)
        )).scalar()

        result.append({
            "patient_id": pid,
            "name": p.name,
            "gender": p.gender or "",
            "age": p.age if hasattr(p, "age") else "",
            "created_at": _fmt_ts(p.created_at),
            "msg_count": msg_count,
            "rec_count": rec_count,
            "pending_tasks": pending_tasks,
            "last_message": _fmt_ts(last_msg),
        })
    return {"patients": result}


@router.get("/api/admin/doctors/{doctor_id}/timeline")
async def admin_doctor_timeline(
    doctor_id: str,
    patient_id: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Case timeline for a patient — messages, records, suggestions, tasks."""
    events: list[dict] = []

    if not patient_id:
        return {"events": []}

    # Messages
    msgs = (await db.execute(
        select(PatientMessage).where(PatientMessage.patient_id == patient_id)
        .order_by(PatientMessage.created_at.desc()).limit(limit)
    )).scalars().all()
    for m in msgs:
        events.append({
            "time": _fmt_ts(m.created_at), "type": "message",
            "detail": (m.content or "")[:100], "status": m.direction or "inbound",
            "id": m.id,
        })

    # Records
    recs = (await db.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.patient_id == patient_id)
        .order_by(MedicalRecordDB.created_at.desc()).limit(limit)
    )).scalars().all()
    for r in recs:
        events.append({
            "time": _fmt_ts(r.created_at), "type": "record",
            "detail": r.chief_complaint or "", "status": r.status.value if r.status else "draft",
            "id": r.id,
        })

    # AI suggestions (linked via record)
    for r in recs:
        suggs = (await db.execute(
            select(AISuggestion).where(AISuggestion.record_id == r.id)
        )).scalars().all()
        for s in suggs:
            events.append({
                "time": _fmt_ts(s.created_at), "type": "ai_suggestion",
                "detail": s.section or "", "status": s.decision.value if s.decision else "pending",
                "id": s.id,
            })

    # Tasks
    tasks = (await db.execute(
        select(DoctorTask).where(DoctorTask.patient_id == patient_id)
        .order_by(DoctorTask.created_at.desc()).limit(limit)
    )).scalars().all()
    for t in tasks:
        events.append({
            "time": _fmt_ts(t.created_at), "type": "task",
            "detail": t.title or "", "status": t.status.value if t.status else "pending",
            "id": t.id,
        })

    events.sort(key=lambda e: e["time"] or "", reverse=True)
    return {"events": events[:limit]}
```

- [ ] **Step 2: Register the new router**

In `src/channels/web/doctor_dashboard/__init__.py`, add:

```python
from channels.web.doctor_dashboard import admin_overview as _admin_overview
```

And at the bottom with the other `include_router` calls:

```python
router.include_router(_admin_overview.router)
```

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/doctor_dashboard/admin_overview.py \
  src/channels/web/doctor_dashboard/__init__.py
git commit -m "feat: add admin overview API endpoints for beta monitoring"
```

---

### Task 3: Admin Frontend — Overview Tab

**Files:**
- Rewrite: `frontend/web/src/pages/admin/AdminPage.jsx` (keep raw data functionality, add overview)
- Create: `frontend/web/src/pages/admin/AdminOverview.jsx` (overview tab component)
- Create: `frontend/web/src/pages/admin/AdminRawData.jsx` (extracted raw data tab)
- Modify: `frontend/web/src/api/adminApi.js` or equivalent (add overview API calls)

This task is large and UI-heavy. The implementing agent should:
1. Read the mockup HTML at `docs/specs/2026-03-30-admin-debug-mockup.html` for exact layout
2. Read the existing `AdminPage.jsx` to understand the current raw data table pattern
3. Build the overview tab matching the dense mockup: stat strip, alert strip, 2x2 grid panels

- [ ] **Step 1: Create API helper functions**

Create or extend the admin API module to add these fetch functions:

```javascript
export async function fetchAdminOverview() {
  const res = await fetch("/api/admin/overview");
  return res.json();
}
export async function fetchAdminDoctors() {
  const res = await fetch("/api/admin/doctors");
  return res.json();
}
export async function fetchAdminActivity(limit = 20) {
  const res = await fetch(`/api/admin/activity?limit=${limit}`);
  return res.json();
}
```

- [ ] **Step 2: Create AdminOverview.jsx**

Build the overview component matching the dense mockup:
- `StatStrip` — 6 horizontal stat cells (doctors, messages, records, suggestions, tasks, LLM calls)
- `AlertStrip` — red/amber alert rows
- 2-column grid: doctor table (left) + activity feed (right)
- 2-column grid: task pipeline (left) + AI suggestions (right)
- Use MUI `Chip` for status chips with color mapping from the spec
- Row background colors: `#fce4ec` (error), `#fffde7` (warn), `#fff3e0` (alert)
- Dense table styles: `fontSize: 11`, `padding: "4px 8px"`

- [ ] **Step 3: Extract raw data into AdminRawData.jsx**

Move the existing table browser code from `AdminPage.jsx` into a new `AdminRawData.jsx`.
Group the table tabs: 核心 / 设置 / 系统 as per the spec.

- [ ] **Step 4: Rewrite AdminPage.jsx as tab container**

Replace the current AdminPage with a 3-tab layout:
```
总览 | 医生 (count) | 原始数据
```

Tab 1 renders `<AdminOverview />`
Tab 2 renders the doctor drill-down (Task 4)
Tab 3 renders `<AdminRawData />`

Add topbar: "Doctor AI Admin · beta · N doctors · N patients" with link to debug dashboard.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/admin/
git commit -m "feat: admin overview tab with stats, alerts, activity feed"
```

---

### Task 4: Admin Frontend — Doctor Drill-Down

**Files:**
- Create: `frontend/web/src/pages/admin/AdminDoctorDetail.jsx`
- Modify: `frontend/web/src/pages/admin/AdminPage.jsx` (wire up doctor tab navigation)

- [ ] **Step 1: Create API helper functions**

```javascript
export async function fetchDoctorDetail(doctorId) {
  const res = await fetch(`/api/admin/doctors/${doctorId}`);
  return res.json();
}
export async function fetchDoctorPatients(doctorId) {
  const res = await fetch(`/api/admin/doctors/${doctorId}/patients`);
  return res.json();
}
export async function fetchDoctorTimeline(doctorId, patientId) {
  const res = await fetch(`/api/admin/doctors/${doctorId}/timeline?patient_id=${patientId}`);
  return res.json();
}
```

- [ ] **Step 2: Create AdminDoctorDetail.jsx**

Build the doctor detail component matching the dense mockup:
- One-line header: name, specialty, ID, dates + inline setup checklist (✓/✗ icons)
- `StatStrip` — 6 metrics for this doctor (reuse component from Task 3)
- Patient table — dense, with AI adoption per patient, pending items, status chips
- Clicking a patient expands/shows the case timeline below the table
- Timeline rows: colored dots (blue=message, purple=AI, green=record, orange=task) + detail + trace ID link

- [ ] **Step 3: Wire up navigation in AdminPage.jsx**

When clicking a doctor name in overview tab or doctor tab:
- Set `selectedDoctor` state to the doctor_id
- Switch to the 医生 tab
- Render `<AdminDoctorDetail doctorId={selectedDoctor} />` in the 医生 tab

Add back button in doctor detail header to clear selection and return to overview.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/admin/AdminDoctorDetail.jsx \
  frontend/web/src/pages/admin/AdminPage.jsx
git commit -m "feat: admin doctor drill-down with patient timeline"
```

---

### Notes for Implementing Agents

1. **Read the mockup HTML** at `docs/specs/2026-03-30-admin-debug-mockup.html` before writing any frontend code. It contains exact colors, spacing, and data density.

2. **UI Design System rules from CLAUDE.md apply** — use theme tokens (COLOR, TYPE, RADIUS) for all values. Use MUI components. No hardcoded hex colors. No emojis as icons.

3. **Dense table style reference:**
   - Base font: 12px (body), 11px (table cells), 10px (labels/chips)
   - Table cell padding: `4px 8px`
   - Chip padding: `1px 5px`, borderRadius: 3px, font-size: 10px
   - Stat strip: horizontal flex, 8-12px padding per cell

4. **Backend queries use SQLAlchemy async** — follow the pattern in `admin_table_rows.py`. All queries use `await db.execute(select(...))`.

5. **No tests required** per project testing policy (non-safety-critical UI/admin code).

6. **Tasks 1 and 2 are independent** and can run in parallel. Tasks 3 and 4 depend on Task 2 (API endpoints).
