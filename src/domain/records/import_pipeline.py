"""
历史病历导入 — 异步处理流水线。

Covers: duplicate detection, patient resolution, LLM structuring, DB persistence,
reply building, and chat-export sender selection.
"""

from __future__ import annotations

from typing import Any, List, Optional

from db.engine import AsyncSessionLocal
from utils.log import log

from domain.records.import_text_processing import (
    _extract_chunk_date,
    _t,
    _OCR_NAME_RE,
    _OCR_GENDER_RE,
    _OCR_AGE_RE,
)


async def _mark_duplicates(
    chunks: List[dict],
    doctor_id: str,
    patient_id: int,
) -> List[dict]:
    """Mark chunks that appear to duplicate existing records using content matching."""
    from db.crud import get_records_for_patient
    async with AsyncSessionLocal() as session:
        existing = await get_records_for_patient(session, doctor_id, patient_id)
    if not existing:
        return chunks
    existing_contents = [
        (rec.content or "").strip().lower()
        for rec in existing
        if rec.content
    ]
    for chunk in chunks:
        s = chunk.get("structured", {})
        chunk_content = (s.get("content") or "").strip().lower()
        if len(chunk_content) < 20:
            continue
        chunk_prefix = chunk_content[:80]
        for existing_content in existing_contents:
            if chunk_prefix in existing_content or existing_content[:80] in chunk_content:
                chunk["status"] = "duplicate"
                break
    return chunks


def _format_import_preview(
    chunks: List[dict],
    patient_name: Optional[str],
    source: str,
) -> str:
    """Build the confirmation message shown to the doctor."""
    source_label = {
        "pdf": "PDF文件",
        "word": "Word文件",
        "chat_export": "微信聊天记录",
    }.get(source, "文字")
    name_part = f"患者【{patient_name}】" if patient_name else "未关联患者"
    total = len(chunks)
    dup_count = sum(1 for c in chunks if c["status"] == "duplicate")
    new_count = total - dup_count

    lines = [f"📂 {name_part}历史记录\n共 {total} 条（来自{source_label}）\n"]
    ICONS = ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
    for i, chunk in enumerate(chunks):
        s = chunk.get("structured", {})
        icon = ICONS[i] if i < len(ICONS) else f"{i+1}."
        date_str = _extract_chunk_date(chunk.get("raw_text", "")) or "?"
        cc = _t(s.get("content") or "—", 14)
        tags_list = s.get("tags") or []
        diag = _t(tags_list[0] if tags_list else "", 12)
        diag_part = f"·{diag}" if diag else ""
        dup_tag = "⚠️疑似重复" if chunk["status"] == "duplicate" else ""
        lines.append(f"{icon} {date_str} {cc}{diag_part} {dup_tag}".strip())

    lines.append("")
    if dup_count > 0:
        lines.append(f"{new_count} 条新记录，{dup_count} 条疑似重复。")
        lines.append("「确认导入」保存全部\n「跳过重复」仅存新记录\n「取消」放弃")
    else:
        lines.append(f"「确认导入」保存全部 {total} 条\n「取消」放弃")
    return "\n".join(lines)


def _extract_patient_from_ocr(text: str) -> tuple:
    """Extract (name, gender, age) from OCR'd hospital record header."""
    sample = text[:300]
    name_m = _OCR_NAME_RE.search(sample)
    gender_m = _OCR_GENDER_RE.search(sample)
    age_m = _OCR_AGE_RE.search(sample)
    name = name_m.group(1) if name_m else None
    gender = gender_m.group(1) if gender_m else None
    age = int(age_m.group(1)) if age_m else None
    return name, gender, age


async def _resolve_import_patient(
    doctor_id: str,
    patient_name: Optional[str],
    patient_id: Optional[int],
    source: str,
    ocr_gender: Optional[str],
    ocr_age: Optional[int],
) -> tuple:
    """Resolve (but do NOT auto-create) patient for import.

    Returns (patient_name, patient_id, needs_create).  When needs_create
    is True, the caller should create the patient only after confirming
    the import has viable chunks — preventing orphan patient rows from
    failed/empty imports.
    """
    from db.crud import find_patient_by_name
    needs_create = False
    if patient_name and patient_id is None:
        async with AsyncSessionLocal() as session:
            patient = await find_patient_by_name(session, doctor_id, patient_name)
            if patient:
                patient_id = patient.id
            elif source == "image":
                needs_create = True
    return patient_name, patient_id, needs_create


