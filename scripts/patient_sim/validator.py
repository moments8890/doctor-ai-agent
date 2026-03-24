"""Four-tier validation for patient simulation runs.

Tier 1: DB integrity checks (hard gate)
Tier 2: Semantic fact extraction — 3 LLM judges, majority vote (hard gate)
Tier 3: LLM quality score — 5 judges across providers, median (soft)
Tier 4: Anomaly review — LLM inspects DB fields + conversation for issues (soft)

Uses sqlite3 directly — no ORM imports.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ---------------------------------------------------------------------------
# DB path resolution — mirrors tests/integration/conftest.py
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_db_path() -> str:
    """Resolve DB path: env var > config/runtime.json > fallback."""
    env = os.environ.get("PATIENTS_DB_PATH")
    if env:
        return str(Path(env).expanduser())

    runtime_json = _REPO_ROOT / "config" / "runtime.json"
    if runtime_json.exists():
        try:
            cfg = json.loads(runtime_json.read_text(encoding="utf-8"))
            val = cfg.get("PATIENTS_DB_PATH")
            if isinstance(cfg.get("database"), dict):
                val = val or cfg["database"].get("PATIENTS_DB_PATH")
            if val:
                return str(Path(val).expanduser())
        except Exception:
            pass

    return str(_REPO_ROOT / "data" / "patients.db")


# ---------------------------------------------------------------------------
# SOAP field keys
# ---------------------------------------------------------------------------

SOAP_FIELDS: List[str] = [
    "department", "chief_complaint", "present_illness", "past_history",
    "allergy_history", "personal_history", "marital_reproductive",
    "family_history", "physical_exam", "specialist_exam", "auxiliary_exam",
    "diagnosis", "treatment_plan", "orders_followup",
]


# ---------------------------------------------------------------------------
# LLM calling helpers (shared by Tier 2 and Tier 3)
# ---------------------------------------------------------------------------

# All judges use Groq with different models (all < $0.10/M input tokens).
# Model diversity gives independent perspectives; same API key.
_JUDGE_MODELS = [
    {"model": "llama-3.1-8b-instant", "label": "Llama-3.1-8B"},        # $0.05/M
    {"model": "openai/gpt-oss-20b", "label": "GPT-OSS-20B"},           # $0.075/M
    {"model": "openai/gpt-oss-safeguard-20b", "label": "Safeguard-20B"},  # $0.075/M
]

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_KEY_ENV = "GROQ_API_KEY"


def _pick_judges(n: int) -> List[dict]:
    """Pick *n* judge configs, round-robin across models."""
    api_key = os.environ.get(_GROQ_KEY_ENV, "")
    if not api_key:
        raise RuntimeError(f"{_GROQ_KEY_ENV} not set — needed for judges")
    return [
        {
            "base_url": _GROQ_BASE_URL,
            "model": _JUDGE_MODELS[i % len(_JUDGE_MODELS)]["model"],
            "label": _JUDGE_MODELS[i % len(_JUDGE_MODELS)]["label"],
            "api_key_env": _GROQ_KEY_ENV,
        }
        for i in range(n)
    ]


async def _llm_call(provider: dict, prompt: str, temperature: float = 0.2) -> str:
    """Single LLM chat completion call. Returns raw content string."""
    api_key = os.environ.get(provider["api_key_env"], "")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{provider['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": provider["model"],
                "messages": [{"role": "user", "content": f"/no_think\n{prompt}"}],
                "temperature": temperature,
                "max_tokens": 512,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    raw = data["choices"][0]["message"]["content"]
    # Strip think tags and code fences
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw.strip()


def _parse_json_response(raw: str) -> dict:
    """Best-effort JSON extraction from LLM response."""
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try to find JSON object in the text
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# Tier 1 — DB integrity checks (unchanged)
# ---------------------------------------------------------------------------

def validate_tier1(
    record_id: int,
    session_id: str,
    review_id: Optional[int],
    persona: dict,
    db_path: str,
) -> dict:
    """Hard-gate DB validation."""
    checks: Dict[str, Dict[str, Any]] = {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # 1. Record created
        row = conn.execute(
            "SELECT id, content, record_type FROM medical_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            checks["record_created"] = {"pass": False, "detail": f"record id={record_id} not found"}
        else:
            content_ok = bool(row["content"] and row["content"].strip())
            type_ok = row["record_type"] == "interview_summary"
            ok = content_ok and type_ok
            checks["record_created"] = {"pass": ok, "detail": "OK" if ok else "content empty or wrong type"}

        # 2. SOAP chief_complaint populated
        if row is not None:
            cc = conn.execute("SELECT chief_complaint FROM medical_records WHERE id = ?", (record_id,)).fetchone()
            cc_ok = bool(cc and cc["chief_complaint"] and cc["chief_complaint"].strip())
            checks["soap_fields"] = {"pass": cc_ok, "detail": "OK" if cc_ok else "chief_complaint empty"}
        else:
            checks["soap_fields"] = {"pass": False, "detail": "skipped"}

        # 3. Session confirmed
        sess = conn.execute("SELECT status FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
        if sess is None:
            checks["session_confirmed"] = {"pass": False, "detail": "session not found"}
        else:
            ok = sess["status"] == "confirmed"
            checks["session_confirmed"] = {"pass": ok, "detail": "OK" if ok else f"status={sess['status']!r}"}

        # 4. Patient linked
        if row is not None:
            pat = conn.execute(
                "SELECT p.name FROM patients p JOIN medical_records mr ON mr.patient_id = p.id WHERE mr.id = ?",
                (record_id,),
            ).fetchone()
            expected = persona.get("name", "")
            if pat is None:
                checks["patient_linked"] = {"pass": False, "detail": "no patient linked"}
            else:
                ok = pat["name"] == expected
                checks["patient_linked"] = {"pass": ok, "detail": "OK" if ok else f"name mismatch: {pat['name']!r}"}
        else:
            checks["patient_linked"] = {"pass": False, "detail": "skipped"}

        # 5. Review task
        task = conn.execute(
            "SELECT id FROM doctor_tasks WHERE record_id = ? AND task_type = 'review'", (record_id,),
        ).fetchone()
        checks["review_task"] = {
            "pass": task is not None,
            "detail": f"OK (task id={task['id']})" if task else "no review task found",
        }

    finally:
        conn.close()

    return {"pass": all(c["pass"] for c in checks.values()), "checks": checks}


# ---------------------------------------------------------------------------
# Tier 2 — Semantic extraction: 3 LLM judges, majority vote
# ---------------------------------------------------------------------------

def _load_soap_from_db(record_id: int, db_path: str) -> Dict[str, str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = ", ".join(SOAP_FIELDS)
        row = conn.execute(f"SELECT {cols} FROM medical_records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return {}
        return {f: (row[f] or "") for f in SOAP_FIELDS}
    finally:
        conn.close()


_EXTRACTION_JUDGE_PROMPT = """\
/no_think
你是一位医学信息提取评审专家。请判断系统从预问诊对话中提取的信息是否与期望的关键信息在语义上一致。

