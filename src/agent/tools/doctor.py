"""Doctor-role tools for the LangChain ReAct agent."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

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
        "scheduled_for": t.scheduled_for.isoformat() if getattr(t, "scheduled_for", None) else None,
        "remind_at": t.remind_at.isoformat() if getattr(t, "remind_at", None) else None,
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


# ── Internal write helpers ───────────────────────────────────────────


async def _create_pending_record(
    doctor_id: str, patient_id: int, patient_name: str,
    gender: Optional[str] = None, age: Optional[int] = None,
) -> Dict[str, Any]:
    """Collect clinical text from conversation, structure, save as pending."""
    from domain.records.structuring import structure_medical_record
    from db.crud.pending import create_pending_record
    from db.engine import AsyncSessionLocal

    # Collect clinical text from agent's in-memory history.
    # Filter: only include messages that mention the target patient name
    # to avoid cross-patient data contamination.
    # Import lazily to avoid circular: doctor.py -> session.py -> setup.py -> doctor.py
    from agent import session as _session_mod
    history = _session_mod.get_agent_history(doctor_id)

    # Take messages from the most recent mention of the patient name onward
    relevant_messages: List[str] = []
    collecting = False
    for msg in history:
        content = getattr(msg, "content", "") or ""
        if patient_name in content:
            collecting = True
        if collecting and content.strip():
            relevant_messages.append(content)

    clinical_text = "\n".join(relevant_messages)

    if not clinical_text.strip():
        return {"status": "error", "message": "没有找到临床信息，请先提供患者症状"}

    try:
        medical_record = await structure_medical_record(clinical_text, doctor_id=doctor_id)
    except Exception as e:
        return {"status": "error", "message": f"病历结构化失败：{e}"}

    draft_json = medical_record.model_dump_json()
    record_id = str(uuid.uuid4())

    async with AsyncSessionLocal() as session:
        await create_pending_record(
            session,
            record_id=record_id,
            doctor_id=doctor_id,
            draft_json=draft_json,
            patient_id=patient_id,
            patient_name=patient_name,
        )
        return {
            "status": "pending_confirmation",
            "preview": medical_record.content,
            "pending_id": record_id,
        }


async def _update_pending_record(
    doctor_id: str, patient_id: int, patient_name: str,
    instruction: str,
) -> Dict[str, Any]:
    """Apply update instruction to latest record, save as pending."""
    from domain.records.structuring import structure_medical_record
    from db.crud.records import get_records_for_patient
    from db.crud.pending import create_pending_record
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

    draft_json = medical_record.model_dump_json()
    record_id = str(uuid.uuid4())

    async with AsyncSessionLocal() as session:
        await create_pending_record(
            session,
            record_id=record_id,
            doctor_id=doctor_id,
            draft_json=draft_json,
            patient_id=patient_id,
            patient_name=patient_name,
        )
        return {
            "status": "pending_confirmation",
            "preview": medical_record.content,
            "pending_id": record_id,
        }


async def _commit_task(
    doctor_id: str, patient_id: int,
    title: str,
    task_type: str = "general",
    content: Optional[str] = None,
    scheduled_for: Optional[str] = None,
    remind_at: Optional[str] = None,
) -> Dict[str, Any]:
    from db.crud.tasks import create_task as db_create_task
    from db.engine import AsyncSessionLocal

    try:
        sched = datetime.fromisoformat(scheduled_for) if scheduled_for else None
    except ValueError:
        return {"status": "error", "message": f"日期格式无效：{scheduled_for}"}
    try:
        remind = datetime.fromisoformat(remind_at) if remind_at else None
    except ValueError:
        return {"status": "error", "message": f"提醒时间格式无效：{remind_at}"}

    async with AsyncSessionLocal() as session:
        task = await db_create_task(
            session,
            doctor_id=doctor_id,
            task_type=task_type,
            title=title,
            content=content,
            patient_id=patient_id,
            scheduled_for=sched,
            remind_at=remind,
        )
        return {"status": "ok", "task_id": task.id, "title": title}


# ── Read tools ───────────────────────────────────────────────────────


@tool
async def query_records(
    patient_name: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """查询患者的既往病历记录。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved
    records = await _fetch_records(resolved["doctor_id"], resolved["patient_id"], limit)
    return truncate_result({"status": "ok", "data": records})


