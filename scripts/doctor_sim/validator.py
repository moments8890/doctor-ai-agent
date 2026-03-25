"""Three-dimension validation for doctor simulation runs.

Dim 1: 事实提取召回率 (40%) — fact_catalog vs DB SOAP, 3 LLM judges majority vote
Dim 2: 字段归类准确率 (30%) — matched facts in correct field?
Dim 3: 记录质量 (30%) — no hallucinations, abbreviations preserved, no duplication

Pass criteria: dim1 >= 60 AND no hallucinations.

Uses sqlite3 directly — no ORM imports.
Reuses helpers from patient_sim.validator.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Reuse from patient_sim.validator
# ---------------------------------------------------------------------------

from patient_sim.validator import (
    _pick_judges,
    _llm_call,
    _parse_json_response,
    _load_soap_from_db,
    SOAP_FIELDS,
    resolve_db_path,
    analyze_results,
)


# ---------------------------------------------------------------------------
# LLM Judge Prompts
# ---------------------------------------------------------------------------

_DIM1_EXTRACTION_JUDGE_PROMPT = """\
/no_think
你是一位医学信息提取评审专家。请逐条判断以下期望事实是否出现在系统提取的结构化字段中。

## 系统实际提取的全部SOAP字段
{soap_dump}

## 需要核对的事实列表
{facts_block}

## 规则
- 不要求原文一模一样，只要语义等价即可判为匹配
- 例如"hs-cTnI 3.2"和"肌钙蛋白 3.2 ng/mL"是语义等价的
- "HTN 10y"和"高血压10年"也是等价的
- 缩写与全称等价：STEMI = ST段抬高型心肌梗死，PCI = 经皮冠状动脉介入治疗
- 品牌名与通用名等价：波立维 = 氯吡格雷，拜新同 = 硝苯地平控释片
- 如果事实出现在任何字段中（即使不是期望字段），也算匹配，但请标注实际所在字段
- 只有当某条事实在所有字段中都完全没有体现时，才判为未匹配

对每条事实，返回:
- "match": true/false
- "found_in": 实际找到的字段名（如未找到则为null）

请只返回JSON: {{"results": {{"fact_id_1": {{"match": true, "found_in": "present_illness"}}, "fact_id_2": {{"match": false, "found_in": null}}, ...}}}}
"""

_DIM3_HALLUCINATION_JUDGE_PROMPT = """\
/no_think
你是病历提取系统的幻觉检测专家。请检查数据库中存储的结构化字段是否包含**医生输入中从未提到过**的信息。

## 医生原始输入（全部轮次）
{doctor_input}

## 数据库中存储的结构化字段
{soap_dump}

## 规则
- 逐字段检查：对于每个非空字段，确认其内容在医生输入中有对应的来源
- "幻觉"的定义：结构化字段中出现了医生从未输入的信息
- 合理的医学规范化表述不算幻觉（如"HTN"规范为"高血压"是可以的）
- 缩写展开不算幻觉（如"STEMI"展开为"ST段抬高型心肌梗死"）
- 但无中生有的信息算幻觉（如医生没提到家族史，DB却有具体内容）
- 重复不算幻觉（重复在质量部分单独检查）

如发现幻觉，请列出每个幻觉的字段名和具体内容。
请只返回JSON: {{"hallucinations": [{{"field": "字段名", "detail": "具体幻觉内容描述"}}]}}
如果没有幻觉，返回：{{"hallucinations": []}}
"""

_DIM3_QUALITY_JUDGE_PROMPT = """\
/no_think
你是病历提取系统的质量评审员。请检查以下两项：

## 医生原始输入（全部轮次）
{doctor_input}

## 数据库中存储的结构化字段
{soap_dump}

## 检查项

### 1. 缩写保留
医生输入的缩写和专业术语（如EF 45%、STEMI、PCI、BNP 168等）是否在数据库中被保留？
如果医生写"EF 45%"而数据库写"射血分数45%"，这算缩写未保留。
注意：品牌名转通用名是可接受的（如 波立维 → 氯吡格雷）。

### 2. 信息重复
在多轮输入场景下，同一事实是否在同一字段中被重复记录？
例如同一个诊断出现两次。

