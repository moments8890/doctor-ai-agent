"""Unit tests for services.domain.intent_handlers._confirm_pending."""
from __future__ import annotations

import json
import pytest
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from db.models.medical_record import MedicalRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOD = "services.domain.intent_handlers._confirm_pending"


def _pending(
    pid: str = "abc123",
    doctor_id: str = "doc1",
    patient_id: int = 1,
    patient_name: str = "张三",
    draft_json: Optional[str] = None,
    raw_input: Optional[str] = None,
):
    if draft_json is None:
        draft_json = json.dumps({
            "content": "头痛三天，伴恶心呕吐",
            "tags": ["头痛", "恶心"],
            "record_type": "visit",
            "specialty_scores": [],
        }, ensure_ascii=False)
    return SimpleNamespace(
        id=pid,
        doctor_id=doctor_id,
        patient_id=patient_id,
        patient_name=patient_name,
        draft_json=draft_json,
        raw_input=raw_input,
    )


def _mock_db_ctx():
    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_db


# ============================================================================
# _parse_pending_draft
# ============================================================================

class TestParsePendingDraft:
    """Test _parse_pending_draft — parse JSON draft into MedicalRecord."""

    @pytest.mark.asyncio
    async def test_valid_draft(self):
        """Valid draft JSON → returns (MedicalRecord, cvd_raw)."""
        from services.domain.intent_handlers._confirm_pending import _parse_pending_draft
        pending = _pending()
        result = await _parse_pending_draft(pending, "doc1")
        assert result is not None
        record, cvd_raw = result
        assert isinstance(record, MedicalRecord)
        assert record.content == "头痛三天，伴恶心呕吐"
        assert cvd_raw is None

    @pytest.mark.asyncio
    async def test_draft_with_cvd_context(self):
        """Draft with cvd_context → extracted and removed from record fields."""
        from services.domain.intent_handlers._confirm_pending import _parse_pending_draft
        draft_data = {
            "content": "脑出血术后",
            "tags": [],
            "record_type": "visit",
            "specialty_scores": [],
            "cvd_context": {"diagnosis_subtype": "ICH"},
        }
        pending = _pending(draft_json=json.dumps(draft_data, ensure_ascii=False))
        result = await _parse_pending_draft(pending, "doc1")
        assert result is not None
        record, cvd_raw = result
        assert record.content == "脑出血术后"
        assert cvd_raw == {"diagnosis_subtype": "ICH"}

    @pytest.mark.asyncio
    async def test_invalid_draft_json(self):
        """Invalid JSON → returns None."""
        from services.domain.intent_handlers._confirm_pending import _parse_pending_draft
        pending = _pending(draft_json="not-valid-json{{{")
        result = await _parse_pending_draft(pending, "doc1")
        assert result is None

    @pytest.mark.asyncio
    async def test_draft_missing_required_field(self):
        """Draft missing required 'content' field → returns None."""
        from services.domain.intent_handlers._confirm_pending import _parse_pending_draft
        pending = _pending(draft_json=json.dumps({"tags": []}))
        result = await _parse_pending_draft(pending, "doc1")
        assert result is None


# ============================================================================
# _persist_pending_record
# ============================================================================