## 评审字段: {field}

### 期望包含的关键信息
{expected}

### 系统实际提取的内容
{got}

## 规则
- 不要求原文一模一样，只要语义等价即可判为匹配
- 例如"体检发现动脉瘤"和"MRA检查发现脑动脉瘤"是语义等价的
- "高血压5年"和"高血压病史5年，服用氨氯地平"也是等价的
- 如果期望的信息完全没有在实际内容中体现（即使用不同措辞），判为不匹配
- 不需要每个关键词都出现，只要核心临床含义被覆盖即可

请只返回JSON: {{"match": true/false, "reason": "一句话解释"}}
"""


async def _judge_extraction_field(
    field: str, expected: List[str], got: str, provider: dict,
) -> dict:
    """One judge evaluates one field. Returns {"match": bool, "reason": str}."""
    prompt = _EXTRACTION_JUDGE_PROMPT.format(
        field=field,
        expected="\n".join(f"- {kw}" for kw in expected),
        got=got or "（空）",
    )
    label = provider.get("label", provider.get("model", "?"))
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        return {
            "match": bool(parsed.get("match", False)),
            "reason": str(parsed.get("reason", raw[:100])),
            "model": label,
        }
    except Exception as e:
        return {"match": False, "reason": f"judge error: {e}", "model": label}


async def _judge_field_with_majority(
    field: str, expected: List[str], got: str,
) -> dict:
    """Run 3 judges on one field, majority vote."""
    providers = _pick_judges(3)
    results = await asyncio.gather(*[
        _judge_extraction_field(field, expected, got, p)
        for p in providers
    ])
    votes = [r["match"] for r in results]
    match = sum(votes) >= 2  # majority
    reasons = [r["reason"] for r in results]
    models = [r.get("model", "?") for r in results]
    return {
        "match": match,
        "votes": votes,
        "reasons": reasons,
        "models": models,
    }


async def validate_tier2(
    persona: dict,
    db_path: str,
    record_id: int,
) -> dict:
    """Semantic extraction validation with 3 LLM judges per field.

    Validates against DB (medical_records SOAP columns) — the persisted
    record is the source of truth, not the transient LLM turn response.
    """
    soap = _load_soap_from_db(record_id, db_path)

    expected_extracted: Dict[str, List[str]] = persona.get("expected_extracted", {})
    extraction: Dict[str, Dict[str, Any]] = {}

    # Judge all fields concurrently
    tasks = {}
    for field, keywords in expected_extracted.items():
        got_text = soap.get(field, "")
        tasks[field] = _judge_field_with_majority(field, keywords, got_text)

    judge_results = {}
    for field, coro in tasks.items():
        judge_results[field] = await coro

    all_match = True
    for field, keywords in expected_extracted.items():
        got_text = soap.get(field, "")
        jr = judge_results.get(field, {"match": False, "votes": [], "reasons": []})
        if not jr["match"]:
            all_match = False
        extraction[field] = {
            "expected": keywords,
            "got": got_text[:200] if got_text else "",
            "match": jr["match"],
            "votes": jr["votes"],
            "reasons": jr["reasons"],
        }

    # Checklist coverage — must_ask entries are natural-language topics
    # (e.g. "头痛", "家族史"), not SOAP field keys. Search across all fields.
    checklist = persona.get("checklist", {})
    must_ask: List[str] = checklist.get("must_ask", [])
    min_coverage: float = checklist.get("min_coverage", 0.6)

    all_soap_text = " ".join(str(v) for v in soap.values() if v)
    populated = sum(1 for topic in must_ask if topic in all_soap_text)
    coverage = populated / len(must_ask) if must_ask else 1.0
    checklist_pass = coverage >= min_coverage

    return {
        "pass": all_match and checklist_pass,
        "extraction": extraction,
        "checklist_coverage": round(coverage, 3),
        "checklist_pass": checklist_pass,
    }


# ---------------------------------------------------------------------------
# Tier 3 — Quality: 5 LLM judges, median score
# ---------------------------------------------------------------------------

_QUALITY_JUDGE_PROMPT = """\
/no_think
评估以下预问诊对话的质量（0-10分）。