@tool
async def list_patients() -> Dict[str, Any]:
    """列出医生的患者名单。"""
    doctor_id = get_current_identity()
    patients = await _fetch_patients(doctor_id)
    return truncate_result({"status": "ok", "data": patients})


@tool
async def list_tasks(status: Optional[str] = None) -> Dict[str, Any]:
    """查询任务列表。可按状态筛选（pending/completed）。"""
    doctor_id = get_current_identity()
    tasks = await _fetch_tasks(doctor_id, status)
    return truncate_result({"status": "ok", "data": tasks})


# ── Write tools ──────────────────────────────────────────────────────


@tool
async def create_record(
    patient_name: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
) -> Dict[str, Any]:
    """为患者创建病历。收集对话中的临床信息，结构化后生成病历预览。
    医生确认后才会永久保存。如果患者不存在会自动创建。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id, auto_create=True, gender=gender, age=age)
    if "status" in resolved:
        return resolved
    result = await _create_pending_record(
        resolved["doctor_id"], resolved["patient_id"],
        resolved["patient_name"], gender, age,
    )
    return truncate_result(result)


@tool
async def update_record(
    instruction: str,
    patient_name: Optional[str] = None,
) -> Dict[str, Any]:
    """按医生指示修改现有病历。返回修改预览，医生确认后才会保存。
    如果患者不存在会自动创建。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id, auto_create=True)
    if "status" in resolved:
        return resolved
    result = await _update_pending_record(
        resolved["doctor_id"], resolved["patient_id"],
        resolved["patient_name"], instruction,
    )
    return truncate_result(result)


@tool
async def create_task(
    patient_name: str,
    title: str,
    task_type: str = "general",
    content: Optional[str] = None,
    scheduled_for: Optional[str] = None,
    remind_at: Optional[str] = None,
) -> Dict[str, Any]:
    """为患者创建任务或预约。scheduled_for 和 remind_at 为 ISO-8601 格式。"""
    doctor_id = get_current_identity()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved
    return await _commit_task(
        resolved["doctor_id"], resolved["patient_id"],
        title=title, task_type=task_type, content=content,
        scheduled_for=scheduled_for, remind_at=remind_at,
    )


# ── Export tools ──────────────────────────────────────────────────────


@tool
async def export_pdf(
    patient_name: str,
) -> Dict[str, Any]:
    """导出患者病历为PDF文件。返回PDF文件路径。"""
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


# ── Knowledge tools ──────────────────────────────────────────────────


@tool
async def search_knowledge(
    query: str,
) -> Dict[str, Any]:
    """搜索医生的个人知识库。用于查找临床指南、经验笔记等。"""
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


# ── Patient search tools ─────────────────────────────────────────────


@tool
async def search_patients(
    query: str,
) -> Dict[str, Any]:
    """按条件搜索患者。支持姓名、性别、年龄等自然语言查询。
    例如："60岁以上的女性患者"、"姓张的患者"。"""
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


# ── Patient timeline tool ────────────────────────────────────────────


@tool
async def get_patient_timeline(
    patient_name: str,
) -> Dict[str, Any]:
    """获取患者的完整就诊时间线，包括病历、任务、随访等。"""
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


# ── Task management tools ────────────────────────────────────────────


@tool
async def complete_task(
    task_id: int,
) -> Dict[str, Any]:
    """将任务标记为已完成。"""
    doctor_id = get_current_identity()
    try:
        from db.crud.tasks import update_task_status
        from db.engine import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await update_task_status(session, task_id, "completed")
        return {"status": "ok", "message": f"任务#{task_id}已完成"}
    except Exception as e:
        return {"status": "error", "message": f"更新任务失败：{e}"}


# ── All doctor tools ────────────────────────────────────────────────

# Core tools only — keeps token count low for free-tier LLM providers.
# Extended tools (export_pdf, search_knowledge, search_patients,
# get_patient_timeline, complete_task) are defined above but excluded
# from the default set to avoid rate limits. Add them back when using
# paid providers or higher rate limits.
DOCTOR_TOOLS = [
    query_records, list_patients, list_tasks,
    create_record, update_record, create_task,
]