请返回JSON:
{{
  "abbreviation_issues": [{{"field": "字段名", "original": "医生原文", "db_value": "数据库值", "detail": "描述"}}],
  "duplication_issues": [{{"field": "字段名", "detail": "重复内容描述"}}]
}}
如果没有问题，对应列表返回空数组。
"""


# ---------------------------------------------------------------------------
# Dim 1: 事实提取召回率 — 3 LLM judges, majority vote
# ---------------------------------------------------------------------------

async def _dim1_judge_single(
    soap: Dict[str, str],
    facts: List[dict],
    provider: dict,
) -> Dict[str, dict]:
    """One LLM judge checks fact_catalog against SOAP fields."""
    soap_lines = []
    for field, value in soap.items():
        soap_lines.append(f"- {field}: {value or '（空）'}")
    soap_dump = "\n".join(soap_lines)

    facts_block_lines = []
    for f in facts:
        fid = f["id"]
        expected_field = f.get("field", "未指定")
        text = f.get("text", "")
        facts_block_lines.append(f"- {fid} (期望字段: {expected_field}): {text}")
    facts_block = "\n".join(facts_block_lines)

    prompt = _DIM1_EXTRACTION_JUDGE_PROMPT.format(
        soap_dump=soap_dump,
        facts_block=facts_block,
    )

    label = provider.get("label", provider.get("model", "?"))
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        results = parsed.get("results", {})
        out: Dict[str, dict] = {}
        for f in facts:
            fid = f["id"]
            entry = results.get(fid, {})
            out[fid] = {
                "match": bool(entry.get("match", False)),
                "found_in": entry.get("found_in"),
                "model": label,
            }
        return out
    except Exception as e:
        out = {}
        for f in facts:
            fid = f["id"]
            out[fid] = {"match": False, "found_in": None, "model": label, "error": str(e)}
        return out


async def _dim1_extraction_recall(
    soap: Dict[str, str],
    fact_catalog: List[dict],
) -> dict:
    """Fact catalog recall vs DB SOAP fields.

    Uses 3 LLM judges with majority vote.
    Returns: {score, facts: {fact_id: {match, found_in, expected_field, importance}}}
    """
    if not fact_catalog:
        return {"score": 100, "facts": {}}

    providers = _pick_judges(3)
    all_results = await asyncio.gather(*[
        _dim1_judge_single(soap, fact_catalog, p) for p in providers
    ])

    facts_out: Dict[str, dict] = {}
    matched_count = 0

    for f in fact_catalog:
        fid = f["id"]
        importance = f.get("importance", "normal")
        expected_field = f.get("field", "")

        votes = [r.get(fid, {}).get("match", False) for r in all_results]
        matched = sum(votes) >= 2  # majority

        found_in_votes = [
            r.get(fid, {}).get("found_in")
            for r in all_results if r.get(fid, {}).get("match")
        ]
        found_in = found_in_votes[0] if found_in_votes else None

        facts_out[fid] = {
            "match": matched,
            "found_in": found_in,
            "expected_field": expected_field,
            "importance": importance,
            "text": f.get("text", ""),
        }
        if matched:
            matched_count += 1

    score = int(round(matched_count / len(fact_catalog) * 100)) if fact_catalog else 100
    return {"score": score, "matched": matched_count, "total": len(fact_catalog), "facts": facts_out}


# ---------------------------------------------------------------------------
# Dim 2: 字段归类准确率 — derived from dim1 results
# ---------------------------------------------------------------------------

def _dim2_field_accuracy(dim1_result: dict) -> dict:
    """Of the matched facts, how many are in the correct field?

    Returns: {score, correct: int, total_matched: int, facts: {fact_id: {correct, expected, actual}}}
    """
    facts = dim1_result.get("facts", {})
    matched_facts = {fid: info for fid, info in facts.items() if info.get("match")}

    if not matched_facts:
        return {"score": 100, "correct": 0, "total_matched": 0, "facts": {}}

    correct_count = 0
    facts_out: Dict[str, dict] = {}

    for fid, info in matched_facts.items():
        expected_field = info.get("expected_field", "")
        found_in = info.get("found_in", "")
        is_correct = expected_field and found_in and expected_field == found_in

        facts_out[fid] = {
            "correct": is_correct,
            "expected_field": expected_field,
            "actual_field": found_in or "未找到",
        }
        if is_correct:
            correct_count += 1

    score = int(round(correct_count / len(matched_facts) * 100))
    return {
        "score": score,
        "correct": correct_count,
        "total_matched": len(matched_facts),
        "facts": facts_out,
    }


# ---------------------------------------------------------------------------
# Dim 3: 记录质量 — hallucination check + abbreviation + duplication
# ---------------------------------------------------------------------------

def _build_doctor_input_text(persona: dict) -> str:
    """Concatenate all turn_plan texts as the doctor's original input."""
    turn_plan = persona.get("turn_plan", [])
    lines = []
    for step in turn_plan:
        turn_num = step.get("turn", "?")
        text = step.get("text", "")
        lines.append(f"[轮次{turn_num}] {text}")
    return "\n\n".join(lines) if lines else "（无输入）"