async def _structure_chunks(
    chunks_raw: List[str],
    doctor_id: str,
) -> tuple:
    """Structure raw text chunks via LLM. Returns (structured_chunks, failed_chunks)."""
    from domain.records.structuring import structure_medical_record
    structured_chunks: list = []
    failed_chunks: list = []
    for i, chunk_text in enumerate(chunks_raw[:10]):
        try:
            record = await structure_medical_record(chunk_text)
            structured_chunks.append({
                "idx": i + 1,
                "raw_text": chunk_text[:600],
                "structured": record.model_dump(),
                "status": "pending",
            })
        except Exception as e:
            log(f"[Import] chunk {i+1} structuring FAILED doctor={doctor_id}: {e}")
            failed_chunks.append(i + 1)
    return structured_chunks, failed_chunks


async def _save_import_chunks(
    structured_chunks: List[dict],
    doctor_id: str,
    patient_id: Optional[int],
) -> int:
    """Save non-duplicate structured chunks in a single transaction.

    All chunks succeed or none are committed, preventing partial imports
    with orphaned side effects (category recomputes, auto-tasks).
    """
    from db.crud import save_record
    async with AsyncSessionLocal() as session:
        saved = 0
        for chunk in structured_chunks:
            if chunk.get("status") == "duplicate":
                continue
            try:
                from db.models.medical_record import MedicalRecord as MR
                fields = chunk.get("structured", {})
                record = MR(**{k: fields.get(k) for k in MR.model_fields})
                await save_record(session, doctor_id, record, patient_id, commit=False)
                saved += 1
            except Exception as e:
                log(f"[Import] save chunk FAILED doctor={doctor_id}: {e}")
                await session.rollback()
                return 0
        if saved:
            await session.commit()
    return saved


async def _resolve_session_patient(
    doctor_id: str,
    patient_name: Optional[str],
    source: str,
    text: str,
) -> tuple:
    """从当前会话或 OCR 补全患者名。返回 (patient_name, patient_id, ocr_gender, ocr_age)。"""
    patient_id: Optional[int] = None
    ocr_gender: Optional[str] = None
    ocr_age: Optional[int] = None
    if source == "image" and not patient_name:
        ocr_name, ocr_gender, ocr_age = _extract_patient_from_ocr(text)
        if ocr_name:
            patient_name = ocr_name
            log(f"[Import] OCR patient extracted: name={patient_name} gender={ocr_gender} age={ocr_age}")
    return patient_name, patient_id, ocr_gender, ocr_age


def _build_import_reply(
    saved: int,
    patient_name: Optional[str],
    failed_chunks: List[int],
    total_chunks: int,
) -> str:
    """构建导入完成的回复文本。"""
    patient_label = f"【{patient_name}】" if patient_name else "当前患者"
    reply = f"✅ 已导入 {saved} 条病历\n患者：{patient_label}"
    if failed_chunks:
        reply += (
            f"\n⚠️ {len(failed_chunks)} 条记录解析失败"
            f"（片段 {', '.join(str(n) for n in failed_chunks)}），已跳过"
        )
    if total_chunks > 10:
        reply += (
            f"\n⚠️ 共检测到 {total_chunks} 条记录，本次仅处理前10条。"
            f"如需导入剩余记录，请分批发送。"
        )
    return reply


async def _handle_chat_export_import(
    text: str,
    doctor_id: str,
    intent_result: Any,
    source: str,
) -> Optional[str]:
    """Handle multi-sender chat export: prompt for sender selection if needed.

    Returns a reply string if sender selection is needed, else None.
    """
    from channels.wechat.wechat_chat_export import list_senders
    senders = list_senders(text)
    sender_filter = intent_result.extra_data.get("sender_filter")
    if len(senders) > 1 and not sender_filter:
        sender_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(senders))
        return (
            f"检测到群聊记录，共 {len(senders)} 位发言人：\n{sender_list}\n\n"
            f"请回复发言人姓名或序号，指定导入哪位医生的记录。"
        )
    return None
