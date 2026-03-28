"""Doctor read-only tools — query and search operations."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.identity import get_current_identity
from agent.tools.resolve import resolve
from agent.tools.truncate import truncate_result
from agent.tools.doctor_helpers import (
    _serialize_record,
    _serialize_patient,
    _serialize_task,
)


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


async def search_patients(
    query: str,
) -> Dict[str, Any]:
    """按条件搜索患者。支持姓名、性别、年龄等自然语言查询。"""
    doctor_id = get_current_identity()
    try:
        from domain.patients.nl_search import extract_criteria
        from db.crud.patient import get_all_patients
        from db.engine import AsyncSessionLocal
        from datetime import datetime

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
                age = datetime.now().year - p.year_of_birth
                if age < criteria.min_age:
                    continue
            if criteria.max_age and getattr(p, "year_of_birth", None):
                age = datetime.now().year - p.year_of_birth
                if age > criteria.max_age:
                    continue
            results.append(_serialize_patient(p))

        return truncate_result({"status": "ok", "data": results, "total": len(results)})
    except Exception as e:
        return {"status": "error", "message": f"患者搜索失败：{e}"}


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
