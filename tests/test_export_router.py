"""Export router unit tests: PDF generation, template CRUD, helper functions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import routers.export as export_mod


# ---------------------------------------------------------------------------
# Pure helper tests (no I/O)
# ---------------------------------------------------------------------------


class TestSha256Hex:
    def test_deterministic(self):
        assert export_mod._sha256_hex(b"hello") == export_mod._sha256_hex(b"hello")

    def test_different_inputs(self):
        assert export_mod._sha256_hex(b"a") != export_mod._sha256_hex(b"b")


class TestSafePdfFilename:
    def test_basic(self):
        name = export_mod._safe_pdf_filename("病历", 42)
        assert name == "病历_42.pdf"

    def test_with_suffix(self):
        name = export_mod._safe_pdf_filename("报告", 1, suffix="extra-info")
        assert name.endswith(".pdf")
        assert "1" in name
        assert "报告" in name

    def test_suffix_sanitized(self):
        name = export_mod._safe_pdf_filename("prefix", 5, suffix="a/b?c")
        assert "/" not in name
        assert "?" not in name


class TestContentDisposition:
    def test_ascii(self):
        result = export_mod._content_disposition("test.pdf")
        assert "attachment" in result
        assert "filename*=UTF-8''" in result

    def test_unicode(self):
        result = export_mod._content_disposition("病历_42.pdf")
        assert "UTF-8''" in result


class TestValidateMagicBytes:
    def test_pdf_magic_matches(self):
        export_mod._validate_magic_bytes(b"%PDF-1.4 content", "application/pdf")

    def test_pdf_magic_mismatch_declared(self):
        with pytest.raises(HTTPException) as exc:
            export_mod._validate_magic_bytes(b"%PDF-1.4 content", "image/jpeg")
        assert exc.value.status_code == 415

    def test_jpeg_magic_matches(self):
        export_mod._validate_magic_bytes(b"\xff\xd8\xff some jpeg", "image/jpeg")

    def test_png_magic_matches(self):
        export_mod._validate_magic_bytes(b"\x89PNG\r\n\x1a\n rest", "image/png")

    def test_riff_webp_matches(self):
        data = b"RIFF____WEBP" + b"\x00" * 20
        export_mod._validate_magic_bytes(data, "image/webp")

    def test_riff_not_webp_skips(self):
        data = b"RIFF____NOPE" + b"\x00" * 20
        export_mod._validate_magic_bytes(data, "text/plain")

    def test_no_match_non_text_logs_warning(self):
        export_mod._validate_magic_bytes(
            b"\x00\x00\x00\x00", "application/octet-stream"
        )

    def test_docx_magic_matches(self):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        export_mod._validate_magic_bytes(b"PK\x03\x04 rest of zip", mime)

    def test_docx_magic_mismatch(self):
        with pytest.raises(HTTPException) as exc:
            export_mod._validate_magic_bytes(b"PK\x03\x04 rest of zip", "image/png")
        assert exc.value.status_code == 415


class TestBuildPatientInfoLine:
    def test_gender_and_birth(self):
        patient = SimpleNamespace(gender="男", year_of_birth=1980)
        result = export_mod._build_patient_info_line(patient)
        assert "男" in result
        assert "岁" in result

    def test_gender_only(self):
        patient = SimpleNamespace(gender="女", year_of_birth=None)
        result = export_mod._build_patient_info_line(patient)
        assert result == "女"

    def test_no_info(self):
        patient = SimpleNamespace(gender=None, year_of_birth=None)
        result = export_mod._build_patient_info_line(patient)
        assert result is None


# ---------------------------------------------------------------------------
# Endpoint tests — mock _resolve_ui_doctor_id + all DB + PDF generation
# ---------------------------------------------------------------------------


def _fake_patient(
    pid=1, name="张三", doctor_id="web_doctor", gender="男", year_of_birth=1980
):
    return SimpleNamespace(
        id=pid,
        name=name,
        doctor_id=doctor_id,
        gender=gender,
        year_of_birth=year_of_birth,
    )


def _fake_record(rid=10, patient_id=1, doctor_id="web_doctor"):
    return SimpleNamespace(
        id=rid, patient_id=patient_id, doctor_id=doctor_id, created_at=None
    )


def _mock_db_context(patient, records):
    """Async context manager mock for patient + records queries."""
    db = AsyncMock()
    patient_result = MagicMock()
    patient_result.scalar_one_or_none.return_value = patient

    records_result = MagicMock()
    records_result.scalars.return_value.all.return_value = records

    db.execute = AsyncMock(side_effect=[patient_result, records_result])

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# Patch _resolve_ui_doctor_id so we bypass auth resolution
_RESOLVE = "routers.export._resolve_ui_doctor_id"


@pytest.mark.asyncio
async def test_export_patient_pdf_success():
    patient = _fake_patient()
    records = [_fake_record()]
    pdf_bytes = b"%PDF-1.4 fake content"

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export.AsyncSessionLocal",
            return_value=_mock_db_context(patient, records),
        ),
        patch(
            "routers.export.generate_records_pdf", return_value=pdf_bytes
        ) as gen_mock,
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        resp = await export_mod.export_patient_pdf(
            patient_id=1, doctor_id="web_doctor", authorization=None, limit=200
        )

    assert resp.status_code == 200
    assert resp.media_type == "application/pdf"
    assert resp.body == pdf_bytes
    gen_mock.assert_called_once()


@pytest.mark.asyncio
async def test_export_patient_pdf_not_found():
    db = AsyncMock()
    patient_result = MagicMock()
    patient_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=patient_result)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch("routers.export.AsyncSessionLocal", return_value=ctx),
        patch("routers.export.audit", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod.export_patient_pdf(
                patient_id=999,
                doctor_id="web_doctor",
                authorization=None,
                limit=200,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_export_patient_pdf_generation_failure():
    patient = _fake_patient()
    records = [_fake_record()]

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export.AsyncSessionLocal",
            return_value=_mock_db_context(patient, records),
        ),
        patch(
            "routers.export.generate_records_pdf",
            side_effect=RuntimeError("render fail"),
        ),
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod.export_patient_pdf(
                patient_id=1,
                doctor_id="web_doctor",
                authorization=None,
                limit=200,
            )
    assert exc.value.status_code == 500
    assert "PDF generation failed" in exc.value.detail


# ---------------------------------------------------------------------------
# Single record export
# ---------------------------------------------------------------------------


def _mock_record_db_context(record, patient_obj=None):
    """Mock for record query + optional patient query."""
    db = AsyncMock()
    record_result = MagicMock()
    record_result.scalar_one_or_none.return_value = record

    if record is not None and record.patient_id is not None:
        patient_result = MagicMock()
        patient_result.scalar_one_or_none.return_value = patient_obj
        db.execute = AsyncMock(side_effect=[record_result, patient_result])
    else:
        db.execute = AsyncMock(return_value=record_result)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_export_record_pdf_success():
    record = _fake_record()
    patient = _fake_patient()
    pdf_bytes = b"%PDF-1.4 record pdf"

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export.AsyncSessionLocal",
            return_value=_mock_record_db_context(record, patient),
        ),
        patch("routers.export.generate_records_pdf", return_value=pdf_bytes),
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        resp = await export_mod.export_record_pdf(
            record_id=10, doctor_id="web_doctor", authorization=None
        )

    assert resp.status_code == 200
    assert resp.body == pdf_bytes


@pytest.mark.asyncio
async def test_export_record_pdf_not_found():
    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export.AsyncSessionLocal",
            return_value=_mock_record_db_context(None),
        ),
        patch("routers.export.audit", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod.export_record_pdf(
                record_id=999, doctor_id="web_doctor", authorization=None
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_export_record_pdf_generation_failure():
    record = _fake_record()
    patient = _fake_patient()

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export.AsyncSessionLocal",
            return_value=_mock_record_db_context(record, patient),
        ),
        patch(
            "routers.export.generate_records_pdf",
            side_effect=RuntimeError("fail"),
        ),
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod.export_record_pdf(
                record_id=10, doctor_id="web_doctor", authorization=None
            )
    assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# Outpatient report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_outpatient_report_success():
    patient = _fake_patient()
    records = [_fake_record()]
    fields = {"chief_complaint": "头痛", "diagnosis": "偏头痛"}
    pdf_bytes = b"%PDF-outpatient"

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export.AsyncSessionLocal",
            return_value=_mock_db_context(patient, records),
        ),
        patch(
            "routers.export._extract_outpatient_fields_safe",
            new=AsyncMock(return_value=fields),
        ),
        patch(
            "routers.export.generate_outpatient_report_pdf",
            return_value=pdf_bytes,
        ),
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        resp = await export_mod.export_outpatient_report(
            patient_id=1, doctor_id="web_doctor", authorization=None, limit=200
        )

    assert resp.status_code == 200
    assert resp.body == pdf_bytes


@pytest.mark.asyncio
async def test_export_outpatient_report_no_records():
    patient = _fake_patient()

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export.AsyncSessionLocal",
            return_value=_mock_db_context(patient, []),
        ),
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod.export_outpatient_report(
                patient_id=1,
                doctor_id="web_doctor",
                authorization=None,
                limit=200,
            )
    assert exc.value.status_code == 404
    assert "No records" in exc.value.detail


@pytest.mark.asyncio
async def test_export_outpatient_report_pdf_render_failure():
    patient = _fake_patient()
    records = [_fake_record()]
    fields = {"chief_complaint": "头痛"}

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export.AsyncSessionLocal",
            return_value=_mock_db_context(patient, records),
        ),
        patch(
            "routers.export._extract_outpatient_fields_safe",
            new=AsyncMock(return_value=fields),
        ),
        patch(
            "routers.export.generate_outpatient_report_pdf",
            side_effect=RuntimeError("render"),
        ),
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod.export_outpatient_report(
                patient_id=1,
                doctor_id="web_doctor",
                authorization=None,
                limit=200,
            )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_extract_outpatient_fields_safe_extraction_error():
    """_extract_outpatient_fields_safe converts ExtractionError -> 502."""
    from services.export.outpatient_report import ExtractionError

    with patch(
        "services.export.outpatient_report.extract_outpatient_fields",
        new=AsyncMock(side_effect=ExtractionError("llm down")),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod._extract_outpatient_fields_safe([], None, "doc1", 1)
    assert exc.value.status_code == 502


# ---------------------------------------------------------------------------
# Template endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_template_unsupported_type():
    file = MagicMock()
    file.content_type = "application/zip"

    with patch(_RESOLVE, return_value="web_doctor"):
        with pytest.raises(HTTPException) as exc:
            await export_mod.upload_report_template(
                file=file, doctor_id="web_doctor", authorization=None
            )
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_template_too_large():
    file = MagicMock()
    file.content_type = "text/plain"
    file.read = AsyncMock(return_value=b"x" * (1024 * 1024 + 1))

    with patch(_RESOLVE, return_value="web_doctor"):
        with pytest.raises(HTTPException) as exc:
            await export_mod.upload_report_template(
                file=file, doctor_id="web_doctor", authorization=None
            )
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_upload_template_empty_text():
    file = MagicMock()
    file.content_type = "text/plain"
    file.read = AsyncMock(return_value=b"   ")
    file.filename = "empty.txt"

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export._extract_template_text",
            new=AsyncMock(return_value="   "),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod.upload_report_template(
                file=file, doctor_id="web_doctor", authorization=None
            )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_upload_template_success():
    file = MagicMock()
    file.content_type = "text/plain"
    file.read = AsyncMock(return_value=b"template text content")
    file.filename = "my_template.txt"

    db = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "routers.export._extract_template_text",
            new=AsyncMock(return_value="template text content"),
        ),
        patch("db.crud.upsert_system_prompt", new=AsyncMock()),
        patch("routers.export.AsyncSessionLocal", return_value=ctx),
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        resp = await export_mod.upload_report_template(
            file=file, doctor_id="web_doctor", authorization=None
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_template_status_exists():
    row = SimpleNamespace(content="some template content")
    db = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "db.crud.get_system_prompt",
            new=AsyncMock(return_value=row),
        ),
        patch("routers.export.AsyncSessionLocal", return_value=ctx),
    ):
        result = await export_mod.get_template_status(
            doctor_id="web_doctor", authorization=None
        )

    assert result["has_template"] is True
    assert result["chars"] == len("some template content")


@pytest.mark.asyncio
async def test_get_template_status_not_exists():
    db = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch(
            "db.crud.get_system_prompt",
            new=AsyncMock(return_value=None),
        ),
        patch("routers.export.AsyncSessionLocal", return_value=ctx),
    ):
        result = await export_mod.get_template_status(
            doctor_id="web_doctor", authorization=None
        )

    assert result["has_template"] is False
    assert result["chars"] == 0


@pytest.mark.asyncio
async def test_delete_template():
    db = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(_RESOLVE, return_value="web_doctor"),
        patch("db.crud.upsert_system_prompt", new=AsyncMock()),
        patch("routers.export.AsyncSessionLocal", return_value=ctx),
        patch("routers.export.audit", new=AsyncMock()),
        patch("asyncio.create_task"),
    ):
        result = await export_mod.delete_report_template(
            doctor_id="web_doctor", authorization=None
        )

    assert result["status"] == "deleted"


# ---------------------------------------------------------------------------
# Template text extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_template_text_plain():
    result = await export_mod._extract_template_text(b"hello world", "text/plain")
    assert result == "hello world"


@pytest.mark.asyncio
async def test_extract_template_text_pdf():
    with patch("routers.export._extract_pdf_text", return_value="pdf text"):
        result = await export_mod._extract_template_text(
            b"%PDF", "application/pdf"
        )
    assert result == "pdf text"


@pytest.mark.asyncio
async def test_extract_template_text_docx():
    mime = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    with patch("routers.export._extract_docx_text", return_value="docx text"):
        result = await export_mod._extract_template_text(b"PK\x03\x04", mime)
    assert result == "docx text"


@pytest.mark.asyncio
async def test_extract_template_text_msword():
    with patch("routers.export._extract_docx_text", return_value="word text"):
        result = await export_mod._extract_template_text(
            b"data", "application/msword"
        )
    assert result == "word text"


@pytest.mark.asyncio
async def test_extract_template_text_image():
    with patch(
        "routers.export._extract_image_text",
        new=AsyncMock(return_value="ocr text"),
    ):
        result = await export_mod._extract_template_text(
            b"\xff\xd8\xff", "image/jpeg"
        )
    assert result == "ocr text"


@pytest.mark.asyncio
async def test_extract_template_text_unknown():
    result = await export_mod._extract_template_text(
        b"data", "application/octet-stream"
    )
    assert result == ""


def test_extract_pdf_text_pypdf():
    import sys

    mock_pypdf = MagicMock()
    page = MagicMock()
    page.extract_text.return_value = "page1 text"
    mock_pypdf.PdfReader.return_value.pages = [page]

    with patch.dict(sys.modules, {"pypdf": mock_pypdf}):
        result = export_mod._extract_pdf_text(b"fake pdf bytes")
    assert "page1 text" in result


def test_extract_pdf_text_fallback_to_raw():
    """When both pypdf and pdfminer unavailable, fall back to raw decode."""
    with patch(
        "builtins.__import__", side_effect=ImportError("no module")
    ):
        result = export_mod._extract_pdf_text(b"plain text fallback")
    assert "plain text fallback" in result


def test_extract_docx_text_success():
    with patch("docx.Document") as doc_cls:
        p1 = MagicMock()
        p1.text = "paragraph 1"
        p2 = MagicMock()
        p2.text = "paragraph 2"
        doc_cls.return_value.paragraphs = [p1, p2]
        result = export_mod._extract_docx_text(b"fake docx")
    assert "paragraph 1" in result
    assert "paragraph 2" in result


def test_extract_docx_text_failure():
    with patch("docx.Document", side_effect=ImportError("no docx")):
        result = export_mod._extract_docx_text(b"fake")
    assert result == ""


@pytest.mark.asyncio
async def test_extract_image_text_success():
    with patch(
        "services.ai.vision.extract_text_from_image",
        new=AsyncMock(return_value="ocr result"),
    ):
        result = await export_mod._extract_image_text(b"img", "image/png")
    assert result == "ocr result"


@pytest.mark.asyncio
async def test_extract_image_text_empty_raises_422():
    with patch(
        "services.ai.vision.extract_text_from_image",
        new=AsyncMock(return_value="   "),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod._extract_image_text(b"img", "image/png")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_extract_image_text_error_raises_500():
    with patch(
        "services.ai.vision.extract_text_from_image",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(HTTPException) as exc:
            await export_mod._extract_image_text(b"img", "image/png")
    assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# _fetch_patient_and_records (direct helper test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_patient_and_records_success():
    patient = _fake_patient()
    records = [_fake_record()]
    db = AsyncMock()
    patient_result = MagicMock()
    patient_result.scalar_one_or_none.return_value = patient
    records_result = MagicMock()
    records_result.scalars.return_value.all.return_value = records
    db.execute = AsyncMock(side_effect=[patient_result, records_result])

    p, recs = await export_mod._fetch_patient_and_records(
        db, 1, "web_doctor", 200
    )
    assert p.name == "张三"
    assert len(recs) == 1


@pytest.mark.asyncio
async def test_fetch_patient_and_records_not_found():
    db = AsyncMock()
    patient_result = MagicMock()
    patient_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=patient_result)

    with pytest.raises(HTTPException) as exc:
        await export_mod._fetch_patient_and_records(db, 999, "web_doctor", 200)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# _fetch_record_and_patient_name (direct helper test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_record_and_patient_name_success():
    record = _fake_record(rid=10, patient_id=1)
    patient = _fake_patient()
    db = AsyncMock()
    record_result = MagicMock()
    record_result.scalar_one_or_none.return_value = record
    patient_result = MagicMock()
    patient_result.scalar_one_or_none.return_value = patient
    db.execute = AsyncMock(side_effect=[record_result, patient_result])

    rec, pname = await export_mod._fetch_record_and_patient_name(
        db, 10, "web_doctor"
    )
    assert rec.id == 10
    assert pname == "张三"


@pytest.mark.asyncio
async def test_fetch_record_and_patient_name_no_patient():
    record = SimpleNamespace(id=10, patient_id=None, doctor_id="web_doctor")
    db = AsyncMock()
    record_result = MagicMock()
    record_result.scalar_one_or_none.return_value = record
    db.execute = AsyncMock(return_value=record_result)

    rec, pname = await export_mod._fetch_record_and_patient_name(
        db, 10, "web_doctor"
    )
    assert rec.id == 10
    assert pname is None


@pytest.mark.asyncio
async def test_fetch_record_and_patient_name_not_found():
    db = AsyncMock()
    record_result = MagicMock()
    record_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=record_result)

    with pytest.raises(HTTPException) as exc:
        await export_mod._fetch_record_and_patient_name(
            db, 999, "web_doctor"
        )
    assert exc.value.status_code == 404
