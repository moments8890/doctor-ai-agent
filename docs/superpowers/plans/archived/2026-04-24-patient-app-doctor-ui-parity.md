# Patient App — Doctor UI Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the v2 patient portal to visual + structural parity with the v2 doctor app, finishing the Phase 2 / 3 work the prior parity spec deferred.

**Architecture:** Five independently shippable phases — (0) tiny backend additions to make a real task-detail page possible, (1) lift patient token into a zustand store, (2) extract two real shared primitives, (3) React Query layer for patient (chat stays bespoke), (4) visual rewrites mirroring the doctor card pattern, (5) real subpage content + final cleanup.

**Tech Stack:** FastAPI + SQLAlchemy + pytest (backend); React + antd-mobile + zustand + @tanstack/react-query + MUI icons + Vite + Playwright (frontend).

**Spec:** [`docs/superpowers/specs/2026-04-24-patient-app-doctor-ui-parity-design.md`](../specs/2026-04-24-patient-app-doctor-ui-parity-design.md) (3-pass Codex-reviewed v3.1).

**Project conventions** (from `CLAUDE.md` + `AGENTS.md`):
- pytest invocation: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest <path> -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
- E2E + sim runs on `:8001` only — never `:8000` (dev server)
- Use shared `Card` / `TintedIconRow` from `v2/components` (created in Phase 2) — never duplicate
- Use `FONT.* / ICON.* / RADIUS.* / APP.*` tokens from `v2/theme.js` — never hardcode
- MUI outlined icons for row icons (`*Outlined`) — never antd-mobile-icons for row content
- Commits: each task ends with a commit step. The executor must NOT push (`git push` is never run automatically — user invocation only).

---

## File Structure

### Created
| Path | Responsibility |
|---|---|
| `frontend/web/src/store/patientStore.js` | Zustand store for patient token + identity (Phase 1) |
| `frontend/web/src/v2/lib/patientFontScale.js` | Patient-local font tier util — wraps localStorage + `applyFontScale()` (Phase 4) |
| `frontend/web/src/v2/components/ListSectionDivider.jsx` | Renamed from `SectionHeader.jsx` (Phase 2) |
| `frontend/web/src/v2/components/Card.jsx` | Shared white card primitive (Phase 2) |
| `frontend/web/src/v2/components/TintedIconRow.jsx` | Shared 36px tinted-circle list row (Phase 2) |
| `frontend/web/src/lib/patientQueries.js` | React Query hooks + mutations for patient (Phase 3) |
| `frontend/web/src/v2/pages/PrivacyContent.jsx` | Extracted reusable privacy body (Phase 5) |
| `frontend/web/src/v2/version.js` | Single source for `APP_VERSION` (Phase 5, only if not already centralized) |
| `frontend/web/tests/e2e/25-patient-record-detail.spec.ts` | E2E for patient record detail (Phase 5) |
| `frontend/web/tests/e2e/26-patient-task-detail.spec.ts` | E2E for patient task detail + complete/undo (Phase 5) |
| `frontend/web/tests/e2e/27-patient-my-subpages.spec.ts` | E2E for MyPage → about / privacy / font (Phase 5) |
| `tests/channels/test_patient_task_detail_endpoint.py` | Backend tests for new GET-by-id endpoint (Phase 0) |

### Modified
| Path | Change | Phase |
|---|---|---|
| `src/channels/web/patient_portal/tasks.py` | Add `completed_at`, `source_record_id` to `PatientTaskOut`; add `GET /api/patient/tasks/{id}`; populate fields in 3 existing handlers | 0 |
| `frontend/web/src/api.js` | Add `getPatientTaskDetail`; populate new fields in mock | 0 |
| `frontend/web/src/api/PatientApiContext.jsx` | Wire new fn through | 0 |
| `frontend/web/src/api/patientMockApi.js` | Add `getPatientTaskDetail` mock | 0 |
| `frontend/web/src/v2/pages/patient/PatientPage.jsx` | Read identity from `usePatientStore`; drop local state + storage keys | 1 |
| `frontend/web/src/v2/components/index.js` | Re-exports for new primitives + temporary `SectionHeader` alias | 2 |
| `frontend/web/src/v2/pages/doctor/ReviewPage.jsx` | Update `SectionHeader` import to `ListSectionDivider` | 2 |
| `frontend/web/src/v2/pages/doctor/SettingsPage.jsx` | Drop local `Card` + `SettingsRow`; use shared | 2 |
| `frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx` | Drop local `Card`; use shared | 2 |
| `frontend/web/src/lib/queryKeys.js` | Add `PK` namespace | 3 |
| `frontend/web/src/v2/pages/patient/RecordsTab.jsx` | Migrate to `usePatientRecords()` (Phase 3); apply card pattern + PullToRefresh (Phase 4) | 3, 4 |
| `frontend/web/src/v2/pages/patient/TasksTab.jsx` | Migrate to `usePatientTasks()` + mutations (Phase 3); apply card pattern + PullToRefresh, keep visible tap targets (Phase 4) | 3, 4 |
| `frontend/web/src/v2/pages/patient/MyPage.jsx` | Full rewrite mirroring doctor `SettingsPage` style; use shared primitives + local SectionHeader | 4 |
| `frontend/web/src/v2/pages/patient/ChatTab.jsx` | QuickActions row → `Card` + `TintedIconRow`; chat polling untouched | 4 |
| `frontend/web/src/v2/pages/patient/PatientOnboarding.jsx` | Token cleanup — replace literals with `FONT.* / ICON.* / APP.* / RADIUS.*` | 4 |
| `frontend/web/src/v2/pages/patient/PatientRecordDetailPage.jsx` | Replace stub with real card-pattern subpage | 5 |
| `frontend/web/src/v2/pages/patient/PatientTaskDetailPage.jsx` | Replace stub with real card-pattern subpage + Section 0 fields | 5 |
| `frontend/web/src/v2/pages/patient/PatientAboutSubpage.jsx` | Replace stub with real content using shared `Card` | 5 |
| `frontend/web/src/v2/pages/patient/PatientPrivacySubpage.jsx` | Replace stub with `<PrivacyContent />` wrapper | 5 |
| `frontend/web/src/v2/pages/PrivacyPage.jsx` | Body → `<PrivacyContent />` | 5 |
| `frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx` | Import `APP_VERSION` from shared source if extraction needed | 5 |
| `scripts/lint-ui.sh` | Add 5-line guard against new `SectionHeader` imports from `v2/components` | 5 |
| `frontend/web/tests/e2e/22-patient-records.spec.ts` | Update selectors for new card layout + detail round-trip | 4 / 5 |
| `frontend/web/tests/e2e/23-patient-tasks.spec.ts` | Update selectors for visible-tap-prefix + body-tap detail | 4 / 5 |

---

## Phase 0 — Backend (Section 0 of spec)

Three tasks. TDD.

### Task 0.1: Add `completed_at` + `source_record_id` to `PatientTaskOut`

**Files:**
- Modify: `src/channels/web/patient_portal/tasks.py:39-47` (schema), `:99-110` (list handler), `:151-159` (complete handler), `:181-189` (uncomplete handler)
- Test: `tests/channels/test_patient_task_detail_endpoint.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/channels/test_patient_task_detail_endpoint.py`:

```python
"""Tests for the patient-portal task endpoints — focused on the new
`completed_at` and `source_record_id` fields surfaced in PatientTaskOut.

Uses an in-process FastAPI test client and a real SQLite session so the
schema additions are exercised end-to-end.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import app  # FastAPI instance
from db.models.tasks import DoctorTask
from db.models.patients import Patient
from db.models.doctors import Doctor
from db.models.records import MedicalRecord
from db.session import AsyncSessionLocal
from channels.web.patient_portal.auth import _issue_patient_token


@pytest.mark.asyncio
async def test_patient_task_list_includes_completed_at_and_source_record_id(monkeypatch):
    """List endpoint must surface completed_at + source_record_id (derived
    from task.record_id, not task.source_id)."""
    async with AsyncSessionLocal() as db:
        doctor = Doctor(doctor_id="dr_test_t01", name="Dr T")
        patient = Patient(doctor_id="dr_test_t01", name="P")
        record = MedicalRecord(doctor_id="dr_test_t01", patient_id=1, record_type="visit", content="x")
        db.add_all([doctor, patient, record])
        await db.flush()
        task = DoctorTask(
            doctor_id="dr_test_t01",
            patient_id=patient.id,
            target="patient",
            record_id=record.id,
            source_id=999,  # decoy — must NOT appear in source_record_id
            task_type="follow_up",
            title="复查",
            content="一周后复查",
            status="completed",
            completed_at=datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc),
        )
        db.add(task)
        await db.commit()
        token = _issue_patient_token(patient.id)

    client = TestClient(app)
    resp = client.get("/api/patient/tasks", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["completed_at"] is not None
    assert row["source_record_id"] == record.id  # NOT 999
    assert row["task_type"] == "follow_up"
    assert row["status"] == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/channels/test_patient_task_detail_endpoint.py::test_patient_task_list_includes_completed_at_and_source_record_id -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: FAIL — KeyError on `completed_at` or `source_record_id` (fields don't exist on the response schema yet).

> If `_issue_patient_token` import path differs in this repo, run `grep -rn "_issue_patient_token" src/channels/web/patient_portal/auth.py` and adjust the import; the symbol is the existing helper used by other patient tests.

- [ ] **Step 3: Add fields to schema + populate in list handler**

In `src/channels/web/patient_portal/tasks.py` lines 39-47, replace:

```python
class PatientTaskOut(BaseModel):
    id: int
    task_type: str
    title: str
    content: Optional[str] = None
    status: str
    due_at: Optional[datetime] = None
    source_type: Optional[str] = None
    created_at: datetime
```

with:

```python
class PatientTaskOut(BaseModel):
    id: int
    task_type: str
    title: str
    content: Optional[str] = None
    status: str
    due_at: Optional[datetime] = None
    source_type: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    source_record_id: Optional[int] = None
```

In the same file, update **all three** existing `PatientTaskOut(...)` constructions (list at line ~99, complete at ~151, uncomplete at ~181) to add:

```python
            completed_at=t.completed_at,    # or task.completed_at in single-task handlers
            source_record_id=t.record_id,   # NB: task.record_id, NOT task.source_id
```

For the single-task handlers replace `t.` with `task.` to match local variable naming.

- [ ] **Step 4: Run test to verify it passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/channels/test_patient_task_detail_endpoint.py::test_patient_task_list_includes_completed_at_and_source_record_id -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/patient_portal/tasks.py tests/channels/test_patient_task_detail_endpoint.py
git commit -m "feat(patient-api): expose completed_at and source_record_id on PatientTaskOut"
```

---

### Task 0.2: Add `GET /api/patient/tasks/{task_id}` endpoint

**Files:**
- Modify: `src/channels/web/patient_portal/tasks.py` (append after the existing GET handler at line 76)
- Test: append to `tests/channels/test_patient_task_detail_endpoint.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/channels/test_patient_task_detail_endpoint.py`:

