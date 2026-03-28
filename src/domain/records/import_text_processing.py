"""
历史病历导入 — 文本预处理与分块。

Regex constants, heuristics, preprocessing, and chunking utilities used by the
import pipeline.  No async code, no DB access.
"""

from __future__ import annotations

import re as _re
from typing import List, Optional


_VISIT_BOUNDARY_RE = _re.compile(
    r"(?:^|\n)(?="
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}"
    r"|第\d+次|初诊|复诊|【\d{4}"
    r")",
    _re.MULTILINE,
)

_DATE_IN_TEXT_RE = _re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}")

_CHAT_EXPORT_HEADER_RE = _re.compile(
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?\s+\S",
    _re.MULTILINE,
)

_EXAM_SUMMARY_RE = _re.compile(
    r"(?:^|\n)(?:\d+[.．、]\s*)?(?:"
    r"检查综述|体检结论|健康评估|主要.*?问题|检查结论|体检小结"
    r"|体检重要异常结果|阳性结果和异常情况|异常结果及建议"
    r"|重要检查结论|体检报告总结"
    r")",
    _re.MULTILINE,
)

_STRUCTURED_REPORT_RE = _re.compile(
    r"(?:"
    r"(?:姓\s*名|患者姓名|检查日期|报告日期|体检编号|住院号|门诊号|标本编号|送检日期)"
    r".{0,20}"
    r"(?:性\s*别|年\s*龄|科\s*室|床\s*号|检查者)"
    r"|"
    r"(?:健康体检报告|MEDICAL EXAMINATION REPORT).{0,60}(?:体检号|用户ID|检查日期)"
    r")",
    _re.DOTALL,
)

_REPORT_SECTION_RE = _re.compile(
    r"(?:^|\n)【[^】]{2,12}】"
    r"|(?:^|\n)[一二三四五六七八九十]+[、.．]\s*\S"
    r"|(?:^|\n)\d+\s{2,}[\u4e00-\u9fff]"
)

_OCR_NAME_RE = _re.compile(r"姓\s*名[：:]\s*([\u4e00-\u9fff]{2,5})")
_OCR_GENDER_RE = _re.compile(r"性\s*别[：:]\s*([男女])")
_OCR_AGE_RE = _re.compile(r"年\s*龄[：:]\s*(\d{1,3})")


def _looks_like_chat_export(text: str) -> bool:
    """Heuristic: does the text look like a WeChat chat export?"""
    return bool(_CHAT_EXPORT_HEADER_RE.search(text[:2000]))


def _looks_like_structured_report(text: str) -> bool:
    """Return True if text is a single structured report (体检报告, 化验单, etc.)"""
    sample = text[:1500]
    return bool(_STRUCTURED_REPORT_RE.search(sample)) and bool(_REPORT_SECTION_RE.search(sample))


def _extract_exam_identity(header: str) -> str:
    """Extract name/gender/age/date from exam report header."""
    name_m = _re.search(r"姓\s*名\s+(\S+)", header) or _re.search(
        r"REPORT\s+(\S{2,4})\s+(?:女士|先生|男士)", header
    )
    gender_m = _re.search(r"性别\s+([男女])", header) or _re.search(
        r"(\S{2,4})\s+(女士|先生)", header
    )
    age_m = _re.search(r"年龄\s+(\d+\s*岁?)", header)
    date_m = _re.search(r"体检日期\s+(\S+)", header) or _re.search(
        r"(\d{4}年\d{1,2}月\d{1,2}日)的体检报告", header
    )
    parts = []
    if name_m:
        parts.append(f"姓名：{name_m.group(1)}")
    if gender_m:
        raw = gender_m.group(2) if gender_m.lastindex and gender_m.lastindex >= 2 else gender_m.group(1)
        val = "女" if "女" in raw else ("男" if "男" in raw else raw)
        parts.append(f"性别：{val}")
    if age_m:
        parts.append(f"年龄：{age_m.group(1)}")
    if date_m:
        parts.append(f"体检日期：{date_m.group(1)}")
    return "  ".join(parts)


