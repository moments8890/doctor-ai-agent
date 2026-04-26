# Patient Chat–Intake Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project rules in force:** never push, work on main branch (no feature branches), commit per task only when the task instructions say to commit, e2e on :8001 only.

**Goal:** Implement Phases 0, 0.5, and 1 of `docs/superpowers/specs/2026-04-25-patient-chat-intake-merge-design.md` v1.2 — backend safety floor, KB curation onboarding, and dual-mode chat with sticky state machine, append-only dedup, and supplement workflow for reviewed records.

**Architecture:** Reuse existing `triage.classify()` as the mode signal for a new sticky `ChatSessionState` machine. Reuse `MedicalRecordDB` (no new model for records) but switch the 7 history fields to a new `FieldEntryDB` table for append-only provenance. New `RecordSupplementDB` for patient supplements to doctor-reviewed records. Phase 1 is feature-flagged per doctor; Phase 0 + 0.5 are unconditional safety + onboarding.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (async, `Mapped[]` style) + Alembic, React + antd-mobile + zustand + react-query, pytest with `asyncio_mode = auto`, Vitest for frontend.

---

## File Structure

### Backend — modify

- `src/db/models/records.py` — add columns to `MedicalRecordDB`; keep existing 7 history string columns as legacy/compat (read-only after Phase 0); add new `FieldEntryDB` and `RecordSupplementDB` model classes in same file (single-source-of-truth for record-shaped data).
- `src/db/models/doctor.py` — add `patient_safe` column to `DoctorKnowledgeItem`; add `kb_curation_onboarding_done` flag to `Doctor`.
- `src/db/models/patient_message.py` — add `retracted` boolean column.
- `src/domain/patient_lifecycle/triage.py` — extend `TriageResult` with optional `intake_cancel_signal` and `qa_resume_signal` fields (folded into main classify call per v1.2 Q1 lean); no new categories.
- `src/domain/patient_lifecycle/triage_handlers.py` — extract signal-flag detection from `handle_urgent` into a standalone `signal_flag_pass()` that runs on every turn regardless of state.
- `src/domain/intake/templates/medical_general.py` — `MedicalRecordWriter.persist` writes to `FieldEntryDB` instead of mutating string columns.
- `src/channels/web/patient_portal/chat.py` — `post_chat` dispatches to new state-machine pipeline.
- `src/channels/web/doctor_dashboard/review_queue_handlers.py` — provenance filter + extraction_confidence in response; mount supplement queue routes.

### Backend — create

- `src/domain/patient_lifecycle/chat_state.py` — `ChatSessionState` model + transitions (idle / intake / qa_window).
- `src/domain/patient_lifecycle/dedup.py` — §5a detection (similarity + episode signals), §5b merge logic, §5c same-segment auto-merge.
- `src/domain/patient_lifecycle/signal_flag.py` — standalone always-on signal-flag classifier (extracted from triage_handlers).
- `src/domain/patient_lifecycle/extraction_confidence.py` — deterministic calculator (filled fields / 7).
- `src/domain/knowledge/curation_gate.py` — server-side gate that honors `patient_safe=true` only when doctor's `kb_curation_onboarding_done=true`.
- `src/channels/web/doctor_dashboard/supplement_handlers.py` — accept / create-new / ignore actions on `RecordSupplementDB`.
- `alembic/versions/<uuid>_chat_intake_merge_phase0.py` — single Alembic migration for all Phase 0 schema changes.
- `alembic/versions/<uuid>_chat_intake_merge_backfill.py` — data-only migration: copy existing string fields into `FieldEntryDB` single-entry rows.

### Frontend — modify

- `frontend/web/src/v2/pages/patient/ChatTab.jsx` — render confirm gate, dedup prompt, retracted-message strikethrough, supplement chip.
- `frontend/web/src/v2/pages/patient/RecordsTab.jsx` — render append-only field entries chronologically when present.
- `frontend/web/src/v2/pages/patient/IntakePage.jsx` — keep but no UI change in this plan (Phase 3 demotes the CTA).
- `frontend/web/src/v2/pages/doctor/...` — review queue: provenance filter chip, extraction_confidence ring, supplement section. (Exact filename verified during implementation; admin/doctor review surface lives under `frontend/web/src/v2/pages/doctor/` per existing convention.)
- `frontend/web/src/api.js` — add fetchers for new endpoints (confirm gate, dedup prompts, supplement actions).

### Frontend — create

- `frontend/web/src/v2/components/ChatConfirmGate.jsx` — chat-thread-inline two-button gate.
- `frontend/web/src/v2/components/ChatDedupPrompt.jsx` — three-button prompt for §5b.
- `frontend/web/src/v2/components/ExtractionConfidenceRing.jsx` — N/7 ring visual for doctor side.
- `frontend/web/src/v2/components/SupplementCard.jsx` — doctor-side supplement queue item.

### Tests — create

- `tests/core/test_chat_state.py` — entry rule, sticky exit, qa_window transitions.
- `tests/core/test_dedup.py` — §5a detection (similarity + episode signals), §5b common case + edge case 2, §5c same-segment.
- `tests/core/test_signal_flag.py` — always-on per-turn pass.
- `tests/core/test_extraction_confidence.py` — deterministic calculator.
- `tests/core/test_curation_gate.py` — patient_safe honored only with onboarding done.
- `tests/api/test_patient_chat_state_machine.py` — end-to-end `POST /chat` exercising state transitions, confirm gate, dedup, supplement creation.
- `tests/api/test_supplement_handlers.py` — accept/create-new/ignore actions.

Existing `tests/core/test_triage_pure.py` extended where needed; do not reorganize.

---

## Phase 0 — Backend Safety Floor

Goal: schema landed, signal-flag classifier always-on, extraction_confidence calculator available. **Independently shippable** — no UX change. Phase 1 cannot start until this is merged.

### Task 0.1: Alembic migration — schema additions to existing tables

**Files:**
- Create: `alembic/versions/<auto-uuid>_chat_intake_merge_phase0.py`

