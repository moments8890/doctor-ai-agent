"""
病历 Pydantic 模型：chat-first 设计，以整理后的自由文本为核心，附带关键词标签。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class MedicalRecord(BaseModel):
    content: str = Field(..., min_length=1, max_length=16000)
    """LLM 整理后的临床笔记（自由文本）。保留所有临床信息，语言流畅简洁。"""

    tags: List[str] = Field(default_factory=list)
    """关键词标签：诊断名称、药品、随访时间等，用于过滤和风险评估。"""

    record_type: Optional[str] = Field(default="visit")
    """记录类型：visit | dictation | import | interview_summary"""

    @field_validator("record_type", mode="before")
    @classmethod
    def _default_record_type(cls, v: object) -> str:
        return v if isinstance(v, str) and v.strip() else "visit"

    specialty_scores: List[dict] = Field(default_factory=list)
    """专科量表评分列表：[{"score_type": "NIHSS", "score_value": 8, "raw_text": "..."}]"""

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("content cannot be empty")
        return stripped