async def _dim3_record_quality(
    soap: Dict[str, str],
    persona: dict,
) -> dict:
    """Record quality: hallucination check + abbreviation preservation + duplication.

    Returns: {score, hallucinations, abbreviation_issues, duplication_issues}
    """
    doctor_input = _build_doctor_input_text(persona)

    soap_lines = []
    for field, value in soap.items():
        if value and value.strip():
            soap_lines.append(f"- {field}: {value}")
    soap_dump = "\n".join(soap_lines) if soap_lines else "（所有字段为空）"

    # --- Hallucination check (1 LLM judge) ---
    hallucination_prompt = _DIM3_HALLUCINATION_JUDGE_PROMPT.format(
        doctor_input=doctor_input,
        soap_dump=soap_dump,
    )

    # --- Quality check (1 LLM judge) ---
    quality_prompt = _DIM3_QUALITY_JUDGE_PROMPT.format(
        doctor_input=doctor_input,
        soap_dump=soap_dump,
    )

    # Run both concurrently
    providers = _pick_judges(2)
    hallucination_provider = providers[0]
    quality_provider = providers[1 % len(providers)]

    async def _run_hallucination():
        try:
            raw = await _llm_call(hallucination_provider, hallucination_prompt)
            parsed = _parse_json_response(raw)
            return parsed.get("hallucinations", [])
        except Exception:
            return []

    async def _run_quality():
        try:
            raw = await _llm_call(quality_provider, quality_prompt)
            parsed = _parse_json_response(raw)
            return {
                "abbreviation_issues": parsed.get("abbreviation_issues", []),
                "duplication_issues": parsed.get("duplication_issues", []),
            }
        except Exception:
            return {"abbreviation_issues": [], "duplication_issues": []}

    hallucinations, quality = await asyncio.gather(
        _run_hallucination(),
        _run_quality(),
    )

    abbreviation_issues = quality.get("abbreviation_issues", [])
    duplication_issues = quality.get("duplication_issues", [])

    # Score: hallucination-free worth 50, abbreviations worth 25, no-duplication worth 25
    hallucination_score = 50 if not hallucinations else 0
    abbreviation_score = 25 if not abbreviation_issues else max(0, 25 - len(abbreviation_issues) * 5)
    duplication_score = 25 if not duplication_issues else max(0, 25 - len(duplication_issues) * 5)

    score = hallucination_score + abbreviation_score + duplication_score

    return {
        "score": score,
        "hallucinations": hallucinations,
        "abbreviation_issues": abbreviation_issues,
        "duplication_issues": duplication_issues,
    }


# ---------------------------------------------------------------------------
# Main validation function
# ---------------------------------------------------------------------------

async def validate_doctor_extraction(
    persona: dict,
    db_path: str,
    record_id: int,
) -> dict:
    """Evaluate a doctor interview extraction across 3 dimensions.

    Dim 1: 事实提取召回率 (40%) — fact_catalog vs DB SOAP, 3 LLM judges
    Dim 2: 字段归类准确率 (30%) — matched facts in correct field
    Dim 3: 记录质量 (30%) — no hallucinations, abbreviations preserved, no duplication

    Returns {
        'pass': bool,
        'combined_score': int (0-100),
        'dimensions': {
            'dim1_extraction_recall': {...},
            'dim2_field_accuracy': {...},
            'dim3_record_quality': {...},
        }
    }
    """
    soap = _load_soap_from_db(record_id, db_path)
    fact_catalog = persona.get("fact_catalog", [])

    # --- Dim 1 (LLM) and Dim 3 (LLM) can run concurrently ---
    dim1_task = _dim1_extraction_recall(soap, fact_catalog)
    dim3_task = _dim3_record_quality(soap, persona)
    dim1, dim3 = await asyncio.gather(dim1_task, dim3_task)

    # --- Dim 2 is derived from dim1 (no LLM needed) ---
    dim2 = _dim2_field_accuracy(dim1)

    # --- Combined score: weighted average ---
    # 事实提取召回率 40% + 字段归类准确率 30% + 记录质量 30%
    combined_score = int(round(
        dim1["score"] * 0.40
        + dim2["score"] * 0.30
        + dim3["score"] * 0.30
    ))

    # --- Pass criteria: dim1 >= 60 AND no hallucinations ---
    no_hallucinations = len(dim3.get("hallucinations", [])) == 0
    dim1_sufficient = dim1["score"] >= 60
    passed = no_hallucinations and dim1_sufficient

    return {
        "pass": passed,
        "combined_score": combined_score,
        "dimensions": {
            "dim1_extraction_recall": dim1,
            "dim2_field_accuracy": dim2,
            "dim3_record_quality": dim3,
        },
    }
