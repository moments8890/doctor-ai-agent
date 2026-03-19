"""
WeChat 病历导出处理层：病历PDF、门诊病历PDF的生成与发送逻辑。
"""

from __future__ import annotations

from typing import Any, Optional

from db.engine import AsyncSessionLocal
from infra.observability.audit import audit
from utils.log import log, safe_create_task


def _t(s: Optional[str], n: int = 30) -> str:
    """Truncate string for mobile display."""
    if not s:
        return ""
    return s[:n] + "…" if len(s) > n else s


async def _fetch_patient_and_records(
    session: Any,
    doctor_id: str,
    intent_result: Any,
    limit: int = 200,
) -> tuple:
    """Shared helper: resolve patient from intent or session, fetch records."""
    from sqlalchemy import select
    from db.models import MedicalRecordDB
    from db.crud import find_patient_by_name
    patient_id = None
    patient_name = None
    patient_obj = None

    if intent_result.patient_name:
        patient_obj = await find_patient_by_name(session, doctor_id, intent_result.patient_name)
        if patient_obj:
            patient_id = patient_obj.id
            patient_name = patient_obj.name

    records = []
    if patient_id is not None:
        result = await session.execute(
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == doctor_id,
            )
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(limit)
        )
        records = list(result.scalars().all())

    return patient_id, patient_name, patient_obj, records


async def _try_send_pdf(doctor_id: str, pdf_bytes: bytes, filename: str) -> None:
    """Upload PDF bytes as a WeCom temp media and send as file message."""
    from channels.wechat.wechat_notify import upload_temp_media, send_file_message
    media_id = await upload_temp_media(pdf_bytes, filename)
    await send_file_message(doctor_id, media_id)


def _build_export_text_fallback(
    patient_name: Optional[str],
    records: list,
) -> str:
    """Build text fallback for export when PDF sending fails."""
    lines = [
        "⚠️ 病历 PDF 发送失败，以下为文字摘要：",
        f"📄 【{patient_name}】病历摘要（共 {len(records)} 条）\n",
    ]
    for r in records[:10]:
        date_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else "?"
        snippet = _t(r.content or "—", 60)
        lines.append(f"▪ {date_str}\n{snippet}")
    if len(records) > 10:
        lines.append(f"\n… 还有 {len(records) - 10} 条记录，可在管理后台导出完整 PDF。")
    return "\n".join(lines)


async def handle_export_records(doctor_id: str, intent_result: Any) -> str:
    """Generate a PDF of patient records and send via WeCom file message.

    Falls back to formatted text summary if PDF upload is not available,
    with an explicit warning so the doctor knows the PDF was not sent.
    """
    async with AsyncSessionLocal() as session:
        patient_id, patient_name, _patient, records = await _fetch_patient_and_records(
            session, doctor_id, intent_result
        )

    if patient_id is None:
        return "❓ 请先告知患者姓名，例如：「导出张三的病历」"
    if not records:
        return f"📂 患者【{patient_name}】暂无历史记录，无法导出。"

    try:
        from domain.records.pdf_export import generate_records_pdf
        pdf_bytes = generate_records_pdf(
            records=list(reversed(records)),
            patient_name=patient_name, patient=_patient,
        )
        await _try_send_pdf(doctor_id, pdf_bytes, f"病历_{patient_id}.pdf")
        safe_create_task(
            audit(doctor_id, "EXPORT", resource_type="patient", resource_id=str(patient_id))
        )
        return f"📄 【{patient_name}】共 {len(records)} 条记录的病历 PDF 已发送。"
    except Exception as exc:
        log(f"[WeChat] export PDF via WeCom file failed ({exc}), falling back to text")

    return _build_export_text_fallback(patient_name, records)


def _build_patient_info_line(patient_obj: Any) -> Optional[str]:
    """Build patient info string (gender + age) from patient object."""
    from utils.response_formatting import build_patient_info_line
    return build_patient_info_line(patient_obj)


async def _generate_and_send_outpatient_pdf(
    doctor_id: str,
    patient_id: int,
    patient_name: Optional[str],
    patient_info: Optional[str],
    fields: dict,
) -> str:
    """Generate outpatient report PDF and send; return reply message."""
    from domain.records.pdf_export import generate_outpatient_report_pdf
    try:
        pdf_bytes = generate_outpatient_report_pdf(
            fields=fields,
            patient_name=patient_name,
            patient_info=patient_info,
        )
        await _try_send_pdf(doctor_id, pdf_bytes, f"门诊病历_{patient_id}.pdf")
        filled = sum(1 for v in fields.values() if v)
        return f"📋 【{patient_name}】卫生部 2010 标准门诊病历已发送（已填写 {filled}/10 项）。"
    except Exception as exc:
        log(f"[WeChat] outpatient report PDF/upload failed: {exc}")
        return (
            f"⚠️ 门诊病历 PDF 发送失败（{exc}）。\n"
            f"初步诊断：{fields.get('diagnosis') or '—'}\n"
            f"治疗方案：{fields.get('treatment') or '—'}\n"
            f"请在管理后台导出完整 PDF。"
        )


async def handle_export_outpatient_report(doctor_id: str, intent_result: Any) -> str:
    """Generate a 卫生部 2010 标准门诊病历 PDF and send via WeCom file message.

    Uses LLM to extract structured fields from all records.
    Falls back to a text explanation if PDF generation or upload fails.
    """
    async with AsyncSessionLocal() as session:
        patient_id, patient_name, patient_obj, records = await _fetch_patient_and_records(
            session, doctor_id, intent_result
        )
    if patient_id is None:
        return "❓ 请先告知患者姓名，例如：「生成张三的标准门诊病历」"
    if not records:
        return f"📂 患者【{patient_name}】暂无历史记录，无法生成门诊病历。"

    from domain.records.outpatient_report import ExtractionError, extract_outpatient_fields
    try:
        fields = await extract_outpatient_fields(
            records, patient_obj, doctor_id=doctor_id,
        )
    except ExtractionError as exc:
        log(f"[WeChat] outpatient report LLM extraction failed: {exc}")
        return "⚠️ AI 字段提取失败，暂时无法生成门诊病历 PDF，请稍后重试。"

    patient_info = _build_patient_info_line(patient_obj)
    reply = await _generate_and_send_outpatient_pdf(
        doctor_id, patient_id, patient_name, patient_info, fields
    )
    # Audit only when the reply indicates success (not a fallback/failure).
    if "已发送" in reply:
        safe_create_task(
            audit(doctor_id, "EXPORT", resource_type="outpatient_report", resource_id=str(patient_id))
        )
    return reply
