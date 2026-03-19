"""
WeChat 历史病历导入处理层：从PDF/Word/图片/语音/文本批量导入患者历史病历的业务逻辑。
"""

from __future__ import annotations

import asyncio
import re as _re
from typing import Any, Dict, List, Optional

from db.engine import AsyncSessionLocal
from utils.log import log


_VISIT_BOUNDARY_RE = _re.compile(
    r"(?:^|\n)(?="
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}"
    r"|第\d+次|初诊|复诊|【\d{4}"
    r")",
    _re.MULTILINE,
)

_DATE_IN_TEXT_RE = _re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}")

_CHAT_EXPORT_HEADER_RE = _re.compile(
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?\s+\S",
    _re.MULTILINE,
)

_EXAM_SUMMARY_RE = _re.compile(
    r"(?:^|\n)(?:\d+[.．、]\s*)?(?:"
    r"检查综述|体检结论|健康评估|主要.*?问题|检查结论|体检小结"
    r"|体检重要异常结果|阳性结果和异常情况|异常结果及建议"
    r"|重要检查结论|体检报告总结"
    r")",
    _re.MULTILINE,
)

_STRUCTURED_REPORT_RE = _re.compile(
    r"(?:"
    r"(?:姓\s*名|患者姓名|检查日期|报告日期|体检编号|住院号|门诊号|标本编号|送检日期)"
    r".{0,20}"
    r"(?:性\s*别|年\s*龄|科\s*室|床\s*号|检查者)"
    r"|"
    r"(?:健康体检报告|MEDICAL EXAMINATION REPORT).{0,60}(?:体检号|用户ID|检查日期)"
    r")",
    _re.DOTALL,
)

_REPORT_SECTION_RE = _re.compile(
    r"(?:^|\n)【[^】]{2,12}】"
    r"|(?:^|\n)[一二三四五六七八九十]+[、.．]\s*\S"
    r"|(?:^|\n)\d+\s{2,}[\u4e00-\u9fff]"
)

_OCR_NAME_RE = _re.compile(r"姓\s*名[：:]\s*([\u4e00-\u9fff]{2,5})")
_OCR_GENDER_RE = _re.compile(r"性\s*别[：:]\s*([男女])")
_OCR_AGE_RE = _re.compile(r"年\s*龄[：:]\s*(\d{1,3})")


def _looks_like_chat_export(text: str) -> bool:
    """Heuristic: does the text look like a WeChat chat export?"""
    return bool(_CHAT_EXPORT_HEADER_RE.search(text[:2000]))


def _looks_like_structured_report(text: str) -> bool:
    """Return True if text is a single structured report (体检报告, 化验单, etc.)"""
    sample = text[:1500]
    return bool(_STRUCTURED_REPORT_RE.search(sample)) and bool(_REPORT_SECTION_RE.search(sample))


def _extract_exam_identity(header: str) -> str:
    """Extract name/gender/age/date from exam report header."""
    name_m = _re.search(r"姓\s*名\s+(\S+)", header) or _re.search(
        r"REPORT\s+(\S{2,4})\s+(?:女士|先生|男士)", header
    )
    gender_m = _re.search(r"性别\s+([男女])", header) or _re.search(
        r"(\S{2,4})\s+(女士|先生)", header
    )
    age_m = _re.search(r"年龄\s+(\d+\s*岁?)", header)
    date_m = _re.search(r"体检日期\s+(\S+)", header) or _re.search(
        r"(\d{4}年\d{1,2}月\d{1,2}日)的体检报告", header
    )
    parts = []
    if name_m:
        parts.append(f"姓名：{name_m.group(1)}")
    if gender_m:
        raw = gender_m.group(2) if gender_m.lastindex and gender_m.lastindex >= 2 else gender_m.group(1)
        val = "女" if "女" in raw else ("男" if "男" in raw else raw)
        parts.append(f"性别：{val}")
    if age_m:
        parts.append(f"年龄：{age_m.group(1)}")
    if date_m:
        parts.append(f"体检日期：{date_m.group(1)}")
    return "  ".join(parts)


