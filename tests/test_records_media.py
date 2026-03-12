"""Unit tests for routers/records_media.py — media upload endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from db.models.medical_record import MedicalRecord
from routers.records_media import (
    create_record_from_audio,
    create_record_from_image,
    create_record_from_text,
    extract_file_for_chat,
    ocr_image_only,
    record_history,
    transcribe_audio_only,
)


class _Upload:
    """Fake UploadFile for testing."""

    def __init__(
        self,
        *,
        content_type: str = "image/jpeg",
        data: bytes = b"fakebytes",
        filename: str = "test.bin",
    ):
        self.content_type = content_type
        self._data = data
        self.filename = filename

    async def read(self):
        return self._data


def _record():
    return MedicalRecord(content="胸痛 冠心病 随访", tags=["冠心病"])


class _TextInput:
    """Stub matching routers.records.TextInput."""

    def __init__(self, text: str):
        self.text = text


# ---------------------------------------------------------------------------
# /from-text
# ---------------------------------------------------------------------------
class TestCreateRecordFromText:
    @pytest.mark.asyncio
    async def test_success(self):
        body = _TextInput("患者胸痛一天")
        with patch("routers.records_media.structure_medical_record", new_callable=AsyncMock, return_value=_record()):
            result = await create_record_from_text(body)
        assert result.content == "胸痛 冠心病 随访"

    @pytest.mark.asyncio
    async def test_empty_text_raises_422(self):
        body = _TextInput("   ")
        with pytest.raises(HTTPException) as exc_info:
            await create_record_from_text(body)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_value_error_raises_422(self):
        body = _TextInput("bad record")
        with patch("routers.records_media.structure_medical_record", new_callable=AsyncMock, side_effect=ValueError("bad")):
            with pytest.raises(HTTPException) as exc_info:
                await create_record_from_text(body)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_generic_error_raises_500(self):
        body = _TextInput("some text")
        with patch("routers.records_media.structure_medical_record", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc_info:
                await create_record_from_text(body)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# /from-image
# ---------------------------------------------------------------------------
class TestCreateRecordFromImage:
    @pytest.mark.asyncio
    async def test_success(self):
        upload = _Upload(content_type="image/png")
        with patch("routers.records_media.extract_text_from_image", new_callable=AsyncMock, return_value="OCR结果") as mock_ocr, \
             patch("routers.records_media.structure_medical_record", new_callable=AsyncMock, return_value=_record()):
            result = await create_record_from_image(upload)
        assert result.content == "胸痛 冠心病 随访"
        mock_ocr.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unsupported_type_raises_422(self):
        upload = _Upload(content_type="application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            await create_record_from_image(upload)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_value_error_raises_422(self):
        upload = _Upload(content_type="image/jpeg")
        with patch("routers.records_media.extract_text_from_image", new_callable=AsyncMock, return_value="text"), \
             patch("routers.records_media.structure_medical_record", new_callable=AsyncMock, side_effect=ValueError("bad")):
            with pytest.raises(HTTPException) as exc_info:
                await create_record_from_image(upload)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_generic_error_raises_500(self):
        upload = _Upload(content_type="image/jpeg")
        with patch("routers.records_media.extract_text_from_image", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc_info:
                await create_record_from_image(upload)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# /from-audio
# ---------------------------------------------------------------------------
class TestCreateRecordFromAudio:
    @pytest.mark.asyncio
    async def test_success(self):
        upload = _Upload(content_type="audio/mpeg", filename="rec.mp3")
        with patch("routers.records_media.transcribe_audio", new_callable=AsyncMock, return_value="转录文本") as mock_asr, \
             patch("routers.records_media.structure_medical_record", new_callable=AsyncMock, return_value=_record()):
            result = await create_record_from_audio(upload)
        assert result.content == "胸痛 冠心病 随访"
        mock_asr.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unsupported_type_raises_422(self):
        upload = _Upload(content_type="video/mp4")
        with pytest.raises(HTTPException) as exc_info:
            await create_record_from_audio(upload)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_value_error_raises_422(self):
        upload = _Upload(content_type="audio/wav")
        with patch("routers.records_media.transcribe_audio", new_callable=AsyncMock, return_value="text"), \
             patch("routers.records_media.structure_medical_record", new_callable=AsyncMock, side_effect=ValueError("bad")):
            with pytest.raises(HTTPException) as exc_info:
                await create_record_from_audio(upload)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_generic_error_raises_500(self):
        upload = _Upload(content_type="audio/wav")
        with patch("routers.records_media.transcribe_audio", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc_info:
                await create_record_from_audio(upload)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# /transcribe
# ---------------------------------------------------------------------------
class TestTranscribeAudioOnly:
    @pytest.mark.asyncio
    async def test_success(self):
        upload = _Upload(content_type="audio/mpeg", filename="rec.mp3")
        with patch("routers.records_media.transcribe_audio", new_callable=AsyncMock, return_value="hello"):
            result = await transcribe_audio_only(upload)
        assert result == {"text": "hello"}

    @pytest.mark.asyncio
    async def test_unsupported_non_audio_raises_422(self):
        upload = _Upload(content_type="text/plain")
        with pytest.raises(HTTPException) as exc_info:
            await transcribe_audio_only(upload)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_generic_audio_type_accepted(self):
        """An audio/* type not in the explicit set is still accepted."""
        upload = _Upload(content_type="audio/x-custom")
        with patch("routers.records_media.transcribe_audio", new_callable=AsyncMock, return_value="ok"):
            result = await transcribe_audio_only(upload)
        assert result == {"text": "ok"}

    @pytest.mark.asyncio
    async def test_content_type_with_params_stripped(self):
        upload = _Upload(content_type="audio/mpeg; charset=utf-8")
        with patch("routers.records_media.transcribe_audio", new_callable=AsyncMock, return_value="ok"):
            result = await transcribe_audio_only(upload)
        assert result == {"text": "ok"}

    @pytest.mark.asyncio
    async def test_error_raises_500(self):
        upload = _Upload(content_type="audio/wav")
        with patch("routers.records_media.transcribe_audio", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
            with pytest.raises(HTTPException) as exc_info:
                await transcribe_audio_only(upload)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# /ocr
# ---------------------------------------------------------------------------
class TestOcrImageOnly:
    @pytest.mark.asyncio
    async def test_success(self):
        upload = _Upload(content_type="image/png")
        with patch("routers.records_media.extract_text_from_image", new_callable=AsyncMock, return_value="OCR文本"):
            result = await ocr_image_only(upload)
        assert result == {"text": "OCR文本"}

    @pytest.mark.asyncio
    async def test_unsupported_type_raises_422(self):
        upload = _Upload(content_type="application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            await ocr_image_only(upload)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_content_type_params_stripped(self):
        upload = _Upload(content_type="image/jpeg; charset=utf-8")
        with patch("routers.records_media.extract_text_from_image", new_callable=AsyncMock, return_value="ok"):
            result = await ocr_image_only(upload)
        assert result == {"text": "ok"}

    @pytest.mark.asyncio
    async def test_error_raises_500(self):
        upload = _Upload(content_type="image/png")
        with patch("routers.records_media.extract_text_from_image", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
            with pytest.raises(HTTPException) as exc_info:
                await ocr_image_only(upload)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# /extract-file
# ---------------------------------------------------------------------------
class TestExtractFileForChat:
    @pytest.mark.asyncio
    async def test_pdf_with_llm_success(self):
        upload = _Upload(content_type="application/pdf", filename="report.pdf", data=b"pdf data")
        with patch("routers.records_media.extract_text_from_pdf_llm", new_callable=AsyncMock, return_value="PDF内容"):
            result = await extract_file_for_chat(upload)
        assert result == {"text": "PDF内容", "filename": "report.pdf"}

    @pytest.mark.asyncio
    async def test_pdf_fallback_when_llm_returns_none(self):
        upload = _Upload(content_type="application/pdf", filename="report.pdf", data=b"pdf data")
        with patch("routers.records_media.extract_text_from_pdf_llm", new_callable=AsyncMock, return_value=None), \
             patch("routers.records_media.extract_text_from_pdf", return_value="fallback text"):
            result = await extract_file_for_chat(upload)
        assert result["text"] == "fallback text"

    @pytest.mark.asyncio
    async def test_pdf_by_extension(self):
        upload = _Upload(content_type="application/octet-stream", filename="report.PDF", data=b"data")
        with patch("routers.records_media.extract_text_from_pdf_llm", new_callable=AsyncMock, return_value="ext text"):
            result = await extract_file_for_chat(upload)
        assert result["text"] == "ext text"

    @pytest.mark.asyncio
    async def test_image_extraction(self):
        upload = _Upload(content_type="image/jpeg", filename="photo.jpg", data=b"img data")
        with patch("routers.records_media.extract_text_from_image", new_callable=AsyncMock, return_value="图片文本"):
            result = await extract_file_for_chat(upload)
        assert result == {"text": "图片文本", "filename": "photo.jpg"}

    @pytest.mark.asyncio
    async def test_unsupported_type_raises_422(self):
        upload = _Upload(content_type="text/html", filename="page.html", data=b"<html>")
        with pytest.raises(HTTPException) as exc_info:
            await extract_file_for_chat(upload)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_file_too_large_raises_413(self):
        big_data = b"x" * (21 * 1024 * 1024)  # 21 MB
        upload = _Upload(content_type="application/pdf", filename="big.pdf", data=big_data)
        with pytest.raises(HTTPException) as exc_info:
            await extract_file_for_chat(upload)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_generic_error_raises_500(self):
        upload = _Upload(content_type="image/png", filename="img.png", data=b"data")
        with patch("routers.records_media.extract_text_from_image", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc_info:
                await extract_file_for_chat(upload)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# /{record_id}/history
# ---------------------------------------------------------------------------
class TestRecordHistory:
    @pytest.mark.asyncio
    async def test_returns_versions(self):
        from datetime import datetime

        mock_rec = SimpleNamespace(id=1, doctor_id="doc1")
        mock_version = SimpleNamespace(
            id=10, old_content="old", old_tags="[\"tag1\"]",
            old_record_type="门诊", changed_at=datetime(2026, 3, 10),
        )

        mock_db = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = mock_rec
        mock_db.execute.return_value = exec_result

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.records_media.resolve_doctor_id_from_auth_or_fallback", return_value="doc1"), \
             patch("routers.records_media.AsyncSessionLocal", return_value=ctx), \
             patch("db.crud.get_record_versions", new_callable=AsyncMock, return_value=[mock_version]):
            result = await record_history(record_id=1, doctor_id="doc1")

        assert result["record_id"] == 1
        assert len(result["versions"]) == 1
        assert result["versions"][0]["old_content"] == "old"

    @pytest.mark.asyncio
    async def test_record_not_found_raises_404(self):
        mock_db = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = exec_result

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routers.records_media.resolve_doctor_id_from_auth_or_fallback", return_value="doc1"), \
             patch("routers.records_media.AsyncSessionLocal", return_value=ctx):
            with pytest.raises(HTTPException) as exc_info:
                await record_history(record_id=999, doctor_id="doc1")
        assert exc_info.value.status_code == 404
