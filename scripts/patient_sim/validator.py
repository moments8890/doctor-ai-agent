"""Four-tier validation for patient simulation runs.

Tier 1: DB integrity checks (hard gate)
Tier 2: 5-dimension interview scorecard (validate_interview)
        Dim 1: Simulator Fidelity — did the simulator volunteer the right facts?
        Dim 2: Interview Policy — did the conversation cover must-elicit topics?
        Dim 3: Disclosure — were critical/important facts mentioned in the conversation?
        Dim 4: Extraction Accuracy — were disclosed facts captured in DB SOAP fields?
        Dim 5: Record Quality — chief complaint format + hallucination check
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

# 5 diverse Chinese LLM judges across 2 providers (OpenRouter + Groq).
# 4 Chinese-native models + 1 international for cross-model diversity.
_JUDGE_POOL = [
    # OpenRouter models (all OpenAI-compatible)
    {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-chat-v3-0324",
        "label": "DeepSeek-V3",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "qwen/qwen3-30b-a3b",
        "label": "Qwen3-30B",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "qwen/qwen-2.5-7b-instruct",
        "label": "Qwen-2.5-7B",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "mistralai/mistral-small-3.2-24b-instruct",
        "label": "Mistral-Small-24B",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    # Groq model (different provider for diversity)
    {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.1-8b-instant",
        "label": "Llama-3.1-8B",
        "api_key_env": "GROQ_API_KEY",
    },
]


def _pick_judges(n: int) -> List[dict]:
    """Pick *n* judge configs, round-robin across the diverse model pool."""
    available = [j for j in _JUDGE_POOL if os.environ.get(j["api_key_env"])]
    if not available:
        raise RuntimeError("No API keys set for judges (need OPENROUTER_API_KEY or GROQ_API_KEY)")
    return [available[i % len(available)] for i in range(n)]


async def _llm_call(provider: dict, prompt: str, temperature: float = 0.2) -> str:
    """Single LLM chat completion call with retry. Returns raw content string."""
    api_key = os.environ.get(provider["api_key_env"], "")
    data = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{provider['base_url']}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": provider["model"],
                        "messages": [{"role": "user", "content": f"请直接回答，不要输出思考过程。\n\n{prompt}"}],
                        "temperature": temperature,
                        "max_tokens": 512,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                break
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))
            else:
                raise
    if data is None:
        raise RuntimeError("LLM call failed after 3 attempts")
    msg = data["choices"][0]["message"]
    raw = msg.get("content") or ""
    # Some models put output in reasoning field when content is null
    if not raw and msg.get("reasoning"):
        raw = msg["reasoning"]
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
    # Try to find the outermost JSON object (supports nested braces)
    # Walk forward from the first '{', count brace depth
    start = raw.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i + 1])
                    except json.JSONDecodeError:
                        break
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
# Tier 2 — 3-axis hybrid scorecard: elicitation, extraction, NHC compliance
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


# ---------------------------------------------------------------------------
# Dim 2: Interview Policy — LLM prompt (reuses elicitation judge pattern)
# ---------------------------------------------------------------------------

_DIM2_POLICY_JUDGE_PROMPT = """\
/no_think
你是预问诊对话质量评审员。请判断以下对话中是否**覆盖**了指定话题。

## 完整对话记录
{conversation}

## 需要检查的话题列表
{topics_block}

## 规则
- "覆盖"的标准：该话题的相关信息在对话中**出现过**，无论是AI助手主动询问、还是患者主动提供
- 例如：患者说"我高血压5年，吃氨氯地平"→"用药情况"话题已覆盖（即使AI没问）
- 例如：患者说"最近头痛是隐痛，一周两三次"→"头痛性质"话题已覆盖
- 例如：AI问"有没有药物过敏？"→"过敏史"话题已覆盖
- 宽松匹配：措辞不需要完全一样，只要语义涉及该话题即可
- 只有当对话中完全没有涉及某话题时，才判为false