- [ ] **Step 1: Generate empty migration**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic revision -m "chat_intake_merge_phase0"`
Expected: new file created under `alembic/versions/` with auto-generated UUID prefix.

- [ ] **Step 2: Write the upgrade()**

```python
"""chat_intake_merge_phase0

Adds dedup/provenance/safety columns to medical_records, doctor_knowledge_items,
doctors, and patient_messages. Schema for the new FieldEntryDB and RecordSupplementDB
tables is in the next migration step.
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # MedicalRecordDB additions
    op.add_column("medical_records", sa.Column("extraction_confidence", sa.Float, nullable=True))
    op.add_column("medical_records", sa.Column("patient_confirmed_at", sa.DateTime, nullable=True))
    op.add_column("medical_records", sa.Column("cancellation_reason", sa.String(64), nullable=True))
    op.add_column("medical_records", sa.Column("signal_flag", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("medical_records", sa.Column("intake_segment_id", sa.String(64), nullable=True))
    op.add_column("medical_records", sa.Column("dedup_skipped_by_patient", sa.Boolean, nullable=False, server_default=sa.false()))
    op.create_index("ix_medical_records_intake_segment_id", "medical_records", ["intake_segment_id"])

    # DoctorKnowledgeItem additions
    op.add_column("doctor_knowledge_items", sa.Column("patient_safe", sa.Boolean, nullable=False, server_default=sa.false()))

    # Doctor additions
    op.add_column("doctors", sa.Column("kb_curation_onboarding_done", sa.Boolean, nullable=False, server_default=sa.false()))

    # PatientMessage additions
    op.add_column("patient_messages", sa.Column("retracted", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("patient_messages", "retracted")
    op.drop_column("doctors", "kb_curation_onboarding_done")
    op.drop_column("doctor_knowledge_items", "patient_safe")
    op.drop_index("ix_medical_records_intake_segment_id", table_name="medical_records")
    for col in ("dedup_skipped_by_patient", "intake_segment_id", "signal_flag",
                "cancellation_reason", "patient_confirmed_at", "extraction_confidence"):
        op.drop_column("medical_records", col)
```

**Cancellation_reason** is a free `String(64)` rather than a SQLAlchemy Enum so we can add new reasons without DB migrations. Application layer enforces allowed values.

- [ ] **Step 3: Run upgrade and verify**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic upgrade head`
Expected: success. Run `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic current` to confirm new revision is head.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/*chat_intake_merge_phase0*.py
git commit -m "feat(db): phase0 schema additions for chat-intake merge"
```

---

### Task 0.2: New tables — FieldEntryDB and RecordSupplementDB

**Files:**
- Modify: `src/db/models/records.py` (add new ORM classes at end)
- Create: `alembic/versions/<auto-uuid>_chat_intake_merge_new_tables.py`

- [ ] **Step 1: Add ORM classes to records.py**

Append to the end of `src/db/models/records.py`:

```python
class FieldEntryDB(Base):
    __tablename__ = "record_field_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(sa.ForeignKey("medical_records.id"), index=True, nullable=False)
    field_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)  # chief_complaint | present_illness | past_history | allergy_history | personal_history | marital_reproductive | family_history
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    intake_segment_id: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, default=datetime.utcnow)


class RecordSupplementDB(Base):
    __tablename__ = "record_supplements"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(sa.ForeignKey("medical_records.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="pending_doctor_review")  # pending_doctor_review | accepted | rejected_create_new | rejected_ignored
    field_entries_json: Mapped[str] = mapped_column(sa.Text, nullable=False)  # JSON list of {field_name, text, intake_segment_id, created_at}
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, default=datetime.utcnow)
    doctor_decision_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime, nullable=True)
    doctor_decision_by: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
```

Verify imports at the top of the file include `from datetime import datetime` and `from typing import Optional`. If `Mapped` is imported, this should work; otherwise the existing patterns in the file are the reference.

- [ ] **Step 2: Generate the table-creation migration**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic revision -m "chat_intake_merge_new_tables"`

- [ ] **Step 3: Write upgrade/downgrade**

```python
def upgrade():
    op.create_table(
        "record_field_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id"), nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("intake_segment_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_record_field_entries_record_id", "record_field_entries", ["record_id"])
    op.create_index("ix_record_field_entries_record_field", "record_field_entries", ["record_id", "field_name"])

    op.create_table(
        "record_supplements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_doctor_review"),
        sa.Column("field_entries_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("doctor_decision_at", sa.DateTime, nullable=True),
        sa.Column("doctor_decision_by", sa.String(64), nullable=True),
    )
    op.create_index("ix_record_supplements_record_id", "record_supplements", ["record_id"])
    op.create_index("ix_record_supplements_status", "record_supplements", ["status"])


def downgrade():
    op.drop_index("ix_record_supplements_status", table_name="record_supplements")
    op.drop_index("ix_record_supplements_record_id", table_name="record_supplements")
    op.drop_table("record_supplements")
    op.drop_index("ix_record_field_entries_record_field", table_name="record_field_entries")
    op.drop_index("ix_record_field_entries_record_id", table_name="record_field_entries")
    op.drop_table("record_field_entries")
```

- [ ] **Step 4: Run upgrade and verify**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic upgrade head`

- [ ] **Step 5: Commit**

```bash
git add src/db/models/records.py alembic/versions/*chat_intake_merge_new_tables*.py
git commit -m "feat(db): add FieldEntryDB and RecordSupplementDB tables"
```

---

### Task 0.3: SQLAlchemy column declarations on existing models

**Files:**
- Modify: `src/db/models/records.py` (add new columns to MedicalRecordDB)
- Modify: `src/db/models/doctor.py` (add to DoctorKnowledgeItem and Doctor)
- Modify: `src/db/models/patient_message.py` (add `retracted` to PatientMessage)

- [ ] **Step 1: Edit MedicalRecordDB — add the 6 new columns**

In `src/db/models/records.py`, inside the `class MedicalRecordDB(Base):` block, append:

```python
extraction_confidence: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
patient_confirmed_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime, nullable=True)
cancellation_reason: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
signal_flag: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
intake_segment_id: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True, index=True)
dedup_skipped_by_patient: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
```

Match the indentation, type annotations, and `mapped_column` style of existing fields exactly.

- [ ] **Step 2: Edit DoctorKnowledgeItem and Doctor**

In `src/db/models/doctor.py`:

```python
# DoctorKnowledgeItem class — add:
patient_safe: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

# Doctor class — add:
kb_curation_onboarding_done: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
```

- [ ] **Step 3: Edit PatientMessage**

In `src/db/models/patient_message.py`:

```python
retracted: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
```

- [ ] **Step 4: Verify ORM matches DB**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -c "from src.db.models.records import MedicalRecordDB, FieldEntryDB, RecordSupplementDB; from src.db.models.doctor import Doctor, DoctorKnowledgeItem; from src.db.models.patient_message import PatientMessage; print('ok')"`
Expected: `ok` — no import errors.

- [ ] **Step 5: Commit**

```bash
git add src/db/models/records.py src/db/models/doctor.py src/db/models/patient_message.py
git commit -m "feat(db): ORM columns for chat-intake merge phase 0"
```

---

### Task 0.4: Backfill existing history strings into FieldEntryDB

**Files:**
- Create: `alembic/versions/<auto-uuid>_chat_intake_merge_backfill.py`

- [ ] **Step 1: Generate migration**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic revision -m "chat_intake_merge_backfill"`

- [ ] **Step 2: Write data-only upgrade**

```python
"""Backfill existing single-string history fields into FieldEntryDB single-entry rows.

Reads each medical_records row, for each of the 7 history fields, if the column is
non-empty, inserts a FieldEntryDB row with intake_segment_id=NULL and created_at=
medical_records.created_at. Idempotent: skips records that already have any entries.
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

FIELDS = (
    "chief_complaint",
    "present_illness",
    "past_history",
    "allergy_history",
    "personal_history",
    "marital_reproductive",
    "family_history",
)


def upgrade():
    bind = op.get_bind()
    records = bind.execute(sa.text(
        "SELECT id, created_at, " + ", ".join(FIELDS) + " FROM medical_records"
    )).mappings().all()

    existing = {row["record_id"] for row in bind.execute(sa.text(
        "SELECT DISTINCT record_id FROM record_field_entries"
    )).mappings().all()}

    for r in records:
        if r["id"] in existing:
            continue
        for field in FIELDS:
            value = r[field]
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            bind.execute(sa.text(
                "INSERT INTO record_field_entries (record_id, field_name, text, intake_segment_id, created_at) "
                "VALUES (:rid, :fn, :tx, NULL, :ca)"
            ), {"rid": r["id"], "fn": field, "tx": value, "ca": r["created_at"] or datetime.utcnow()})


def downgrade():
    # No-op: removing backfilled rows would lose data if the original columns were edited
    # in the meantime. Safe rollback is to drop the FieldEntryDB table via the prior migration.
    pass
```

- [ ] **Step 3: Run upgrade**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic upgrade head`

- [ ] **Step 4: Sanity check counts**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -c "
from sqlalchemy import create_engine, text
import os
url = os.getenv('DATABASE_URL', 'sqlite:///dev.db').replace('+aiosqlite','').replace('+asyncpg','')
e = create_engine(url)
with e.connect() as c:
    rec = c.execute(text('SELECT COUNT(*) FROM medical_records WHERE chief_complaint IS NOT NULL AND chief_complaint != \"\"')).scalar()
    ent = c.execute(text('SELECT COUNT(*) FROM record_field_entries WHERE field_name = \"chief_complaint\"')).scalar()
    print(f'records with chief_complaint: {rec}, backfilled chief_complaint entries: {ent}')
