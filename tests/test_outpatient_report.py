"""门诊报告测试：验证 LLM 门诊字段提取及门诊报告 PDF 生成的正确性。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.export.outpatient_report import (
    OUTPATIENT_FIELDS,
    ExtractionError,
    extract_outpatient_fields,
)
from services.export.pdf_export import generate_outpatient_report_pdf


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_outpatient_fields_returns_all_keys():
    """Mocked LLM: all 10 field keys must appear in the result."""
    mock_response = {k: f"sample {label}" for k, label in OUTPATIENT_FIELDS}
    import json
    from types import SimpleNamespace

    fake_choice = SimpleNamespace(message=SimpleNamespace(content=json.dumps(mock_response)))
    fake_resp = SimpleNamespace(choices=[fake_choice])

    with patch("services.export.outpatient_report._get_llm_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        mock_client_fn.return_value = (mock_client, "test-model")

        records = [SimpleNamespace(content="患者张三，高血压病史。")]
        result = await extract_outpatient_fields(records, doctor_id=None)

    assert set(result.keys()) == {k for k, _ in OUTPATIENT_FIELDS}
    assert result["chief_complaint"] == "sample 主诉"


@pytest.mark.asyncio
async def test_extract_outpatient_fields_raises_on_failure():
    """On LLM error, ExtractionError is raised so callers can surface a proper HTTP error."""
    with patch("services.export.outpatient_report._get_llm_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM down"))
        mock_client_fn.return_value = (mock_client, "test-model")

        with pytest.raises(ExtractionError):
            await extract_outpatient_fields([], doctor_id=None)


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def test_generate_outpatient_report_pdf_returns_valid_pdf():
    fields = {k: f"示例内容：{label}" for k, label in OUTPATIENT_FIELDS}
    pdf = generate_outpatient_report_pdf(
        fields=fields,
        patient_name="李四",
        patient_info="男  52岁",
        clinic_name="测试诊所",
        doctor_name="王医生",
    )
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000
    assert pdf[:4] == b"%PDF"


def test_generate_outpatient_report_pdf_empty_fields():
    fields = {k: "" for k, _ in OUTPATIENT_FIELDS}
    pdf = generate_outpatient_report_pdf(fields=fields)
    assert pdf[:4] == b"%PDF"


def test_generate_outpatient_report_pdf_partial_fields():
    fields = {k: "" for k, _ in OUTPATIENT_FIELDS}
    fields["chief_complaint"] = "头痛三天"
    fields["diagnosis"] = "高血压 II 级"
    pdf = generate_outpatient_report_pdf(fields=fields, patient_name="赵六")
    assert pdf[:4] == b"%PDF"
