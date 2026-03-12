"""历史病历导入单元测试：覆盖文本分块、预处理、预览格式化和重复检测等纯函数逻辑。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers imported directly (pure Python, no DB or LLM calls)
# ---------------------------------------------------------------------------
from services.wechat.wechat_domain import (
    _chunk_history_text,
    _preprocess_import_text,
    _format_import_preview,
    _mark_duplicates,
)


DOCTOR = "test_import_doctor"


# ---------------------------------------------------------------------------
# 1. _chunk_history_text — date-boundary splitting
# ---------------------------------------------------------------------------

def test_chunk_by_date_boundaries():
    text = (
        "2023-11-01\n头痛，恶心，BP 130/80。给予止痛片。\n\n"
        "2023-12-05\n复诊，症状改善，停药观察。\n\n"
        "2024-01-10\n随访正常，结案。"
    )
    chunks = _chunk_history_text(text)
    assert len(chunks) >= 2, f"Expected ≥2 chunks, got {chunks}"
    assert any("头痛" in c for c in chunks)
    assert any("复诊" in c for c in chunks)


# ---------------------------------------------------------------------------
# 2. _chunk_history_text — paragraph fallback
# ---------------------------------------------------------------------------

def test_chunk_by_paragraph_fallback():
    # Use paragraphs each ≥80 chars so the merge buffer flushes separately.
    para1 = "患者主诉头痛三天，无发热，血压正常130/80，给予布洛芬400mg口服，嘱多休息，一周后复诊评估疗效。"
    para2 = "患者一周后复诊，头痛明显缓解，血压维持正常范围，无新发症状，建议停药观察，一个月后门诊随访复查血压。"
    text = para1 + "\n\n" + para2
    chunks = _chunk_history_text(text)
    assert len(chunks) >= 2, f"Expected ≥2 paragraph chunks, got {chunks}"


# ---------------------------------------------------------------------------
# 3. _preprocess_import_text — strips PDF prefix
# ---------------------------------------------------------------------------

def test_preprocess_strips_pdf_prefix():
    raw = "[PDF:patient_records.pdf] 2023-01-01\n主诉头痛。"
    result = _preprocess_import_text(raw, "pdf")
    assert not result.startswith("[PDF:")
    assert "主诉头痛" in result


# ---------------------------------------------------------------------------
# 4. _preprocess_import_text — strips Word prefix
# ---------------------------------------------------------------------------

def test_preprocess_strips_word_prefix():
    raw = "[Word:history.docx] 患者既往史如下。"
    result = _preprocess_import_text(raw, "word")
    assert not result.startswith("[Word:")
    assert "患者既往史" in result


# ---------------------------------------------------------------------------
# 5. _format_import_preview — no duplicates
# ---------------------------------------------------------------------------

def test_format_preview_no_duplicates():
    chunks = [
        {
            "idx": 1,
            "raw_text": "2023-01-05\n头痛主诉。",
            "structured": {"chief_complaint": "头痛", "diagnosis": "紧张性头痛"},
            "status": "pending",
        },
        {
            "idx": 2,
            "raw_text": "2023-03-10\n腹痛主诉。",
            "structured": {"chief_complaint": "腹痛", "diagnosis": None},
            "status": "pending",
        },
    ]
    preview = _format_import_preview(chunks, "张三", "pdf")
    assert "张三" in preview
    assert "2 条" in preview
    assert "确认导入" in preview
    assert "疑似重复" not in preview


# ---------------------------------------------------------------------------
# 6. _format_import_preview — with duplicates shows warning
# ---------------------------------------------------------------------------

def test_format_preview_with_duplicates():
    chunks = [
        {
            "idx": 1,
            "raw_text": "2023-01-05\n头痛。",
            "structured": {"chief_complaint": "头痛", "diagnosis": "紧张性头痛"},
            "status": "duplicate",
        },
        {
            "idx": 2,
            "raw_text": "2023-03-10\n腹痛。",
            "structured": {"chief_complaint": "腹痛", "diagnosis": None},
            "status": "pending",
        },
    ]
    preview = _format_import_preview(chunks, "李四", "word")
    assert "疑似重复" in preview
    assert "跳过重复" in preview
    assert "1 条新记录" in preview



# ---------------------------------------------------------------------------
# 10. _mark_duplicates — marks chunk with matching chief_complaint as duplicate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_duplicates_flags_matching_complaint():
    existing_rec = SimpleNamespace(content="患者头痛伴恶心，持续3天，无发热，血压正常范围")

    chunks = [
        {
            "idx": 1,
            "raw_text": "2023-01-01\n头痛",
            "structured": {"content": "患者头痛伴恶心，持续3天，无发热，血压正常范围"},
            "status": "pending",
        },
        {
            "idx": 2,
            "raw_text": "2023-02-01\n腹泻",
            "structured": {"content": "患者腹泻水样便，每日5次，无血便，发病2天"},
            "status": "pending",
        },
    ]

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("services.wechat.wechat_import.AsyncSessionLocal", return_value=mock_session),
        patch(
            "db.crud.get_records_for_patient",
            new=AsyncMock(return_value=[existing_rec]),
        ),
    ):
        result = await _mark_duplicates(chunks, DOCTOR, patient_id=1)

    statuses = {c["idx"]: c["status"] for c in result}
    assert statuses[1] == "duplicate"
    assert statuses[2] == "pending"