评分维度：
1. completeness — 是否收集了足够的临床信息？（病史、用药、家族史、过敏等）
2. appropriateness — 问题是否与患者的病情相关且有逻辑？
3. communication — 是否清晰、专业、有耐心？对患者友好？

患者背景：{name}，{condition}
对话记录：
{transcript}

请只返回JSON格式：
{{"score": N, "completeness": N, "appropriateness": N, "communication": N, "explanation": "一句话评价"}}
"""


async def _single_quality_judge(
    provider: dict, transcript: str, persona: dict,
) -> dict:
    """One quality judge. Returns parsed scores or defaults."""
    prompt = _QUALITY_JUDGE_PROMPT.format(
        name=persona.get("name", "?"),
        condition=persona.get("condition", "?"),
        transcript=transcript,
    )
    default = {"score": -1, "completeness": -1, "appropriateness": -1, "communication": -1, "explanation": ""}
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        return {
            "score": int(parsed.get("score", -1)),
            "completeness": int(parsed.get("completeness", -1)),
            "appropriateness": int(parsed.get("appropriateness", -1)),
            "communication": int(parsed.get("communication", -1)),
            "explanation": str(parsed.get("explanation", "")),
        }
    except Exception as e:
        default["explanation"] = f"judge error: {e}"
        return default


async def validate_tier3(
    conversation: list,
    persona: dict,
    provider: str,
) -> dict:
    """5 LLM judges score the conversation, return median scores."""
    transcript_lines = []
    for turn in conversation:
        role = "AI助手" if turn.get("role") == "system" else "患者"
        text = turn.get("content", turn.get("text", ""))
        transcript_lines.append(f"{role}: {text}")
    transcript = "\n".join(transcript_lines)

    providers = _pick_judges(5)
    results = await asyncio.gather(*[
        _single_quality_judge(p, transcript, persona)
        for p in providers
    ])

    # Filter out failed judges (score == -1)
    valid = [r for r in results if r["score"] >= 0]
    if not valid:
        return {
            "score": -1, "completeness": -1, "appropriateness": -1, "communication": -1,
            "explanation": "all judges failed",
            "judge_count": len(results), "valid_count": 0, "all_scores": [],
        }

    return {
        "score": int(median(r["score"] for r in valid)),
        "completeness": int(median(r["completeness"] for r in valid)),
        "appropriateness": int(median(r["appropriateness"] for r in valid)),
        "communication": int(median(r["communication"] for r in valid)),
        "explanation": valid[0]["explanation"],
        "judge_count": len(results),
        "valid_count": len(valid),
        "all_scores": [r["score"] for r in results],
        "all_completeness": [r["completeness"] for r in results],
        "all_appropriateness": [r["appropriateness"] for r in results],
        "all_communication": [r["communication"] for r in results],
        "all_explanations": [r["explanation"] for r in results],
    }


# ---------------------------------------------------------------------------
# Tier 4 — Anomaly review: LLM inspects DB fields + conversation (soft)
# ---------------------------------------------------------------------------

_ANOMALY_REVIEW_PROMPT = """\
/no_think
你是预问诊系统的质量审查员。请审查以下预问诊的数据库记录和对话记录，找出所有异常。

