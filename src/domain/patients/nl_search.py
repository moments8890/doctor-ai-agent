"""
自然语言患者搜索：从中文自由文本中提取结构化搜索条件。

示例：
    "那个姓张的阿姨"       → surname="张", gender="女"
    "上周来的高血压患者"    → days_since_visit=7, keywords=["高血压"]
    "60多岁的男性脑梗"      → age_min=60, age_max=69, gender="男", keywords=["脑梗"]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Gender hint lists ────────────────────────────────────────────────────────
_FEMALE_HINTS = ["阿姨", "女士", "奶奶", "姐姐", "大姐", "妈妈", "女孩", "女性", "她", "女"]
_MALE_HINTS   = ["叔叔", "大爷", "爷爷", "哥哥", "大哥", "爸爸", "男孩", "男性", "他", "男"]

# ── Recency keywords → days ──────────────────────────────────────────────────
_RECENCY_MAP: dict[str, int] = {
    "昨天":   1,
    "这两天":  2,
    "最近":   3,
    "本周":   7,
    "这周":   7,
    "上周":   7,
    "本月":   30,
    "这个月":  30,
    "上个月":  30,
}

# ── Words that are NOT medical keywords ─────────────────────────────────────
_STOPWORDS = frozenset({
    "那个", "这个", "哪个", "一个", "患者", "病人", "的人", "来的",
    "最近", "上周", "本周", "这周", "本月", "昨天",
    "阿姨", "女士", "奶奶", "姐姐", "大姐", "妈妈", "女孩", "女性",
    "叔叔", "大爷", "爷爷", "哥哥", "大哥", "爸爸", "男孩", "男性",
    "中年", "老年", "老人", "年轻", "岁的",
    "多岁", "几岁", "左右", "年龄",
    "姓名", "找找", "查查", "搜索", "搜一下",
})


@dataclass
class PatientSearchCriteria:
    """Structured search criteria extracted from a natural language query."""
    surname: Optional[str] = None          # e.g. "张"
    gender: Optional[str] = None           # "男" | "女"
    age_min: Optional[int] = None          # inclusive lower bound
    age_max: Optional[int] = None          # inclusive upper bound
    keywords: list[str] = field(default_factory=list)  # diagnosis / treatment terms
    days_since_visit: Optional[int] = None  # only return patients with a record within N days

    def is_empty(self) -> bool:
        return (
            self.surname is None
            and self.gender is None
            and self.age_min is None
            and self.age_max is None
            and not self.keywords
            and self.days_since_visit is None
        )


_CN_NUMS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_or_int(s: str) -> Optional[int]:
    if s in _CN_NUMS:
        return _CN_NUMS[s]
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _extract_age(q: str, c: PatientSearchCriteria) -> None:
    """从查询字符串提取年龄范围并写入 c.age_min / c.age_max。"""
    m = re.search(r'([一二三四五六七八九十\d]{1,3})多岁', q)
    if m:
        base = _cn_or_int(m.group(1))
        if base is not None:
            c.age_min, c.age_max = base, base + 9
            return
    m = re.search(r'([一二三四五六七八九\d])([零一二三四五六七八九十几]?)十(?:多|几)?岁', q)
    if m:
        base = (_cn_or_int(m.group(1)) or 1) * 10
        c.age_min, c.age_max = base, base + 9
        return
    if "中年" in q:
        c.age_min, c.age_max = 35, 59
    elif "老年" in q or "老人" in q or "老爷爷" in q or "老奶奶" in q:
        c.age_min = 60
    elif "年轻" in q or "小伙" in q or "小姑娘" in q:
        c.age_max = 35


def _extract_keywords(q: str) -> list:
    """剥离姓名/性别/年龄/时间结构词后，提取剩余中文医学关键词。"""
    residual = q
    residual = re.sub(r'姓[^\s，,的]{1,3}', '', residual)
    for h in _FEMALE_HINTS + _MALE_HINTS:
        residual = residual.replace(h, ' ')
    residual = re.sub(r'[一二三四五六七八九十\d]{1,3}多岁', '', residual)
    residual = re.sub(r'[一二三四五六七八九\d][零一二三四五六七八九十几]?十(?:多|几)?岁', '', residual)
    for phrase in _RECENCY_MAP:
        residual = residual.replace(phrase, ' ')
    for word in ["患者", "病人", "病患"]:
        residual = residual.replace(word, ' ')
    residual = re.sub(r'[那这哪一个的来了得有和与及或]{1,2}', ' ', residual)

    tokens = re.findall(r'[\u4e00-\u9fa5]{2,6}', residual)
    seen: set[str] = set()
    result = []
    for t in tokens:
        if t in seen or t in _STOPWORDS:
            continue
        seen.add(t)
        result.append(t)
    return result


def extract_criteria(query: str) -> PatientSearchCriteria:
    """将中文自由文本查询解析为结构化搜索条件。"""
    c = PatientSearchCriteria()
    q = query.strip()

    m = re.search(r'姓([^\s，,的]{1,3})', q)
    if m:
        c.surname = m.group(1).strip()

    if any(h in q for h in _FEMALE_HINTS):
        c.gender = "女"
    elif any(h in q for h in _MALE_HINTS):
        c.gender = "男"

    _extract_age(q, c)

    for phrase, days in _RECENCY_MAP.items():
        if phrase in q:
            c.days_since_visit = days
            break

    c.keywords = _extract_keywords(q)
    return c
