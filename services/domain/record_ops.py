"""共享病历组装：构建 MedicalRecord 对象（不保存），调用方负责渠道特定的保存策略。"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.ai.structuring import structure_medical_record
from services.patient.encounter_detection import detect_encounter_type
from utils.log import log

# History turns shorter than this are likely commands ("查", "删除张三"), not clinical content.
_MIN_HISTORY_TURN_LEN = 15
# Prefix-based exclusion: turns starting with these are admin/task/control, not clinical.
_CMD_PREFIXES = (
    "患者列表", "所有患者", "删除", "创建", "查", "待办", "今天任务", "PDF",
    "建档", "导入", "导出", "帮助", "help", "Help",
    "确认", "保存", "取消", "撤销", "不要",
)
# Regex-based exclusion: turns matching these patterns are non-clinical.
_NON_CLINICAL_RE = re.compile(
    r"^(?:"
    r"你好|早上?好|晚上好|下午好|嗨|hi|hello"            # greetings
    r"|好的[，。]?"                                        # acknowledgements
    r"|完成\s*\d+"                                         # task completion
    r"|取消\s*(?:任务|待办)"                               # task cancellation
    r"|推迟\s*(?:任务|待办)"                               # task postponement
    r"|(?:查询|查看|调出).*(?:病历|记录|档案)"             # record queries
    r"|帮我?(?:查|看|找|建|删)"                            # admin requests
    r"|请?问.*叫什么"                                      # name asking
    r"|.*有哪些功能"                                       # feature inquiry
    r"|怎么用"                                             # usage inquiry
    r"|预约.*(?:门诊|复查)"                                # appointment scheduling
    r"|(?:设|安排).*随访"                                  # follow-up scheduling
    r")$",
    re.IGNORECASE,
)

# Lines in a prior-visit summary that look like prompt-injection attempts.
_SUMMARY_BLOCKED_PREFIXES = ("忽略", "SYSTEM", "system", "System", "#", "---")



def _is_clinical_turn(content: str) -> bool:
    """Return True if a history turn looks like clinical content (not admin/task/control)."""
    if len(content) < _MIN_HISTORY_TURN_LEN:
        return False
    if any(content.startswith(p) for p in _CMD_PREFIXES):
        return False
    if _NON_CLINICAL_RE.match(content.strip()):
        return False
    return True


def build_clinical_context(text: str, history: list[dict]) -> str:
    """Filter history to clinical-only turns and append current text, deduplicated.

    This is the single source of truth for building the LLM structuring input.
    Excludes task operations, queries, greetings, and other admin chatter.
    """
    doctor_ctx = [
        m["content"] for m in (history or [])[-6:]
        if m["role"] == "user" and _is_clinical_turn(m["content"])
    ]
    doctor_ctx.append(text)
    return "\n".join(dict.fromkeys(filter(None, doctor_ctx)))


def _sanitize_prior_summary(enc_type: str, raw_summary: Optional[str]) -> Optional[str]:
    """Return a sanitized prior-visit summary block, or None if not applicable."""
    if enc_type != "follow_up" or not raw_summary:
        return None
    safe_lines = [
        line for line in raw_summary.strip().splitlines()
        if not any(line.lstrip().startswith(kw) for kw in _SUMMARY_BLOCKED_PREFIXES)
    ]
    return f"\n<prior_summary>\n{chr(10).join(safe_lines)[:500]}\n</prior_summary>\n"


async def assemble_record(
    intent_result: "IntentResult",  # type: ignore[name-defined]
    text: str,
    history: list[dict],
    doctor_id: str,
    patient_id: Optional[int] = None,
    visit_scenario: Optional[str] = None,
    note_style: Optional[str] = None,
) -> MedicalRecord:
    """Build a MedicalRecord by calling the structuring LLM.

    The structuring LLM is called with:
      - Filtered history (clinical turns only, last 6)
      - Encounter type (first_visit | follow_up | unknown)
      - Prior-visit summary injected as context for follow-up encounters

    Does NOT save the record — that is the caller's responsibility.

    Raises:
        ValueError: If structuring LLM rejects the input as non-clinical.
        Exception: Any other structuring or DB error propagates to the caller.
    """

    full_text = build_clinical_context(text, history)

    async def _detect() -> str:
        async with AsyncSessionLocal() as s:
            return await detect_encounter_type(s, doctor_id, patient_id, text)

    async def _prior() -> Optional[str]:
        if patient_id is None:
            return None
        try:
            from services.patient.prior_visit import get_prior_visit_summary
            return await get_prior_visit_summary(doctor_id, patient_id)
        except Exception:
            return None

    enc_type, raw_summary = await asyncio.gather(_detect(), _prior())
    prior_summary = _sanitize_prior_summary(enc_type, raw_summary)

    log(f"[domain] structuring enc_type={enc_type} prior={'yes' if prior_summary else 'no'} doctor={doctor_id}")
    return await structure_medical_record(
        full_text,
        encounter_type=enc_type,
        prior_visit_summary=prior_summary,
    )