对每个话题，返回true（已覆盖）或false（未覆盖）。
请只返回JSON: {{"results": {{"话题1": true, "话题2": false, ...}}}}
"""

# ---------------------------------------------------------------------------
# Dim 3: Disclosure — LLM prompt (which facts appeared in conversation?)
# ---------------------------------------------------------------------------

_DIM3_DISCLOSURE_JUDGE_PROMPT = """\
/no_think
你是预问诊对话内容评审员。请判断以下事实是否在对话中被**提及**过。

## 完整对话记录
{conversation}

## 需要检查的事实列表
{facts_block}

## 规则
- "提及"的标准：该事实的核心信息在对话中出现过，无论是AI助手提到还是患者提到
- 不要求原文一模一样，只要语义等价即可判为已提及
- 例如"高血压5年"和"血压高了好几年"是语义等价的
- 例如"对青霉素过敏"和"吃青霉素会过敏"是语义等价的
- 只有当对话中完全没有涉及某条事实时，才判为false

对每条事实，返回true（已提及）或false（未提及）。
请只返回JSON: {{"results": {{"fact_id_1": true, "fact_id_2": false, ...}}}}
"""

# ---------------------------------------------------------------------------
# Dim 4: Extraction Accuracy — LLM prompt (reuses fact-match judge pattern)
# ---------------------------------------------------------------------------

_DIM4_EXTRACTION_JUDGE_PROMPT = """\
/no_think
你是一位医学信息提取评审专家。请逐条判断以下期望事实是否出现在系统提取的结构化字段中。

## 系统实际提取的全部SOAP字段
{soap_dump}

## 需要核对的事实列表
{facts_block}

## 规则
- 不要求原文一模一样，只要语义等价即可判为匹配
- 例如"体检发现动脉瘤"和"MRA检查发现脑动脉瘤"是语义等价的
- "高血压5年"和"高血压病史5年，服用氨氯地平"也是等价的
- 如果事实出现在任何字段中（即使不是期望字段），也算匹配，但请标注实际所在字段
- 只有当某条事实在所有字段中都完全没有体现时，才判为未匹配

对每条事实，返回:
- "match": true/false
- "found_in": 实际找到的字段名（如未找到则为null）

请只返回JSON: {{"results": {{"fact_id_1": {{"match": true, "found_in": "present_illness"}}, "fact_id_2": {{"match": false, "found_in": null}}, ...}}}}
"""

# ---------------------------------------------------------------------------
# Dim 5: Record Quality — LLM hallucination check prompt
# ---------------------------------------------------------------------------

_DIM5_HALLUCINATION_JUDGE_PROMPT = """\
/no_think
你是预问诊系统的幻觉检测专家。请检查数据库中存储的结构化字段是否包含**对话中从未提到过**的信息。

## 完整对话记录
{conversation}

## 数据库中存储的结构化字段
{soap_dump}

## 规则
- 逐字段检查：对于每个非空字段，确认其内容在对话中有对应的来源
- "幻觉"的定义：结构化字段中出现了患者从未提到、AI助手也从未确认的信息
- 合理的医学规范化表述不算幻觉（如将口语"血压高"规范为"高血压"）
- 合理的否认推断不算幻觉（如患者未提过敏史，记录"否认药物及食物过敏史"）
- 只有明显无中生有、或与对话内容矛盾的信息才算幻觉

