"""
病历 Pydantic 模型（LLM → Repository 传输层）。
- content：可读临床笔记（字符串）
- structured：结构化字段 dict，Repository 写入时展开为独立列
- tags：关键词标签
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class MedicalRecord(BaseModel):
    content: str = Field(..., min_length=1, max_length=16000)
    """LLM 整理后的临床笔记（可读文本）。"""

    structured: Optional[Dict[str, str]] = Field(default=None)
    """结构化字段 dict — RecordRepository.create() 展开写入 DB 独立列。"""

    tags: List[str] = Field(default_factory=list)
    """关键词标签：诊断名称、药品、随访时间等。"""

    record_type: Optional[str] = Field(default="visit")
    """记录类型：visit | dictation | import | interview_summary"""

    @field_validator("record_type", mode="before")
    @classmethod
    def _default_record_type(cls, v: object) -> str:
        return v if isinstance(v, str) and v.strip() else "visit"

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("content cannot be empty")
        return stripped
