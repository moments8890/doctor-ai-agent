"""Auto-generate follow-up tasks from a medical record's orders/treatment fields.

Called after interview confirm or record status change to completed/pending_review.
Parses orders_followup and treatment_plan into discrete tasks via LLM.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from utils.log import log


class TaskType(str, Enum):
    follow_up = "follow_up"
    medication = "medication"
    checkup = "checkup"
    general = "general"


class ExtractedTask(BaseModel):
    title: str
    task_type: TaskType = TaskType.follow_up
    due_days: Optional[int] = None
    content: Optional[str] = None


class TaskExtractionResponse(BaseModel):
    tasks: List[ExtractedTask] = Field(default_factory=list)


async def generate_tasks_from_record(
    doctor_id: str,
    patient_id: int,
    record_id: int,
    orders_followup: Optional[str] = None,
    treatment_plan: Optional[str] = None,
    patient_name: str = "",
) -> List[int]:
    """Extract actionable tasks from record fields and create them in DB.

    Returns list of created task IDs.
    """
    text_parts = []
    if orders_followup and orders_followup.strip():
        text_parts.append(f"医嘱及随访：{orders_followup}")
    if treatment_plan and treatment_plan.strip():
        text_parts.append(f"治疗方案：{treatment_plan}")

    if not text_parts:
        return []

    combined = "\n".join(text_parts)
    tasks_data = await _extract_tasks_via_llm(combined)

    if not tasks_data:
        return []

    from db.crud.tasks import create_task
    from db.engine import AsyncSessionLocal

    created_ids = []
    async with AsyncSessionLocal() as db:
        for t in tasks_data[:5]:  # cap at 5 tasks per record
            title = t.get("title", "").strip()
            if not title:
                continue
            task_type = t.get("task_type", "follow_up")
            if task_type not in ("follow_up", "medication", "checkup", "general"):
                task_type = "follow_up"

            # Parse relative days to absolute date
            due_at = _parse_due_days(t.get("due_days"))

            task = await create_task(
                db,
                doctor_id=doctor_id,
                task_type=task_type,
                title=f"{patient_name} {title}" if patient_name else title,
                content=t.get("content"),
                patient_id=patient_id,
                record_id=record_id,
                due_at=due_at,
            )
            created_ids.append(task.id)
        await db.commit()

    log(f"[task_gen] created {len(created_ids)} tasks from record={record_id}")
    return created_ids


def _parse_due_days(due_days) -> Optional[datetime]:
    """Convert relative days (int or str) to absolute datetime."""
    if due_days is None:
        return None
    try:
        days = int(due_days)
        return datetime.now(timezone.utc) + timedelta(days=days)
    except (ValueError, TypeError):
        return None


async def _extract_tasks_via_llm(text: str) -> list:
    """Use LLM to extract discrete tasks from medical orders text.

    Returns list of dicts: [{title, task_type, due_days, content}]
    """
    from agent.llm import structured_call

    prompt = f"""/no_think
从以下医嘱和治疗方案中提取可执行的随访任务。

输入：
{text}

## Constraints
- 只提取明确的可执行项，不要编造
- 如果没有可执行任务，tasks 返回空数组"""

    try:
        result = await structured_call(
            response_model=TaskExtractionResponse,
            messages=[{"role": "user", "content": prompt}],
            op_name="task_gen.extract",
            temperature=0.1,
            max_tokens=512,
        )
        return [t.model_dump(mode="json") for t in result.tasks]
    except Exception as exc:
        log(f"[task_gen] LLM extraction failed: {exc}", level="warning")
        return []