如发现幻觉，请列出每个幻觉的字段名和具体内容。
请只返回JSON: {{"hallucinations": [{{"field": "字段名", "detail": "具体幻觉内容描述"}}]}}
如果没有幻觉，返回：{{"hallucinations": []}}
"""


# ---------------------------------------------------------------------------
# Shared conversation text builder
# ---------------------------------------------------------------------------

def _build_conversation_text(conversation: list) -> str:
    """Build full conversation text from turn list, labelling both parties."""
    conv_lines = []
    for turn in conversation:
        role = turn.get("role", "")
        label = "AI助手" if role in ("system", "assistant") else "患者"
        text = turn.get("content", turn.get("text", ""))
        conv_lines.append(f"{label}：{text}")
    return "\n".join(conv_lines) if conv_lines else "（无对话记录）"


def _build_patient_text(conversation: list) -> str:
    """Build text from PATIENT messages only (role=user or patient)."""
    lines = []
    for turn in conversation:
        role = turn.get("role", "")
        if role in ("user", "patient"):
            text = turn.get("content", turn.get("text", ""))
            lines.append(text)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dim 1: Simulator Fidelity (deterministic — no LLM)
# ---------------------------------------------------------------------------

def _dim1_simulator_fidelity(persona: dict, conversation: list) -> dict:
    """Check which volunteer=true facts from allowed_facts were actually
    disclosed by the patient simulator.  Uses simple keyword matching."""
    allowed_facts = persona.get("allowed_facts", [])
    volunteer_facts = [f for f in allowed_facts if f.get("volunteer") is True]

    if not volunteer_facts:
        return {"score": 100, "facts": {}}

    patient_text = _build_patient_text(conversation).lower()

    facts_out: Dict[str, Dict[str, bool]] = {}
    found = 0
    for fact_entry in volunteer_facts:
        fact_text = fact_entry.get("fact", "")
        # Extract key phrases: split on common delimiters, keep tokens >= 2 chars
        keywords = re.split(r"[，,；;。、\s]+", fact_text)
        keywords = [k.strip() for k in keywords if len(k.strip()) >= 2]
        # A fact is considered disclosed if ALL its keywords appear in patient text
        disclosed = all(kw.lower() in patient_text for kw in keywords) if keywords else False
        facts_out[fact_text] = {"disclosed": disclosed}
        if disclosed:
            found += 1

    score = int(round(found / len(volunteer_facts) * 100)) if volunteer_facts else 100
    return {"score": score, "facts": facts_out}


# ---------------------------------------------------------------------------
# Dim 2: Interview Policy (1 LLM judge)
# ---------------------------------------------------------------------------

async def _dim2_interview_policy(
    persona: dict,
    conversation: list,
) -> dict:
    """Check which must_elicit topics were covered in the conversation."""
    coverage_expectation = persona.get("coverage_expectation", {})
    must_elicit: List[str] = coverage_expectation.get("must_elicit", [])
    if not must_elicit:
        return {"score": 100, "topics": {}}

    conv_text = _build_conversation_text(conversation)
    topics_block = "\n".join(f"- {t}" for t in must_elicit)
    prompt = _DIM2_POLICY_JUDGE_PROMPT.format(
        conversation=conv_text,
        topics_block=topics_block,
    )

    provider = _pick_judges(1)[0]
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        results = parsed.get("results", {})
        topic_map: Dict[str, bool] = {}
        for topic in must_elicit:
            topic_map[topic] = bool(results.get(topic, False))
    except Exception:
        topic_map = {t: False for t in must_elicit}

    covered = sum(1 for v in topic_map.values() if v)
    score = int(round(covered / len(must_elicit) * 100)) if must_elicit else 100
    return {"score": score, "topics": topic_map}


# ---------------------------------------------------------------------------
# Dim 3: Disclosure (1 LLM judge)
# ---------------------------------------------------------------------------

async def _dim3_disclosure(
    persona: dict,
    conversation: list,
) -> dict:
    """Check which critical/important facts from fact_catalog were mentioned
    anywhere in the conversation."""
    fact_catalog = persona.get("fact_catalog", [])
    relevant_facts = [
        f for f in fact_catalog
        if f.get("importance", "normal") in ("critical", "important")
    ]
    if not relevant_facts:
        return {"score": 100, "facts": {}}

    conv_text = _build_conversation_text(conversation)

    # Build facts block for prompt
    facts_lines = []
    for f in relevant_facts:
        fid = f.get("id", f.get("fact", "?"))
        facts_lines.append(f"- {fid}: {f.get('text', f.get('fact', ''))}")
    facts_block = "\n".join(facts_lines)

    prompt = _DIM3_DISCLOSURE_JUDGE_PROMPT.format(
        conversation=conv_text,
        facts_block=facts_block,
    )

    provider = _pick_judges(1)[0]
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        results = parsed.get("results", {})
    except Exception:
        results = {}

    facts_out: Dict[str, dict] = {}
    disclosed_count = 0
    for f in relevant_facts:
        fid = f.get("id", f.get("fact", "?"))
        importance = f.get("importance", "normal")
        disclosed = bool(results.get(fid, False))
        facts_out[fid] = {"disclosed": disclosed, "importance": importance}
        if disclosed:
            disclosed_count += 1

    score = int(round(disclosed_count / len(relevant_facts) * 100)) if relevant_facts else 100
    return {"score": score, "facts": facts_out}


# ---------------------------------------------------------------------------
# Dim 4: Extraction Accuracy (3 LLM judges, majority vote)
# ---------------------------------------------------------------------------

async def _dim4_judge_single(
    soap: Dict[str, str],
    facts: List[dict],
    provider: dict,
) -> Dict[str, dict]:
    """One LLM judge checks disclosed facts against SOAP fields."""
    soap_lines = []
    for field, value in soap.items():
        soap_lines.append(f"- {field}: {value or '（空）'}")
    soap_dump = "\n".join(soap_lines)

    facts_block_lines = []
    for f in facts:
        fid = f.get("id", f.get("fact", "?"))
        facts_block_lines.append(
            f"- {fid} (期望字段: {f.get('field', f.get('expected_field', '未指定'))}): "
            f"{f.get('text', f.get('fact', ''))}"
        )
    facts_block = "\n".join(facts_block_lines)

    prompt = _DIM4_EXTRACTION_JUDGE_PROMPT.format(
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
            fid = f.get("id", f.get("fact", "?"))
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
            fid = f.get("id", f.get("fact", "?"))
            out[fid] = {"match": False, "found_in": None, "model": label, "error": str(e)}
        return out


async def _dim4_extraction_accuracy(
    soap: Dict[str, str],
    dim3_result: dict,
    fact_catalog: List[dict],
) -> dict:
    """Of the facts that dim3 said were disclosed, how many are captured in
    SOAP fields? Uses 3 LLM judges with majority vote."""
    # Only evaluate facts where dim3 said disclosed=true
    disclosed_ids = {
        fid for fid, info in dim3_result.get("facts", {}).items()
        if info.get("disclosed")
    }
    if not disclosed_ids:
        return {"score": 100, "facts": {}}

    # Build the subset of fact_catalog that was disclosed
    disclosed_facts = [
        f for f in fact_catalog
        if f.get("id", f.get("fact", "?")) in disclosed_ids
    ]
    if not disclosed_facts:
        return {"score": 100, "facts": {}}

    # 3 LLM judges, majority vote
    providers = _pick_judges(3)
    all_results = await asyncio.gather(*[
        _dim4_judge_single(soap, disclosed_facts, p) for p in providers
    ])

    facts_out: Dict[str, dict] = {}
    captured_count = 0

    for f in disclosed_facts:
        fid = f.get("id", f.get("fact", "?"))
        importance = f.get("importance", "normal")

        votes = [r.get(fid, {}).get("match", False) for r in all_results]
        captured = sum(votes) >= 2  # majority

        found_in_votes = [
            r.get(fid, {}).get("found_in")
            for r in all_results if r.get(fid, {}).get("match")
        ]
        found_in = found_in_votes[0] if found_in_votes else None

        facts_out[fid] = {
            "disclosed": True,
            "captured": captured,
            "found_in": found_in,
            "importance": importance,
        }
        if captured:
            captured_count += 1

    score = int(round(captured_count / len(disclosed_facts) * 100)) if disclosed_facts else 100
    return {"score": score, "facts": facts_out}


# ---------------------------------------------------------------------------
# Dim 5: Record Quality (deterministic CC + 1 LLM hallucination check)
# ---------------------------------------------------------------------------

async def _dim5_record_quality(
    soap: Dict[str, str],
    conversation: list,
) -> dict:
    """Chief complaint format checks (deterministic) + hallucination detection
    (1 LLM judge)."""
    cc_text = soap.get("chief_complaint", "")

    # --- Chief complaint checks (deterministic) ---
    cc_length = len(cc_text)
    cc_max_chars = 20

    duration_pattern = re.compile(
        r"(\d+\s*(天|日|周|月|年|小时|分钟|个月|余年|余月|余天))"
        r"|(\d+[天日周月年])"
        r"|(半[天月年])"
    )
    has_duration = bool(duration_pattern.search(cc_text)) if cc_text else False

    cc_pass = (cc_length <= cc_max_chars) and has_duration if cc_text else False

    # --- Hallucination check (1 LLM judge) ---
    conv_text = _build_conversation_text(conversation)
    soap_lines = []
    for field, value in soap.items():
        if value and value.strip():
            soap_lines.append(f"- {field}: {value}")
    soap_dump = "\n".join(soap_lines) if soap_lines else "（所有字段为空）"

    prompt = _DIM5_HALLUCINATION_JUDGE_PROMPT.format(
        conversation=conv_text,
        soap_dump=soap_dump,
    )

    provider = _pick_judges(1)[0]
    hallucinations: List[dict] = []
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        hallucinations = parsed.get("hallucinations", [])
    except Exception:
        pass

    # Score: CC checks worth 50, hallucination-free worth 50
    cc_score_part = 50 if cc_pass else (25 if (cc_length <= cc_max_chars or has_duration) else 0)
    hallucination_score_part = 50 if not hallucinations else 0
    score = cc_score_part + hallucination_score_part

    return {
        "score": score,
        "chief_complaint": {
            "length": cc_length,
            "max_chars": cc_max_chars,
            "has_duration": has_duration,
            "pass": cc_pass,
        },
        "hallucinations": hallucinations,
    }


# ---------------------------------------------------------------------------
# validate_interview — 5-dimension evaluation orchestrator
# ---------------------------------------------------------------------------

async def validate_interview(
    persona: dict,
    db_path: str,
    record_id: int,
    conversation: list,
) -> dict:
    """Evaluate an interview across 5 dimensions.

    Dim 1: 模拟器忠实度 (Simulator Fidelity) — deterministic keyword match
    Dim 2: 问诊策略 (Interview Policy) — 1 LLM judge
    Dim 3: 信息披露 (Disclosure) — 1 LLM judge
    Dim 4: 提取准确度 (Extraction Accuracy) — 3 LLM judges, majority vote
    Dim 5: 记录质量 (Record Quality) — deterministic CC + 1 LLM hallucination

    Returns {
        'pass': bool,
        'combined_score': int (0-100),
        'dimensions': {
            'dim1_simulator_fidelity': {...},
            'dim2_interview_policy': {...},
            'dim3_disclosure': {...},
            'dim4_extraction_accuracy': {...},
            'dim5_record_quality': {...},
        }
    }
    """
    soap = _load_soap_from_db(record_id, db_path)

    # --- Dim 2 & 3 can run concurrently (independent LLM calls) ---
    dim2_task = _dim2_interview_policy(persona, conversation)
    dim3_task = _dim3_disclosure(persona, conversation)
    dim2, dim3 = await asyncio.gather(dim2_task, dim3_task)

    # --- Dim 4 depends on dim3 result ---
    fact_catalog = persona.get("fact_catalog", [])
    dim4 = await _dim4_extraction_accuracy(soap, dim3, fact_catalog)

    # --- Dim 5 runs independently ---
    dim5 = await _dim5_record_quality(soap, conversation)

    # --- Combined score: weighted average (4 dimensions) ---
    # 问诊策略 20% + 信息披露 25% + 提取准确度 35% + 记录质量 20%
    combined_score = int(round(
        dim2["score"] * 0.20
        + dim3["score"] * 0.25
        + dim4["score"] * 0.35
        + dim5["score"] * 0.20
    ))

    # --- Pass criteria ---
    no_hallucinations = len(dim5.get("hallucinations", [])) == 0
    dim4_sufficient = dim4["score"] >= 60
    passed = no_hallucinations and dim4_sufficient

    return {
        "pass": passed,
        "combined_score": combined_score,
        "dimensions": {
            "dim2_interview_policy": dim2,
            "dim3_disclosure": dim3,
            "dim4_extraction_accuracy": dim4,
            "dim5_record_quality": dim5,
        },
    }


# --------------- Tier 2 backward-compatible wrapper -----------------------

async def validate_tier2(
    persona: dict,
    db_path: str,
    record_id: int,
    conversation: list,
) -> dict:
    """Backward-compatible wrapper: delegates to validate_interview and
    reshapes the result to include the dimensions key plus top-level
    combined_score and pass."""
    result = await validate_interview(persona, db_path, record_id, conversation)
    return result


# ---------------------------------------------------------------------------
# AI Report Analysis — 2 analysts review full results and provide suggestions
# ---------------------------------------------------------------------------

_ANALYST_PROMPT = """\
请直接回答，不要输出思考过程。

