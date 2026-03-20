# scripts/patient_sim/validator.py
"""3-tier validation for patient simulation results."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


@dataclass
class ValidationResult:
    # Tier 1
    db_pass: bool = False
    db_errors: List[str] = field(default_factory=list)
    # Tier 2
    extraction_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    extraction_pass: bool = False
    checklist_coverage: float = 0.0
    # Tier 3
    quality_score: Optional[int] = None
    quality_detail: Optional[Dict[str, Any]] = None
    # Overall
    passed: bool = False


def validate_tier1_db(
    db_path: str,
    session_id: Optional[str],
    record_id: Optional[int],
    review_id: Optional[int],
    persona_name: str,
) -> Tuple[bool, List[str]]:
    """Tier 1: DB state checks. Returns (pass, errors)."""
    errors = []
    conn = sqlite3.connect(db_path)
    try:
        # Record exists with content
        if record_id:
            row = conn.execute(
                "SELECT content, record_type, structured FROM medical_records WHERE id=?",
                (record_id,),
            ).fetchone()
            if not row:
                errors.append(f"medical_records row not found for id={record_id}")
            else:
                if not row[0]:
                    errors.append("medical_records.content is empty")
                if row[1] != "interview_summary":
                    errors.append(f"record_type={row[1]}, expected interview_summary")
                if row[2]:
                    try:
                        s = json.loads(row[2])
                        if not s.get("chief_complaint"):
                            errors.append("structured.chief_complaint is empty")
                    except json.JSONDecodeError:
                        errors.append("structured is not valid JSON")
                else:
                    errors.append("structured is null")
        else:
            errors.append("No record_id returned from confirm")

        # Review queue
        if review_id:
            row = conn.execute(
                "SELECT status FROM review_queue WHERE id=?", (review_id,),
            ).fetchone()
            if not row:
                errors.append(f"review_queue row not found for id={review_id}")
            elif row[0] != "pending_review":
                errors.append(f"review_queue status={row[0]}, expected pending_review")
        else:
            errors.append("No review_id returned from confirm")

        # Session confirmed
        if session_id:
            row = conn.execute(
                "SELECT status FROM interview_sessions WHERE id=?", (session_id,),
            ).fetchone()
            if not row:
                errors.append(f"interview_sessions row not found for id={session_id}")
            elif row[0] != "confirmed":
                errors.append(f"session status={row[0]}, expected confirmed")
    finally:
        conn.close()

    return (len(errors) == 0, errors)


def validate_tier2_extraction(
    collected: Dict[str, str],
    structured_json: Optional[str],
    expected_extracted: Dict[str, List[str]],
    checklist: Dict[str, Any],
) -> Tuple[bool, Dict[str, Dict[str, Any]], float]:
    """Tier 2: fact extraction. Returns (pass, field_results, checklist_coverage)."""
    # Merge collected + structured
    structured = {}
    if structured_json:
        try:
            structured = json.loads(structured_json)
        except json.JSONDecodeError:
            pass
    merged = {**structured, **collected}

    # Check expected keywords in extracted fields
    field_results = {}
    all_match = True
    for fld, keywords in expected_extracted.items():
        value = str(merged.get(fld, ""))
        matches = {kw: kw in value for kw in keywords}
        field_pass = all(matches.values())
        field_results[fld] = {"expected": keywords, "got": value[:100], "matches": matches, "pass": field_pass}
        if not field_pass:
            all_match = False

    # Checklist coverage: fraction of must_ask fields that have non-empty collected values
    must_ask = checklist.get("must_ask", [])
    min_cov = checklist.get("min_coverage", 0.6)
    if must_ask:
        covered = sum(1 for topic in must_ask if any(topic in str(v) for v in merged.values()))
        coverage = covered / len(must_ask)
    else:
        coverage = 1.0

    passed = all_match and coverage >= min_cov
    return (passed, field_results, coverage)


def validate_tier3_quality(
    client: OpenAI,
    model: str,
    conversation: List[Dict[str, str]],
    condition: str,
) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """Tier 3: LLM quality scoring. Returns (score, detail_dict)."""
    transcript = "\n".join(
        f"{'系统' if t['role'] == 'assistant' else '患者'}: {t['content']}"
        for t in conversation
    )

    prompt = f"""评估以下预问诊对话的质量（0-10分）。

评分维度：
1. 信息完整性 — 是否收集了足够的临床信息？
2. 问题相关性 — 问题是否与患者的病情相关？
3. 沟通质量 — 是否清晰、专业、有耐心？

患者背景：{condition}

对话记录：
{transcript}

返回JSON格式（只返回JSON，不要其他文字）：
{{"score": N, "completeness": N, "appropriateness": N, "communication": N, "explanation": "..."}}"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )
        text = resp.choices[0].message.content.strip()
        # Extract JSON from response (handle markdown fences)
        if "```" in text:
            text = text.split("```")[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        detail = json.loads(text)
        return (detail.get("score"), detail)
    except Exception:
        return (None, None)


def validate(
    db_path: str,
    sim_result: "SimResult",
    persona: Dict[str, Any],
    judge_client: Optional[OpenAI] = None,
    judge_model: str = "deepseek-chat",
) -> ValidationResult:
    """Run all 3 validation tiers."""
    from patient_sim.engine import SimResult

    vr = ValidationResult()

    # Tier 1
    vr.db_pass, vr.db_errors = validate_tier1_db(
        db_path, sim_result.session_id, sim_result.record_id,
        sim_result.review_id, persona["name"],
    )

    # Tier 2 — get structured from DB for merge
    structured_json = None
    if sim_result.record_id:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT structured FROM medical_records WHERE id=?", (sim_result.record_id,)).fetchone()
            if row:
                structured_json = row[0]
        finally:
            conn.close()

    vr.extraction_pass, vr.extraction_results, vr.checklist_coverage = validate_tier2_extraction(
        sim_result.final_collected,
        structured_json,
        persona.get("expected_extracted", {}),
        persona.get("checklist", {}),
    )

    # Tier 3
    if judge_client and sim_result.conversation:
        vr.quality_score, vr.quality_detail = validate_tier3_quality(
            judge_client, judge_model, sim_result.conversation, persona["condition"],
        )

    # Overall: Tier 1 + Tier 2 must pass; Tier 3 is informational
    vr.passed = vr.db_pass and vr.extraction_pass
    return vr
