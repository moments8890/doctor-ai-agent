"""
历史病历导入处理层：从PDF/Word/图片/语音/文本批量导入患者历史病历的业务逻辑。

Channel-agnostic domain logic. Both web and WeChat channels import from here.

This module is a thin hub that re-exports the public API from the focused
sub-modules and hosts the top-level ``handle_import_history`` entrypoint.
"""

from __future__ import annotations

from typing import Any

from utils.log import log
from db.engine import AsyncSessionLocal

# Re-exports for callers that import helpers directly from this module.
from domain.records.import_text_processing import (  # noqa: F401
    _looks_like_chat_export,
    _preprocess_import_text,
    _chunk_history_text,
    _extract_chunk_date,
    _t,
)
from domain.records.import_pipeline import (  # noqa: F401
    _mark_duplicates,
    _format_import_preview,
    _resolve_import_patient,
    _structure_chunks,
    _save_import_chunks,
    _resolve_session_patient,
    _build_import_reply,
    _handle_chat_export_import,
)


async def handle_import_history(
    text: str,
    doctor_id: str,
    intent_result: Any,
) -> str:
    """批量导入患者历史病历（PDF/Word/图片/语音/文字），识别来源并结构化保存。"""
    source = intent_result.extra_data.get("source", "text")
    patient_name = intent_result.patient_name

    patient_name, patient_id, ocr_gender, ocr_age = await _resolve_session_patient(
        doctor_id, patient_name, source, text
    )
    patient_name, patient_id, _needs_create = await _resolve_import_patient(
        doctor_id, patient_name, patient_id, source, ocr_gender, ocr_age
    )

    if source == "chat_export" or (source == "text" and _looks_like_chat_export(text)):
        early = await _handle_chat_export_import(text, doctor_id, intent_result, source)
        if early is not None:
            return early
        sender_filter = intent_result.extra_data.get("sender_filter")
        from channels.wechat.wechat_chat_export import list_senders
        senders = list_senders(text)
        clean_text = _preprocess_import_text(
            text, source,
            sender_filter=sender_filter or (senders[0] if senders else None),
        )
    else:
        clean_text = _preprocess_import_text(text, source)

    chunks_raw = _chunk_history_text(clean_text)
    if not chunks_raw:
        return "未能从内容中提取有效病历记录，请检查格式后重试。"

    total_chunks = len(chunks_raw)
    structured_chunks, failed_chunks = await _structure_chunks(chunks_raw, doctor_id)
    if not structured_chunks:
        return "未能解析病历内容，请确认文件是否包含可读文字后重试。"

    if patient_id:
        structured_chunks = await _mark_duplicates(structured_chunks, doctor_id, patient_id)

    # Deferred patient creation: only auto-create after structuring proves viable.
    if patient_id is None and _needs_create and patient_name:
        from db.crud.patient import create_patient
        try:
            async with AsyncSessionLocal() as _session:
                patient, _access_code = await create_patient(
                    _session, doctor_id, patient_name, ocr_gender, ocr_age
                )
                patient_id = patient.id
                log(f"[Import] OCR auto-created patient {patient_name} id={patient_id}")
        except Exception as e:
            log(f"[Import] OCR patient create failed: {e}")

    # Require a valid patient_id before bulk-persisting records.
    if patient_id is None:
        return "⚠️ 无法确定患者身份，请先指定患者姓名再导入历史病历。"

    log(f"[silent-save] bulk import doctor={doctor_id} patient_id={patient_id} chunks={len(structured_chunks)}")
    saved = await _save_import_chunks(structured_chunks, doctor_id, patient_id)
    log(f"[silent-save] bulk import done doctor={doctor_id} patient_id={patient_id} saved={saved}/{len(structured_chunks)}")

    return _build_import_reply(saved, patient_name, failed_chunks, total_chunks)