你是一位医疗AI系统的高级质量分析师。请分析以下患者预问诊模拟测试的完整结果，并提供结构化的分析报告。

## 测试概览
- 通过: {passed}/{total}
- 患者模型: {patient_llm}

## 各角色结果摘要
{persona_summaries}

## 请提供以下分析

### 1. 关键发现（3-5条）
列出最重要的系统问题，按严重程度排序。每条包含：具体表现、影响范围、根本原因推测。

### 2. 优势（2-3条）
系统做得好的方面。

### 3. 改进建议（3-5条）
具体、可操作的改进建议，按优先级排序。每条说明：改什么、为什么、预期效果。

### 4. 一句话总结
用一句话概括这次测试的核心结论。

请用中文回答，保持简洁专业。直接输出分析内容，不要输出JSON。
"""


async def analyze_results(results: list, patient_llm: str) -> list:
    """Run 2 AI analysts (different models) on the full simulation results.

    Returns a list of {"model": str, "analysis": str} dicts.
    """
    passed = sum(1 for r in results if r.get("pass"))
    total = len(results)

    # Build persona summaries
    summaries = []
    for r in results:
        p = r.get("persona", {})
        t2 = r.get("tier2", {})
        dims = t2.get("dimensions", {})
        t3 = r.get("tier3", {})
        collected = r.get("collected", {})

        icon = "✓" if r.get("pass") else "✗"
        d2 = dims.get("dim2_interview_policy", {}).get("score", "?")
        d3 = dims.get("dim3_disclosure", {}).get("score", "?")
        d4 = dims.get("dim4_extraction_accuracy", {}).get("score", "?")
        d5 = dims.get("dim5_record_quality", {}).get("score", "?")

        cc = collected.get("chief_complaint", "")
        pi_len = len(collected.get("present_illness", ""))

        summary = (
            f"{icon} {p.get('id')} {p.get('name')} ({p.get('condition', '')})\n"
            f"  轮次={r.get('turns')} 综合={t2.get('combined_score', '?')} "
            f"问诊={d2} 披露={d3} 提取={d4} 质量={d5} "
            f"质量评分={t3.get('score', '?')}/10\n"
            f"  主诉: {cc[:40]}\n"
            f"  现病史: {pi_len}字"
        )
        summaries.append(summary)

    prompt = _ANALYST_PROMPT.format(
        passed=passed,
        total=total,
        patient_llm=patient_llm,
        persona_summaries="\n\n".join(summaries),
    )

    # Pick 2 different models for independent analysis
    all_judges = _pick_judges(5)
    # Use first 2 distinct models
    seen_models = set()
    analysts = []
    for j in all_judges:
        if j["model"] not in seen_models and len(analysts) < 2:
            analysts.append(j)
            seen_models.add(j["model"])

    # Run both analysts concurrently
    async def _run_analyst(provider: dict) -> dict:
        try:
            raw = await _llm_call(provider, prompt, temperature=0.3)
            return {"model": provider["label"], "analysis": raw}
        except Exception as e:
            return {"model": provider["label"], "analysis": f"分析失败: {e}"}

    results_out = await asyncio.gather(*[_run_analyst(a) for a in analysts])
    return list(results_out)


# ---------------------------------------------------------------------------
# Tier 3 — Quality: 5 LLM judges, median score
# ---------------------------------------------------------------------------

_QUALITY_JUDGE_PROMPT = """\
/no_think
评估以下**患者预问诊**对话的质量（0-10分）。

