"""Four-tier validation for patient simulation runs.

Tier 1: DB integrity checks (hard gate)
Tier 2: 3-axis hybrid scorecard — elicitation completeness, extraction
        fidelity (3 LLM judges), NHC record quality (hard gate)
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
# Clinical record field keys (per NHC 卫医政发〔2010〕11号)
# ---------------------------------------------------------------------------

CLINICAL_FIELDS: List[str] = [
    "department", "chief_complaint", "present_illness", "past_history",
    "allergy_history", "personal_history", "marital_reproductive",
    "family_history", "physical_exam", "specialist_exam", "auxiliary_exam",
    "diagnosis", "treatment_plan", "orders_followup",
]

# Backward-compat alias (deprecated — use CLINICAL_FIELDS)
SOAP_FIELDS = CLINICAL_FIELDS


# ---------------------------------------------------------------------------
# LLM calling helpers (shared by Tier 2 and Tier 3)
# ---------------------------------------------------------------------------

# All judges use Groq. GPT-OSS models failed semantic matching tasks,
# so we use Llama-3.1-8B (which works reliably) for all judges.
# Cost: $0.05/M input — cheapest available on Groq.
_JUDGE_MODELS = [
    {"model": "llama-3.1-8b-instant", "label": "Llama-3.1-8B"},
    {"model": "llama-3.1-8b-instant", "label": "Llama-3.1-8B"},
    {"model": "llama-3.1-8b-instant", "label": "Llama-3.1-8B"},
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
            type_ok = row["record_type"] == "intake_summary"
            ok = content_ok and type_ok
            checks["record_created"] = {"pass": ok, "detail": "OK" if ok else "content empty or wrong type"}

        # 2. Clinical record chief_complaint populated
        if row is not None:
            cc = conn.execute("SELECT chief_complaint FROM medical_records WHERE id = ?", (record_id,)).fetchone()
            cc_ok = bool(cc and cc["chief_complaint"] and cc["chief_complaint"].strip())
            checks["clinical_fields"] = {"pass": cc_ok, "detail": "OK" if cc_ok else "chief_complaint empty"}
        else:
            checks["clinical_fields"] = {"pass": False, "detail": "skipped"}

        # 3. Session confirmed
        sess = conn.execute("SELECT status FROM intake_sessions WHERE id = ?", (session_id,)).fetchone()
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

def _load_record_from_db(record_id: int, db_path: str) -> Dict[str, str]:
    """Load clinical record fields from DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = ", ".join(CLINICAL_FIELDS)
        row = conn.execute(f"SELECT {cols} FROM medical_records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return {}
        return {f: (row[f] or "") for f in CLINICAL_FIELDS}
    finally:
        conn.close()

# Backward-compat alias (deprecated — use _load_record_from_db)
_load_soap_from_db = _load_record_from_db


# --------------- Axis 1: Elicitation Completeness prompts ----------------

_ELICITATION_JUDGE_PROMPT = """\
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

# --------------- Axis 2: Extraction Fidelity prompts ---------------------

_FACT_EXTRACT_FROM_DIALOG_PROMPT = """\
/no_think
你是预问诊对话审查员。请判断患者是否提到了以下每条事实，如果提到了，摘录患者的原话。

## 患者的全部发言（逐条列出）
{patient_text}

## 需要检查的事实主题
{facts_block}

## 严格规则
- 只看上方「患者的全部发言」，不看AI助手的话
- 患者描述自己的情况才算，转述家人不算（"我妈有高血压"不算患者本人的高血压）
- 必须从患者原话中找到对应内容才能填写；绝对不能把「事实主题」中的描述当作患者说过的话
- 患者说"脑出血6个月"≠ 患者说了"左侧基底节区脑出血15ml保守治疗"，后者的细节如果患者没说就是没说
- 如果患者只说了笼统的话（如"有高血压"），只返回笼统的部分，不要补充患者没说的数字、药名、部位等细节
- 如果患者完全没提到该主题，返回空字符串""

请只返回JSON: {{"results": {{"fact_id_1": "患者原话摘要（仅限患者说过的）", "fact_id_2": "", ...}}}}
"""

_FACT_MATCH_JUDGE_PROMPT = """\
/no_think
你是一位医学信息提取评审专家。请逐条判断：患者说的内容是否被系统正确记录到了结构化病历中。

## 系统实际提取的全部结构化病历字段
{record_dump}

## 需要核对的内容（患者实际表述 → 对应的事实主题）
{facts_block}

## 匹配级别（三级）
- "exact": 患者说的核心信息已完整体现在病历中（语义等价即可）
- "partial": 核心概念已出现，但患者说的部分细节未被记录
- "missed": 患者说的内容在所有字段中都完全没有体现

## 判断规则
- 比较的是"患者说了什么"vs"病历记了什么"，不是"理想上应该有什么"
- 如果患者只说了"有高血压"，病历记了"高血压" → exact（患者说的都记了）
- 如果患者说了"高血压10年，吃缬沙坦"，病历只记了"高血压" → partial（核心在，细节丢了）
- 如果患者说了"高血压"，病历完全没提 → missed
- 出现在任何字段中都算匹配

对每条事实，返回:
- "match": "exact" / "partial" / "missed"
- "found_in": 实际找到的字段名（如未找到则为null）

请只返回JSON: {{"results": {{"fact_id_1": {{"match": "exact", "found_in": "past_history"}}, ...}}}}
"""

# --------------- Axis 3: NHC Record Quality prompts ----------------------

_NHC_COMPLIANCE_JUDGE_PROMPT = """\
/no_think
你是一位病历质量审查专家。请审查以下结构化病历字段是否符合中国住院病历书写规范。

## 现病史字段内容
{present_illness}

## 既往史字段内容
{past_history}

## 需要检查的现病史子项
{pi_subsections}

## 需要检查的既往史子项
{ph_subsections}

## 规则
- 对每个子项，判断该内容是否在对应字段中有所体现（语义层面，不要求原文）
- "体现"的标准：有明确描述或否认（如"无糖尿病"也算覆盖了"既往疾病"子项）

请只返回JSON:
{{"present_illness": {{"子项1": true, "子项2": false, ...}}, "past_history": {{"子项1": true, ...}}}}
"""


# --------------- Axis 1 implementation -----------------------------------

async def _evaluate_elicitation(
    conversation: list,
    must_elicit: List[str],
    provider: dict,
) -> Dict[str, bool]:
    """Single LLM judge checks which must_elicit topics were covered in the conversation."""
    # Build full conversation text (both AI and patient)
    conv_lines = []
    for turn in conversation:
        role = turn.get("role", "")
        label = "AI助手" if role in ("system", "assistant") else "患者"
        text = turn.get("content", turn.get("text", ""))
        conv_lines.append(f"{label}：{text}")
    conv_text = "\n".join(conv_lines) if conv_lines else "（无对话记录）"

    topics_block = "\n".join(f"- {t}" for t in must_elicit)
    prompt = _ELICITATION_JUDGE_PROMPT.format(
        conversation=conv_text,
        topics_block=topics_block,
    )
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        results = parsed.get("results", {})
        # Normalise: map back to the original topic strings
        topic_map: Dict[str, bool] = {}
        for topic in must_elicit:
            topic_map[topic] = bool(results.get(topic, False))
        return topic_map
    except Exception:
        return {t: False for t in must_elicit}


async def _axis1_elicitation(
    conversation: list,
    coverage_expectation: dict,
) -> dict:
    """Axis 1: Elicitation Completeness — did the intake ask about the right topics?"""
    must_elicit: List[str] = coverage_expectation.get("must_elicit", [])
    if not must_elicit:
        return {"score": 1.0, "topics": {}}

    # Single LLM call to check all topics
    provider = _pick_judges(1)[0]
    topic_results = await _evaluate_elicitation(conversation, must_elicit, provider)

    covered = sum(1 for v in topic_results.values() if v)
    score = (covered / len(must_elicit) * 100) if must_elicit else 100

    return {
        "score": int(round(score)),
        "topics": topic_results,
    }


# --------------- Axis 2 implementation -----------------------------------

async def _judge_facts_single(
    record: Dict[str, str],
    facts: List[dict],
    provider: dict,
    patient_statements: Optional[Dict[str, str]] = None,
) -> Dict[str, dict]:
    """One LLM judge checks patient's actual statements against clinical record fields.

    If patient_statements is provided, uses those instead of persona fact text.
    This ensures we judge 'did the record capture what the patient said' not
    'did the record match the persona ideal'.
    """
    record_lines = []
    for field, value in record.items():
        record_lines.append(f"- {field}: {value or '（空）'}")
    record_dump = "\n".join(record_lines)

    facts_block_lines = []
    for f in facts:
        fid = f.get("id", f.get("fact", "?"))
        # Use patient's actual statement if available, otherwise fall back to persona text
        actual_text = (patient_statements or {}).get(fid, "")
        persona_text = f.get("text", f.get("fact", ""))
        display_text = actual_text if actual_text else persona_text
        target_field = f.get('field', f.get('expected_field', '未指定'))
        if actual_text:
            facts_block_lines.append(
                f"- {fid} (目标字段: {target_field}): 患者说「{actual_text}」"
            )
        else:
            facts_block_lines.append(
                f"- {fid} (目标字段: {target_field}): {persona_text}"
            )
    facts_block = "\n".join(facts_block_lines)

    prompt = _FACT_MATCH_JUDGE_PROMPT.format(
        record_dump=record_dump,
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
            # Handle tiered match: "exact"/"partial"/"missed" or legacy bool
            raw_match = entry.get("match", "missed")
            if isinstance(raw_match, bool):
                match_level = "exact" if raw_match else "missed"
            elif isinstance(raw_match, str):
                match_level = raw_match.lower() if raw_match.lower() in ("exact", "partial", "missed") else "missed"
            else:
                match_level = "missed"
            out[fid] = {
                "match_level": match_level,
                "found_in": entry.get("found_in"),
                "model": label,
            }
        return out
    except Exception as e:
        out = {}
        for f in facts:
            fid = f.get("id", f.get("fact", "?"))
            out[fid] = {"match_level": "missed", "found_in": None, "model": label, "error": str(e)}
        return out





async def _extract_patient_statements(conversation: list, facts: List[dict]) -> Dict[str, str]:
    """LLM-based extraction: what did the patient actually say for each fact topic?

    Returns {fact_id: "patient's actual statement"} — empty string means not disclosed.
    This replaces the separate disclosure check and gives us the actual text to judge against.
    """
    patient_text = "\n".join(
        turn.get("content", turn.get("text", ""))
        for turn in conversation
        if turn.get("role") in ("user", "patient")
    )
    if not patient_text:
        return {f.get("id", f.get("fact", "?")): "" for f in facts}

    # Option 1: Send only short topic labels, not full expected text (prevents contamination)
    _TOPIC_LABELS = {
        "cc_": "主诉相关", "pi_": "现病史相关", "ph_": "既往史相关",
        "al_": "过敏史相关", "fh_": "家族史相关", "sh_": "个人史相关",
    }
    facts_lines = []
    for f in facts:
        fid = f.get("id", f.get("fact", "?"))
        # Use a short generic label instead of the full expected text
        full_text = f.get("text", f.get("fact", ""))
        # Extract just the core topic: first clause or first 8 chars
        short_topic = full_text.split("，")[0].split("、")[0][:15] if full_text else fid
        facts_lines.append(f"- {fid}: {short_topic}")
    facts_block = "\n".join(facts_lines)

    prompt = _FACT_EXTRACT_FROM_DIALOG_PROMPT.format(
        patient_text=patient_text,
        facts_block=facts_block,
    )

    provider = _pick_judges(1)[0]
    try:
        raw = await _llm_call(provider, prompt)
        parsed = _parse_json_response(raw)
        results = parsed.get("results", {})

        # Option 2: Post-verification — check LLM output against actual patient text
        import jieba
        verified: Dict[str, str] = {}
        for f in facts:
            fid = f.get("id", f.get("fact", "?"))
            claimed = str(results.get(fid, "")).strip()
            if not claimed:
                verified[fid] = ""
                continue
            # Extract key terms from claimed text and verify at least one appears in patient text
            key_terms = [w for w in jieba.cut(claimed) if len(w) >= 2]
            if key_terms and any(term in patient_text for term in key_terms[:5]):
                verified[fid] = claimed
            else:
                verified[fid] = ""  # hallucination — term not in patient text
        return verified
    except Exception:
        return {f.get("id", f.get("fact", "?")): "" for f in facts}


async def _axis2_extraction(
    record: Dict[str, str],
    fact_catalog: List[dict],
    conversation: Optional[list] = None,
) -> dict:
    """Axis 2: Extraction Fidelity — did the system capture what the patient said?

    If conversation is provided, facts not disclosed by the patient are reported
    separately and do not count toward hard-fail conditions.
    """
    # Filter to critical + important facts only
    relevant_facts = [
        f for f in fact_catalog
        if f.get("importance", "normal") in ("critical", "important")
    ]
    if not relevant_facts:
        return {"score": 1.0, "facts": {}, "undisclosed_facts": []}

    # Step 1: Extract what the patient actually said for each fact topic
    patient_statements: Optional[Dict[str, str]] = None
    if conversation:
        patient_statements = await _extract_patient_statements(conversation, relevant_facts)
        for f in relevant_facts:
            fid = f.get("id", f.get("fact", "?"))
            actual = (patient_statements or {}).get(fid, "")
            f["_disclosed"] = bool(actual.strip())
            f["_patient_said"] = actual.strip()
    else:
        for f in relevant_facts:
            f["_disclosed"] = True
            f["_patient_said"] = ""

    # Step 2: Judge patient's actual statements against the record (3 LLM judges)
    providers = _pick_judges(3)
    all_results = await asyncio.gather(*[
        _judge_facts_single(record, relevant_facts, p, patient_statements=patient_statements)
        for p in providers
    ])

    # Majority vote per fact (tiered: exact > partial > missed)
    _LEVEL_RANK = {"exact": 2, "partial": 1, "missed": 0}
    facts_out: Dict[str, dict] = {}
    any_critical_missing = False

    for f in relevant_facts:
        fid = f.get("id", f.get("fact", "?"))
        expected_field = f.get("field", f.get("expected_field", ""))
        importance = f.get("importance", "normal")

        # Collect tiered votes from all judges
        level_votes = [r.get(fid, {}).get("match_level", "missed") for r in all_results]
        # Majority vote: pick the level that >= 2 judges agree on, else take median
        from collections import Counter
        level_counts = Counter(level_votes)
        majority_level = level_counts.most_common(1)[0][0]
        # If no clear majority (all different), take the median by rank
        if level_counts.most_common(1)[0][1] < 2:
            sorted_levels = sorted(level_votes, key=lambda l: _LEVEL_RANK.get(l, 0))
            majority_level = sorted_levels[len(sorted_levels) // 2]

        # For backward compat: match = True if exact or partial
        match = majority_level in ("exact", "partial")

        # Determine found_in from judges that reported a match
        found_in_votes = [
            r.get(fid, {}).get("found_in")
            for r in all_results
            if r.get(fid, {}).get("match_level", "missed") != "missed"
        ]
        found_in = found_in_votes[0] if found_in_votes else None

        # Classify location
        if match and found_in == expected_field:
            location = "correct_field"
        elif match and found_in and found_in != expected_field:
            location = "wrong_field"
        elif match:
            location = "found"
        else:
            location = "missed"
            # Only count as critical missing if the patient actually disclosed the fact
            disclosed = f.get("_disclosed", True)
            if importance == "critical" and disclosed:
                any_critical_missing = True

        facts_out[fid] = {
            "expected_field": expected_field,
            "found_in": found_in,
            "match": match,
            "match_level": majority_level,
            "votes": level_votes,
            "location": location,
            "importance": importance,
            "disclosed": f.get("_disclosed", True),
            "patient_said": f.get("_patient_said", ""),
        }

    # Score only on disclosed facts (undisclosed are reported but don't affect score)
    disclosed_facts = {k: v for k, v in facts_out.items() if v.get("disclosed", True)}
    undisclosed_facts = [k for k, v in facts_out.items() if not v.get("disclosed", True)]

    if disclosed_facts:
        score_sum = sum(
            1.0 if v["match_level"] == "exact" else 0.5 if v["match_level"] == "partial" else 0.0
            for v in disclosed_facts.values()
        )
        score = (score_sum / len(disclosed_facts) * 100)
    else:
        score = 100

    return {
        "score": int(round(score)),
        "facts": facts_out,
        "any_critical_missing": any_critical_missing,
        "undisclosed_facts": undisclosed_facts,
    }


# --------------- Axis 3 implementation -----------------------------------

async def _axis3_nhc_compliance(
    record: Dict[str, str],
    record_expectation: dict,
) -> dict:
    """Axis 3: NHC Record Quality — is the final record properly structured?"""
    result: Dict[str, Any] = {"score": 0.0}

    # --- chief_complaint checks (deterministic) ---
    cc_expect = record_expectation.get("chief_complaint", {})
    cc_text = record.get("chief_complaint", "")
    cc_max_chars = cc_expect.get("max_chars", 30)
    cc_require_duration = cc_expect.get("require_duration", True)
    cc_acceptable_variants = cc_expect.get("acceptable_variants", [])

    cc_checks: Dict[str, Any] = {}
    cc_checks["length_ok"] = len(cc_text) <= cc_max_chars if cc_text else False
    cc_checks["actual_length"] = len(cc_text)
    cc_checks["max_chars"] = cc_max_chars

    # Duration check: look for common Chinese duration patterns
    duration_pattern = re.compile(
        r"(\d+\s*(天|日|周|月|年|小时|分钟|个月|余年|余月|余天))"
        r"|(\d+[天日周月年])"
        r"|(半[天月年])"
    )
    has_duration = bool(duration_pattern.search(cc_text)) if cc_text else False
    cc_checks["has_duration"] = has_duration
    cc_checks["duration_required"] = cc_require_duration
    cc_checks["duration_ok"] = has_duration or not cc_require_duration

    # Variant match: check if CC matches any acceptable variant
    if cc_acceptable_variants and cc_text:
        variant_matched = any(v in cc_text or cc_text in v for v in cc_acceptable_variants)
        cc_checks["variant_matched"] = variant_matched
    else:
        cc_checks["variant_matched"] = True  # no variants specified = pass

    # CC score: all checks must pass
    cc_pass_count = sum([
        cc_checks["length_ok"],
        cc_checks["duration_ok"],
        cc_checks["variant_matched"],
    ])
    cc_score = cc_pass_count / 3.0
    cc_checks["score"] = round(cc_score, 3)
    result["chief_complaint"] = cc_checks

    # --- present_illness + past_history checks (LLM judge) ---
    # Filter subsections by status: only check required and required_if_available.
    # Skip not_applicable and required_if_asked (negative findings like "无手术史").
    _CHECKABLE = {"required", "required_if_available"}

    def _get_checkable_subsections(field_expect: dict) -> List[str]:
        subs = field_expect.get("subsections", {})
        if isinstance(subs, list):
            return subs  # backward compat: flat list
        return [name for name, cfg in subs.items()
                if isinstance(cfg, dict) and cfg.get("status", "") in _CHECKABLE]

    pi_expect = record_expectation.get("present_illness", {})
    ph_expect = record_expectation.get("past_history", {})
    pi_subsections = _get_checkable_subsections(pi_expect)
    ph_subsections = _get_checkable_subsections(ph_expect)

    pi_text = record.get("present_illness", "")
    ph_text = record.get("past_history", "")

    if pi_subsections or ph_subsections:
        provider = _pick_judges(1)[0]
        prompt = _NHC_COMPLIANCE_JUDGE_PROMPT.format(
            present_illness=pi_text or "（空）",
            past_history=ph_text or "（空）",
            pi_subsections="\n".join(f"- {s}" for s in pi_subsections) if pi_subsections else "（无需检查）",
            ph_subsections="\n".join(f"- {s}" for s in ph_subsections) if ph_subsections else "（无需检查）",
        )
        try:
            raw = await _llm_call(provider, prompt)
            parsed = _parse_json_response(raw)
        except Exception:
            parsed = {}

        # Present illness subsection results
        pi_results = parsed.get("present_illness", {})
        pi_covered: Dict[str, bool] = {}
        for s in pi_subsections:
            pi_covered[s] = bool(pi_results.get(s, False))
        pi_score = (sum(pi_covered.values()) / len(pi_subsections)) if pi_subsections else 1.0

        # Past history subsection results
        ph_results = parsed.get("past_history", {})
        ph_covered: Dict[str, bool] = {}
        for s in ph_subsections:
            ph_covered[s] = bool(ph_results.get(s, False))
        ph_score = (sum(ph_covered.values()) / len(ph_subsections)) if ph_subsections else 1.0
    else:
        pi_covered = {}
        pi_score = 1.0
        ph_covered = {}
        ph_score = 1.0

    result["present_illness"] = {
        "subsections": pi_covered,
        "score": round(pi_score, 3),
    }
    result["past_history"] = {
        "subsections": ph_covered,
        "score": round(ph_score, 3),
    }

    # --- NHC score (0-100 scale) ---
    # Only chief_complaint format is scored per Article 13 (outpatient).
    # Present illness / past history subsection coverage is informational
    # (the 5-subsection breakdown is Article 18, inpatient only).
    result["score"] = int(round(cc_score * 100))

    return result


# --------------- Tier 2 orchestrator -------------------------------------

async def validate_tier2(
    persona: dict,
    db_path: str,
    record_id: int,
    conversation: list,
) -> dict:
    """3-axis hybrid scorecard validation.

    Axis 1: Elicitation Completeness — did the AI ask about the right topics?
    Axis 2: Extraction Fidelity — did the system capture what the patient said?
    Axis 3: NHC Record Quality — is the final record properly structured?

    Returns {
        'pass': bool,
        'elicitation': {'score': float, 'topics': {topic: bool}},
        'extraction': {'score': float, 'facts': {id: {...}}},
        'nhc_compliance': {'score': float, 'chief_complaint': {...}, ...},
        'combined_score': int (0-100),
    }
    """
    record = _load_record_from_db(record_id, db_path)

    # Read persona expectation sections (new schema)
    coverage_expectation = persona.get("coverage_expectation", {})
    fact_catalog = persona.get("fact_catalog", [])
    record_expectation = persona.get("record_expectation", {})

    # --- Backward compatibility: derive from old schema if new keys absent ---
    if not coverage_expectation and persona.get("checklist"):
        checklist = persona["checklist"]
        coverage_expectation = {
            "must_elicit": checklist.get("must_ask", []),
            "min_coverage": checklist.get("min_coverage", 0.6),
        }

    if not fact_catalog and persona.get("expected_extracted"):
        # Convert old {field: [keywords]} to fact_catalog list
        idx = 0
        for field, keywords in persona["expected_extracted"].items():
            for kw in keywords:
                fact_catalog.append({
                    "id": f"legacy_{idx}",
                    "fact": kw,
                    "expected_field": field,
                    "importance": "important",
                })
                idx += 1

    if not record_expectation:
        record_expectation = {
            "chief_complaint": {"max_chars": 30, "require_duration": True},
            "present_illness": {"subsections": []},
            "past_history": {"subsections": []},
        }

    # Run all 3 axes concurrently
    axis1_task = _axis1_elicitation(conversation, coverage_expectation)
    axis2_task = _axis2_extraction(record, fact_catalog, conversation=conversation)
    axis3_task = _axis3_nhc_compliance(record, record_expectation)

    elicitation, extraction, nhc_compliance = await asyncio.gather(
        axis1_task, axis2_task, axis3_task,
    )

    # --- Combined score (0-100) ---
    # Weights: elicitation 30%, extraction 40%, NHC compliance 30%
    combined_score = int(round(
        elicitation["score"] * 0.3
        + extraction["score"] * 0.4
        + nhc_compliance["score"] * 0.3
    ))

    # --- Hard-fail conditions ---
    cc_text = record.get("chief_complaint", "")
    hard_fail_cc_length = len(cc_text) > 30
    hard_fail_critical_missing = extraction.get("any_critical_missing", False)
    min_coverage_pct = int(coverage_expectation.get("min_coverage", 0.5) * 100)
    hard_fail_elicitation = elicitation["score"] < 50  # scores are now 0-100

    has_hard_fail = hard_fail_cc_length or hard_fail_critical_missing or hard_fail_elicitation

    # --- Pass criteria ---
    # All critical facts captured AND elicitation >= min_coverage AND no hard fails
    all_critical_captured = not hard_fail_critical_missing
    elicitation_sufficient = elicitation["score"] >= min_coverage_pct
    passed = all_critical_captured and elicitation_sufficient and not has_hard_fail

    return {
        "pass": passed,
        "elicitation": elicitation,
        "extraction": extraction,
        "nhc_compliance": nhc_compliance,
        "combined_score": combined_score,
        "hard_fails": {
            "cc_over_30_chars": hard_fail_cc_length,
            "critical_fact_missing": hard_fail_critical_missing,
            "elicitation_below_50pct": hard_fail_elicitation,
        },
    }


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

## 数据库中存储的完整结构化病历字段
以下是数据库中实际存储的所有字段及其值。审查时必须逐字段核对，不要凭印象判断。
{record_dump}

## 对话记录
{transcript}

## 审查规则（严格遵守）

### 关于"提取遗漏"的判定标准
在判定"提取遗漏"之前，你必须：
1. 逐一检查上面列出的每个病历字段的值
2. 如果患者提到的信息出现在**任何**字段中（哪怕不是你预期的字段），则**不是**遗漏
3. 信息可能被改写、概括或用医学术语替代——只要语义等价就算已提取
4. 例如：患者说"做康复训练"，如果present_illness中有"康复训练"或"康复治疗"或类似表述，则不是遗漏
5. 只有当某条重要临床信息在所有病历字段中都完全没有体现时，才判定为提取遗漏

### 关于"提取错误"的判定标准
在判定"提取错误"（幻觉）之前，你必须：
1. 仔细重读完整对话记录，确认患者确实从未说过相关内容
2. 考虑患者可能用口语、方言、近义词或不同表述方式说过类似的话
3. 考虑AI助手在总结时可能进行了合理的医学推断或规范化表述
4. 只有当结构化字段中的信息与对话内容明显矛盾、或完全无中生有时，才判定为提取错误

### 检查类型
1. **内容重复**：同一字段中是否有重复或近义重复的内容（如同一事实用不同措辞出现两次）
2. **系统错误**：对话中是否出现系统错误消息（如"系统繁忙"、"请稍后再试"）
3. **提取遗漏**：（按上述严格标准判定）患者明确提到但所有病历字段中均无体现的重要临床信息
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
    record = _load_record_from_db(record_id, db_path)
    record_lines = []
    for field, value in record.items():
        if value and value.strip():
            record_lines.append(f"- {field}: {value}")
    record_dump = "\n".join(record_lines) if record_lines else "（所有字段为空）"

    transcript_lines = []
    for turn in conversation:
        role = "AI助手" if turn.get("role") == "system" else "患者"
        text = turn.get("content", turn.get("text", ""))
        transcript_lines.append(f"{role}: {text}")
    transcript = "\n".join(transcript_lines)

    prompt = _ANOMALY_REVIEW_PROMPT.format(
        name=persona.get("name", "?"),
        condition=persona.get("condition", "?"),
        record_dump=record_dump,
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