def _trim_exam_clinical(clinical: str) -> str:
    """Trim clinical body to exclude raw data tables."""
    conclusion_m = _re.search(
        r"(?:体检结论|健康建议|医师签名"
        r"|(?:^|\n)\s*3[\s、.．]+健康体检结果"
        r"|(?:^|\n)\s*[三3][\s、.．]+检查详细"
        r")",
        clinical,
        _re.MULTILINE,
    )
    if conclusion_m:
        return clinical[:conclusion_m.start() + 2000]
    return clinical


def _preprocess_exam_report(text: str) -> str:
    """Extract clinically relevant sections from a 体检报告."""
    m = _EXAM_SUMMARY_RE.search(text)
    if not m:
        return text
    body_start = m.start() + (1 if text[m.start()] in "\n\r" else 0)
    header = text[:body_start]
    identity_line = _extract_exam_identity(header)
    clinical = _trim_exam_clinical(text[body_start:].strip())
    return (identity_line + "\n\n" + clinical).strip() if identity_line else clinical


def _preprocess_import_text(
    text: str,
    source: str,
    sender_filter: Optional[str] = None,
) -> str:
    """Strip media prefixes and clean WeChat chat export formatting."""
    text = _re.sub(r"^\[(PDF|Word|Image):[^\]]*\]\s*", "", text, flags=_re.IGNORECASE)
    if source == "chat_export" or _looks_like_chat_export(text):
        from channels.wechat.wechat_media_pipeline import preprocess_wechat_chat_export
        text = preprocess_wechat_chat_export(text, sender_filter=sender_filter)
    elif _looks_like_structured_report(text):
        text = _preprocess_exam_report(text)
    return text.strip()


def _merge_short_paragraphs(paragraphs: List[str]) -> List[str]:
    """Merge tiny stub paragraphs (< 15 chars) into the following one."""
    merged: list = []
    buf = ""
    for p in paragraphs:
        if buf and len(buf) < 15:
            buf = (buf + "\n" + p).strip()
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return merged


def _merge_short_chunks(raw_chunks: List[str]) -> List[str]:
    """Merge adjacent short chunks (< 40 chars) into the next."""
    sections: list = []
    buf = ""
    for chunk in raw_chunks:
        buf = (buf + "\n" + chunk).strip() if buf else chunk
        if len(buf) >= 40:
            sections.append(buf)
            buf = ""
    if buf:
        if sections:
            sections[-1] = (sections[-1] + "\n" + buf).strip()
        else:
            sections.append(buf)
    return sections


def _chunk_history_text(text: str) -> List[str]:
    """Split bulk history text into individual visit chunks."""
    if _looks_like_structured_report(text):
        return [text]

    raw_boundaries = [m.start() for m in _VISIT_BOUNDARY_RE.finditer(text)]
    boundaries: list = []
    for pos in raw_boundaries:
        actual = pos + 1 if pos < len(text) and text[pos] == "\n" else pos
        if not boundaries or actual != boundaries[-1]:
            boundaries.append(actual)

    paragraphs = [p.strip() for p in _re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) >= 2:
        merged = _merge_short_paragraphs(paragraphs)
        if len(merged) >= 2:
            return merged

    if len(boundaries) >= 2:
        raw_chunks = []
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            chunk = text[start:end].strip()
            if chunk:
                raw_chunks.append(chunk)
        sections = _merge_short_chunks(raw_chunks)
        if len(sections) >= 2:
            return sections

    return [text]


def _extract_chunk_date(chunk: str) -> Optional[str]:
    """Extract the first date string from a chunk for display."""
    m = _DATE_IN_TEXT_RE.search(chunk)
    return m.group(0) if m else None


def _t(s: Optional[str], n: int = 30) -> str:
    if not s:
        return ""
    return s[:n] + "…" if len(s) > n else s


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
                if patient_id is not None:
                    from domain.patients.categorization import recompute_patient_category
                    await recompute_patient_category(patient_id, session, commit=False)
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