## 患者信息
姓名：{name}，{condition}

## 数据库中存储的结构化字段
{soap_dump}

## 对话记录
{transcript}

## 请检查以下类型的异常
1. **内容重复**：同一字段中是否有重复或近义重复的内容（如同一事实用不同措辞出现两次）
2. **系统错误**：对话中是否出现系统错误消息（如"系统繁忙"、"请稍后再试"）
3. **提取遗漏**：患者在对话中明确提到但未出现在结构化字段中的重要临床信息
4. **提取错误**：结构化字段中出现患者从未提到的信息（幻觉）
5. **字段错位**：信息被存储到了错误的字段中（如家族史写进了个人史）
6. **对话质量**：AI是否重复提问、忽略患者回答、或在收集完信息后仍继续提问
7. **截断/不完整**：对话是否被过早结束导致信息收集不完整

请只返回JSON格式：
{{"anomalies": [{{"type": "类型", "severity": "high|medium|low", "detail": "具体描述"}}], "summary": "一句话总结"}}
如果没有异常，返回：{{"anomalies": [], "summary": "未发现异常"}}
"""


async def validate_tier4(
    conversation: list,
    persona: dict,
    db_path: str,
    record_id: int,
) -> dict:
    """Anomaly review — 3 LLM judges inspect DB + conversation for issues."""
    soap = _load_soap_from_db(record_id, db_path)
    soap_lines = []
    for field, value in soap.items():
        if value and value.strip():
            soap_lines.append(f"- {field}: {value}")
    soap_dump = "\n".join(soap_lines) if soap_lines else "（所有字段为空）"

    transcript_lines = []
    for turn in conversation:
        role = "AI助手" if turn.get("role") == "system" else "患者"
        text = turn.get("content", turn.get("text", ""))
        transcript_lines.append(f"{role}: {text}")
    transcript = "\n".join(transcript_lines)

    prompt = _ANOMALY_REVIEW_PROMPT.format(
        name=persona.get("name", "?"),
        condition=persona.get("condition", "?"),
        soap_dump=soap_dump,
        transcript=transcript,
    )

    judges = _pick_judges(3)
    results = await asyncio.gather(*[
        _single_anomaly_judge(j, prompt) for j in judges
    ])

    # Merge anomalies from all judges, dedup by type+detail similarity
    all_anomalies = []
    seen = set()
    for r in results:
        for a in r.get("anomalies", []):
            key = (a.get("type", ""), a.get("detail", "")[:50])
            if key not in seen:
                seen.add(key)
                all_anomalies.append(a)

    # Count by severity
    high = sum(1 for a in all_anomalies if a.get("severity") == "high")
    medium = sum(1 for a in all_anomalies if a.get("severity") == "medium")
    low = sum(1 for a in all_anomalies if a.get("severity") == "low")

    summaries = [r.get("summary", "") for r in results if r.get("summary")]

    return {
        "anomalies": all_anomalies,
        "high": high,
        "medium": medium,
        "low": low,
        "summary": summaries[0] if summaries else "审查完成",
        "judge_count": len(results),
    }


async def _single_anomaly_judge(provider: dict, prompt: str) -> dict:
    """One anomaly judge. Returns parsed result or empty."""
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        return {
            "anomalies": parsed.get("anomalies", []),
            "summary": str(parsed.get("summary", "")),
        }
    except Exception as e:
        return {"anomalies": [], "summary": f"judge error: {e}"}