def _trim_exam_clinical(clinical: str) -> str:
    """Trim clinical body to exclude raw data tables."""
    conclusion_m = _re.search(
        r"(?:体检结论|健康建议|医师签名"
        r"|(?:^|\n)\s*3[\s、.．]+健康体检结果"
        r"|(?:^|\n)\s*[三3][\s、.．]+检查详细"
        r")",
        clinical,
        _re.MULTILINE,
    )
    if conclusion_m:
        return clinical[:conclusion_m.start() + 2000]
    return clinical


def _preprocess_exam_report(text: str) -> str:
    """Extract clinically relevant sections from a 体检报告."""
    m = _EXAM_SUMMARY_RE.search(text)
    if not m:
        return text
    body_start = m.start() + (1 if text[m.start()] in "\n\r" else 0)
    header = text[:body_start]
    identity_line = _extract_exam_identity(header)
    clinical = _trim_exam_clinical(text[body_start:].strip())
    return (identity_line + "\n\n" + clinical).strip() if identity_line else clinical


def _preprocess_import_text(
    text: str,
    source: str,
    sender_filter: Optional[str] = None,
) -> str:
    """Strip media prefixes and clean chat export formatting."""
    text = _re.sub(r"^\[(PDF|Word|Image):[^\]]*\]\s*", "", text, flags=_re.IGNORECASE)
    if source == "chat_export" or _looks_like_chat_export(text):
        from channels.wechat.wechat_media_pipeline import preprocess_wechat_chat_export
        text = preprocess_wechat_chat_export(text, sender_filter=sender_filter)
    elif _looks_like_structured_report(text):
        text = _preprocess_exam_report(text)
    return text.strip()


def _merge_short_paragraphs(paragraphs: List[str]) -> List[str]:
    """Merge tiny stub paragraphs (< 15 chars) into the following one."""
    merged: list = []
    buf = ""
    for p in paragraphs:
        if buf and len(buf) < 15:
            buf = (buf + "\n" + p).strip()
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return merged


def _merge_short_chunks(raw_chunks: List[str]) -> List[str]:
    """Merge adjacent short chunks (< 40 chars) into the next."""
    sections: list = []
    buf = ""
    for chunk in raw_chunks:
        buf = (buf + "\n" + chunk).strip() if buf else chunk
        if len(buf) >= 40:
            sections.append(buf)
            buf = ""
    if buf:
        if sections:
            sections[-1] = (sections[-1] + "\n" + buf).strip()
        else:
            sections.append(buf)
    return sections


def _chunk_history_text(text: str) -> List[str]:
    """Split bulk history text into individual visit chunks."""
    if _looks_like_structured_report(text):
        return [text]

    raw_boundaries = [m.start() for m in _VISIT_BOUNDARY_RE.finditer(text)]
    boundaries: list = []
    for pos in raw_boundaries:
        actual = pos + 1 if pos < len(text) and text[pos] == "\n" else pos
        if not boundaries or actual != boundaries[-1]:
            boundaries.append(actual)

    paragraphs = [p.strip() for p in _re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) >= 2:
        merged = _merge_short_paragraphs(paragraphs)
        if len(merged) >= 2:
            return merged

    if len(boundaries) >= 2:
        raw_chunks = []
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            chunk = text[start:end].strip()
            if chunk:
                raw_chunks.append(chunk)
        sections = _merge_short_chunks(raw_chunks)
        if len(sections) >= 2:
            return sections

    return [text]


def _extract_chunk_date(chunk: str) -> Optional[str]:
    """Extract the first date string from a chunk for display."""
    m = _DATE_IN_TEXT_RE.search(chunk)
    return m.group(0) if m else None


def _t(s: Optional[str], n: int = 30) -> str:
    if not s:
        return ""
    return s[:n] + "…" if len(s) > n else s
