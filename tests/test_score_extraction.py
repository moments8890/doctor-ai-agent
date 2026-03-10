"""专科量表评分测试：验证量表关键词检测、LLM 评分提取及微信草稿预览中评分展示的正确性。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from services.patient.score_extraction import detect_score_keywords, extract_specialty_scores
from utils.response_formatting import format_draft_preview
from db.models.medical_record import MedicalRecord


# ---------------------------------------------------------------------------
# detect_score_keywords
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("NIHSS评分8分", True),
    ("nihss 12", True),
    ("mRS 3级", True),
    ("改良Rankin评分2", True),
    ("GCS评分15分", True),
    ("MMSE 26分", True),
    ("moca评分28", True),
    ("UPDRS评分40", True),
    ("患者今日复诊，血压控制良好", False),
    ("头痛、发热，体温38.5℃", False),
    ("", False),
])
def test_detect_score_keywords(text, expected):
    assert detect_score_keywords(text) == expected


# ---------------------------------------------------------------------------
# extract_specialty_scores (LLM mocked)
# ---------------------------------------------------------------------------

def _make_score_completion(scores: list):
    import json
    from types import SimpleNamespace
    msg = SimpleNamespace(content=json.dumps({"scores": scores}))
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


@pytest.fixture
def mock_score_llm(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(
        "services.patient.score_extraction.AsyncOpenAI",
        lambda **kw: type("_Client", (), {"chat": type("_C", (), {"completions": type("_CC", (), {"create": mock})()})()})(),
    )
    return mock


async def test_extract_specialty_scores_returns_list(monkeypatch):
    scores = [{"score_type": "NIHSS", "score_value": 8, "raw_text": "NIHSS 8分"}]

    async def _fake_create(*a, **kw):
        return _make_score_completion(scores)

    with patch("services.patient.score_extraction.AsyncOpenAI") as MockClient:
        MockClient.return_value.chat.completions.create = AsyncMock(side_effect=_fake_create)
        result = await extract_specialty_scores("NIHSS评分8分")

    assert result == scores


async def test_extract_specialty_scores_returns_empty_on_failure(monkeypatch):
    async def _fail(*a, **kw):
        raise RuntimeError("LLM offline")

    with patch("services.patient.score_extraction.AsyncOpenAI") as MockClient:
        MockClient.return_value.chat.completions.create = AsyncMock(side_effect=_fail)
        result = await extract_specialty_scores("NIHSS评分8分")

    assert result == []


# ---------------------------------------------------------------------------
# format_draft_preview with specialty scores
# ---------------------------------------------------------------------------

def test_format_draft_preview_shows_scores():
    record = MedicalRecord(
        content="患者卒中后复诊，NIHSS 8分。",
        tags=["卒中", "NIHSS"],
        specialty_scores=[
            {"score_type": "NIHSS", "score_value": 8, "raw_text": "NIHSS 8分"},
        ],
    )
    preview = format_draft_preview(record, patient_name="张三")
    assert "📊 量表评分" in preview
    assert "NIHSS" in preview
    assert "8" in preview
    assert "请核对原始记录" in preview


def test_format_draft_preview_no_scores_section_when_empty():
    record = MedicalRecord(content="血压 140/90，控制良好。", tags=["高血压"])
    preview = format_draft_preview(record)
    assert "📊" not in preview


def test_format_draft_preview_score_without_value():
    record = MedicalRecord(
        content="患者mRS评分待测。",
        tags=[],
        specialty_scores=[
            {"score_type": "mRS", "score_value": None, "raw_text": "mRS评分待测"},
        ],
    )
    preview = format_draft_preview(record)
    assert "mRS" in preview
    assert "mRS评分待测" in preview