class TestPersistPendingRecord:
    """Test _persist_pending_record — save with scores, CVD context, single commit."""

    @pytest.mark.asyncio
    async def test_basic_save(self):
        """Basic save: record saved, pending confirmed, commit called."""
        from services.domain.intent_handlers._confirm_pending import _persist_pending_record
        pending = _pending()
        record = MedicalRecord(content="头痛三天", tags=["头痛"], specialty_scores=[])
        db_record = SimpleNamespace(id=100)

        mock_ctx, mock_db = _mock_db_ctx()
        mock_db.commit = AsyncMock()

        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=db_record), \
             patch(f"{_MOD}.confirm_pending_record", new_callable=AsyncMock):
            result = await _persist_pending_record(pending, record, None, "doc1")

        assert result is not None
        assert result.id == 100
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_with_specialty_scores(self):
        """Record with specialty_scores → save_specialty_scores called."""
        from services.domain.intent_handlers._confirm_pending import _persist_pending_record
        pending = _pending()
        scores = [{"score_type": "NIHSS", "score_value": 8, "raw_text": "NIHSS 8分"}]
        record = MedicalRecord(content="脑卒中", specialty_scores=scores)
        db_record = SimpleNamespace(id=101)

        mock_ctx, mock_db = _mock_db_ctx()
        mock_db.commit = AsyncMock()

        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=db_record), \
             patch(f"{_MOD}.confirm_pending_record", new_callable=AsyncMock), \
             patch("db.crud.scores.save_specialty_scores", new_callable=AsyncMock) as mock_sss:
            result = await _persist_pending_record(pending, record, None, "doc1")

        assert result is not None
        mock_sss.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_with_cvd_context(self):
        """cvd_raw present → NeuroCVDSurgicalContext validated and saved."""
        from services.domain.intent_handlers._confirm_pending import _persist_pending_record
        pending = _pending()
        record = MedicalRecord(content="脑出血", specialty_scores=[])
        db_record = SimpleNamespace(id=102)
        cvd_raw = {"diagnosis_subtype": "ICH", "hemorrhage_location": "基底节"}

        mock_ctx, mock_db = _mock_db_ctx()
        mock_db.commit = AsyncMock()

        mock_cvd = MagicMock()
        mock_cvd.has_data.return_value = True

        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=db_record), \
             patch(f"{_MOD}.confirm_pending_record", new_callable=AsyncMock), \
             patch("db.models.neuro_case.NeuroCVDSurgicalContext.model_validate", return_value=mock_cvd), \
             patch("db.crud.specialty.save_cvd_context", new_callable=AsyncMock) as mock_save_cvd:
            result = await _persist_pending_record(pending, record, cvd_raw, "doc1")

        assert result is not None
        mock_save_cvd.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_failure_returns_none(self):
        """save_record raises exception → returns None."""
        from services.domain.intent_handlers._confirm_pending import _persist_pending_record
        pending = _pending()
        record = MedicalRecord(content="内容", specialty_scores=[])

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, side_effect=Exception("DB error")):
            result = await _persist_pending_record(pending, record, None, "doc1")

        assert result is None


# ============================================================================
# save_pending_record (orchestrator)
# ============================================================================

class TestSavePendingRecord:
    """Test save_pending_record — full orchestration."""

    @pytest.mark.asyncio
    async def test_success_returns_tuple(self):
        """Successful save → returns (patient_name, record_id)."""
        from services.domain.intent_handlers._confirm_pending import save_pending_record
        pending = _pending(patient_name="张三")
        record = MedicalRecord(content="头痛三天", tags=[], specialty_scores=[])
        db_record = SimpleNamespace(id=200)

        with patch(f"{_MOD}._parse_pending_draft", new_callable=AsyncMock, return_value=(record, None)), \
             patch(f"{_MOD}._persist_pending_record", new_callable=AsyncMock, return_value=db_record), \
             patch(f"{_MOD}._fire_post_save_tasks"):
            result = await save_pending_record("doc1", pending)

        assert result is not None
        assert result == ("张三", 200)

    @pytest.mark.asyncio
    async def test_parse_failure_returns_none(self):
        """Parse fails → returns None."""
        from services.domain.intent_handlers._confirm_pending import save_pending_record
        pending = _pending(draft_json="invalid")

        with patch(f"{_MOD}._parse_pending_draft", new_callable=AsyncMock, return_value=None):
            result = await save_pending_record("doc1", pending)

        assert result is None

    @pytest.mark.asyncio
    async def test_persist_failure_returns_none(self):
        """Persist fails → returns None."""
        from services.domain.intent_handlers._confirm_pending import save_pending_record
        pending = _pending()
        record = MedicalRecord(content="内容", specialty_scores=[])

        with patch(f"{_MOD}._parse_pending_draft", new_callable=AsyncMock, return_value=(record, None)), \
             patch(f"{_MOD}._persist_pending_record", new_callable=AsyncMock, return_value=None):
            result = await save_pending_record("doc1", pending)

        assert result is None

    @pytest.mark.asyncio
    async def test_default_patient_name_when_missing(self):
        """When pending.patient_name is None → uses '未关联患者'."""
        from services.domain.intent_handlers._confirm_pending import save_pending_record
        pending = _pending(patient_name=None)
        record = MedicalRecord(content="内容", specialty_scores=[])
        db_record = SimpleNamespace(id=300)

        with patch(f"{_MOD}._parse_pending_draft", new_callable=AsyncMock, return_value=(record, None)), \
             patch(f"{_MOD}._persist_pending_record", new_callable=AsyncMock, return_value=db_record), \
             patch(f"{_MOD}._fire_post_save_tasks"):
            result = await save_pending_record("doc1", pending)

        assert result == ("未关联患者", 300)


