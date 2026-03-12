"""
文本清理工具：从复合创建消息中剥离患者人口学信息前缀。

使用已提取的实体（姓名/性别/年龄）逐步消除开头的命令词和人口学片段，
保留后续的临床叙述内容。
"""

from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.ai.intent import IntentResult


def strip_leading_create_demographics(
    body_text: str,
    intent_result: Optional["IntentResult"] = None,
    *,
    patient_name: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
) -> str:
    """Strip leading patient-identification segments from a compound create message.

    Uses already-extracted entity fields (name, gender, age) rather than a brittle
    regex.  Consumes, in order:

    1. Optional command intro (帮我/请 + 录入/建立/新建/创建/添加)
    2. Optional patient-category words (新患者/患者/病人)
    3. Exact patient name
    4. Gender token (男/女/男性/女性)
    5. Age token (52岁)

    Returns the remaining clinical text, or empty string if nothing useful remains.
    """
    if not body_text:
        return ""

    # Prefer IntentResult fields; keyword args as fallback for testing.
    _name = (intent_result.patient_name if intent_result else None) or patient_name
    _gender = (intent_result.gender if intent_result else None) or gender
    _age = (intent_result.age if intent_result else None) or age

    text = body_text.strip()

    # 1. Command intro verbs
    text = re.sub(
        r"^(?:帮我?|请)*\s*(?:录入|建立|新建|创建|添加)\s*",
        "",
        text,
    )

    # 2. Patient-category words + optional leading quantifier
    text = re.sub(
        r"^(?:一[个位])?\s*(?:新)?\s*(?:患者|病人|病历)\s*[，,]?\s*",
        "",
        text,
    )

    # 3. Exact patient name
    if _name:
        text = re.sub(rf"^{re.escape(_name)}\s*[，,]?\s*", "", text)

    # 4. Gender
    if _gender:
        text = re.sub(rf"^{re.escape(_gender)}(?:性)?\s*[，,]?\s*", "", text)

    # 5. Age
    if _age is not None:
        text = re.sub(rf"^{_age}\s*岁\s*[，,。]?\s*", "", text)

    # Clean residual leading separators
    text = text.lstrip("，, 。\t\n")

    return text
