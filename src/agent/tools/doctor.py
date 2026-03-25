"""Doctor-role business logic — called by Plan-and-Act handlers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent.identity import get_current_identity
from agent.tools.resolve import resolve
from agent.tools.truncate import truncate_result


# ── Serialization helpers ────────────────────────────────────────────


def _serialize_record(r: Any) -> Dict[str, Any]:
    tags = []
    if getattr(r, "tags", None):
        try:
            tags = json.loads(r.tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    return {
        "id": r.id,
        "content": r.content or "",
        "tags": tags,
        "record_type": getattr(r, "record_type", None),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_patient(p: Any) -> Dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "gender": getattr(p, "gender", None),
        "year_of_birth": getattr(p, "year_of_birth", None),
    }


def _serialize_task(t: Any) -> Dict[str, Any]:
    return {
        "id": t.id,
        "task_type": getattr(t, "task_type", None),
        "title": getattr(t, "title", None),
        "content": getattr(t, "content", None),
        "status": getattr(t, "status", None),
        "patient_id": getattr(t, "patient_id", None),
        "due_at": t.due_at.isoformat() if getattr(t, "due_at", None) else None,
    }


# ── Internal read helpers ────────────────────────────────────────────


async def _fetch_records(
    doctor_id: str, patient_id: int, limit: int = 5,
) -> List[Dict[str, Any]]:
    from db.crud.records import get_records_for_patient
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_records_for_patient(session, doctor_id, patient_id, limit=limit)
        return [_serialize_record(r) for r in records]


async def _fetch_patients(doctor_id: str) -> List[Dict[str, Any]]:
    from db.crud.patient import get_all_patients
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        patients = await get_all_patients(session, doctor_id)
        return [_serialize_patient(p) for p in patients]


async def _fetch_tasks(
    doctor_id: str, status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    from db.crud.tasks import list_tasks as db_list_tasks
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        tasks = await db_list_tasks(session, doctor_id, status=status)
        return [_serialize_task(t) for t in tasks]


async def _fetch_recent_records(
    doctor_id: str, limit: int = 10,
) -> List[Dict[str, Any]]:
    from db.crud.records import get_all_records_for_doctor
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_all_records_for_doctor(session, doctor_id, limit=limit)
        return [_serialize_record(r) for r in records]


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


# ── Read functions ───────────────────────────────────────────────────


async def query_records(
    patient_name: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """查询患者的既往病历记录。返回最近的病历列表，包含内容摘要和创建时间。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved
    records = await _fetch_records(resolved["doctor_id"], resolved["patient_id"], limit)
    return truncate_result({"status": "ok", "data": records})


async def list_patients() -> Dict[str, Any]:
    """列出当前医生的全部患者。返回姓名、性别、出生年份等基本信息。无需参数。"""
    doctor_id = get_current_identity()
    patients = await _fetch_patients(doctor_id)
    return truncate_result({"status": "ok", "data": patients})


async def list_tasks(status: Optional[str] = None) -> Dict[str, Any]:
    """查询当前医生的任务列表。返回任务标题、状态、患者、计划时间等。"""
    doctor_id = get_current_identity()
    tasks = await _fetch_tasks(doctor_id, status)
    return truncate_result({"status": "ok", "data": tasks})


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


# ── Export functions ──────────────────────────────────────────────────


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


# ── Knowledge functions ──────────────────────────────────────────────


async def search_knowledge(
    query: str,
) -> Dict[str, Any]:
    """搜索医生的个人知识库，查找临床指南、经验笔记、用药方案等。"""
    doctor_id = get_current_identity()
    try:
        from domain.knowledge.doctor_knowledge import load_knowledge_context_for_prompt
        from db.engine import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            context = await load_knowledge_context_for_prompt(session, doctor_id, query)
        if not context or not context.strip():
            return {"status": "empty", "message": "知识库中未找到相关内容"}
        return truncate_result({"status": "ok", "data": context})
    except Exception as e:
        return {"status": "error", "message": f"知识库检索失败：{e}"}


# ── Patient search functions ─────────────────────────────────────────


async def search_patients(
    query: str,
) -> Dict[str, Any]:
    """按条件搜索患者。支持姓名、性别、年龄等自然语言查询。"""
    doctor_id = get_current_identity()
    try:
        from domain.patients.nl_search import extract_criteria
        from db.crud.patient import get_all_patients
        from db.engine import AsyncSessionLocal

        criteria = extract_criteria(query)
        async with AsyncSessionLocal() as session:
            all_patients = await get_all_patients(session, doctor_id)

        # Apply criteria filters
        results = []
        for p in all_patients:
            if criteria.name and criteria.name not in (p.name or ""):
                continue
            if criteria.gender and criteria.gender != getattr(p, "gender", None):
                continue
            if criteria.min_age and getattr(p, "year_of_birth", None):
                from datetime import datetime
                age = datetime.now().year - p.year_of_birth
                if age < criteria.min_age:
                    continue
            if criteria.max_age and getattr(p, "year_of_birth", None):
                from datetime import datetime
                age = datetime.now().year - p.year_of_birth
                if age > criteria.max_age:
                    continue
            results.append(_serialize_patient(p))

        return truncate_result({"status": "ok", "data": results, "total": len(results)})
    except Exception as e:
        return {"status": "error", "message": f"患者搜索失败：{e}"}


# ── Patient timeline function ────────────────────────────────────────


async def get_patient_timeline(
    patient_name: str,
) -> Dict[str, Any]:
    """获取患者的完整就诊时间线，按时间排列病历、任务、随访记录。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved

    try:
        from domain.patients.timeline import build_patient_timeline
        from db.engine import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            timeline = await build_patient_timeline(
                session, resolved["doctor_id"], resolved["patient_id"],
            )
        if not timeline:
            return {"status": "empty", "message": f"{patient_name}没有就诊记录"}
        return truncate_result({"status": "ok", "data": timeline})
    except Exception as e:
        return {"status": "error", "message": f"时间线获取失败：{e}"}


# ── Task management functions ────────────────────────────────────────


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


# ── Plain async functions — called directly by Plan-and-Act handlers ──
# (Previously a LangChain tool list; routing LLM now handles param extraction.)
