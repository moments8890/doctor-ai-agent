"""Chinese name validation — surname-based heuristic.

Used by resolve._ensure_patient to avoid auto-creating patients
with symptom/medical-term names like "头痛" or "血压".
"""
from __future__ import annotations

# Top single-character surnames covering >99% of Chinese population.
# Rare single-char surnames that collide with common medical/clinical terms
# (门, 高, etc.) are excluded — better to miss a rare surname than to
# auto-create a patient named "高血压" or "门诊".
_SINGLE_SURNAMES = frozenset(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何林罗郑梁谢宋唐许韩冯邓曹彭曾肖田"
    "董潘袁蔡蒋余于杜叶程魏苏吕丁任沈姚卢傅钟姜崔谭廖范汪陆金石戴贾韦夏邱"
    "方侯邹熊孟秦白江阎薛尹段雷黎史龙贺顾毛郝龚邵万钱严覃武陶洪赖莫孔汤向"
    "常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳"
    "甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴"
    "蒙鲍华喻祁蒲房奚穆萧佘闵解强柏米松连宗瞿褚巫慕和艾隋景冀凤花闻麻"
    "燕古全仇吉寇丛苑粟池边竺权逄卞鄂扈练佟栗仲占司甄桑敖冷卓居项楚危铁"
    "暴瑞银查付原买朴尉元鹿义束芦户荆那车逯乜养勾植岑晏桂从巩禹井满漆简栾"
    "荀央汲双税后明应晋拓夙虞"
)

# Compound surnames (复姓) — checked as 2-char prefixes
_COMPOUND_SURNAMES = frozenset({
    "欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "令狐", "申屠", "宇文", "尉迟",
    "呼延", "公孙", "南宫", "太史", "淳于", "长孙", "慕容", "轩辕", "端木", "独孤",
    "百里", "东郭", "南门", "西门", "赫连", "鲜于", "闻人", "万俟",
    "澹台", "公冶", "宗政", "夹谷", "濮阳", "钟离",
})

# Prefixes used in informal names: 小王, 老李, 大刘, 阿芳
_NAME_PREFIXES = frozenset({"小", "老", "大"})
# Note: "阿" excluded as prefix — collides with "阿司匹林", "阿托伐他汀" etc.


def looks_like_chinese_name(s: str) -> bool:
    """Return True if *s* looks like a plausible Chinese person name.

    Handles:
    - 张三, 李淑芳, 王建国 (2-3 char, single surname)
    - 欧阳明, 诸葛亮, 司马懿 (3-4 char, compound surname)
    - 小王, 老李, 大刘 (prefix + surname, 2-3 char result)
    - 上官婉儿 (4 char, compound surname)

    Rejects:
    - 头痛, 血压, 胸闷 (symptoms)
    - 阿司匹林, 阿托伐他汀 (drugs)
    - 心电图, 高血压, 门诊 (medical terms)
    - Single characters, >4 chars without prefix
    """
    if not s or len(s) < 2:
        return False

    # Strip optional prefix (小王 → 王, 老李华 → 李华)
    core = s
    has_prefix = False
    if s[0] in _NAME_PREFIXES and len(s) >= 2:
        core = s[1:]
        has_prefix = True

    # Prefixed names: core can be 1 char (小王) or 2-3 chars (小王明)
    # Non-prefixed names: core must be 2-4 chars (张三, 欧阳明远)
    if has_prefix:
        if len(core) < 1 or len(core) > 3:
            return False
    else:
        if len(core) < 2 or len(core) > 4:
            return False

    # Check compound surnames first (欧阳X, 诸葛X)
    if len(core) >= 3 and core[:2] in _COMPOUND_SURNAMES:
        return True

    # Check single-character surname
    if core[0] in _SINGLE_SURNAMES:
        return True

    return False