## 重要背景
这是患者在就诊前通过AI助手完成的**预问诊**（不是正式门诊）。预问诊的目的是：
- 收集患者主观信息：主诉、现病史、既往史、过敏史、家族史、个人史
- 为医生面诊做准备

以下内容**不属于预问诊范围**，不应因缺少这些而扣分：
- 体格检查（需医生亲自操作）
- 诊断（需医生判断）
- 治疗方案（需医生制定）
- 辅助检查结果（需实验室/影像）
- 医嘱及随访（需医生签署）

## 评分维度（每项0-10分）
1. completeness — 在预问诊范围内，是否充分收集了病史信息？（主诉、现病史、既往史、用药、家族史、过敏史、个人史）
2. appropriateness — 问题是否与患者的病情相关且有逻辑？是否按合理顺序追问？
3. communication — 是否清晰、专业、有耐心？对患者友好？是否回应了患者的疑问？

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

## 数据库中存储的完整结构化字段（SOAP）
以下是数据库中实际存储的所有字段及其值。审查时必须逐字段核对，不要凭印象判断。
{soap_dump}

## 对话记录
{transcript}

## 审查规则（严格遵守）

### 关于"提取遗漏"的判定标准
在判定"提取遗漏"之前，你必须：
1. 逐一检查上面列出的每个SOAP字段的值
2. 如果患者提到的信息出现在**任何**字段中（哪怕不是你预期的字段），则**不是**遗漏
3. 信息可能被改写、概括或用医学术语替代——只要语义等价就算已提取
4. 例如：患者说"做康复训练"，如果present_illness中有"康复训练"或"康复治疗"或类似表述，则不是遗漏
5. 只有当某条重要临床信息在所有字段中都完全没有体现时，才判定为提取遗漏

### 关于"提取错误"的判定标准
在判定"提取错误"（幻觉）之前，你必须：
1. 仔细重读完整对话记录，确认患者确实从未说过相关内容
2. 考虑患者可能用口语、方言、近义词或不同表述方式说过类似的话
3. 考虑AI助手在总结时可能进行了合理的医学推断或规范化表述
4. 只有当结构化字段中的信息与对话内容明显矛盾、或完全无中生有时，才判定为提取错误

### 检查类型
1. **内容重复**：同一字段中是否有重复或近义重复的内容（如同一事实用不同措辞出现两次）
2. **系统错误**：对话中是否出现系统错误消息（如"系统繁忙"、"请稍后再试"）
3. **提取遗漏**：（按上述严格标准判定）患者明确提到但所有SOAP字段中均无体现的重要临床信息
4. **提取错误**：（按上述严格标准判定）结构化字段中出现患者从未提到的信息
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
