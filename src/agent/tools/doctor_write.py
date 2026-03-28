"""Doctor write tools — record creation, updates, tasks, and export."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from agent.identity import get_current_identity
from agent.tools.resolve import resolve
from agent.tools.truncate import truncate_result
from agent.tools.doctor_helpers import _serialize_record


# ── Internal write helpers ───────────────────────────────────────────


async def _create_pending_record(
    doctor_id: str, patient_id: int, patient_name: str,
    gender: Optional[str] = None, age: Optional[int] = None,
    clinical_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Structure clinical text and save directly to medical_records.

    PendingRecord table removed — saves immediately instead of creating a draft.
    """
    from domain.records.structuring import structure_medical_record
    from db.crud.records import save_record
    from db.engine import AsyncSessionLocal

    if not clinical_text or not clinical_text.strip():
        return {"status": "error", "message": "没有找到临床信息，请先提供患者症状"}

    try:
        medical_record = await structure_medical_record(clinical_text, doctor_id=doctor_id)
    except Exception as e:
        return {"status": "error", "message": f"病历结构化失败：{e}"}

    async with AsyncSessionLocal() as session:
        db_record = await save_record(session, doctor_id, medical_record, patient_id)
        return {
            "status": "saved",
            "preview": medical_record.content,
            "record_id": db_record.id,
        }


async def _update_pending_record(
    doctor_id: str, patient_id: int, patient_name: str,
    instruction: str,
) -> Dict[str, Any]:
    """Apply update instruction to latest record, save directly."""
    from domain.records.structuring import structure_medical_record
    from db.crud.records import get_records_for_patient, save_record
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_records_for_patient(session, doctor_id, patient_id, limit=1)
        if not records:
            return {"status": "error", "message": f"{patient_name}没有病历可修改"}
        latest = records[0]
        combined_text = f"{latest.content}\n\n医生修改指示：{instruction}"

    try:
        medical_record = await structure_medical_record(combined_text, doctor_id=doctor_id)
    except Exception as e:
        return {"status": "error", "message": f"病历结构化失败：{e}"}

    async with AsyncSessionLocal() as session:
        db_record = await save_record(session, doctor_id, medical_record, patient_id)
        return {
            "status": "saved",
            "preview": medical_record.content,
            "record_id": db_record.id,
        }


async def _commit_task(
    doctor_id: str, patient_id: int,
    title: str,
    task_type: str = "general",
    content: Optional[str] = None,
    due_at: Optional[str] = None,
) -> Dict[str, Any]:
    from db.crud.tasks import create_task as db_create_task
    from db.engine import AsyncSessionLocal

    try:
        due = datetime.fromisoformat(due_at) if due_at else None
    except ValueError:
        return {"status": "error", "message": f"日期格式无效：{due_at}"}

    async with AsyncSessionLocal() as session:
        task = await db_create_task(
            session,
            doctor_id=doctor_id,
            task_type=task_type,
            title=title,
            content=content,
            patient_id=patient_id,
            due_at=due,
        )
        return {"status": "ok", "task_id": task.id, "title": title}


# ── Write functions ──────────────────────────────────────────────────


async def create_record(
    patient_name: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    clinical_text: Optional[str] = None,
) -> Dict[str, Any]:
    """为患者创建病历。将临床信息结构化后生成病历预览。
    可通过 clinical_text 传入临床摘要，也可留空由系统自动从对话中提取。
    返回病历预览，医生说"确认"后才永久保存。患者不存在会自动创建。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id, auto_create=True, gender=gender, age=age)
    if "status" in resolved:
        return resolved
    result = await _create_pending_record(
        resolved["doctor_id"], resolved["patient_id"],
        resolved["patient_name"], gender, age, clinical_text,
    )
    return truncate_result(result)


async def update_record(
    instruction: str,
    patient_name: Optional[str] = None,
) -> Dict[str, Any]:
    """按医生指示修改患者最近一条病历。instruction 传入修改内容（如'血压改为130/85'）。
    返回修改预览，医生说"确认"后才保存。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id, auto_create=True)
    if "status" in resolved:
        return resolved
    result = await _update_pending_record(
        resolved["doctor_id"], resolved["patient_id"],
        resolved["patient_name"], instruction,
    )
    return truncate_result(result)


async def create_task(
    patient_name: str,
    title: str,
    task_type: str = "general",
    content: Optional[str] = None,
    due_at: Optional[str] = None,
) -> Dict[str, Any]:
    """为患者创建任务或预约。立即生效，无需确认。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved
    return await _commit_task(
        resolved["doctor_id"], resolved["patient_id"],
        title=title, task_type=task_type, content=content,
        due_at=due_at,
    )


async def complete_task(
    task_id: int,
) -> Dict[str, Any]:
    """将指定任务标记为已完成。需要先通过 list_tasks 获取任务ID。"""
    doctor_id = get_current_identity()
    try:
        from db.crud.tasks import update_task_status
        from db.engine import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await update_task_status(session, task_id, "completed")
        return {"status": "ok", "message": f"任务#{task_id}已完成"}
    except Exception as e:
        return {"status": "error", "message": f"更新任务失败：{e}"}


async def export_pdf(
    patient_name: str,
) -> Dict[str, Any]:
    """导出患者全部病历为PDF文件。返回文件路径和记录数量。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved

    try:
        from db.crud.records import get_records_for_patient
        from domain.records.pdf_export import generate_records_pdf
        from db.engine import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            records = await get_records_for_patient(
                session, resolved["doctor_id"], resolved["patient_id"], limit=50,
            )
        if not records:
            return {"status": "empty", "message": f"{patient_name}没有病历记录"}

        records_data = [_serialize_record(r) for r in records]
        pdf_bytes = generate_records_pdf(records_data, patient_name=patient_name)
        # Save to temp file
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".pdf", prefix=f"export_{patient_name}_")
        os.write(fd, pdf_bytes)
        os.close(fd)
        return {"status": "ok", "file_path": path, "record_count": len(records_data)}
    except Exception as e:
        return {"status": "error", "message": f"PDF导出失败：{e}"}
