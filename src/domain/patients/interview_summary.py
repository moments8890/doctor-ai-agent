"""Generate MedicalRecord from completed interview (ADR 0016).

Includes a post-interview reconciliation sweep that:
1. Normalizes chief_complaint to NHC spec (≤20 chars, symptom + duration only)
2. Moves overflow from chief_complaint to present_illness
3. Scans full transcript for missed past_history/allergy/family mentions
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from db.models.medical_record import MedicalRecord
from domain.patients.completeness import ALL_COLLECTABLE
from utils.log import log

FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "personal_history": "个人史",
    "marital_reproductive": "婚育史",
    "family_history": "家族史",
    "physical_exam": "体格检查",
    "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查",
    "diagnosis": "诊断",
    "treatment_plan": "治疗方案",
    "orders_followup": "医嘱及随访",
}


def generate_content(collected: Dict[str, str]) -> str:
    """Generate prose content string from collected fields."""
    lines: List[str] = []
    for field in ALL_COLLECTABLE:
        value = collected.get(field, "")
        if not value:
            continue
        label = FIELD_LABELS.get(field, field)
        lines.append(f"{label}：{value}")
    return "\n".join(lines) if lines else ""


def generate_structured(collected: Dict[str, str]) -> Dict[str, str]:
    """Map collected fields to the 14-field outpatient schema."""
    from domain.records.schema import FIELD_KEYS
    structured: Dict[str, str] = {}
    for key in FIELD_KEYS:
        structured[key] = collected.get(key, "")
    return structured


def extract_tags(collected: Dict[str, str]) -> List[str]:
    """Extract keyword tags from chief_complaint and present_illness."""
    tags: List[str] = []
    for field in ("chief_complaint", "present_illness"):
        value = collected.get(field, "")
        if not value:
            continue
        parts = re.split(r"[，。；、\s]+", value)
        for part in parts:
            part = part.strip()
            if 1 < len(part) <= 10 and part not in tags:
                tags.append(part)
    return tags[:10]


def build_medical_record(collected: Dict[str, str]) -> MedicalRecord:
    """Build a MedicalRecord from interview collected fields."""
    content = generate_content(collected)
    if not content:
        content = "预问诊记录（无临床内容）"

    structured = generate_structured(collected)
    tags = extract_tags(collected)

    return MedicalRecord(
        content=content,
        structured=structured,
        tags=tags,
        record_type="interview_summary",
    )


_RECONCILE_PROMPT = """\
/no_think
你是病历质量审查员。请根据完整对话记录，对已提取的SOAP字段进行一次性规范化校正。

## 依据：卫医政发〔2010〕11号《病历书写基本规范》

### 字段定义
- **chief_complaint（主诉）**：促使患者本次就诊/转诊的**主要问题**及持续时间。≤20字，格式："[主要就诊原因][时间]"。主诉不局限于症状；检查/影像异常发现或转诊原因也可作为主诉。
- **present_illness（现病史）**：本次疾病的发生、演变、诊疗详细情况。包括：发病情况、主要症状特点、伴随症状、诊疗经过、一般情况变化
- **past_history（既往史）**：既往疾病史、手术外伤史、输血史

## 当前已提取字段
{collected_json}

## 完整对话记录
{transcript}

## 任务
1. **规范化 chief_complaint**：先判断"什么促使患者本次就诊"。若当前主诉不是真正的就诊原因（如选了慢性症状而非检查发现），则改为正确的就诊原因+时间。若超过20字或包含描述/细节，缩短为"[就诊原因][时间]"，多余内容移到 present_illness
2. **补漏 past_history**：扫描对话中是否有患者提到但未被提取的：疾病史、手术史、输血史、外伤史
3. **补漏其他字段**：扫描对话中是否有患者明确提到但未被提取的过敏、家族史、个人史信息
4. **不要**修改已正确提取的字段内容，不要删除任何已有信息
5. **不要**编造患者没有说过的信息

返回JSON，只包含需要修改或补充的字段：
{{"chief_complaint": "规范化后的主诉", "present_illness": "需要追加的内容（如有）", "past_history": "需要追加的内容（如有）"}}
如果所有字段都正确无需修改，返回：{{}}
"""


async def reconcile_collected(
    collected: Dict[str, str],
    conversation: list,
) -> Dict[str, str]:
    """Post-interview reconciliation sweep over the full transcript.

    Runs once at confirm time. Normalizes chief_complaint to NHC spec,
    catches missed fields, and returns the corrected collected dict.
    """
    from agent.llm import llm_call

    transcript_lines = []
    for turn in conversation:
        role = "AI助手" if turn.get("role") in ("assistant", "system") else "患者"
        text = turn.get("content", turn.get("text", ""))
        transcript_lines.append(f"{role}：{text}")
    transcript = "\n".join(transcript_lines)

    prompt = _RECONCILE_PROMPT.format(
        collected_json=json.dumps(collected, ensure_ascii=False, indent=2),
        transcript=transcript,
    )

    try:
        raw = await llm_call(
            messages=[{"role": "user", "content": prompt}],
            op_name="interview.reconcile",
            temperature=0.1,
            max_tokens=512,
            json_mode=True,
        )
        # Parse corrections
        import re as _re
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        corrections = json.loads(cleaned)
        if not isinstance(corrections, dict) or not corrections:
            log("[reconcile] no corrections needed")
            return collected

        # Apply corrections
        result = dict(collected)
        for field, value in corrections.items():
            if not isinstance(value, str) or not value.strip():
                continue
            if field == "chief_complaint":
                # Overwrite — reconciliation normalizes the full value
                result[field] = value.strip()
            elif field in result and result[field]:
                # Append new content for appendable fields
                existing = result[field]
                if value.strip() not in existing:
                    result[field] = f"{existing}；{value.strip()}"
            else:
                result[field] = value.strip()

        log(f"[reconcile] applied corrections: {list(corrections.keys())}")
        return result

    except Exception as exc:
        log(f"[reconcile] failed (non-fatal): {exc}", level="warning")
        return collected


async def confirm_interview(
    session_id: str,
    doctor_id: str,
    patient_id: int,
    patient_name: str,
    collected: Dict[str, str],
    conversation: Optional[list] = None,
) -> Dict[str, int]:
    """Finalize interview: reconcile → save record → create review task. Returns {record_id, review_id}."""
    from db.crud.records import save_record
    from db.crud.tasks import create_task
    from db.engine import AsyncSessionLocal

    # Reconciliation sweep: normalize chief_complaint, catch missed fields
    if conversation:
        collected = await reconcile_collected(collected, conversation)

    record = build_medical_record(collected)

    async with AsyncSessionLocal() as db:
        from db.models.records import RecordStatus
        db_record = await save_record(
            db, doctor_id, record, patient_id,
            status=RecordStatus.pending_review.value,
            commit=True,
        )

        # Create review task for the doctor
        task = await create_task(
            db, doctor_id,
            task_type="review",
            title=f"审阅患者【{patient_name}】预问诊记录",
            content=f"患者已完成预问诊，请审阅病历记录。",
            patient_id=patient_id,
            record_id=db_record.id,
        )
        await db.commit()

    log(f"[interview] confirmed session={session_id} record={db_record.id} task={task.id}")

    # Notify doctor (best-effort, don't block on failure)
    try:
        from domain.tasks.notifications import send_doctor_notification
        await send_doctor_notification(
            doctor_id,
            f"患者【{patient_name}】已完成预问诊，请查看待审核记录。",
        )
    except Exception as e:
        log(f"[interview] doctor notification failed: {e}", level="warning")

    return {"record_id": db_record.id, "review_id": task.id}