```python
@pytest.mark.asyncio
async def test_get_patient_task_by_id_happy_path():
    """Returns a single PatientTaskOut for an owned, patient-targeted task."""
    async with AsyncSessionLocal() as db:
        doctor = Doctor(doctor_id="dr_t02", name="Dr T")
        patient = Patient(doctor_id="dr_t02", name="P")
        db.add_all([doctor, patient])
        await db.flush()
        task = DoctorTask(
            doctor_id="dr_t02",
            patient_id=patient.id,
            target="patient",
            task_type="general",
            title="提醒服药",
            status="pending",
        )
        db.add(task)
        await db.commit()
        token = _issue_patient_token(patient.id)

    client = TestClient(app)
    resp = client.get(f"/api/patient/tasks/{task.id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == task.id
    assert body["title"] == "提醒服药"
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_get_patient_task_by_id_404_when_not_found():
    async with AsyncSessionLocal() as db:
        patient = Patient(doctor_id="dr_t03", name="P")
        db.add(patient)
        await db.commit()
        token = _issue_patient_token(patient.id)

    client = TestClient(app)
    resp = client.get("/api/patient/tasks/9999999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_patient_task_by_id_404_for_other_patients_task():
    """Cross-patient isolation: requesting another patient's task → 404, not 403."""
    async with AsyncSessionLocal() as db:
        doctor = Doctor(doctor_id="dr_t04", name="Dr T")
        p1 = Patient(doctor_id="dr_t04", name="A")
        p2 = Patient(doctor_id="dr_t04", name="B")
        db.add_all([doctor, p1, p2])
        await db.flush()
        task = DoctorTask(doctor_id="dr_t04", patient_id=p1.id, target="patient",
                          task_type="general", title="A's task", status="pending")
        db.add(task)
        await db.commit()
        token_p2 = _issue_patient_token(p2.id)

    client = TestClient(app)
    resp = client.get(f"/api/patient/tasks/{task.id}", headers={"Authorization": f"Bearer {token_p2}"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/channels/test_patient_task_detail_endpoint.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 3 FAIL — endpoint returns 404 for *all* requests because the route doesn't exist yet.

- [ ] **Step 3: Add the endpoint**

In `src/channels/web/patient_portal/tasks.py`, immediately after the existing `get_patient_tasks` handler (~line 111), insert:

```python
@tasks_router.get("/tasks/{task_id}", response_model=PatientTaskOut)
async def get_patient_task_detail(
    task_id: int,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return a single patient-owned task by id. 404 on missing or not owned."""
    patient = await _authenticate_patient(authorization)

    task = (await db.execute(
        select(DoctorTask).where(DoctorTask.id == task_id)
    )).scalar_one_or_none()

    if task is None or task.patient_id != patient.id or task.target != "patient":
        raise HTTPException(status_code=404, detail="Task not found")

    safe_create_task(audit(
        "patient", "READ",
        resource_type="patient_task", resource_id=str(task_id),
    ))
    return PatientTaskOut(
        id=task.id,
        task_type=task.task_type,
        title=task.title,
        content=task.content,
        status=task.status,
        due_at=task.due_at,
        source_type=task.source_type,
        created_at=task.created_at,
        completed_at=task.completed_at,
        source_record_id=task.record_id,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/channels/test_patient_task_detail_endpoint.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 4 PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/patient_portal/tasks.py tests/channels/test_patient_task_detail_endpoint.py
git commit -m "feat(patient-api): GET /api/patient/tasks/{id} with ownership isolation"
```

---

### Task 0.3: Wire `getPatientTaskDetail` through the frontend API surface

**Files:**
- Modify: `frontend/web/src/api.js` (after line 1003 — after `uncompletePatientTask`)
- Modify: `frontend/web/src/api/patientMockApi.js`
- Modify: `frontend/web/src/api/PatientApiContext.jsx`

This task has no automated test (a Vitest mock-API test would be lower-value than the actual integration via Phase 3 hooks). Verify by running the existing patient mock app.

- [ ] **Step 1: Add `getPatientTaskDetail` to `api.js`**

In `frontend/web/src/api.js` immediately after `uncompletePatientTask` (~line 1003):

```javascript
export async function getPatientTaskDetail(token, taskId) {
  return patientRequest(`/api/patient/tasks/${taskId}`, token);
}
```

- [ ] **Step 2: Add the mock**

In `frontend/web/src/api/patientMockApi.js`, alongside the existing `getPatientTasks` mock:

```javascript
export async function getPatientTaskDetail(_token, taskId) {
  const all = await getPatientTasks(_token);
  const found = all.find((t) => String(t.id) === String(taskId));
  if (!found) {
    const err = new Error("Task not found");
    err.status = 404;
    throw err;
  }
  return found;
}
```

- [ ] **Step 3: Wire through `PatientApiContext`**

In `frontend/web/src/api/PatientApiContext.jsx`, add `getPatientTaskDetail` to the import list at the top and to the value object exposed by the provider (mirror the existing `completePatientTask` pattern at lines 7-8 + 25-26).

- [ ] **Step 4: Verify import surface compiles**

```bash
cd frontend/web && npx tsc --noEmit 2>&1 | head -20 || true
```

Expected: no new errors mentioning `getPatientTaskDetail`. (The repo doesn't enforce TS but this catches typos.)

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/api.js frontend/web/src/api/patientMockApi.js frontend/web/src/api/PatientApiContext.jsx
git commit -m "feat(patient-frontend): expose getPatientTaskDetail via api + mock + context"
```

---

## Phase 1 — Patient token store (Section 1 of spec)

Two tasks.

### Task 1.1: Create `patientStore.js` with one-shot localStorage migration

**Files:**
- Create: `frontend/web/src/store/patientStore.js`
- Test: `frontend/web/tests/unit/patient-store.spec.js` (new — uses Vitest, already configured per memory)

- [ ] **Step 1: Write the failing test**

Create `frontend/web/tests/unit/patient-store.spec.js`:

```javascript
import { describe, it, expect, beforeEach } from "vitest";

describe("usePatientStore", () => {
  beforeEach(() => {
    // Reset localStorage between tests so persist middleware is clean
    localStorage.clear();
  });

  it("loginWithIdentity replaces all identity fields atomically", async () => {
    const { usePatientStore } = await import("../../src/store/patientStore.js");
    usePatientStore.getState().loginWithIdentity({
      token: "tok-1", patientId: "p1", patientName: "Alice",
      doctorId: "d1", doctorName: "Dr A",
    });
    expect(usePatientStore.getState().token).toBe("tok-1");
    expect(usePatientStore.getState().patientName).toBe("Alice");

    // Second login with only some fields wipes the rest (atomic replace)
    usePatientStore.getState().loginWithIdentity({ token: "tok-2", doctorId: "d2" });
    const s = usePatientStore.getState();
    expect(s.token).toBe("tok-2");
    expect(s.patientId).toBe("");      // wiped
    expect(s.patientName).toBe("");    // wiped
    expect(s.doctorId).toBe("d2");
    expect(s.doctorName).toBe("");     // wiped
  });

  it("mergeProfile updates only provided fields and never touches token", async () => {
    const { usePatientStore } = await import("../../src/store/patientStore.js");
    usePatientStore.getState().loginWithIdentity({ token: "T", patientId: "p1", patientName: "A" });
    usePatientStore.getState().mergeProfile({ patientName: "Alice", doctorId: "dx" });
    const s = usePatientStore.getState();
    expect(s.token).toBe("T");          // untouched
    expect(s.patientId).toBe("p1");     // untouched (not provided)
    expect(s.patientName).toBe("Alice"); // updated
    expect(s.doctorId).toBe("dx");       // updated
  });

  it("clearAuth wipes everything", async () => {
    const { usePatientStore } = await import("../../src/store/patientStore.js");
    usePatientStore.getState().loginWithIdentity({ token: "T", patientId: "p1" });
    usePatientStore.getState().clearAuth();
    expect(usePatientStore.getState().token).toBe("");
    expect(usePatientStore.getState().patientId).toBe("");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend/web && npx vitest run tests/unit/patient-store.spec.js
```

Expected: FAIL — `Cannot find module '../../src/store/patientStore.js'`.

- [ ] **Step 3: Create `patientStore.js`**

Create `frontend/web/src/store/patientStore.js`:

```javascript
import { create } from "zustand";
import { persist } from "zustand/middleware";

const EMPTY = {
  token: "",
  patientId: "",
  patientName: "",
  doctorId: "",
  doctorName: "",
};

export const usePatientStore = create(
  persist(
    (set) => ({
      ...EMPTY,
      // Atomic identity replace — use at login boundaries (QR absorption, /login).
      // Any field not provided is cleared, so stale identity from a prior session
      // never bleeds into the new one.
      loginWithIdentity: (next = {}) =>
        set({
          token: next.token || "",
          patientId: next.patientId || "",
          patientName: next.patientName || "",
          doctorId: next.doctorId || "",
          doctorName: next.doctorName || "",
        }),
      // Partial profile merge. Use only after login is established (e.g., when
      // /patient/me refresh returns canonical profile fields). Never touches token.
      mergeProfile: (partial = {}) =>
        set((s) => ({
          patientId: partial.patientId ?? s.patientId,
          patientName: partial.patientName ?? s.patientName,
          doctorId: partial.doctorId ?? s.doctorId,
          doctorName: partial.doctorName ?? s.doctorName,
        })),
      clearAuth: () => set(EMPTY),
    }),
    { name: "patient-portal-auth" }
  )
);

// One-shot migration from the legacy per-key localStorage scheme used by
// PatientPage before this store existed. Runs once on module load: if the new
// persisted store hasn't been written yet AND any of the old keys exist, hydrate
// the new store and delete the old keys. Idempotent across reloads.
const LEGACY_KEYS = {
  token:        "patient_portal_token",
  patientName:  "patient_portal_name",
  doctorId:     "patient_portal_doctor_id",
  doctorName:   "patient_portal_doctor_name",
  patientId:    "patient_portal_patient_id",
};

(function migrateLegacyAuth() {
  if (typeof localStorage === "undefined") return;
  if (localStorage.getItem("patient-portal-auth")) return; // new store wins
  const next = {};
  let any = false;
  for (const [field, legacyKey] of Object.entries(LEGACY_KEYS)) {
    const v = localStorage.getItem(legacyKey);
    if (v) { next[field] = v; any = true; }
  }
  if (!any) return;
  usePatientStore.getState().loginWithIdentity(next);
  for (const legacyKey of Object.values(LEGACY_KEYS)) {
    localStorage.removeItem(legacyKey);
  }
})();
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend/web && npx vitest run tests/unit/patient-store.spec.js
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/store/patientStore.js frontend/web/tests/unit/patient-store.spec.js
git commit -m "feat(patient-store): zustand-persisted patient auth with one-shot legacy migration"
```

---

### Task 1.2: Migrate `PatientPage.jsx` to read identity from `usePatientStore`

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientPage.jsx` (lines 48-181 substantially rewritten)

This is mostly mechanical replacement; behavior is preserved. No new automated test — covered by existing `24-patient-shell.spec.ts`.

- [ ] **Step 1: Replace the storage-key block + identity state**

In `frontend/web/src/v2/pages/patient/PatientPage.jsx`:

Delete the storage key block (lines 48-56):
```javascript
const STORAGE_KEY = "patient_portal_token";
const STORAGE_NAME_KEY = "patient_portal_name";
const STORAGE_DOCTOR_KEY = "patient_portal_doctor_id";
const STORAGE_DOCTOR_NAME_KEY = "patient_portal_doctor_name";
const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";
const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";
```

Keep only `LAST_SEEN_CHAT_KEY` and `PATIENT_CHAT_STORAGE_KEY` (chat code still uses them).

Add an import near the top (after other store imports):
```javascript
import { usePatientStore } from "../../../store/patientStore";
```

Replace the identity-state block (lines 90-93):
```javascript
const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
const [doctorName, setDoctorName] = useState(() => localStorage.getItem(STORAGE_DOCTOR_NAME_KEY) || "");
const [doctorId, setDoctorId] = useState(() => localStorage.getItem(STORAGE_DOCTOR_KEY) || "");
```

with:
```javascript
const { token, patientName, doctorName, doctorId } = usePatientStore();
```

- [ ] **Step 2: Replace the QR-absorption block to use the store atomically**

Replace the existing `useState(() => { ... QR absorption ... })` block (lines 73-87) with:

```javascript
useState(() => {
  const params = new URLSearchParams(window.location.search);
  const qrToken = params.get("token");
  if (!qrToken) return;
  usePatientStore.getState().loginWithIdentity({
    token: qrToken,
    patientName: params.get("name") || "",
    doctorId: params.get("doctor_id") || "",
    // patientId + doctorName intentionally empty — refreshed by /patient/me
  });
  const cleanUrl = new URL(window.location.href);
  ["token", "doctor_id", "name"].forEach((k) => cleanUrl.searchParams.delete(k));
  window.history.replaceState({}, "", cleanUrl.toString());
});
```

- [ ] **Step 3: Replace mock-mode and `/patient/me` refresh effects**

Replace the mock-mode effect (lines 101-108):

```javascript
useEffect(() => {
  if (!api.isMock) return;
  usePatientStore.getState().loginWithIdentity({
    token: "mock-patient-token",
    patientName: "陈伟强",
    doctorId: "mock_doctor",
    doctorName: "张医生",
  });
}, [api.isMock]);
```

Replace the `getPatientMe` refresh effect (lines 111-124) — `mergeProfile` only, never touches token:

```javascript
useEffect(() => {
  if (!token || api.isMock) return;
  api.getPatientMe(token).then((data) => {
    usePatientStore.getState().mergeProfile({
      patientId: data.patient_id ? String(data.patient_id) : undefined,
      patientName: data.patient_name || undefined,
      doctorId: data.doctor_id || undefined,
      doctorName: data.doctor_name || undefined,
    });
  }).catch(() => {});
}, [token, api]);
```

- [ ] **Step 4: Replace `handleLogout`**

Replace `handleLogout` (lines 166-179) with:

```javascript
const handleLogout = useCallback(() => {
  localStorage.removeItem(PATIENT_CHAT_STORAGE_KEY);
  usePatientStore.getState().clearAuth();
}, []);
```

- [ ] **Step 5: Run existing E2E to verify no regression, then commit**

Per memory: e2e on `:8001`. Start the validate-v2 e2e runner (already exists per `scripts/validate-v2-e2e.sh` from recent commits):

```bash
bash scripts/validate-v2-e2e.sh frontend/web/tests/e2e/24-patient-shell.spec.ts
```

Expected: PASS.

```bash
git add frontend/web/src/v2/pages/patient/PatientPage.jsx
git commit -m "refactor(patient-shell): read identity from usePatientStore (atomic login + merge profile)"
```

---

## Phase 2 — Shared primitives + barrel rename (Section 2 of spec)

Four tasks.

### Task 2.1: Rename `SectionHeader.jsx` → `ListSectionDivider.jsx` + barrel alias

**Files:**
- Rename: `frontend/web/src/v2/components/SectionHeader.jsx` → `ListSectionDivider.jsx`
- Modify: `frontend/web/src/v2/components/index.js`
- Modify: `frontend/web/src/v2/pages/doctor/ReviewPage.jsx:29`

- [ ] **Step 1: Git-rename the file**

```bash
git mv frontend/web/src/v2/components/SectionHeader.jsx frontend/web/src/v2/components/ListSectionDivider.jsx
```

No code edit inside the file is needed — the `export default function SectionHeader` line stays as-is for now (renaming the function symbol is a separate sweep that risks breaking the alias). The file path change is the only structural shift.

- [ ] **Step 2: Update the barrel**

Replace line 5 of `frontend/web/src/v2/components/index.js`:

```javascript
export { default as SectionHeader } from "./SectionHeader";
```

with:

```javascript
export { default as ListSectionDivider } from "./ListSectionDivider";
export { default as SectionHeader } from "./ListSectionDivider"; // DEPRECATED — removed in Phase 5 (Task 5.6)
```

- [ ] **Step 3: Update external consumers**

There are **two** external consumers (the original spec missed `TasksTab.jsx` — verify with the grep in Step 4 before assuming the count):

In `frontend/web/src/v2/pages/doctor/ReviewPage.jsx:29`, replace:

```javascript
import { ActionFooter, SectionHeader, CitationPopup } from "../../components";
```

with:

```javascript
import { ActionFooter, ListSectionDivider as SectionHeader, CitationPopup } from "../../components";
```

In `frontend/web/src/v2/pages/patient/TasksTab.jsx:17`, replace:

```javascript
import { LoadingCenter, EmptyState, SectionHeader } from "../../components";
```

with:

```javascript
import { LoadingCenter, EmptyState, ListSectionDivider as SectionHeader } from "../../components";
```

(Local `as SectionHeader` aliases keep the JSX usages untouched — Phase 5 sweeps both files to use the new name and removes the alias.)

- [ ] **Step 4: Verify no other consumers broke**

```bash
grep -rn "from.*v2/components.*SectionHeader\|SectionHeader.*from.*v2/components" frontend/web/src 2>/dev/null
```

Expected: only the alias line in `index.js` and the aliased import in `ReviewPage.jsx`. No other matches.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/components/ListSectionDivider.jsx frontend/web/src/v2/components/index.js frontend/web/src/v2/pages/doctor/ReviewPage.jsx
git commit -m "refactor(v2-components): rename SectionHeader → ListSectionDivider + alias for migration"
```

---

### Task 2.2: Create shared `Card` primitive

**Files:**
- Create: `frontend/web/src/v2/components/Card.jsx`
- Modify: `frontend/web/src/v2/components/index.js`

- [ ] **Step 1: Create the file**

Create `frontend/web/src/v2/components/Card.jsx`:

```jsx
/**
 * Card — the standard floating white card used across v2 doctor + patient pages.
 *
 * Usage: a Card sits on the gray pageContainer bg with a small horizontal margin.
 * Section headers and other chrome go OUTSIDE the Card on the gray bg.
 */
import { APP, RADIUS } from "../theme";

export default function Card({ children, style }) {
  return (
    <div
      style={{
        background: APP.surface,
        margin: "0 12px",
        borderRadius: RADIUS.lg,
        overflow: "hidden",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Add to barrel**

Append to `frontend/web/src/v2/components/index.js`:

```javascript
export { default as Card } from "./Card";
```

- [ ] **Step 3: Verify the export resolves**

```bash
cd frontend/web && node -e "import('./src/v2/components/index.js').then(m => console.log(Object.keys(m).join(' ')))"
```

Expected: output includes `Card`.

- [ ] **Step 4: (skipped — no test step)**

This is a pure presentational primitive with no logic. Visual verification happens in Task 2.4 when SettingsPage starts using it.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/components/Card.jsx frontend/web/src/v2/components/index.js
git commit -m "feat(v2-components): shared Card primitive (floating white card on gray bg)"
```

---

### Task 2.3: Create shared `TintedIconRow` primitive

**Files:**
- Create: `frontend/web/src/v2/components/TintedIconRow.jsx`
- Modify: `frontend/web/src/v2/components/index.js`

- [ ] **Step 1: Create the file**

Create `frontend/web/src/v2/components/TintedIconRow.jsx`:

```jsx
/**
 * TintedIconRow — list row used inside a Card. 36px circular tinted icon on
 * the left, title + optional subtitle in the middle, optional `extra` slot or
 * chevron on the right.
 *
 * Use for settings rows, action menus, navigation rows. See doctor SettingsPage
 * for canonical usage.
 */
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { APP, FONT, ICON, RADIUS } from "../theme";

export default function TintedIconRow({
  Icon,
  iconColor,
  iconBg,
  title,
  subtitle,
  onClick,
  extra,
  isFirst,
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "14px 16px",
        cursor: onClick ? "pointer" : "default",
        borderTop: isFirst ? "none" : `0.5px solid ${APP.borderLight}`,
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: RADIUS.md,
          background: iconBg,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon sx={{ fontSize: ICON.sm, color: iconColor }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
            {subtitle}
          </div>
        )}
      </div>
      {extra ?? (onClick && <ChevronRightIcon sx={{ fontSize: ICON.sm, color: APP.text4 }} />)}
    </div>
  );
}
```

- [ ] **Step 2: Add to barrel**

Append to `frontend/web/src/v2/components/index.js`:

```javascript
export { default as TintedIconRow } from "./TintedIconRow";
```

- [ ] **Step 3: Verify the export resolves**

```bash
cd frontend/web && node -e "import('./src/v2/components/index.js').then(m => console.log(Object.keys(m).join(' ')))"
```

Expected: output includes `TintedIconRow`.

- [ ] **Step 4: (skipped — visual verification in Task 2.4)**

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/components/TintedIconRow.jsx frontend/web/src/v2/components/index.js
git commit -m "feat(v2-components): shared TintedIconRow primitive (36px tinted-circle list row)"
```

---

### Task 2.4: Migrate doctor `SettingsPage` + `AboutSubpage` to shared primitives

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/SettingsPage.jsx` (delete local `Card` + `SettingsRow`, import shared)
- Modify: `frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx` (delete local `Card`, import shared)

Visual change should be zero.

- [ ] **Step 1: Update `SettingsPage.jsx` imports**

In `frontend/web/src/v2/pages/doctor/SettingsPage.jsx`, line 23, replace:

```javascript
import { NameAvatar } from "../../components";
```

with:

```javascript
import { NameAvatar, Card, TintedIconRow } from "../../components";
```

- [ ] **Step 2: Delete the local primitives in `SettingsPage.jsx`**

Delete the local `Card` definition (lines 44-57) and the local `SettingsRow` definition (lines 59-99). The local `SectionHeader` (lines 25-42) **stays** — it has no shared equivalent.

Replace the JSX usages of `<SettingsRow ...>` in lines 162-208 with `<TintedIconRow ...>` — the prop interface is identical, so it's a global rename within this file (use Edit `replace_all`).

- [ ] **Step 3: Update `AboutSubpage.jsx`**

In `frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx`:

Add the import:
```javascript
import { Card } from "../../../components";
```

Delete the local `Card` definition (lines 27-40). The local `SectionHeader` stays (text-only — different from SettingsPage's icon variant).

- [ ] **Step 4: Smoke-verify the doctor settings flow visually**

Start the dev server on `:8001` (the project's QA port) and navigate to `/doctor/settings` and `/doctor/settings/about`. Confirm visual identity to before the change. (No automated assertion — this is a no-op refactor verified by inspection.)

```bash
bash scripts/validate-v2-e2e.sh frontend/web/tests/e2e/11-settings.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/SettingsPage.jsx frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx
git commit -m "refactor(doctor-settings): consume shared Card + TintedIconRow primitives"
```

---

## Phase 3 — Patient query layer (Section 3 of spec)

Three tasks.

### Task 3.1: Add `PK` namespace to `queryKeys.js`

**Files:**
- Modify: `frontend/web/src/lib/queryKeys.js`

- [ ] **Step 1: Append the PK namespace**

Append to `frontend/web/src/lib/queryKeys.js`:

```javascript
// Patient portal keys — parallel to QK (doctor)
export const PK = {
  patientMe:           ()    => ["patient","me"],
  patientRecords:      ()    => ["patient","records"],
  patientRecordDetail: (id)  => ["patient","records", String(id)],
  patientTasks:        ()    => ["patient","tasks"],
  patientTaskDetail:   (id)  => ["patient","tasks", String(id)],
};
```

- [ ] **Step 2: Verify import surface**

```bash
cd frontend/web && node -e "import('./src/lib/queryKeys.js').then(m => console.log('PK:', Object.keys(m.PK).join(',')))"
```

Expected: `PK: patientMe,patientRecords,patientRecordDetail,patientTasks,patientTaskDetail`.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/lib/queryKeys.js
git commit -m "chore(query-keys): add PK namespace for patient portal hooks"
```

---

### Task 3.2: Create `patientQueries.js` with hooks + mutations

**Files:**
- Create: `frontend/web/src/lib/patientQueries.js`

- [ ] **Step 1: Create the file**

Create `frontend/web/src/lib/patientQueries.js`:

```javascript
/**
 * patientQueries — React Query hooks for the patient portal.
 *
 * Mirrors lib/doctorQueries.js shape. Token comes from usePatientStore (not
 * threaded through props/args). ChatTab does NOT live here — its bespoke
 * polling + optimistic dedupe is preserved as-is.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PK } from "./queryKeys";
import { usePatientApi } from "../api/PatientApiContext";
import { usePatientStore } from "../store/patientStore";

// ── Queries ──────────────────────────────────────────────────────────────

export function usePatientMe() {
  const api = usePatientApi();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientMe(),
    queryFn:  () => api.getPatientMe(token),
    enabled:  !!token,
    staleTime: 5 * 60_000,
  });
}

export function usePatientRecords() {
  const api = usePatientApi();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientRecords(),
    queryFn:  () => api.getPatientRecords(token),
    enabled:  !!token,
    staleTime: 30_000,
  });
}

export function usePatientRecordDetail(id) {
  const api = usePatientApi();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientRecordDetail(id),
    queryFn:  () => api.getPatientRecordDetail(token, id),
    enabled:  !!token && !!id,
    staleTime: 60_000,
  });
}

export function usePatientTasks() {
  const api = usePatientApi();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientTasks(),
    queryFn:  () => api.getPatientTasks(token),
    enabled:  !!token,
    staleTime: 30_000,
  });
}

export function usePatientTaskDetail(id) {
  const api = usePatientApi();
  const qc = useQueryClient();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientTaskDetail(id),
    queryFn:  () => api.getPatientTaskDetail(token, id),
    enabled:  !!token && !!id,
    staleTime: 60_000,
    // Use the matching task from the cached list as initialData when present —
    // gives instant render while the per-id endpoint refreshes in the background.
    initialData: () => {
      const list = qc.getQueryData(PK.patientTasks());
      return list?.find((t) => String(t.id) === String(id));
    },
  });
}

// ── Mutations ────────────────────────────────────────────────────────────

export function useCompletePatientTask() {
  const api = usePatientApi();
  const qc = useQueryClient();
  const token = usePatientStore((s) => s.token);
  return useMutation({
    mutationFn: (taskId) => api.completePatientTask(token, taskId),
    onSuccess: (_data, taskId) => {
      qc.invalidateQueries({ queryKey: PK.patientTasks() });
      qc.invalidateQueries({ queryKey: PK.patientTaskDetail(taskId) });
    },
  });
}

export function useUncompletePatientTask() {
  const api = usePatientApi();
  const qc = useQueryClient();
  const token = usePatientStore((s) => s.token);
  return useMutation({
    mutationFn: (taskId) => api.uncompletePatientTask(token, taskId),
    onSuccess: (_data, taskId) => {
      qc.invalidateQueries({ queryKey: PK.patientTasks() });
      qc.invalidateQueries({ queryKey: PK.patientTaskDetail(taskId) });
    },
  });
}
```

- [ ] **Step 2: Verify import surface**

```bash
cd frontend/web && node -e "import('./src/lib/patientQueries.js').then(m => console.log(Object.keys(m).join(',')))"
```

Expected: includes `usePatientMe,usePatientRecords,usePatientRecordDetail,usePatientTasks,usePatientTaskDetail,useCompletePatientTask,useUncompletePatientTask`.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/lib/patientQueries.js
git commit -m "feat(patient-queries): React Query hooks + mutations for patient portal"
```

---

### Task 3.3: Migrate `RecordsTab` + `TasksTab` + `PatientPage` shell to hooks

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/RecordsTab.jsx` (drop inline fetch state)
- Modify: `frontend/web/src/v2/pages/patient/TasksTab.jsx` (drop inline fetch state + use mutation hooks)
- Modify: `frontend/web/src/v2/pages/patient/PatientPage.jsx` (replace `getPatientMe` effect with `usePatientMe()`)

Behavior must be unchanged. Visual change happens in Phase 4.

- [ ] **Step 1: Migrate `RecordsTab`**

In `frontend/web/src/v2/pages/patient/RecordsTab.jsx`, near the top:

Add import:
```javascript
import { usePatientRecords } from "../../../lib/patientQueries";
```

Replace the existing inline fetch state + `useEffect` (around lines 230-260 — the `useState`/`useEffect` block that calls `getPatientRecords(token)`) with:

```javascript
const { data: records = [], isLoading, isError, refetch } = usePatientRecords();
```

Drop the `loading` and `error` local states; use `isLoading` / `isError` from the hook. Remove the `token` prop usage from data fetching (the prop can stay for now if other code still threads it; it just becomes a no-op).

- [ ] **Step 2: Migrate `TasksTab`**

In `frontend/web/src/v2/pages/patient/TasksTab.jsx`:

Add imports:
```javascript
import {
  usePatientTasks,
  useCompletePatientTask,
  useUncompletePatientTask,
} from "../../../lib/patientQueries";
```

Replace inline fetch state with:
```javascript
const { data: tasks = [], isLoading, isError, refetch } = usePatientTasks();
const completeTask   = useCompletePatientTask();
const uncompleteTask = useUncompletePatientTask();
```

Replace existing complete/undo handlers (which currently call `api.completePatientTask` directly + manual list refresh) with calls to `completeTask.mutate(taskId)` / `uncompleteTask.mutate(taskId)`. The mutation invalidation handles the refresh.

- [ ] **Step 3: Migrate `PatientPage` shell to `usePatientMe`**

In `frontend/web/src/v2/pages/patient/PatientPage.jsx`, replace the `useEffect` block from Task 1.2 Step 3 (the one that calls `api.getPatientMe(token)` directly):

```javascript
// Refresh canonical profile from /patient/me; merges into store on success.
const meQuery = usePatientMe();
useEffect(() => {
  if (!meQuery.data) return;
  usePatientStore.getState().mergeProfile({
    patientId: meQuery.data.patient_id ? String(meQuery.data.patient_id) : undefined,
    patientName: meQuery.data.patient_name || undefined,
    doctorId: meQuery.data.doctor_id || undefined,
    doctorName: meQuery.data.doctor_name || undefined,
  });
}, [meQuery.data]);
```

Add the import:
```javascript
import { usePatientMe } from "../../../lib/patientQueries";
```

- [ ] **Step 4: Verify existing patient E2E specs still pass**

```bash
bash scripts/validate-v2-e2e.sh frontend/web/tests/e2e/22-patient-records.spec.ts frontend/web/tests/e2e/23-patient-tasks.spec.ts frontend/web/tests/e2e/24-patient-shell.spec.ts
```

Expected: PASS for all three.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/patient/RecordsTab.jsx frontend/web/src/v2/pages/patient/TasksTab.jsx frontend/web/src/v2/pages/patient/PatientPage.jsx
git commit -m "refactor(patient-tabs): consume React Query hooks (records, tasks, me) — chat unchanged"
```

---

## Phase 4 — Visual rewrites (Section 4 of spec)

Six tasks.

### Task 4.1: Extract `patientFontScale.js` util

**Files:**
- Create: `frontend/web/src/v2/lib/patientFontScale.js`

- [ ] **Step 1: Create the util**

Create `frontend/web/src/v2/lib/patientFontScale.js`:

```javascript
/**
 * Patient font scale — local-only (no server sync, unlike the doctor store).
 *
 * Default tier: "large" (1.15×). The patient audience skews older / less
 * tech-comfortable, so the larger default and the 3-option selector
 * (standard / large / extraLarge) are deliberately preserved here.
 *
 * The doctor app uses a separate store (store/fontScaleStore) keyed under
 * "doctor-font-scale" and auto-syncs to the doctor backend. Patient must NOT
 * use that store — it would cross-contaminate doctor preferences in shared-
 * browser scenarios.
 */
import { applyFontScale } from "../theme";

const FONT_SCALE_KEY = "v2_patient_font_scale";

export const FONT_SCALE_OPTIONS = [
  { key: "standard",   label: "标准" },
  { key: "large",      label: "大" },
  { key: "extraLarge", label: "特大" },
];

export function getFontScale() {
  return localStorage.getItem(FONT_SCALE_KEY) || "large";
}

export function setFontScale(tier) {
  localStorage.setItem(FONT_SCALE_KEY, tier);
  applyFontScale(tier);
}

export function getFontScaleLabel(tier) {
  return FONT_SCALE_OPTIONS.find((o) => o.key === tier)?.label || "标准";
}
```

> Note: the storage key changes from `v2_font_scale` to `v2_patient_font_scale`. To preserve existing patient choices, add a one-shot migration block at module load:

Append to the same file:

```javascript
// One-shot migration from the legacy v2_font_scale key (used by MyPage before
// extraction). Idempotent: only runs if the new key is empty AND the legacy
// key has a value.
(function migrate() {
  if (typeof localStorage === "undefined") return;
  if (localStorage.getItem(FONT_SCALE_KEY)) return;
  const legacy = localStorage.getItem("v2_font_scale");
  if (!legacy) return;
  localStorage.setItem(FONT_SCALE_KEY, legacy);
  localStorage.removeItem("v2_font_scale");
})();
```

- [ ] **Step 2: Smoke-verify**

```bash
cd frontend/web && node -e "import('./src/v2/lib/patientFontScale.js').then(m => console.log(Object.keys(m).join(',')))"
```

Expected: `FONT_SCALE_OPTIONS,getFontScale,setFontScale,getFontScaleLabel`.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/lib/patientFontScale.js
git commit -m "feat(patient-font): extract local-only font-scale util (preserves large default + 3 tiers)"
```

---

### Task 4.2: Rewrite `MyPage` to mirror doctor `SettingsPage` style

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/MyPage.jsx` (full rewrite)

- [ ] **Step 1: Replace the file end-to-end**

Replace the entire contents of `frontend/web/src/v2/pages/patient/MyPage.jsx` with:

```jsx
/**
 * MyPage — patient "我的" settings page (v2, antd-mobile, doctor-card-pattern).
 *
 * Mirrors doctor SettingsPage visual structure: profile card, section headers
 * (icon + label) above each Card, TintedIconRow rows inside Cards, danger-
 * outlined logout button, security footer. The local SectionHeader stays local
 * — patient app is the only second consumer right now and the abstraction
 * isn't earned yet.
 */
import { useState } from "react";
import { Button, Dialog, Popup, Radio, Space } from "antd-mobile";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import FormatSizeOutlinedIcon from "@mui/icons-material/FormatSizeOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import LogoutOutlinedIcon from "@mui/icons-material/LogoutOutlined";
import SecurityOutlinedIcon from "@mui/icons-material/SecurityOutlined";
import { useNavigate } from "react-router-dom";

import { APP, FONT, ICON, RADIUS } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";
import { Card, NameAvatar, TintedIconRow } from "../../components";
import {
  FONT_SCALE_OPTIONS,
  getFontScale,
  setFontScale as persistFontScale,
  getFontScaleLabel,
} from "../../lib/patientFontScale";

const ONBOARDING_DONE_KEY_PREFIX = "patient_onboarding_done_";

// Local section header (icon + label, sits OUTSIDE Card on the gray bg).
// Same visual pattern as doctor/SettingsPage's local SectionHeader.
function SectionHeader({ Icon, iconColor, title }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "0 20px",
        margin: "16px 0 8px",
      }}
    >
      <Icon sx={{ fontSize: ICON.sm, color: iconColor }} />
      <span style={{ fontSize: FONT.base, color: APP.text3, fontWeight: 500 }}>
        {title}
      </span>
    </div>
  );
}

export default function MyPage({ patientName, doctorName, doctorSpecialty, onLogout }) {
  const navigate = useNavigate();
  const [fontScale, setFontScaleState] = useState(getFontScale);
  const [showFontPopup, setShowFontPopup] = useState(false);

  function handleFontScaleChange(tier) {
    setFontScaleState(tier);
    persistFontScale(tier);
    setShowFontPopup(false);
  }

  function handleReplayOnboarding() {
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId) localStorage.removeItem(ONBOARDING_DONE_KEY_PREFIX + patientId);
    window.location.reload();
  }

  function handleLogoutTap() {
    Dialog.confirm({
      title: "退出登录",
      content: "确定要退出登录吗？",
      cancelText: "取消",
      confirmText: "退出",
      onConfirm: onLogout,
    });
  }

  return (
    <div style={pageContainer}>
      <div style={{ ...scrollable, paddingTop: 12, paddingBottom: 24 }}>
        {/* Profile card — display only */}
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 16px" }}>
            <NameAvatar name={patientName || "患"} size={48} color={APP.primary} charPosition="last" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: FONT.lg, fontWeight: 700, color: APP.text1 }}>
                {patientName || "患者"}
              </div>
              <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
                患者
              </div>
            </div>
          </div>
        </Card>

        {/* My doctor */}
        {doctorName && (
          <>
            <SectionHeader Icon={LocalHospitalOutlinedIcon} iconColor={APP.accent} title="我的医生" />
            <Card>
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 16px" }}>
                <NameAvatar name={doctorName} size={44} color={APP.accent} charPosition="last" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>
                    {doctorName}
                  </div>
                  {doctorSpecialty && (
                    <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
                      {doctorSpecialty}
                    </div>
                  )}
                </div>
              </div>
            </Card>
          </>
        )}

        {/* General */}
        <SectionHeader Icon={SettingsOutlinedIcon} iconColor={APP.accent} title="通用" />
        <Card>
          <TintedIconRow
            Icon={InfoOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="关于"
            subtitle="版本信息"
            onClick={() => navigate("/patient/profile/about")}
            isFirst
          />
          <TintedIconRow
            Icon={LockOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="隐私政策"
            subtitle="数据使用与保护"
            onClick={() => navigate("/patient/profile/privacy")}
          />
          <TintedIconRow
            Icon={FormatSizeOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="字体大小"
            subtitle={getFontScaleLabel(fontScale)}
            onClick={() => setShowFontPopup(true)}
          />
          <TintedIconRow
            Icon={RefreshOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="重新查看引导"
            onClick={handleReplayOnboarding}
          />
        </Card>

        {/* Logout */}
        <div style={{ margin: "24px 12px 8px" }}>
          <Button
            block
            color="danger"
            fill="outline"
            onClick={handleLogoutTap}
            style={{
              "--border-radius": `${RADIUS.lg}px`,
              padding: "14px 0",
              fontSize: FONT.md,
              fontWeight: 600,
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <LogoutOutlinedIcon sx={{ fontSize: ICON.sm }} />
              退出登录
            </span>
          </Button>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            padding: "8px 16px",
            fontSize: FONT.sm,
            color: APP.text4,
          }}
        >
          <SecurityOutlinedIcon sx={{ fontSize: ICON.xs, color: APP.text4 }} />
          <span>退出后将清除本地缓存，确保账号安全</span>
        </div>

        {/* Font-size Popup (3 options preserved) */}
        <Popup
          visible={showFontPopup}
          onMaskClick={() => setShowFontPopup(false)}
          position="bottom"
          bodyStyle={{ borderRadius: `${RADIUS.xl}px ${RADIUS.xl}px 0 0`, padding: "16px 16px 32px" }}
        >
          <div style={{ textAlign: "center", fontSize: FONT.md, fontWeight: 600, color: APP.text1, marginBottom: 16 }}>
            字体大小
          </div>
          <Radio.Group value={fontScale} onChange={handleFontScaleChange}>
            <Space direction="vertical" style={{ width: "100%" }}>
              {FONT_SCALE_OPTIONS.map((o) => (
                <Radio key={o.key} value={o.key} style={{ width: "100%", fontSize: FONT.md }}>
                  {o.label}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
          <Button
            block
            color="default"
            style={{ marginTop: 16, borderRadius: RADIUS.md }}
            onClick={() => setShowFontPopup(false)}
          >
            取消
          </Button>
        </Popup>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Smoke-verify visually on `:8001`**

Start the dev environment and navigate to `/patient` → 我的 tab. Confirm:
- Gray page bg with floating white profile + my-doctor + general cards
- 4 tinted-icon rows in 通用 (关于 / 隐私政策 / 字体大小 / 重新查看引导)
- Tapping 字体大小 opens the 3-option Popup
- 退出登录 button (danger outlined) at bottom
- Security footer below

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/patient/MyPage.jsx
git commit -m "feat(patient-mypage): mirror doctor SettingsPage card pattern (font tier large preserved)"
```

---

### Task 4.3: `RecordsTab` — apply card pattern + PullToRefresh

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/RecordsTab.jsx`

- [ ] **Step 1: Switch page bg to `pageContainer`, wrap rows in `<Card>`**

In `frontend/web/src/v2/pages/patient/RecordsTab.jsx`:

Add imports:
```javascript
import { PullToRefresh, Ellipsis } from "antd-mobile";  // Ellipsis may already be imported
import { Card } from "../../components";
```

Wrap the outer container with `pageContainer` style (replace any inline `background: APP.surface` on the outer div).

Replace the existing `List` rendering of records with a stack of `<Card>` rows. Each row:

```jsx
<Card style={{ marginTop: 8 }}>
  <div
    onClick={() => navigate(`/patient/records/${rec.id}`)}
    style={{ padding: "12px 14px", cursor: "pointer" }}
  >
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
      <Tag color={typeColor(rec.record_type)}>{RECORD_TYPE_LABEL[rec.record_type]}</Tag>
      <span style={{ fontSize: FONT.sm, color: APP.text4 }}>{formatDate(rec.created_at)}</span>
    </div>
    <Ellipsis
      content={rec.structured?.chief_complaint || rec.content || "—"}
      rows={1}
      direction="end"
      style={{ fontSize: FONT.base, color: APP.text1 }}
    />
    <div style={{ marginTop: 4, fontSize: FONT.sm, color: APP.text4 }}>
      {DIAGNOSIS_STATUS_LABELS[rec.diagnosis_status] || ""}
    </div>
  </div>
</Card>
```

`typeColor(...)` is a tiny local fn returning `'primary' | 'success' | ...` per record type (or use Tag color tokens already in the file).

Wrap the list in `<PullToRefresh onRefresh={refetch}>...</PullToRefresh>`.

- [ ] **Step 2: Update empty + loading + error**

- Loading: render shared `<LoadingCenter />`.
- Error: render shared `<EmptyState />` with retry.
- Empty list (after load): shared `<EmptyState />`.

- [ ] **Step 3: Smoke-verify on `:8001`**

Navigate to `/patient/records`. Confirm gray bg, floating white cards, pull-to-refresh works (drag down → records reload).

```bash
bash scripts/validate-v2-e2e.sh frontend/web/tests/e2e/22-patient-records.spec.ts
```

If selector failures appear, update them in this same task — the existing spec was written against `<List.Item>` selectors and needs migration to text-based queries.

- [ ] **Step 4: Update `22-patient-records.spec.ts` selectors**

Wherever the spec asserted `getByRole('listitem')` or similar, switch to `getByText(<chief_complaint>)` or a stable test-id. Add `data-testid="patient-record-row"` to the Card wrapper if needed for stability.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/patient/RecordsTab.jsx frontend/web/tests/e2e/22-patient-records.spec.ts
git commit -m "feat(patient-records): card pattern + PullToRefresh + Ellipsis overflow"
```

---

### Task 4.4: `TasksTab` — apply card pattern + PullToRefresh (no SwipeAction)

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/TasksTab.jsx`

- [ ] **Step 1: Wrap rows in `<Card>` with visible tap-target prefix**

Each task becomes:

```jsx
<Card style={{ marginTop: 8 }}>
  <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px" }}>
    {/* Tap-target prefix — visible toggle, not hidden behind a swipe */}
    <div
      onClick={(e) => {
        e.stopPropagation();
        if (task.status === "pending") {
          completeTask.mutate(task.id);
        } else if (task.status === "completed") {
          uncompleteTask.mutate(task.id);
        }
      }}
      style={{
        width: 36, height: 36, borderRadius: RADIUS.md,
        background: task.status === "completed" ? APP.primaryLight : APP.surfaceAlt,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0, cursor: "pointer",
      }}
      role="button"
      aria-label={task.status === "completed" ? "撤销完成" : "标记完成"}
    >
      {task.status === "completed"
        ? <CheckOutlinedIcon sx={{ fontSize: ICON.sm, color: APP.primary }} />
        : <div style={{ width: 18, height: 18, borderRadius: "50%", border: `1.5px solid ${APP.border}` }} />}
    </div>
    {/* Body — tap navigates to detail */}
    <div
      onClick={() => navigate(`/patient/tasks/${task.id}`)}
      style={{ flex: 1, minWidth: 0, cursor: "pointer" }}
    >
      <Ellipsis
        content={task.title}
        rows={2}
        direction="end"
        style={{ fontSize: FONT.base, color: APP.text1, fontWeight: 500 }}
      />
      <div style={{ marginTop: 4, fontSize: FONT.sm, color: APP.text4 }}>
        {task.due_at ? `截止: ${formatDate(task.due_at)}` : ""}
      </div>
    </div>
  </div>
</Card>
```

Add the imports for `Card`, `CheckOutlinedIcon`, `RADIUS`, etc.

Wrap the list in `<PullToRefresh onRefresh={refetch}>...</PullToRefresh>`.

- [ ] **Step 2: Drop the prior `List.Item` chrome**

Delete any leftover `<List>` / `<List.Item>` JSX from this tab — the cards replace them entirely.

- [ ] **Step 3: Smoke-verify on `:8001`**

Navigate to `/patient/tasks`. Confirm:
- Gray bg, floating white card per task
- Tap circle prefix → row toggles between pending and completed (icon flips, list re-fetches)
- Tap body → navigates to `/patient/tasks/:id` (detail page is still the stub from Phase 1; actual content lands in Phase 5 — that's expected)
- Pull down → list refreshes

- [ ] **Step 4: Update `23-patient-tasks.spec.ts` selectors**

Adjust the existing E2E to use:
- Click the prefix tap target via `getByLabel("标记完成")` / `getByLabel("撤销完成")`
- Click body via `getByText(taskTitle)` to navigate to detail (assert URL change to `/patient/tasks/<id>`)

```bash
bash scripts/validate-v2-e2e.sh frontend/web/tests/e2e/23-patient-tasks.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/patient/TasksTab.jsx frontend/web/tests/e2e/23-patient-tasks.spec.ts
git commit -m "feat(patient-tasks): card pattern + visible tap-target prefix + PullToRefresh"
```

---

### Task 4.5: `ChatTab` — QuickActions row → `Card` + `TintedIconRow`

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/ChatTab.jsx` (only the QuickActions block + empty state)

Polling, send, optimistic, unread badge: all untouched.

- [ ] **Step 1: Replace the QuickActions block**

Find the inline QuickActions JSX (a row of 2 inline buttons sitting above the message list). Replace with:

```jsx
import { Card, TintedIconRow } from "../../components";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";

// ...inside the render...
<Card style={{ marginTop: 8, marginBottom: 8 }}>
  <TintedIconRow
    Icon={AddCircleOutlineIcon}
    iconColor={APP.primary}
    iconBg={APP.primaryLight}
    title="新问诊"
    subtitle="开始 AI 预问诊"
    onClick={onNewInterview}
    isFirst
  />
  <TintedIconRow
    Icon={FolderOutlinedIcon}
    iconColor={APP.accent}
    iconBg={APP.accentLight}
    title="查看病历"
    subtitle="历史记录与诊断"
    onClick={onViewRecords}
  />
</Card>
```

- [ ] **Step 2: Replace empty state**

If the chat empty state was inline ("还没有消息..."), replace with the shared `<EmptyState>` component already imported from `v2/components`.

- [ ] **Step 3: Smoke-verify on `:8001`**

Navigate to `/patient/chat`. Confirm:
- Card with 2 tinted-icon rows above the message list (新问诊 green, 查看病历 blue)
- Tapping 新问诊 → navigates to `/patient/records/interview`
- Tapping 查看病历 → navigates to `/patient/records`
- Polling, sending messages, unread badge clearing on tab visit: all unchanged

```bash
bash scripts/validate-v2-e2e.sh frontend/web/tests/e2e/21-patient-chat.spec.ts
```

Expected: PASS (chat behavior is unchanged).

- [ ] **Step 4: (skipped — visual)**

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/patient/ChatTab.jsx
git commit -m "feat(patient-chat): re-skin QuickActions as Card + TintedIconRow (polling untouched)"
```

---

### Task 4.6: `PatientOnboarding` — token cleanup

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientOnboarding.jsx`

- [ ] **Step 1: Sweep hardcoded values**

Replace inline literals with theme tokens:
- `fontSize: 14` / `16` / `18` / etc. (text) → `FONT.sm` / `FONT.base` / `FONT.md` / `FONT.lg` matching intent
- `fontSize: 20` / `24` / `28` (icons) → `ICON.sm` / `ICON.md` / `ICON.lg`
- Hex colors (`#07C160`, `#999`, etc.) → `APP.primary`, `APP.text4`, etc.
- `borderRadius: 8` / `12` / `16` → `RADIUS.md` / `RADIUS.lg` / `RADIUS.xl`

Add the import line at the top:
```javascript
import { APP, FONT, ICON, RADIUS } from "../../theme";
```

(if not already present).

- [ ] **Step 2: Run lint-ui to verify no violations remain**

```bash
bash scripts/lint-ui.sh
```

Expected: zero violations from `PatientOnboarding.jsx`. (Other files may still have known/exempted violations — only check lines mentioning `PatientOnboarding`.)

- [ ] **Step 3: Smoke-verify on `:8001`**

Clear localStorage for the patient onboarding-done key, reload `/patient`. Confirm the 3-step onboarding overlay still renders correctly with no visual regression.

- [ ] **Step 4: (skipped — visual)**

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/patient/PatientOnboarding.jsx
git commit -m "chore(patient-onboarding): tokenize literal sizes/colors/radii (no behavior change)"
```

---

## Phase 5 — Real subpage content + final cleanup (Section 5 of spec)

Six tasks.

### Task 5.1: `PatientRecordDetailPage` real content

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientRecordDetailPage.jsx` (replace stub)

- [ ] **Step 1: Replace the file end-to-end**

Replace contents with:

```jsx
/**
 * @route /patient/records/:id
 * Read-only patient-facing record detail. Doctor card pattern — gray pageContainer
 * with floating white Card sections. Field names match the actual
 * PatientRecordDetailOut payload shape, NOT made-up names.
 */
import { useState } from "react";
import { NavBar, Tag, Collapse } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT, RADIUS } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { Card, LoadingCenter, EmptyState } from "../../components";
import { usePatientRecordDetail } from "../../../lib/patientQueries";

const TYPE_LABEL = {
  visit: "门诊记录",
  dictation: "语音记录",
  import: "导入记录",
  interview_summary: "预问诊",
};

const STATUS_LABEL = {
  completed: { text: "待审核", color: "primary" },
  confirmed: { text: "已确认", color: "success" },
};

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}

function Section({ title, children }) {
  return (
    <Card style={{ marginTop: 8 }}>
      <div style={{ padding: "12px 14px" }}>
        <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 6 }}>
          {title}
        </div>
        <div style={{ fontSize: FONT.base, color: APP.text1, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
          {children}
        </div>
      </div>
    </Card>
  );
}

export default function PatientRecordDetailPage({ recordId }) {
  const navigate = useNavigate();
  const { data: rec, isLoading, isError, refetch } = usePatientRecordDetail(recordId);

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        病历详情
      </NavBar>
      <div style={scrollable}>
        {isLoading && <LoadingCenter />}
        {isError && (
          <EmptyState title="加载失败" description="请稍后重试" actionLabel="重试" onAction={refetch} />
        )}
        {rec && (
          <>
            {/* Header */}
            <Card style={{ marginTop: 8 }}>
              <div style={{ padding: "12px 14px", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <Tag color="primary">{TYPE_LABEL[rec.record_type] || rec.record_type}</Tag>
                <span style={{ fontSize: FONT.sm, color: APP.text4 }}>{formatDate(rec.created_at)}</span>
                {rec.diagnosis_status && STATUS_LABEL[rec.diagnosis_status] && (
                  <Tag color={STATUS_LABEL[rec.diagnosis_status].color}>
                    {STATUS_LABEL[rec.diagnosis_status].text}
                  </Tag>
                )}
              </div>
            </Card>

            {/* 主诉 / 现病史 (each only if non-empty) */}
            {rec.structured?.chief_complaint && <Section title="主诉">{rec.structured.chief_complaint}</Section>}
            {rec.structured?.present_illness && <Section title="现病史">{rec.structured.present_illness}</Section>}

            {/* 既往史 / 过敏史 / 个人史 / 家族史 — combined card if any non-empty */}
            {(rec.structured?.past_history || rec.structured?.allergy_history ||
              rec.structured?.personal_history || rec.structured?.family_history) && (
              <Card style={{ marginTop: 8 }}>
                <div style={{ padding: "12px 14px" }}>
                  {rec.structured.past_history && (
                    <SubField label="既往史" value={rec.structured.past_history} />
                  )}
                  {rec.structured.allergy_history && (
                    <SubField label="过敏史" value={rec.structured.allergy_history} />
                  )}
                  {rec.structured.personal_history && (
                    <SubField label="个人史" value={rec.structured.personal_history} />
                  )}
                  {rec.structured.family_history && (
                    <SubField label="家族史" value={rec.structured.family_history} />
                  )}
                </div>
              </Card>
            )}

            {/* 诊断与用药 — only if treatment_plan present */}
            {rec.treatment_plan && (
              <Card style={{ marginTop: 8 }}>
                <div style={{ padding: "12px 14px" }}>
                  <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 8 }}>
                    诊断与用药
                  </div>
                  {Array.isArray(rec.treatment_plan.medications) && rec.treatment_plan.medications.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      {rec.treatment_plan.medications.map((m, i) => (
                        <div key={i} style={{ fontSize: FONT.base, color: APP.text1, marginBottom: 4 }}>
                          • {m.name || ""}{m.dose ? ` · ${m.dose}` : ""}{m.frequency ? ` · ${m.frequency}` : ""}
                        </div>
                      ))}
                    </div>
                  )}
                  {rec.treatment_plan.follow_up && (
                    <SubField label="随访建议" value={rec.treatment_plan.follow_up} />
                  )}
                  {rec.treatment_plan.lifestyle && (
                    <SubField label="生活方式" value={rec.treatment_plan.lifestyle} />
                  )}
                </div>
              </Card>
            )}

            <div style={{ height: 32 }} />
          </>
        )}
      </div>
    </div>
  );
}

function SubField({ label, value }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ fontSize: FONT.sm, color: APP.text4 }}>{label}</div>
      <div style={{ fontSize: FONT.base, color: APP.text1, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
        {value}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Smoke-verify on `:8001`**

Navigate to a patient record (`/patient/records/:id`). Confirm sections render conditionally based on payload.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/patient/PatientRecordDetailPage.jsx
git commit -m "feat(patient-record-detail): real card-pattern subpage against actual PatientRecordDetailOut fields"
```

---

### Task 5.2: `PatientTaskDetailPage` real content

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientTaskDetailPage.jsx`

- [ ] **Step 1: Replace the file end-to-end**

```jsx
/**
 * @route /patient/tasks/:id
 * Patient task detail with complete/undo. Uses the new GET /api/patient/tasks/:id
 * endpoint (Phase 0). Fields: task_type, status (pending|completed|cancelled),
 * source_record_id (derived from task.record_id), completed_at.
 */
import { Button, Dialog, Ellipsis, NavBar, Tag } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { Card, LoadingCenter, EmptyState } from "../../components";
import {
  usePatientTaskDetail,
  useCompletePatientTask,
  useUncompletePatientTask,
} from "../../../lib/patientQueries";

const STATUS_LABEL = {
  pending:   { text: "待完成", color: "warning" },
  completed: { text: "已完成", color: "success" },
  cancelled: { text: "已取消", color: "default" },
};

function fmt(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
}

export default function PatientTaskDetailPage({ taskId }) {
  const navigate = useNavigate();
  const { data: task, isLoading, isError, refetch } = usePatientTaskDetail(taskId);
  const completeTask   = useCompletePatientTask();
  const uncompleteTask = useUncompletePatientTask();

  function handleComplete() {
    completeTask.mutate(Number(taskId));
  }
  function handleUncomplete() {
    Dialog.confirm({
      title: "撤销完成",
      content: "确定要撤销该任务的完成状态吗？",
      cancelText: "取消",
      confirmText: "撤销",
      onConfirm: () => uncompleteTask.mutate(Number(taskId)),
    });
  }

  const isOverdue = task?.due_at && task.status === "pending"
    && new Date(task.due_at).getTime() < Date.now();

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        任务详情
      </NavBar>
      <div style={scrollable}>
        {isLoading && <LoadingCenter />}
        {isError && (
          <EmptyState
            title="任务不存在或已删除"
            description="请回到任务列表"
            actionLabel="返回列表"
            onAction={() => navigate("/patient/tasks")}
          />
        )}
        {task && (
          <>
            {/* Header */}
            <Card style={{ marginTop: 8 }}>
              <div style={{ padding: "12px 14px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <Tag color={STATUS_LABEL[task.status]?.color || "default"}>
                    {STATUS_LABEL[task.status]?.text || task.status}
                  </Tag>
                </div>
                <div style={{ fontSize: FONT.lg, fontWeight: 700, color: APP.text1 }}>
                  {task.title}
                </div>
              </div>
            </Card>

            {/* 任务详情 */}
            {task.content && (
              <Card style={{ marginTop: 8 }}>
                <div style={{ padding: "12px 14px" }}>
                  <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 6 }}>
                    任务详情
                  </div>
                  <Ellipsis content={task.content} rows={10} expandText="展开" collapseText="收起"
                    style={{ fontSize: FONT.base, color: APP.text1, lineHeight: 1.6 }} />
                </div>
              </Card>
            )}

            {/* 时间 */}
            <Card style={{ marginTop: 8 }}>
              <div style={{ padding: "12px 14px" }}>
                <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 6 }}>
                  时间
                </div>
                {task.due_at && (
                  <div style={{ fontSize: FONT.base, color: isOverdue ? APP.danger : APP.text1, marginBottom: 4 }}>
                    截止: {fmt(task.due_at)}
                  </div>
                )}
                <div style={{ fontSize: FONT.base, color: APP.text1, marginBottom: 4 }}>
                  创建: {fmt(task.created_at)}
                </div>
                {task.status === "completed" && task.completed_at && (
                  <div style={{ fontSize: FONT.base, color: APP.text1 }}>
                    完成: {fmt(task.completed_at)}
                  </div>
                )}
              </div>
            </Card>

            {/* 来源 — only when source_record_id exists */}
            {task.source_record_id && (
              <Card style={{ marginTop: 8 }}>
                <div
                  onClick={() => navigate(`/patient/records/${task.source_record_id}`)}
                  style={{ padding: "12px 14px", cursor: "pointer" }}
                >
                  <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 4 }}>
                    来源
                  </div>
                  <div style={{ fontSize: FONT.base, color: APP.primary }}>
                    {task.task_type === "follow_up" ? "随访任务 · " : ""}关联病历 #{task.source_record_id}
                  </div>
                </div>
              </Card>
            )}

            {/* Action button */}
            <div style={{ margin: "24px 12px" }}>
              {task.status === "pending" && (
                <Button block color="primary" size="large" onClick={handleComplete}
                  loading={completeTask.isPending}>
                  标记完成
                </Button>
              )}
              {task.status === "completed" && (
                <Button block color="default" size="large" onClick={handleUncomplete}
                  loading={uncompleteTask.isPending}>
                  撤销完成
                </Button>
              )}
              {task.status === "cancelled" && (
                <div style={{ textAlign: "center", color: APP.text4, fontSize: FONT.sm }}>
                  此任务已取消
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Smoke-verify on `:8001`**

Navigate to a task → tap body → detail renders. Verify:
- 标记完成 / 撤销完成 / 已取消 branches by status
- 来源 card only when `source_record_id` is present
- Hard-refresh on the URL works (per-id endpoint, not cache-only)

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/patient/PatientTaskDetailPage.jsx
git commit -m "feat(patient-task-detail): real card-pattern subpage with complete/undo + per-id endpoint"
```

---

### Task 5.3: `PatientAboutSubpage` real content + `APP_VERSION` consolidation

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientAboutSubpage.jsx`
- Possibly create: `frontend/web/src/v2/version.js` (if not already centralized)
- Possibly modify: `frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx`

- [ ] **Step 1: Locate the existing `APP_VERSION` source**

```bash
grep -rn "APP_VERSION\|VITE_APP_VERSION\|version" frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx | head
```

Three possible outcomes from this grep:
- A. Already imported from a shared module → use that import in the patient page (skip Step 2).
- B. Hardcoded inline (e.g., `const APP_VERSION = "1.2.0"`) → execute Step 2 to extract.
- C. Reads `import.meta.env.VITE_APP_VERSION` directly → execute Step 2 with the env-var pattern.

- [ ] **Step 2: (conditional) Extract to `v2/version.js`**

If B or C, create `frontend/web/src/v2/version.js`:

```javascript
// Single source for the v2 app version. Used by doctor + patient about subpages.
// Set via Vite at build time (vite.config.js: define APP_VERSION) or fall back to literal.
export const APP_VERSION =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_APP_VERSION) || "1.2.0";

export const BUILD_HASH =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_BUILD_HASH) || null;
```

Update `doctor/settings/AboutSubpage.jsx` to import from `../../../version`. (Adjust relative path as needed.)

- [ ] **Step 3: Replace `PatientAboutSubpage.jsx` end-to-end**

```jsx
/**
 * @route /patient/profile/about
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import { APP, FONT, ICON } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { Card, TintedIconRow } from "../../components";
import { APP_VERSION, BUILD_HASH } from "../../version";

function SectionHeader({ title }) {
  return (
    <div style={{ padding: "16px 20px 8px", fontSize: FONT.sm, color: APP.text4, fontWeight: 500 }}>
      {title}
    </div>
  );
}

export default function PatientAboutSubpage() {
  const navigate = useNavigate();

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        关于
      </NavBar>
      <div style={scrollable}>
        <SectionHeader title="应用信息" />
        <Card>
          <div style={{ padding: "14px 16px" }}>
            <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>患者助手</div>
            <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 4 }}>
              版本 {APP_VERSION}{BUILD_HASH ? ` · ${BUILD_HASH}` : ""}
            </div>
          </div>
        </Card>

        <SectionHeader title="法律信息" />
        <Card>
          <TintedIconRow
            Icon={LockOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="隐私政策"
            onClick={() => navigate("/patient/profile/privacy")}
            isFirst
          />
          <TintedIconRow
            Icon={DescriptionOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="服务条款"
            onClick={() => window.open("https://example.com/terms", "_blank")}
          />
        </Card>
      </div>
    </div>
  );
}
```

(If your repo has a real terms-of-service URL, substitute it in.)

- [ ] **Step 4: Smoke-verify on `:8001`**

Navigate to `/patient/profile/about`. Confirm version displays correctly and 隐私政策 navigates to `/patient/profile/privacy`.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/patient/PatientAboutSubpage.jsx \
        $( [ -f frontend/web/src/v2/version.js ] && echo frontend/web/src/v2/version.js ) \
        $( git diff --name-only frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx | grep . )
git commit -m "feat(patient-about): real about subpage; consolidate APP_VERSION source"
```

---

### Task 5.4: Extract `PrivacyContent` + wire `PatientPrivacySubpage`

**Files:**
- Create: `frontend/web/src/v2/pages/PrivacyContent.jsx`
- Modify: `frontend/web/src/v2/pages/PrivacyPage.jsx`
- Modify: `frontend/web/src/v2/pages/patient/PatientPrivacySubpage.jsx`

- [ ] **Step 1: Extract `PrivacyContent`**

Read the body of `frontend/web/src/v2/pages/PrivacyPage.jsx`. Move the JSX *body* (everything between the outer page chrome and the closing wrapper) into a new file `frontend/web/src/v2/pages/PrivacyContent.jsx`:

```jsx
/**
 * PrivacyContent — body-only privacy policy content. Used by both:
 *   - the standalone /privacy route (PrivacyPage.jsx)
 *   - the patient profile subpage (/patient/profile/privacy)
 */
export default function PrivacyContent() {
  return (
    // ...moved JSX body here...
  );
}
```

- [ ] **Step 2: Update `PrivacyPage.jsx` to render `<PrivacyContent />`**

In `frontend/web/src/v2/pages/PrivacyPage.jsx`, replace the body JSX with:

```jsx
import PrivacyContent from "./PrivacyContent";

// inside the existing page wrapper (NavBar / pageContainer / scrollable):
<PrivacyContent />
```

- [ ] **Step 3: Replace `PatientPrivacySubpage.jsx`**

```jsx
/**
 * @route /patient/profile/privacy
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import PrivacyContent from "../PrivacyContent";

export default function PatientPrivacySubpage() {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        隐私政策
      </NavBar>
      <div style={scrollable}>
        <PrivacyContent />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Smoke-verify on `:8001`**

Navigate to `/privacy` (signup flow) and `/patient/profile/privacy` (patient subpage). Both should render identical body content.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/PrivacyContent.jsx frontend/web/src/v2/pages/PrivacyPage.jsx frontend/web/src/v2/pages/patient/PatientPrivacySubpage.jsx
git commit -m "refactor(privacy): extract PrivacyContent shared between standalone route and patient subpage"
```

---

### Task 5.5: New E2E specs `25 / 26 / 27`

**Files:**
- Create: `frontend/web/tests/e2e/25-patient-record-detail.spec.ts`
- Create: `frontend/web/tests/e2e/26-patient-task-detail.spec.ts`
- Create: `frontend/web/tests/e2e/27-patient-my-subpages.spec.ts`

Pattern after the existing `22-patient-records.spec.ts` and `24-patient-shell.spec.ts` for fixtures and login helpers.

- [ ] **Step 1: Create `25-patient-record-detail.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";
import { loginAsTestPatient } from "./pages/patient-helpers"; // adjust to your existing helpers

test.describe("Patient record detail", () => {
  test("list → detail → back round-trip", async ({ page }) => {
    await loginAsTestPatient(page);
    await page.goto("/patient/records");
    // Tap the first record card
    const firstRecord = page.locator('[data-testid="patient-record-row"]').first();
    await expect(firstRecord).toBeVisible();
    await firstRecord.click();
    await expect(page).toHaveURL(/\/patient\/records\/\d+/);
    // Detail header card present
    await expect(page.getByText("病历详情")).toBeVisible();
    // Back returns to list
    await page.goBack();
    await expect(page).toHaveURL("/patient/records");
  });

  test("conditional 既往史 card omitted when all four sub-fields empty", async ({ page }) => {
    // Requires a seeded record with empty past/allergy/personal/family. If the
    // test fixture set doesn't include such a record, mark this test.skip and
    // file a follow-up to add a seeded fixture.
    test.skip(true, "Requires fixture record with empty history fields — TODO seed");
  });
});
```

- [ ] **Step 2: Create `26-patient-task-detail.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";
import { loginAsTestPatient } from "./pages/patient-helpers";

test.describe("Patient task detail", () => {
  test("body-tap → detail → 标记完成 → list refresh", async ({ page }) => {
    await loginAsTestPatient(page);
    await page.goto("/patient/tasks");
    const firstTask = page.locator('[data-testid="patient-task-row"]').first();
    await expect(firstTask).toBeVisible();
    // Click the body (NOT the prefix circle), navigates to detail
    await firstTask.getByText(/.+/).first().click();
    await expect(page).toHaveURL(/\/patient\/tasks\/\d+/);
    // 标记完成 button visible for pending tasks
    const completeBtn = page.getByText("标记完成", { exact: true });
    if (await completeBtn.isVisible()) {
      await completeBtn.click();
      // List refresh — back to /patient/tasks
      await expect(page).toHaveURL("/patient/tasks");
    }
  });

  test("撤销完成 with confirm dialog", async ({ page }) => {
    await loginAsTestPatient(page);
    // Find a completed task — fixture may not have one; skip if not
    await page.goto("/patient/tasks");
    const completedRow = page.locator('[data-testid="patient-task-row"]')
      .filter({ has: page.getByLabel("撤销完成") }).first();
    if (!(await completedRow.isVisible())) {
      test.skip(true, "No completed task in fixture — seed required");
      return;
    }
    await completedRow.getByText(/.+/).first().click();
    await page.getByText("撤销完成", { exact: true }).click();
    // Confirm dialog
    await expect(page.getByText("确定要撤销该任务的完成状态吗？")).toBeVisible();
    await page.getByText("撤销", { exact: true }).click();
    await expect(page).toHaveURL("/patient/tasks");
  });

  test("deep-link hard-refresh works (per-id endpoint)", async ({ page }) => {
    await loginAsTestPatient(page);
    await page.goto("/patient/tasks");
    const firstTask = page.locator('[data-testid="patient-task-row"]').first();
    await firstTask.getByText(/.+/).first().click();
    const url = page.url();
    // Reload the detail URL directly — must NOT show "任务不存在"
    await page.reload();
    await expect(page.getByText("任务不存在或已删除")).not.toBeVisible();
  });
});
```

- [ ] **Step 3: Create `27-patient-my-subpages.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";
import { loginAsTestPatient } from "./pages/patient-helpers";

test.describe("Patient MyPage subpages", () => {
  test("MyPage → 关于 → back", async ({ page }) => {
    await loginAsTestPatient(page);
    await page.goto("/patient/profile");
    await page.getByText("关于", { exact: true }).click();
    await expect(page).toHaveURL("/patient/profile/about");
    await expect(page.getByText("患者助手")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL("/patient/profile");
  });

  test("MyPage → 隐私政策 → back", async ({ page }) => {
    await loginAsTestPatient(page);
    await page.goto("/patient/profile");
    await page.getByText("隐私政策", { exact: true }).click();
    await expect(page).toHaveURL("/patient/profile/privacy");
    await page.goBack();
    await expect(page).toHaveURL("/patient/profile");
  });

  test("font Popup selects 特大 and persists", async ({ page }) => {
    await loginAsTestPatient(page);
    await page.goto("/patient/profile");
    await page.getByText("字体大小", { exact: true }).click();
    await page.getByText("特大", { exact: true }).click();
    await page.reload();
    await page.getByText("字体大小", { exact: true }).click();
    await expect(page.getByRole("radio", { name: "特大" })).toBeChecked();
  });
});
```

- [ ] **Step 4: Add `data-testid`s to enable the new specs**

In `RecordsTab.jsx` (Task 4.3) and `TasksTab.jsx` (Task 4.4), add `data-testid="patient-record-row"` and `data-testid="patient-task-row"` to the outer Card wrapper of each row. (Edit these files now if you didn't add them earlier.)

- [ ] **Step 5: Run the new specs and commit**

```bash
bash scripts/validate-v2-e2e.sh \
  frontend/web/tests/e2e/25-patient-record-detail.spec.ts \
  frontend/web/tests/e2e/26-patient-task-detail.spec.ts \
  frontend/web/tests/e2e/27-patient-my-subpages.spec.ts
```

Expected: all PASS (or expected `.skip` for fixture-gated cases).

```bash
git add frontend/web/tests/e2e/25-patient-record-detail.spec.ts \
        frontend/web/tests/e2e/26-patient-task-detail.spec.ts \
        frontend/web/tests/e2e/27-patient-my-subpages.spec.ts \
        frontend/web/src/v2/pages/patient/RecordsTab.jsx \
        frontend/web/src/v2/pages/patient/TasksTab.jsx
git commit -m "test(patient-e2e): add specs 25/26/27 (record detail, task detail, my subpages)"
```

---

### Task 5.6: Final cleanup — remove `SectionHeader` alias + add lint-ui guard

**Files:**
- Modify: `frontend/web/src/v2/components/index.js` (remove the alias)
- Modify: `frontend/web/src/v2/pages/doctor/ReviewPage.jsx` (drop the local `as SectionHeader` alias)
- Modify: `scripts/lint-ui.sh` (add the grep guard)

- [ ] **Step 1: Verify zero remaining external `SectionHeader` imports**

```bash
grep -rn "SectionHeader" frontend/web/src --include="*.jsx" --include="*.js" | grep -v "v2/components/index.js" | grep -v "// local SectionHeader"
```

Expected: only matches inside files that define a *local* `SectionHeader` function (doctor SettingsPage, MyAIPage, PatientsPage, TemplateSubpage, AboutSubpage, patient MyPage). No imports of `SectionHeader` from `v2/components`.

If any remain, sweep them to use `ListSectionDivider` directly before proceeding.

- [ ] **Step 2: Sweep both aliased consumers**

In `frontend/web/src/v2/pages/doctor/ReviewPage.jsx:29`, replace:

```javascript
import { ActionFooter, ListSectionDivider as SectionHeader, CitationPopup } from "../../components";
```

with:

```javascript
import { ActionFooter, ListSectionDivider, CitationPopup } from "../../components";
```

In `frontend/web/src/v2/pages/patient/TasksTab.jsx:17`, replace:

```javascript
import { LoadingCenter, EmptyState, ListSectionDivider as SectionHeader } from "../../components";
```

with:

```javascript
import { LoadingCenter, EmptyState, ListSectionDivider } from "../../components";
```

Then global-rename `SectionHeader` → `ListSectionDivider` in the JSX usages within BOTH files. Also update the internal `function SectionHeader(...)` declaration in `frontend/web/src/v2/components/ListSectionDivider.jsx` to `function ListSectionDivider(...)` (the rename was deferred from Task 2.1 to keep the alias chain intact during Phase 2-4).

- [ ] **Step 3: Remove the alias from the barrel**

In `frontend/web/src/v2/components/index.js`, delete the line:

```javascript
export { default as SectionHeader } from "./ListSectionDivider"; // DEPRECATED — removed in Phase 5 (Task 5.6)
```

- [ ] **Step 4: Add the lint-ui guard**

In `scripts/lint-ui.sh`, append a new check (placement: with the other named-import checks):

```bash
# Guard: no new imports of SectionHeader from v2/components — use ListSectionDivider.
echo "Checking: no imports of removed SectionHeader from v2/components..."
SH_HITS=$(grep -rEn "from\s+['\"][^'\"]*v2/components['\"]" frontend/web/src \
  --include="*.jsx" --include="*.js" \
  | grep -E "\\bSectionHeader\\b" \
  | grep -v "// lint-ui-ignore" || true)
if [ -n "$SH_HITS" ]; then
  echo "❌ Found imports of deprecated SectionHeader from v2/components — use ListSectionDivider:"
  echo "$SH_HITS"
  EXIT=1
fi
```

Make sure the script's `EXIT=1` pattern matches existing checks (the script returns `$EXIT` at the end).

- [ ] **Step 5: Run lint-ui + full E2E gate, then commit**

```bash
bash scripts/lint-ui.sh
```

Expected: PASS (no `SectionHeader` import violations).

Run the full patient E2E gate to make sure nothing regressed:

```bash
bash scripts/validate-v2-e2e.sh \
  frontend/web/tests/e2e/20-patient-auth.spec.ts \
  frontend/web/tests/e2e/21-patient-chat.spec.ts \
  frontend/web/tests/e2e/22-patient-records.spec.ts \
  frontend/web/tests/e2e/23-patient-tasks.spec.ts \
  frontend/web/tests/e2e/24-patient-shell.spec.ts \
  frontend/web/tests/e2e/25-patient-record-detail.spec.ts \
  frontend/web/tests/e2e/26-patient-task-detail.spec.ts \
  frontend/web/tests/e2e/27-patient-my-subpages.spec.ts
```

Expected: all PASS.

```bash
git add frontend/web/src/v2/components/index.js \
        frontend/web/src/v2/pages/doctor/ReviewPage.jsx \
        scripts/lint-ui.sh
git commit -m "chore(v2-components): remove SectionHeader alias + lint-ui guard against re-introduction"
```

---

## Self-Review (executed inline before handoff)

**Spec coverage:**
- Section 0 (backend) → Tasks 0.1–0.3 ✓
- Section 1 (patient token store) → Tasks 1.1–1.2 ✓
- Section 2 (shared primitives + barrel rename) → Tasks 2.1–2.4 ✓
- Section 3 (data layer) → Tasks 3.1–3.3 ✓
- Section 4 (visual rewrites) → Tasks 4.1–4.6 ✓
- Section 5 (real subpage content) → Tasks 5.1–5.4 ✓
- Tests + cleanup → Tasks 5.5–5.6 ✓

**Placeholder scan:** all code blocks contain real code; no `TODO` / `TBD` / "implement appropriately". The two `test.skip(...)` calls in Task 5.5 are real fixture-gated skips with concrete reasons, not placeholders.

**Type/name consistency:** `loginWithIdentity` / `mergeProfile` / `clearAuth` are used consistently across Phase 1 (store creation), Phase 1.2 (PatientPage migration), and Phase 3.3 (PatientPage shell `useEffect`). `usePatientStore` import path consistent. `PK.patientTaskDetail(id)` used in both Task 3.2 (definition) and 5.2 (consumption).

---

**Plan complete and saved to** `docs/superpowers/plans/2026-04-24-patient-app-doctor-ui-parity.md`.

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Aligns with the project memory rule "Always use subagent-driven development". Uses `superpowers:subagent-driven-development`.

2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