# ============================================================================
# _fire_post_save_tasks
# ============================================================================

class TestFirePostSaveTasks:
    """Test _fire_post_save_tasks — fires audit, follow-up, auto-learn tasks."""

    @pytest.mark.asyncio
    async def test_fires_audit_task(self):
        """Always fires an audit task."""
        from services.domain.intent_handlers._confirm_pending import _fire_post_save_tasks
        record = MedicalRecord(content="头痛三天", tags=[], specialty_scores=[])
        pending = SimpleNamespace(patient_id=1, raw_input="头痛三天")

        with patch(f"{_MOD}.audit", new_callable=AsyncMock) as mock_audit, \
             patch(f"{_MOD}._bg_auto_tasks", new_callable=AsyncMock), \
             patch(f"{_MOD}._bg_auto_learn", new_callable=AsyncMock), \
             patch(f"{_MOD}._detect_cvd_keywords", return_value=False), \
             patch(f"{_MOD}.create_follow_up_task", new_callable=AsyncMock):
            _fire_post_save_tasks("doc1", record, 100, "张三", pending, None)

    @pytest.mark.asyncio
    async def test_fires_follow_up_when_tag_matches(self):
        """Tags containing '随访' → follow-up task created."""
        from services.domain.intent_handlers._confirm_pending import _fire_post_save_tasks
        record = MedicalRecord(content="头痛三天", tags=["随访复查"], specialty_scores=[])
        pending = SimpleNamespace(patient_id=1, raw_input="头痛三天")

        with patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.create_follow_up_task", new_callable=AsyncMock) as mock_fup, \
             patch(f"{_MOD}._bg_auto_tasks", new_callable=AsyncMock), \
             patch(f"{_MOD}._bg_auto_learn", new_callable=AsyncMock), \
             patch(f"{_MOD}._detect_cvd_keywords", return_value=False):
            _fire_post_save_tasks("doc1", record, 100, "张三", pending, None)

    @pytest.mark.asyncio
    async def test_fires_cvd_extraction_when_keywords_detected(self):
        """CVD keywords in raw_input + no cvd_raw → trigger CVD extraction."""
        from services.domain.intent_handlers._confirm_pending import _fire_post_save_tasks
        record = MedicalRecord(content="脑出血术后", tags=[], specialty_scores=[])
        pending = SimpleNamespace(patient_id=1, raw_input="脑出血术后")

        with patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.create_follow_up_task", new_callable=AsyncMock), \
             patch(f"{_MOD}._bg_auto_tasks", new_callable=AsyncMock), \
             patch(f"{_MOD}._bg_auto_learn", new_callable=AsyncMock), \
             patch(f"{_MOD}._detect_cvd_keywords", return_value=True), \
             patch(f"{_MOD}._bg_extract_cvd_context", new_callable=AsyncMock) as mock_cvd:
            _fire_post_save_tasks("doc1", record, 100, "张三", pending, None)