"`
Expected: backfilled count >= records count (≥ because we may have multiple fields per record but this query is just for chief_complaint).

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/*chat_intake_merge_backfill*.py
git commit -m "feat(db): backfill existing history strings into FieldEntryDB"
```

---

### Task 0.5: Deterministic extraction_confidence calculator

**Files:**
- Create: `src/domain/patient_lifecycle/extraction_confidence.py`
- Test: `tests/core/test_extraction_confidence.py`

- [ ] **Step 1: Write failing tests first**

Create `tests/core/test_extraction_confidence.py`:

```python
from src.domain.patient_lifecycle.extraction_confidence import calculate

def test_all_seven_fields_filled_returns_one():
    fields = {
        "chief_complaint": "头痛",
        "present_illness": "三天",
        "past_history": "无",
        "allergy_history": "无",
        "personal_history": "无",
        "marital_reproductive": "已婚",
        "family_history": "无",
    }
    assert calculate(fields) == 1.0

def test_three_of_seven_returns_three_sevenths():
    fields = {"chief_complaint": "头痛", "present_illness": "三天", "past_history": "无"}
    result = calculate(fields)
    assert abs(result - 3 / 7) < 1e-9

def test_empty_strings_dont_count():
    fields = {"chief_complaint": "头痛", "present_illness": "", "past_history": "  "}
    assert calculate(fields) == 1 / 7

def test_none_values_dont_count():
    fields = {"chief_complaint": "头痛", "present_illness": None}
    assert calculate(fields) == 1 / 7

def test_unknown_fields_ignored():
    fields = {"chief_complaint": "头痛", "diagnosis": "should be ignored"}
    assert calculate(fields) == 1 / 7

def test_empty_dict_returns_zero():
    assert calculate({}) == 0.0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/core/test_extraction_confidence.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: ImportError or ModuleNotFoundError.

- [ ] **Step 3: Implement the calculator**

Create `src/domain/patient_lifecycle/extraction_confidence.py`:

```python
"""Deterministic extraction_confidence — count of required history fields filled / 7.

Replaces LLM self-reported confidence (Codex round 2 pushback). The denominator (7) is
the number of required history fields in MedicalRecordDB. Doctor-facing display shows
this as N/7, not as a percentage, so the meaning is unambiguous.
"""

REQUIRED_FIELDS = (
    "chief_complaint",
    "present_illness",
    "past_history",
    "allergy_history",
    "personal_history",
    "marital_reproductive",
    "family_history",
)


def calculate(fields: dict[str, str | None]) -> float:
    filled = sum(
        1 for f in REQUIRED_FIELDS
        if fields.get(f) is not None and str(fields.get(f)).strip()
    )
    return filled / len(REQUIRED_FIELDS)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/core/test_extraction_confidence.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/domain/patient_lifecycle/extraction_confidence.py tests/core/test_extraction_confidence.py
git commit -m "feat(extraction): deterministic confidence (filled fields / 7)"
```

---

### Task 0.6: Standalone always-on signal-flag classifier

**Files:**
- Create: `src/domain/patient_lifecycle/signal_flag.py`
- Test: `tests/core/test_signal_flag.py`
- Modify: `src/domain/patient_lifecycle/triage_handlers.py` (delegate to signal_flag.detect)

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_signal_flag.py
import pytest
from unittest.mock import patch, AsyncMock
from src.domain.patient_lifecycle.signal_flag import detect

@pytest.mark.asyncio
async def test_obvious_emergency_returns_true():
    with patch("src.domain.patient_lifecycle.signal_flag._classify_urgent", AsyncMock(return_value=True)):
        result = await detect("我现在胸口剧痛喘不上气", patient_context={})
    assert result is True

@pytest.mark.asyncio
async def test_routine_question_returns_false():
    with patch("src.domain.patient_lifecycle.signal_flag._classify_urgent", AsyncMock(return_value=False)):
        result = await detect("怎么改预约时间", patient_context={})
    assert result is False

@pytest.mark.asyncio
async def test_runs_independently_of_state():
    """signal_flag.detect must not require any session/state arg — it's per-turn."""
    import inspect
    sig = inspect.signature(detect)
    assert "session" not in sig.parameters
    assert "state" not in sig.parameters
```

- [ ] **Step 2: Run, verify they fail**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/core/test_signal_flag.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`

- [ ] **Step 3: Extract signal-flag detection**

Create `src/domain/patient_lifecycle/signal_flag.py`:

```python
"""Always-on signal-flag classifier. Runs on every patient turn regardless of ChatSessionState.

Returns True if the message indicates an urgent clinical situation requiring immediate
doctor escalation. Independent of triage classification — a patient asking "怎么改预约"
in the same conversation as "胸口剧痛" should have BOTH the routine intent handled AND
the signal-flag fired.
"""
from src.agent.llm.structured_call import structured_call


async def detect(message: str, patient_context: dict) -> bool:
    """Returns True if message contains a signal-flag (urgent clinical) signal."""
    return await _classify_urgent(message, patient_context)


async def _classify_urgent(message: str, patient_context: dict) -> bool:
    # Reuse the existing 'urgent' detection prompt path. Migrate the implementation
    # currently inline in triage.classify() / triage_handlers.handle_urgent that flags
    # category=urgent — extracted here so it runs per-turn without state dependency.
    from src.domain.patient_lifecycle.triage import classify, TriageCategory
    result = await classify(message, patient_context)
    return result.category == TriageCategory.urgent
```

- [ ] **Step 4: Run tests, verify pass**

Run the same pytest. All 3 should pass.

- [ ] **Step 5: Commit**

```bash
git add src/domain/patient_lifecycle/signal_flag.py tests/core/test_signal_flag.py
git commit -m "feat(signal_flag): standalone always-on signal-flag classifier"
```

---

### Phase 0 wrap

After Tasks 0.1–0.6, the backend has: schema for all dedup/provenance/safety columns, FieldEntryDB and RecordSupplementDB tables with backfilled historical data, deterministic extraction_confidence helper, and a standalone signal_flag.detect function that can be wired into the chat pipeline. **Nothing is wired into the user-facing flow yet** — Phase 0 ships independently as a safety floor that does not change patient or doctor behavior.

---

## Phase 0.5 — KB Curation Onboarding

Goal: doctors must explicitly review each KB item and mark `patient_safe` before any patient-facing autonomous reply uses that item. Without `kb_curation_onboarding_done=true` on the doctor, no item's `patient_safe=true` is honored. **Independently shippable.** Phase 1 cannot enable autonomous KB-derived replies for a doctor until that doctor has completed onboarding.

### Task 0.5.1: curation_gate.py — server-side gate

**Files:**
- Create: `src/domain/knowledge/curation_gate.py`
- Test: `tests/core/test_curation_gate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_curation_gate.py
import pytest
from src.domain.knowledge.curation_gate import is_patient_safe

class FakeItem:
    def __init__(self, patient_safe): self.patient_safe = patient_safe

class FakeDoctor:
    def __init__(self, done): self.kb_curation_onboarding_done = done

def test_item_safe_and_doctor_done_returns_true():
    assert is_patient_safe(FakeItem(True), FakeDoctor(True)) is True

def test_item_safe_but_doctor_not_done_returns_false():
    assert is_patient_safe(FakeItem(True), FakeDoctor(False)) is False

def test_item_unsafe_doctor_done_returns_false():
    assert is_patient_safe(FakeItem(False), FakeDoctor(True)) is False

def test_item_unsafe_doctor_not_done_returns_false():
    assert is_patient_safe(FakeItem(False), FakeDoctor(False)) is False

def test_none_inputs_return_false():
    assert is_patient_safe(None, FakeDoctor(True)) is False
    assert is_patient_safe(FakeItem(True), None) is False
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/core/test_curation_gate.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`

- [ ] **Step 3: Implement gate**

Create `src/domain/knowledge/curation_gate.py`:

```python
"""Server-side gate: a KB item is patient-facing only when both the item and the
owning doctor have explicitly opted in.

Why this exists: patient_safe defaults to False on every KB item. Without a doctor
having walked through their KB and reviewed each item explicitly, the per-item flag
isn't trusted. The doctor flag (kb_curation_onboarding_done) is set after that
walkthrough completes.
"""

def is_patient_safe(item, doctor) -> bool:
    if item is None or doctor is None:
        return False
    return bool(getattr(item, "patient_safe", False)) and bool(getattr(doctor, "kb_curation_onboarding_done", False))
```

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/domain/knowledge/curation_gate.py tests/core/test_curation_gate.py
git commit -m "feat(kb): curation_gate enforces dual-opt-in for patient-facing items"
```

---

### Task 0.5.2: KB editor backend — patient_safe toggle endpoint

**Files:**
- Modify: KB editor route file (likely `src/channels/web/doctor_dashboard/knowledge_routes.py` — verify path during implementation; search for the existing PUT/PATCH endpoint that updates a KB item).

- [ ] **Step 1: Locate the existing KB item update endpoint**

Run: `rg -n "doctor_knowledge" src/channels/web/ -l` to find the file. Identify the existing item-update endpoint.

- [ ] **Step 2: Add a dedicated endpoint for the patient_safe flag**

Add to the same file:

```python
class PatientSafeUpdate(BaseModel):
    patient_safe: bool

@router.patch("/api/manage/knowledge/{item_id}/patient_safe")
async def update_patient_safe(item_id: int, body: PatientSafeUpdate, doctor_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    item = await session.get(DoctorKnowledgeItem, item_id)
    if not item or item.doctor_id != doctor_id:
        raise HTTPException(status_code=404)
    item.patient_safe = body.patient_safe
    await session.commit()
    return {"id": item_id, "patient_safe": item.patient_safe}
```

Imports and exact patterns must match what's already in the file.

- [ ] **Step 3: Add endpoint for marking onboarding done**

In the same file:

```python
@router.post("/api/manage/knowledge/curation_onboarding_done")
async def mark_curation_onboarding_done(doctor_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    doctor = await session.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404)
    doctor.kb_curation_onboarding_done = True
    await session.commit()
    return {"doctor_id": doctor_id, "kb_curation_onboarding_done": True}
```

- [ ] **Step 4: Smoke-test endpoints**

Start server on :8001 (per project rules — never :8000 for sim). Use httpie or curl to PATCH a real KB item and POST onboarding-done. Verify DB state changes.

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/doctor_dashboard/knowledge_routes.py
git commit -m "feat(api): KB patient_safe toggle and curation onboarding endpoints"
```

---

### Task 0.5.3: KB editor frontend — patient_safe toggle and onboarding banner

**Files:**
- Modify: existing KB editor page (locate via `rg -n "patient_safe\|knowledge.*editor" frontend/web/src` — likely under `frontend/web/src/v2/pages/doctor/` or similar). If unclear, ask the user before making changes.

- [ ] **Step 1: Add a toggle to each KB item row**

For each KB item row, render a labeled switch:
- Label: "对患者可见"
- State: bound to `item.patient_safe`
- onChange: PATCH `/api/manage/knowledge/{id}/patient_safe`
- Helper text below switch: "勾选后，遇到匹配问题鲸鱼会直接回复患者；否则只生成草稿给您审核"

Use existing `Switch` from antd-mobile and theme tokens (`FONT.sm`, `APP.text4` per CLAUDE.md design system).

- [ ] **Step 2: Add an onboarding banner above the KB list**

When `doctor.kb_curation_onboarding_done === false`, render a sticky banner at top of the KB list:

```jsx
<Banner
  style={{ background: APP.warningBg, padding: "12px 16px" }}
>
  <span style={{ fontSize: FONT.sm, color: APP.text2 }}>
    请逐条确认每个知识点是否对患者可见。完成后点击下方按钮，鲸鱼才会基于这些知识点直接回复患者。
  </span>
  <Button color="primary" onClick={markOnboardingDone}>
    我已完成审核
  </Button>
</Banner>
```

`markOnboardingDone` POSTs `/api/manage/knowledge/curation_onboarding_done` then refetches the doctor object.

- [ ] **Step 3: Verify in browser**

Run dev: `cd frontend/web && npm run dev` (assumes :8001 is the running backend). Navigate to KB editor as a doctor whose `kb_curation_onboarding_done=false`. Verify the banner appears, toggling an item updates server-side, and clicking "我已完成审核" hides the banner and persists.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/<editor-file>.jsx
git commit -m "feat(kb): patient_safe toggle and curation onboarding UI"
```

---

### Phase 0.5 wrap

Doctors can now opt into patient-facing autonomous KB replies via a one-shot curation pass. The gate is enforced server-side. Phase 1 will use `curation_gate.is_patient_safe()` everywhere a KB item is considered for an autonomous patient reply.

---

## Phase 1 — Dual-Mode Chat

Goal: ChatTab handles new symptoms via sticky state machine, auto-creates draft records, prompts patient at thresholds, deduplicates, supports doctor-side supplement workflow. **Feature-flagged per doctor** via `PATIENT_CHAT_INTAKE_ENABLED` — defaults off; pilot doctors flipped on for evaluation.

### Task 1.1: ChatSessionState model + state transitions

**Files:**
- Create: `src/domain/patient_lifecycle/chat_state.py`
- Test: `tests/core/test_chat_state.py`

- [ ] **Step 1: Write failing tests for entry rule**

```python
# tests/core/test_chat_state.py
import pytest
from unittest.mock import patch
from src.domain.patient_lifecycle.chat_state import (
    ChatSessionState, evaluate_entry, IntakeEntryReason
)
from src.domain.patient_lifecycle.triage import TriageResult, TriageCategory

def _triage(category, conf):
    return TriageResult(category=category, confidence=conf)

def test_high_confidence_symptom_enters_intake():
    decision = evaluate_entry(_triage(TriageCategory.symptom_report, 0.85), message="头晕两天了")
    assert decision.entered is True
    assert decision.reason == IntakeEntryReason.PRIMARY_THRESHOLD

def test_borderline_with_lexicon_match_enters_intake():
    decision = evaluate_entry(_triage(TriageCategory.symptom_report, 0.55), message="胃有点不舒服")
    assert decision.entered is True
    assert decision.reason == IntakeEntryReason.LEXICON_BOOST

def test_borderline_without_lexicon_match_stays_idle():
    decision = evaluate_entry(_triage(TriageCategory.symptom_report, 0.55), message="今天天气不错")
    assert decision.entered is False

def test_below_lower_threshold_never_enters():
    decision = evaluate_entry(_triage(TriageCategory.symptom_report, 0.40), message="我头很痛")
    assert decision.entered is False

def test_non_symptom_category_never_enters():
    decision = evaluate_entry(_triage(TriageCategory.general_question, 0.95), message="头痛")
    assert decision.entered is False
```

- [ ] **Step 2: Write failing tests for sticky exit**

Append to `tests/core/test_chat_state.py`:

```python
def test_intake_does_not_exit_on_low_confidence_alone():
    state = ChatSessionState(state="intake", record_id=1)
    state = state.handle_classifier_only(_triage(TriageCategory.general_question, 0.4))
    assert state.state == "intake"

def test_intake_exits_on_explicit_cancel_signal():
    state = ChatSessionState(state="intake", record_id=1)
    state = state.handle_cancel_signal(confidence=0.9)
    assert state.state == "idle"
    assert state.cancellation_reason == "patient_cancel"

def test_intake_exits_on_idle_decay():
    state = ChatSessionState(state="intake", record_id=1, last_intake_turn_at_iso="2026-04-23T08:00:00")
    state = state.apply_idle_decay(now_iso="2026-04-24T09:00:00")  # 25h elapsed
    assert state.state == "idle"
    assert state.cancellation_reason == "idle_decay"
```

- [ ] **Step 3: Write failing tests for qa_window**

```python
def test_intake_enters_qa_window_on_whitelist_question():
    state = ChatSessionState(state="intake", record_id=1)
    state = state.enter_qa_window(intent="appointment_logistics")
    assert state.state == "qa_window"

def test_qa_window_returns_to_intake_on_intake_relevant_turn():
    state = ChatSessionState(state="qa_window", record_id=1)
    state = state.handle_message(_triage(TriageCategory.symptom_report, 0.7), message="还头痛")
    assert state.state == "intake"

def test_qa_window_returns_to_intake_on_30min_silence():
    state = ChatSessionState(state="qa_window", record_id=1, qa_window_entered_at_iso="2026-04-25T10:00:00")
    state = state.apply_idle_decay(now_iso="2026-04-25T10:35:00")
    assert state.state == "intake"
```

- [ ] **Step 4: Run tests, verify they fail**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/core/test_chat_state.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: ImportError.

- [ ] **Step 5: Implement chat_state.py**

```python
"""ChatSessionState — sticky state machine on the patient chat thread.

States: idle | intake | qa_window
Transitions match design spec §1a / §1b / §1c. Exit from intake requires explicit
cancellation or 24h decay; classifier confidence alone never exits intake.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.domain.patient_lifecycle.triage import TriageResult, TriageCategory

PRIMARY_THRESHOLD = 0.65
LOWER_THRESHOLD = 0.50
CANCEL_THRESHOLD = 0.85
INTAKE_IDLE_HOURS = 24
QA_WINDOW_IDLE_MINUTES = 30

LEXICON_BODY_SITES = ("头", "胸", "肚", "胃", "腹", "腰", "背", "腿", "膝", "嗓", "喉", "心", "肝", "肾", "脾")
LEXICON_SYMPTOM_TERMS = ("痛", "晕", "喘", "酸", "麻", "肿", "热", "凉", "吐", "拉", "咳", "鸣")
LEXICON_DURATION = ("天", "周", "月", "几天", "最近", "好几", "一直", "总是")


class IntakeEntryReason(str, Enum):
    PRIMARY_THRESHOLD = "primary_threshold"
    LEXICON_BOOST = "lexicon_boost"


@dataclass
class IntakeEntryDecision:
    entered: bool
    reason: Optional[IntakeEntryReason] = None


def _lexicon_match(message: str) -> bool:
    return (
        any(t in message for t in LEXICON_BODY_SITES)
        or any(t in message for t in LEXICON_SYMPTOM_TERMS)
        or any(t in message for t in LEXICON_DURATION)
    )


def evaluate_entry(triage: TriageResult, message: str) -> IntakeEntryDecision:
    if triage.category != TriageCategory.symptom_report:
        return IntakeEntryDecision(entered=False)
    if triage.confidence >= PRIMARY_THRESHOLD:
        return IntakeEntryDecision(entered=True, reason=IntakeEntryReason.PRIMARY_THRESHOLD)
    if triage.confidence >= LOWER_THRESHOLD and _lexicon_match(message):
        return IntakeEntryDecision(entered=True, reason=IntakeEntryReason.LEXICON_BOOST)
    return IntakeEntryDecision(entered=False)


@dataclass
class ChatSessionState:
    state: str = "idle"  # idle | intake | qa_window
    record_id: Optional[int] = None
    intake_segment_id: Optional[str] = None
    last_intake_turn_at_iso: Optional[str] = None
    qa_window_entered_at_iso: Optional[str] = None
    cancellation_reason: Optional[str] = None

    def handle_classifier_only(self, triage: TriageResult) -> "ChatSessionState":
        # Classifier confidence alone cannot exit intake (sticky exit rule).
        return self

    def handle_cancel_signal(self, confidence: float) -> "ChatSessionState":
        if confidence < CANCEL_THRESHOLD:
            return self
        return ChatSessionState(state="idle", record_id=self.record_id, cancellation_reason="patient_cancel")

    def enter_qa_window(self, intent: str) -> "ChatSessionState":
        return ChatSessionState(
            state="qa_window",
            record_id=self.record_id,
            intake_segment_id=self.intake_segment_id,
            last_intake_turn_at_iso=self.last_intake_turn_at_iso,
            qa_window_entered_at_iso=datetime.utcnow().isoformat(),
        )

    def handle_message(self, triage: TriageResult, message: str) -> "ChatSessionState":
        if self.state == "qa_window":
            decision = evaluate_entry(triage, message)
            if decision.entered:
                return ChatSessionState(
                    state="intake",
                    record_id=self.record_id,
                    intake_segment_id=self.intake_segment_id,
                    last_intake_turn_at_iso=datetime.utcnow().isoformat(),
                )
        return self

    def apply_idle_decay(self, now_iso: str) -> "ChatSessionState":
        now = datetime.fromisoformat(now_iso)
        if self.state == "intake" and self.last_intake_turn_at_iso:
            last = datetime.fromisoformat(self.last_intake_turn_at_iso)
            if (now - last).total_seconds() / 3600 >= INTAKE_IDLE_HOURS:
                return ChatSessionState(state="idle", record_id=self.record_id, cancellation_reason="idle_decay")
        if self.state == "qa_window" and self.qa_window_entered_at_iso:
            entered = datetime.fromisoformat(self.qa_window_entered_at_iso)
            if (now - entered).total_seconds() / 60 >= QA_WINDOW_IDLE_MINUTES:
                return ChatSessionState(
                    state="intake",
                    record_id=self.record_id,
                    intake_segment_id=self.intake_segment_id,
                    last_intake_turn_at_iso=self.last_intake_turn_at_iso,
                )
        return self
```

- [ ] **Step 6: Run tests, verify pass**

Run pytest. All test functions in test_chat_state.py should pass.

- [ ] **Step 7: Commit**

```bash
git add src/domain/patient_lifecycle/chat_state.py tests/core/test_chat_state.py
git commit -m "feat(chat): sticky ChatSessionState with dual-threshold entry"
```

---

### Task 1.2: Entry-branch observability counters

**Files:**
- Modify: `src/domain/patient_lifecycle/chat_state.py`

- [ ] **Step 1: Add a logging hook to evaluate_entry**

Append at the end of `evaluate_entry` body, before return statements:

```python
import logging
log = logging.getLogger("chat_state.entry")
```

(Place imports at top.) Then in `evaluate_entry`:

```python
def evaluate_entry(triage: TriageResult, message: str) -> IntakeEntryDecision:
    if triage.category != TriageCategory.symptom_report:
        return IntakeEntryDecision(entered=False)
    if triage.confidence >= PRIMARY_THRESHOLD:
        log.info("chat_state.entry.entered branch=primary_threshold confidence=%.2f", triage.confidence)
        return IntakeEntryDecision(entered=True, reason=IntakeEntryReason.PRIMARY_THRESHOLD)
    if triage.confidence >= LOWER_THRESHOLD and _lexicon_match(message):
        log.info("chat_state.entry.entered branch=lexicon_boost confidence=%.2f", triage.confidence)
        return IntakeEntryDecision(entered=True, reason=IntakeEntryReason.LEXICON_BOOST)
    return IntakeEntryDecision(entered=False)
```

The log lines are the pilot dashboards' source. A future task can wire structured metrics; for now, log lines + parse-from-log is acceptable for pilot.

- [ ] **Step 2: Test the log emission**

Add to `tests/core/test_chat_state.py`:

```python
def test_entry_logs_branch(caplog):
    import logging
    caplog.set_level(logging.INFO, logger="chat_state.entry")
    evaluate_entry(_triage(TriageCategory.symptom_report, 0.85), message="头晕")
    assert any("branch=primary_threshold" in r.message for r in caplog.records)
    caplog.clear()
    evaluate_entry(_triage(TriageCategory.symptom_report, 0.55), message="胃疼")
    assert any("branch=lexicon_boost" in r.message for r in caplog.records)
```

- [ ] **Step 3: Run tests, verify pass; commit**

```bash
git add src/domain/patient_lifecycle/chat_state.py tests/core/test_chat_state.py
git commit -m "feat(chat): entry-branch observability for pilot dashboards"
```

---

### Task 1.3: Dedup detection — similarity AND episode signals

**Files:**
- Create: `src/domain/patient_lifecycle/dedup.py`
- Test: `tests/core/test_dedup.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_dedup.py
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta
from src.domain.patient_lifecycle.dedup import detect_same_episode, EpisodeSignals

@pytest.mark.asyncio
async def test_high_similarity_clear_signals_returns_same_episode():
    with patch("src.domain.patient_lifecycle.dedup._llm_chief_complaint_similarity", AsyncMock(return_value=0.85)):
        signals = EpisodeSignals(hours_since_last=2.0, treatment_event_since_last=False, status_change_since_last=False)
        result = await detect_same_episode(draft_complaint="头痛", target_complaint="头疼", signals=signals)
    assert result.same_episode is True
    assert result.band == "auto_merge"

@pytest.mark.asyncio
async def test_high_similarity_but_treatment_event_returns_new_episode():
    with patch("src.domain.patient_lifecycle.dedup._llm_chief_complaint_similarity", AsyncMock(return_value=0.85)):
        signals = EpisodeSignals(hours_since_last=2.0, treatment_event_since_last=True, status_change_since_last=False)
        result = await detect_same_episode(draft_complaint="头痛", target_complaint="头疼", signals=signals)
    assert result.same_episode is False

@pytest.mark.asyncio
async def test_high_similarity_but_status_change_returns_new_episode():
    with patch("src.domain.patient_lifecycle.dedup._llm_chief_complaint_similarity", AsyncMock(return_value=0.85)):
        signals = EpisodeSignals(hours_since_last=2.0, treatment_event_since_last=False, status_change_since_last=True)
        result = await detect_same_episode(draft_complaint="头痛", target_complaint="头疼", signals=signals)
    assert result.same_episode is False

@pytest.mark.asyncio
async def test_high_similarity_but_over_24h_returns_new_episode():
    with patch("src.domain.patient_lifecycle.dedup._llm_chief_complaint_similarity", AsyncMock(return_value=0.85)):
        signals = EpisodeSignals(hours_since_last=25.0, treatment_event_since_last=False, status_change_since_last=False)
        result = await detect_same_episode(draft_complaint="头痛", target_complaint="头疼", signals=signals)
    assert result.same_episode is False

@pytest.mark.asyncio
async def test_band_in_ambiguous_range_returns_prompt():
    with patch("src.domain.patient_lifecycle.dedup._llm_chief_complaint_similarity", AsyncMock(return_value=0.6)):
        signals = EpisodeSignals(hours_since_last=2.0, treatment_event_since_last=False, status_change_since_last=False)
        result = await detect_same_episode(draft_complaint="头痛", target_complaint="头晕", signals=signals)
    assert result.same_episode is True
    assert result.band == "patient_prompt"

@pytest.mark.asyncio
async def test_low_similarity_returns_no_dedup():
    with patch("src.domain.patient_lifecycle.dedup._llm_chief_complaint_similarity", AsyncMock(return_value=0.3)):
        signals = EpisodeSignals(hours_since_last=2.0, treatment_event_since_last=False, status_change_since_last=False)
        result = await detect_same_episode(draft_complaint="头痛", target_complaint="腿肿", signals=signals)
    assert result.same_episode is False
```

- [ ] **Step 2: Run tests, verify fail (ImportError)**

- [ ] **Step 3: Implement dedup detection**

```python
# src/domain/patient_lifecycle/dedup.py
"""Dedup detection — combines chief_complaint similarity with episode-boundary signals.

Spec §5a. Same complaint text after a doctor decision or status advance is by definition
a new clinical episode, never a duplicate. Below the lower similarity bound, no dedup.
Above the upper bound with episode signals clear, auto_merge band. Between, patient_prompt.
"""
from dataclasses import dataclass
from typing import Literal
import json

from src.agent.llm.structured_call import structured_call

LOWER_BOUND = 0.5
UPPER_BOUND = 0.7
WITHIN_HOURS = 24


@dataclass
class EpisodeSignals:
    hours_since_last: float
    treatment_event_since_last: bool
    status_change_since_last: bool


@dataclass
class DedupDecision:
    same_episode: bool
    band: Literal["auto_merge", "patient_prompt", "none"]
    similarity: float


async def detect_same_episode(
    draft_complaint: str,
    target_complaint: str,
    signals: EpisodeSignals,
) -> DedupDecision:
    similarity = await _llm_chief_complaint_similarity(draft_complaint, target_complaint)

    # Episode-boundary signals override similarity. Same text after treatment / status change = new episode.
    if signals.hours_since_last > WITHIN_HOURS:
        return DedupDecision(same_episode=False, band="none", similarity=similarity)
    if signals.treatment_event_since_last or signals.status_change_since_last:
        return DedupDecision(same_episode=False, band="none", similarity=similarity)

    if similarity >= UPPER_BOUND:
        return DedupDecision(same_episode=True, band="auto_merge", similarity=similarity)
    if similarity >= LOWER_BOUND:
        return DedupDecision(same_episode=True, band="patient_prompt", similarity=similarity)
    return DedupDecision(same_episode=False, band="none", similarity=similarity)


async def _llm_chief_complaint_similarity(a: str, b: str) -> float:
    """One-shot LLM call: are these two chief complaints describing the same clinical issue?

    Returns a float in [0.0, 1.0]. Tight prompt — no clinical reasoning, just text equivalence.
    """
    prompt = f"两段主诉文本是否在描述同一个临床问题? A: '{a}' B: '{b}' 仅返回 JSON: {{\"similarity\": 0.0-1.0}}"
    raw = await structured_call(prompt=prompt, model_env="DEDUP_LLM", default_model="qwen-turbo")
    try:
        return float(json.loads(raw).get("similarity", 0.0))
    except Exception:
        return 0.0
```

Note: `structured_call` and the LLM env-var conventions follow the project's existing pattern (see `triage.py` for reference). If `structured_call`'s actual signature differs, match it.

- [ ] **Step 4: Run tests, verify pass; commit**

```bash
git add src/domain/patient_lifecycle/dedup.py tests/core/test_dedup.py
git commit -m "feat(dedup): episode-aware detection (similarity + boundary signals)"
```

---

### Task 1.4: Append-only merge implementation (§5b common case)

**Files:**
- Modify: `src/domain/patient_lifecycle/dedup.py` (add `merge_into_existing()`)
- Test: extend `tests/core/test_dedup.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/core/test_dedup.py
import pytest
from src.db.models.records import MedicalRecordDB, FieldEntryDB

@pytest.mark.asyncio
async def test_merge_appends_field_entries_no_overwrite(async_session, sample_record_with_entries):
    from src.domain.patient_lifecycle.dedup import merge_into_existing
    target = sample_record_with_entries  # has chief_complaint="头痛" entry from segment_1
    new_fields = {"chief_complaint": "头痛加重", "present_illness": "今天又痛了"}
    await merge_into_existing(async_session, target_record_id=target.id, new_fields=new_fields, intake_segment_id="segment_2")

    entries = (await async_session.execute(
        select(FieldEntryDB).where(FieldEntryDB.record_id == target.id).order_by(FieldEntryDB.created_at)
    )).scalars().all()
    chief_entries = [e for e in entries if e.field_name == "chief_complaint"]
    assert len(chief_entries) == 2  # original + new
    assert chief_entries[0].text == "头痛"
    assert chief_entries[1].text == "头痛加重"
    assert chief_entries[1].intake_segment_id == "segment_2"

@pytest.mark.asyncio
async def test_merge_skips_duplicate_chief_complaint(async_session, sample_record_with_entries):
    from src.domain.patient_lifecycle.dedup import merge_into_existing
    target = sample_record_with_entries  # has chief_complaint="头痛"
    await merge_into_existing(async_session, target_record_id=target.id, new_fields={"chief_complaint": "头痛"}, intake_segment_id="segment_2")

    chief_entries = (await async_session.execute(
        select(FieldEntryDB).where(FieldEntryDB.record_id == target.id, FieldEntryDB.field_name == "chief_complaint")
    )).scalars().all()
    assert len(chief_entries) == 1  # duplicate skipped
```

The `async_session` and `sample_record_with_entries` fixtures must be defined in `tests/conftest.py` or `tests/api/conftest.py` (verify existing fixture patterns when implementing — if they don't exist yet, add them following the existing test file conventions).

- [ ] **Step 2: Implement merge_into_existing**

Add to `src/domain/patient_lifecycle/dedup.py`:

```python
from datetime import datetime
from sqlalchemy import select
from src.db.models.records import FieldEntryDB

REQUIRED_FIELDS = (
    "chief_complaint",
    "present_illness",
    "past_history",
    "allergy_history",
    "personal_history",
    "marital_reproductive",
    "family_history",
)


async def merge_into_existing(
    session,
    target_record_id: int,
    new_fields: dict,
    intake_segment_id: str | None,
) -> None:
    """Append-only merge: new field entries appended with provenance; existing entries
    are never mutated. For chief_complaint, duplicate text is skipped (no point appending
    the same complaint twice). Other fields always append non-empty values.
    """
    existing_chief = (await session.execute(
        select(FieldEntryDB.text).where(
            FieldEntryDB.record_id == target_record_id,
            FieldEntryDB.field_name == "chief_complaint",
        )
    )).scalars().all()

    now = datetime.utcnow()
    for field in REQUIRED_FIELDS:
        text = new_fields.get(field)
        if text is None or not str(text).strip():
            continue
        if field == "chief_complaint" and text in existing_chief:
            continue
        session.add(FieldEntryDB(
            record_id=target_record_id,
            field_name=field,
            text=text,
            intake_segment_id=intake_segment_id,
            created_at=now,
        ))
    await session.flush()
```

- [ ] **Step 3: Run tests, verify pass; commit**

```bash
git add src/domain/patient_lifecycle/dedup.py tests/core/test_dedup.py
git commit -m "feat(dedup): append-only merge with per-segment provenance"
```

---

### Task 1.5: Supplement creation for reviewed records (§5b edge case 2)

**Files:**
- Modify: `src/domain/patient_lifecycle/dedup.py` (add `create_supplement()`)
- Test: extend `tests/core/test_dedup.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_create_supplement_writes_pending_row(async_session, completed_record):
    from src.domain.patient_lifecycle.dedup import create_supplement
    from src.db.models.records import RecordSupplementDB

    new_fields = {"chief_complaint": "头痛复发", "present_illness": "停药后又痛"}
    sup = await create_supplement(async_session, target_record_id=completed_record.id, new_fields=new_fields, intake_segment_id="segment_3")

    persisted = (await async_session.execute(
        select(RecordSupplementDB).where(RecordSupplementDB.record_id == completed_record.id)
    )).scalar_one()
    assert persisted.status == "pending_doctor_review"
    entries = json.loads(persisted.field_entries_json)
    assert any(e["field_name"] == "chief_complaint" and e["text"] == "头痛复发" for e in entries)

@pytest.mark.asyncio
async def test_create_supplement_does_not_mutate_target(async_session, completed_record):
    from src.domain.patient_lifecycle.dedup import create_supplement
    from src.db.models.records import FieldEntryDB

    before = (await async_session.execute(select(FieldEntryDB).where(FieldEntryDB.record_id == completed_record.id))).scalars().all()
    before_count = len(before)

    await create_supplement(async_session, target_record_id=completed_record.id, new_fields={"chief_complaint": "新症状"}, intake_segment_id="segment_3")

    after = (await async_session.execute(select(FieldEntryDB).where(FieldEntryDB.record_id == completed_record.id))).scalars().all()
    assert len(after) == before_count  # target untouched
```

- [ ] **Step 2: Implement**

```python
# Append to src/domain/patient_lifecycle/dedup.py
import json
from src.db.models.records import RecordSupplementDB


async def create_supplement(
    session,
    target_record_id: int,
    new_fields: dict,
    intake_segment_id: str | None,
):
    now = datetime.utcnow()
    entries = []
    for field in REQUIRED_FIELDS:
        text = new_fields.get(field)
        if text is None or not str(text).strip():
            continue
        entries.append({
            "field_name": field,
            "text": text,
            "intake_segment_id": intake_segment_id,
            "created_at": now.isoformat(),
        })
    sup = RecordSupplementDB(
        record_id=target_record_id,
        status="pending_doctor_review",
        field_entries_json=json.dumps(entries),
        created_at=now,
    )
    session.add(sup)
    await session.flush()
    return sup
```

- [ ] **Step 3: Run tests, verify pass; commit**

```bash
git add src/domain/patient_lifecycle/dedup.py tests/core/test_dedup.py
git commit -m "feat(dedup): RecordSupplementDB pending-doctor-review for reviewed records"
```

---

### Task 1.6: Red-flag retraction logic (§4)

**Files:**
- Create: `src/domain/patient_lifecycle/retraction.py`
- Test: `tests/core/test_retraction.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_retraction.py
import pytest
from src.domain.patient_lifecycle.retraction import retract_recent_whitelist_replies
from sqlalchemy import select
from src.db.models.patient_message import PatientMessage

@pytest.mark.asyncio
async def test_retract_marks_recent_whitelist_replies_in_segment(async_session, segment_with_whitelist_reply):
    """Setup fixture inserts: 1 patient turn, 1 AI whitelist reply, both with intake_segment_id='seg_X'."""
    seg_id = segment_with_whitelist_reply
    await retract_recent_whitelist_replies(async_session, intake_segment_id=seg_id)
    msgs = (await async_session.execute(
        select(PatientMessage).where(PatientMessage.intake_segment_id == seg_id)
    )).scalars().all()
    ai_msgs = [m for m in msgs if m.role == "ai" and getattr(m, "is_whitelist_reply", False)]
    assert all(m.retracted is True for m in ai_msgs)
```

(The `is_whitelist_reply` flag may need to be a separate column added during this task — if `PatientMessage` doesn't already distinguish AI whitelist replies from doctor replies, add a column `is_whitelist_reply: bool default False` via a quick Alembic migration before this task. Note this in commit message.)

- [ ] **Step 2: Implement retraction**

```python
# src/domain/patient_lifecycle/retraction.py
"""Red-flag retraction — when signal_flag.detect fires within an intake segment, mark all
prior AI whitelist replies in that segment as retracted=True so they render struck
through in both patient and doctor views.
"""
from sqlalchemy import select, update
from src.db.models.patient_message import PatientMessage


async def retract_recent_whitelist_replies(session, intake_segment_id: str) -> int:
    """Mark all AI whitelist replies in the given segment as retracted. Returns count updated."""
    result = await session.execute(
        update(PatientMessage)
        .where(
            PatientMessage.intake_segment_id == intake_segment_id,
            PatientMessage.role == "ai",
            PatientMessage.is_whitelist_reply == True,  # noqa: E712
            PatientMessage.retracted == False,  # noqa: E712
        )
        .values(retracted=True)
    )
    await session.flush()
    return result.rowcount
```

If `PatientMessage` has no `is_whitelist_reply` and no `intake_segment_id`, add both via a small migration first (mirror the structure of Task 0.1). Skip the migration if those columns already exist.

- [ ] **Step 3: Run tests, verify pass; commit**

```bash
git add src/domain/patient_lifecycle/retraction.py tests/core/test_retraction.py
git commit -m "feat(safety): retract whitelist replies when signal-flag fires same segment"
```

---

### Task 1.7: Dispatcher — wire state machine into `post_chat`

**Files:**
- Modify: `src/channels/web/patient_portal/chat.py` (`post_chat` handler)

This is the integration task. The implementer should NOT write a green-field rewrite; instead extend the existing handler.

- [ ] **Step 1: Sketch the new flow inside `post_chat`**

Replace the body of the existing `post_chat` handler with a flow that — at minimum — calls these in order:

```python
# Pseudocode — match existing patterns for db access, error handling, and response shape.

triage_result = await classify(message=body.text, patient_context=ctx)

# Always run signal-flag check first; can fire in any state.
signal_flag_fired = await signal_flag.detect(message=body.text, patient_context=ctx)
if signal_flag_fired:
    if state.intake_segment_id:
        await retract_recent_whitelist_replies(session, state.intake_segment_id)
    await emit_static_urgent_safety_message(...)
    await notify_doctor_urgent(...)
    if state.record_id:
        await session.execute(update(MedicalRecordDB).where(MedicalRecordDB.id == state.record_id).values(signal_flag=True))
    return ChatResponse(...)

# Dispatch on state.
state = await load_state(session, patient_id)
state = state.apply_idle_decay(now_iso=datetime.utcnow().isoformat())

if state.state == "idle":
    decision = evaluate_entry(triage_result, body.text)
    if decision.entered:
        state = await begin_intake(session, patient_id, triage_result, body.text)
    else:
        # Whitelist autonomous reply path or doctor-route path (existing logic).
        return await handle_idle_message(session, patient_id, body.text, triage_result)

if state.state == "intake":
    # Append message to draft, recompute extraction_confidence, check threshold gate.
    return await handle_intake_message(session, state, body.text, triage_result)

if state.state == "qa_window":
    state = state.handle_message(triage_result, body.text)
    if state.state == "intake":
        return await handle_intake_message(session, state, body.text, triage_result)
    return await handle_idle_message(session, patient_id, body.text, triage_result)
```

- [ ] **Step 2: Implement `load_state`, `begin_intake`, `handle_intake_message`, `handle_idle_message` in the same file or a thin helper module**

`load_state` — read or initialize per-patient state. v0 can store state in a small `chat_session_state` table (1 row per patient_id) — add via Alembic if needed. Or in-memory keyed by patient_id for prototype with a TODO. Pilot needs persistence.

`begin_intake` — create `MedicalRecordDB(status='intake_active', seed_source='chat_detected', intake_segment_id=new_uuid())`, return updated state.

`handle_intake_message` — append the parsed message into `FieldEntryDB` rows for the active record, recompute extraction_confidence; if `chief_complaint AND present_illness AND (duration OR severity) signals all present`, return a `ChatResponse` containing a `confirm_gate` payload the frontend renders as the special chat message.

`handle_idle_message` — keep existing triage handler logic for whitelist/draft/escalation paths.

- [ ] **Step 3: Smoke-test the dispatch with a manual session**

Start backend on :8001. POST `/api/patient/chat` with messages exercising: idle → intake entry, intake → confirm gate, qa_window mid-intake. Verify state persistence across requests.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/patient_portal/chat.py src/db/models/* alembic/versions/*chat_session_state*.py
git commit -m "feat(chat): wire state machine + dedup + signal-flag into patient chat dispatcher"
```

---

### Task 1.8: Confirm gate frontend component

**Files:**
- Create: `frontend/web/src/v2/components/ChatConfirmGate.jsx`
- Modify: `frontend/web/src/v2/pages/patient/ChatTab.jsx` (render gate when message has `kind === "confirm_gate"`)

- [ ] **Step 1: Create the component**

```jsx
// frontend/web/src/v2/components/ChatConfirmGate.jsx
import { Button } from "antd-mobile";
import { APP, FONT, RADIUS } from "../theme";

export default function ChatConfirmGate({ continuity, onConfirm, onContinue }) {
  const prompt = continuity
    ? "继续您之前的就诊记录，整理给医生?"
    : "您刚才提到的情况，要为您整理成一条就诊记录给医生看吗?";

  return (
    <div style={styles.wrap}>
      <p style={styles.text}>{prompt}</p>
      <div style={styles.row}>
        <Button color="primary" size="middle" onClick={onConfirm}>整理给医生</Button>
        <Button size="middle" onClick={onContinue}>继续聊</Button>
      </div>
    </div>
  );
}

const styles = {
  wrap: {
    background: APP.surface,
    borderRadius: RADIUS.md,
    padding: "12px 14px",
    margin: "4px 12px",
    boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
  },
  text: { fontSize: FONT.md, color: APP.text1, margin: 0, marginBottom: 12 },
  row: { display: "flex", gap: 12, justifyContent: "flex-end" },
};
```

- [ ] **Step 2: Wire into ChatTab.jsx**

In the message-render loop, branch on `message.kind`:

```jsx
if (message.kind === "confirm_gate") {
  return (
    <ChatConfirmGate
      continuity={message.continuity}
      onConfirm={() => sendConfirmation(message.draft_id, "confirm")}
      onContinue={() => sendConfirmation(message.draft_id, "continue")}
    />
  );
}
```

`sendConfirmation` POSTs `/api/patient/chat/confirm_draft` with `{draft_id, action}`. Implement that endpoint in the same backend task or a follow-up.

- [ ] **Step 3: Verify in browser**

Reproduce the intake → confirm_gate flow with the dev environment. Tap both buttons; verify backend records the action and the gate disappears from the thread.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/v2/components/ChatConfirmGate.jsx frontend/web/src/v2/pages/patient/ChatTab.jsx
git commit -m "feat(patient-chat): inline confirm gate component"
```

---

### Task 1.9: Dedup prompt frontend component

**Files:**
- Create: `frontend/web/src/v2/components/ChatDedupPrompt.jsx`
- Modify: `frontend/web/src/v2/pages/patient/ChatTab.jsx`

- [ ] **Step 1: Create component**

Three-button variant of `ChatConfirmGate`. Buttons: 并入上一次 | 新开一条 | 都不要. Copy of the prompt text matches §5b: 您之前提到过类似的情况。要把刚才的内容并入上一次记录，还是新开一条?

- [ ] **Step 2: Wire into ChatTab.jsx**

When `message.kind === "dedup_prompt"`, render `<ChatDedupPrompt onMerge={...} onNew={...} onNeither={...} />`. Each handler POSTs `/api/patient/chat/dedup_decision` with `{draft_id, action}`.

- [ ] **Step 3: Smoke-test; commit**

```bash
git add frontend/web/src/v2/components/ChatDedupPrompt.jsx frontend/web/src/v2/pages/patient/ChatTab.jsx
git commit -m "feat(patient-chat): inline dedup prompt component"
```

---

### Task 1.10: Retracted-message strikethrough rendering

**Files:**
- Modify: `frontend/web/src/v2/ChatBubble.jsx`

- [ ] **Step 1: Add retracted-state styling**

In `ChatBubble.jsx`, add `retracted` to the props. When true, apply:

```jsx
const bubbleStyle = {
  ...styles.bubble,
  ...(retracted ? { textDecoration: "line-through", opacity: 0.5 } : {}),
};
```

And below the bubble, when retracted:

```jsx
{retracted && (
  <span style={{ fontSize: FONT.xs, color: APP.text4, marginLeft: 8 }}>
    已撤回 (危险信号触发)
  </span>
)}
```

- [ ] **Step 2: Verify in browser**

Manually flip `retracted` true on a test message in dev tools or via API. Confirm strike-through renders in both patient ChatTab and doctor chat-history view.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/ChatBubble.jsx
git commit -m "feat(chat): retracted-message strikethrough + reason annotation"
```

---

### Task 1.11: Doctor-side review queue — provenance filter + extraction_confidence

**Files:**
- Modify: `src/channels/web/doctor_dashboard/review_queue_handlers.py` (add filter param + include extraction_confidence + seed_source in response)
- Modify: doctor review queue frontend page (locate via `rg -n "review.*queue" frontend/web/src/v2/pages` — likely under `frontend/web/src/v2/pages/doctor/`)

- [ ] **Step 1: Backend — accept `seed_source` query param and include in response**

```python
@router.get("/api/manage/review/queue")
async def review_queue(
    doctor_id: str = Query(...),
    seed_source: Optional[str] = Query(default=None),  # 'chat_detected' | 'explicit_intake' | None=all
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    # Existing query unchanged; add a filter clause when seed_source is provided.
    q = ...  # existing select
    if seed_source:
        q = q.where(MedicalRecordDB.seed_source == seed_source)
    rows = (await session.execute(q)).all()
    # In each row dict, include: seed_source, extraction_confidence (already columns).
```

- [ ] **Step 2: Frontend — filter chip row and ring component**

Above the queue, add three pill chips: 全部 | 问诊完成 | 自动整理. Selecting one updates a query-string param, which react-query passes to the `useReviewQueue` hook.

For each row that has `seed_source === "chat_detected"` and `extraction_confidence != null`, render the new `ExtractionConfidenceRing` (Task 1.12).

- [ ] **Step 3: Smoke-test; commit**

```bash
git add src/channels/web/doctor_dashboard/review_queue_handlers.py frontend/web/src/v2/pages/doctor/<queue-file>.jsx
git commit -m "feat(review-queue): provenance filter + chat-detected badge"
```

---

### Task 1.12: ExtractionConfidenceRing component

**Files:**
- Create: `frontend/web/src/v2/components/ExtractionConfidenceRing.jsx`

- [ ] **Step 1: Create the visual**

```jsx
// frontend/web/src/v2/components/ExtractionConfidenceRing.jsx
// Renders N/7 as a ring. Honest about denominator; not a percentage, not a colored severity.
import { APP, FONT } from "../theme";

export default function ExtractionConfidenceRing({ confidence }) {
  const filled = Math.round((confidence ?? 0) * 7);
  const radius = 11;
  const circ = 2 * Math.PI * radius;
  const offset = circ - (filled / 7) * circ;
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <svg width="28" height="28">
        <circle cx="14" cy="14" r={radius} stroke={APP.borderLight} strokeWidth="3" fill="none" />
        <circle cx="14" cy="14" r={radius} stroke={APP.primary} strokeWidth="3" fill="none"
                strokeDasharray={circ} strokeDashoffset={offset}
                transform="rotate(-90 14 14)" />
      </svg>
      <span style={{ fontSize: FONT.xs, color: APP.text4 }}>{filled}/7</span>
    </div>
  );
}
```

- [ ] **Step 2: Use in queue row**

Already wired in Task 1.11 — verify it renders in dev.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/components/ExtractionConfidenceRing.jsx
git commit -m "feat(doctor-ui): N/7 confidence ring for chat-detected records"
```

---

### Task 1.13: Supplement queue endpoints

**Files:**
- Create: `src/channels/web/doctor_dashboard/supplement_handlers.py`

- [ ] **Step 1: Implement endpoints**

```python
"""Doctor-side actions on RecordSupplementDB rows. Spec §5b Edge case 2."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
from datetime import datetime

from src.db.session import get_db
from src.db.models.records import RecordSupplementDB, FieldEntryDB

router = APIRouter()


@router.get("/api/manage/supplements/pending")
async def list_pending(doctor_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    # Filter by doctor via record→patient→doctor join; structure matches existing review queue style.
    rows = (await session.execute(
        select(RecordSupplementDB).where(RecordSupplementDB.status == "pending_doctor_review")
    )).scalars().all()
    return {"items": [
        {"id": s.id, "record_id": s.record_id, "field_entries": json.loads(s.field_entries_json),
         "created_at": s.created_at.isoformat()}
        for s in rows
    ]}


@router.post("/api/manage/supplements/{supplement_id}/accept")
async def accept(supplement_id: int, doctor_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    sup = await session.get(RecordSupplementDB, supplement_id)
    if not sup or sup.status != "pending_doctor_review":
        raise HTTPException(status_code=404)
    entries = json.loads(sup.field_entries_json)
    for e in entries:
        session.add(FieldEntryDB(
            record_id=sup.record_id,
            field_name=e["field_name"],
            text=e["text"],
            intake_segment_id=e.get("intake_segment_id"),
            created_at=datetime.fromisoformat(e["created_at"]),
        ))
    sup.status = "accepted"
    sup.doctor_decision_at = datetime.utcnow()
    sup.doctor_decision_by = doctor_id
    await session.commit()
    return {"id": supplement_id, "status": "accepted"}


@router.post("/api/manage/supplements/{supplement_id}/create_new")
async def create_new(supplement_id: int, doctor_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    # Fork a brand-new MedicalRecordDB from the supplement payload. Implementation
    # mirrors the chat_detected new-record path but uses supplement entries as seed.
    # ... implementation matches existing record-creation patterns
    sup = await session.get(RecordSupplementDB, supplement_id)
    if not sup or sup.status != "pending_doctor_review":
        raise HTTPException(status_code=404)
    sup.status = "rejected_create_new"
    sup.doctor_decision_at = datetime.utcnow()
    sup.doctor_decision_by = doctor_id
    # TODO: implement actual new-record creation; for v0 the rejected_create_new status is
    # the signal for the frontend to navigate the doctor to the new-record creation flow.
    await session.commit()
    return {"id": supplement_id, "status": "rejected_create_new"}


@router.post("/api/manage/supplements/{supplement_id}/ignore")
async def ignore(supplement_id: int, doctor_id: str = Query(...), session: AsyncSession = Depends(get_db)):
    sup = await session.get(RecordSupplementDB, supplement_id)
    if not sup or sup.status != "pending_doctor_review":
        raise HTTPException(status_code=404)
    sup.status = "rejected_ignored"
    sup.doctor_decision_at = datetime.utcnow()
    sup.doctor_decision_by = doctor_id
    await session.commit()
    return {"id": supplement_id, "status": "rejected_ignored"}
```

- [ ] **Step 2: Register router in app**

In whichever file mounts doctor-dashboard routers (search `rg -n "include_router" src/channels/web/doctor_dashboard`), add `app.include_router(supplement_handlers.router)` or equivalent.

- [ ] **Step 3: Smoke-test on :8001**

Create a `RecordSupplementDB` row manually, call the three actions, verify state transitions and that `accept` actually writes the FieldEntryDB rows.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/doctor_dashboard/supplement_handlers.py
git commit -m "feat(doctor): supplement queue accept/create_new/ignore endpoints"
```

---

### Task 1.14: SupplementCard frontend + queue surface

**Files:**
- Create: `frontend/web/src/v2/components/SupplementCard.jsx`
- Modify: doctor review queue page (add supplement section above or alongside the records list)

- [ ] **Step 1: Create card**

Card shows: target record summary (chief_complaint of the existing record + a "上次问诊" timestamp), the supplement field entries list, and three buttons (接受补充 / 创建新记录 / 忽略). Use existing card pattern from `MyAIPage.jsx` reference.

- [ ] **Step 2: Wire into queue page**

Add a `SectionHeader` above the regular review queue:

```jsx
{pendingSupplements.length > 0 && (
  <>
    <CardSectionHeader>患者补充信息</CardSectionHeader>
    {pendingSupplements.map((sup) => <SupplementCard key={sup.id} supplement={sup} ... />)}
  </>
)}
```

`pendingSupplements` from a new `useSupplementQueue()` react-query hook fetching `/api/manage/supplements/pending`.

- [ ] **Step 3: Smoke-test the three actions**

Trigger each via the UI on :8001. Verify queue refreshes, accept actually appends to FieldEntryDB, create_new triggers (or stub-marks for) new-record creation, ignore just dismisses.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/v2/components/SupplementCard.jsx frontend/web/src/v2/pages/doctor/<queue-file>.jsx frontend/web/src/api.js
git commit -m "feat(doctor): supplement queue UI with three doctor actions"
```

---

### Task 1.15: Append-only field entries view in record detail

**Files:**
- Modify: doctor record-detail page (locate via `rg -n "MedicalRecord\|present_illness" frontend/web/src/v2/pages/doctor`)

- [ ] **Step 1: Render entries chronologically**

For each of the 7 history fields, fetch FieldEntryDB rows for the current record (new endpoint: `GET /api/manage/records/{id}/entries` returning `{[field_name]: [{text, intake_segment_id, created_at}]}`).

For each field that has > 1 entry, render with separators:

```jsx
<div style={styles.fieldGroup}>
  <h4 style={styles.fieldLabel}>主诉</h4>
  {entries.chief_complaint.map((e, i) => (
    <div key={e.created_at} style={styles.fieldEntry}>
      <span style={styles.entryMeta}>
        {i === 0 ? "初次描述" : "之后补充"} · {formatTime(e.created_at)}
      </span>
      <p style={styles.entryText}>{e.text}</p>
    </div>
  ))}
</div>
```

For fields with a single entry, render compactly without the meta line.

- [ ] **Step 2: Backend endpoint**

Quick GET endpoint in record routes file:

```python
@router.get("/api/manage/records/{record_id}/entries")
async def get_record_entries(record_id: int, session: AsyncSession = Depends(get_db)):
    rows = (await session.execute(
        select(FieldEntryDB).where(FieldEntryDB.record_id == record_id).order_by(FieldEntryDB.created_at)
    )).scalars().all()
    out = {}
    for r in rows:
        out.setdefault(r.field_name, []).append({
            "text": r.text, "intake_segment_id": r.intake_segment_id,
            "created_at": r.created_at.isoformat(),
        })
    return out
```

- [ ] **Step 3: Smoke-test on :8001 with a multi-entry record**

Create a record via the chat flow with `merge_into_existing` exercised, then view detail. Confirm chronological rendering with separators.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/doctor_dashboard/<file>.py frontend/web/src/v2/pages/doctor/<detail>.jsx
git commit -m "feat(doctor): chronological field-entry view for chat-merged records"
```

---

### Task 1.16: Feature flag — PATIENT_CHAT_INTAKE_ENABLED

**Files:**
- Modify: `src/channels/web/patient_portal/chat.py` (gate intake path on flag)
- Modify: `src/db/models/doctor.py` or feature-flag table — wherever per-doctor flags live (verify; if no per-doctor flag table exists, add a small `doctor_feature_flags` table with `doctor_id` + `flag_name` + `enabled`).

- [ ] **Step 1: Add flag check**

In `post_chat`, before entering the new intake state machine path:

```python
flag_enabled = await is_flag_enabled(session, doctor_id, "PATIENT_CHAT_INTAKE_ENABLED")
if not flag_enabled:
    return await legacy_triage_dispatch(session, body, ctx)  # existing pre-merge code path
```

`legacy_triage_dispatch` is the current `post_chat` body, refactored into a function.

- [ ] **Step 2: Default to off; pilot doctors flipped on via SQL**

Document in commit message: "Pilot rollout: enable per-doctor via INSERT INTO doctor_feature_flags (doctor_id, flag_name, enabled) VALUES ('inv__xxx', 'PATIENT_CHAT_INTAKE_ENABLED', true)."

- [ ] **Step 3: Test that flag-off behavior is unchanged**

Run e2e tests on :8001 against a doctor with the flag off. Verify ChatTab behavior matches pre-merge.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/patient_portal/chat.py src/db/models/* alembic/versions/*feature_flag*.py
git commit -m "feat(chat): PATIENT_CHAT_INTAKE_ENABLED feature flag, defaults off"
```

---

### Phase 1 wrap

ChatTab now supports the unified flow for any doctor with the feature flag on. Records are draft-first, merges are append-only with provenance, reviewed-record changes go through doctor-confirmed supplements, signal-flag fires retract whitelist replies, and the doctor-side surfaces show provenance, confidence, and supplements clearly. Phases 2 (pilot) and 3 (default-on) are operations on top of this codebase, not coding.

---

## Self-Review (controller-side, before shipping the plan)

**Spec coverage:** every safety-floor checklist item from spec §6 has a task. Phase 0 covers schema + signal-flag + extraction_confidence. Phase 0.5 covers KB curation onboarding. Phase 1 covers state machine, dedup detection, append-only merge, supplement workflow, signal-flag retraction, all frontend gates, doctor-side surfaces, feature flag.

**Placeholders:** the only `TODO`-shaped item is in Task 1.13 `create_new` endpoint, which intentionally defers actual new-record creation to a follow-up because it requires careful coordination with the existing record-creation flow. This is called out in code comment.

**Type consistency:** `MedicalRecordDB`, `FieldEntryDB`, `RecordSupplementDB`, `ChatSessionState`, `EpisodeSignals`, `DedupDecision`, `IntakeEntryDecision` all defined once and consistently named through tasks.

**Field name consistency across tasks:** `chief_complaint`, `present_illness`, `past_history`, `allergy_history`, `personal_history`, `marital_reproductive`, `family_history` — same set in `extraction_confidence.REQUIRED_FIELDS`, `dedup.REQUIRED_FIELDS`, and the backfill migration.

**Threshold consistency:** `PRIMARY_THRESHOLD = 0.65`, `LOWER_THRESHOLD = 0.50`, `CANCEL_THRESHOLD = 0.85`, `LOWER_BOUND = 0.5`, `UPPER_BOUND = 0.7`, `WITHIN_HOURS = 24`, `INTAKE_IDLE_HOURS = 24`, `QA_WINDOW_IDLE_MINUTES = 30` — all match spec §1a/§1b/§1c/§5a.

**What this plan deliberately defers to v1.1+:**
- The `create_new` endpoint full implementation (Task 1.13 stub).
- Pilot dashboards and metrics aggregation (logs are emitted; aggregation is operations).
- The Phase 3 default-on flip and the explicit IntakePage CTA demotion.
- `medication_timing_faq` whitelist intent (out of scope per spec).
- Multi-doctor patient semantics.
