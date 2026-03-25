from __future__ import annotations

import re
import unicodedata
from typing import List


def normalize(text: str) -> str:
    """NFKC full→half width, whitespace collapse, lowercase Latin, Chinese punctuation standardization."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.lower()
    text = text.replace("，", ",").replace("。", ".").replace("；", ";")
    text = text.replace("：", ":").replace("（", "(").replace("）", ")")
    return text


# Brand name → generic name mapping (Chinese drugs)
BRAND_GENERIC = {
    "波立维": "氯吡格雷", "拜新同": "硝苯地平",
    "立普妥": "阿托伐他汀", "可定": "瑞舒伐他汀",
    "倍他乐克": "美托洛尔", "格华止": "二甲双胍",
    "拜阿司匹林": "阿司匹林", "泰嘉": "氯吡格雷",
}

# English abbreviation → Chinese full name
ABBREVIATION_FULL = {
    "HTN": "高血压", "DM": "糖尿病", "CHD": "冠心病",
    "BP": "血压", "HR": "心率", "EF": "射血分数",
    "PCI": "经皮冠状动脉介入", "STEMI": "ST段抬高型心肌梗死",
    "NSTEMI": "非ST段抬高型心肌梗死", "ACS": "急性冠脉综合征",
    "CKD": "慢性肾脏病", "COPD": "慢性阻塞性肺疾病",
    "ICH": "脑出血", "SAH": "蛛网膜下腔出血",
    "AVM": "动静脉畸形", "TIA": "短暂性脑缺血发作",
}

# Time/frequency abbreviations → Chinese
TIME_ALIASES = {
    "10y": "10年", "3d": "3天", "90min": "90分钟",
    "qd": "每日一次", "bid": "每日两次", "tid": "每日三次",
    "qid": "每日四次", "prn": "必要时",
}


def expand_aliases(text: str, aliases: List[str]) -> List[str]:
    """Return all normalized forms to search for: original + explicit aliases + brand/generic + abbreviations."""
    forms = [normalize(text)]
    for alias in aliases:
        forms.append(normalize(alias))

    # Add brand↔generic expansions
    for brand, generic in BRAND_GENERIC.items():
        if brand in text or generic in text:
            forms.append(normalize(brand))
            forms.append(normalize(generic))

    # Add abbreviation↔full expansions
    for abbr, full in ABBREVIATION_FULL.items():
        if abbr in text or abbr.lower() in text.lower() or full in text:
            forms.append(normalize(abbr))
            forms.append(normalize(full))

    # Add time alias expansions
    for abbr, full in TIME_ALIASES.items():
        if abbr in text.lower() or full in text:
            forms.append(normalize(abbr))
            forms.append(normalize(full))

    return list(dict.fromkeys(forms))  # dedupe preserving order
