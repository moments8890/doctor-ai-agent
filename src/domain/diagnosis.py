"""
AI diagnosis pipeline — generates differential diagnoses, workup, and treatment
suggestions from a structured medical record.

Shared by APScheduler (auto-run) and the diagnose() chat tool (on-demand).
Follows the exact LLM call pattern used in domain.records.structuring.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from sqlalchemy import select

from db.crud.case_history import match_cases
from db.crud.diagnosis import (
    create_pending_diagnosis,
    save_completed_diagnosis,
    save_failed_diagnosis,
)
from db.engine import AsyncSessionLocal
from db.models.records import MedicalRecordDB
from domain.knowledge.doctor_knowledge import load_knowledge_context_for_prompt
from domain.knowledge.skill_loader import get_diagnosis_skill
from infra.llm.client import _PROVIDERS
from infra.llm.resilience import call_with_retry_and_fallback
from infra.observability.observability import trace_block
from utils.log import log

# Dedicated LLM I/O logger — writes to logs/diagnosis_llm.jsonl
import logging as _logging
import json as _json_mod
from pathlib import Path as _Path

_LLM_LOG_DIR = _Path(__file__).resolve().parents[2] / "logs"
_LLM_LOG_DIR.mkdir(exist_ok=True)
_llm_logger = _logging.getLogger("diagnosis.llm_io")
_llm_logger.setLevel(_logging.DEBUG)
if not _llm_logger.handlers:
    _fh = _logging.FileHandler(str(_LLM_LOG_DIR / "diagnosis_llm.jsonl"), encoding="utf-8")
    _fh.setFormatter(_logging.Formatter("%(message)s"))
    _llm_logger.addHandler(_fh)
    _llm_logger.propagate = False


def _log_llm_io(tag: str, **kwargs: object) -> None:
    """Write one JSONL line to diagnosis_llm.jsonl."""
    from datetime import datetime, timezone
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "tag": tag, **kwargs}
    _llm_logger.debug(_json_mod.dumps(entry, ensure_ascii=False, default=str))

# ---------------------------------------------------------------------------
# Module-level singleton cache: one HTTP connection pool per provider.
# ---------------------------------------------------------------------------
_DIAGNOSIS_CLIENT_CACHE: Dict[str, AsyncOpenAI] = {}

# Valid confidence values; anything else is coerced to "中".
_VALID_CONFIDENCE = {"低", "中", "高"}

# Valid urgency values for workup items.
_VALID_URGENCY = {"常规", "紧急", "急诊"}

# Valid intervention values for treatment items.
_VALID_INTERVENTION = {"手术", "药物", "观察", "转诊"}

# Maximum items per array (per spec).
_MAX_ARRAY_ITEMS = 10


# ---------------------------------------------------------------------------
# Provider resolution — mirrors structuring._resolve_provider() exactly.
# ---------------------------------------------------------------------------

def _resolve_provider(provider_name: str) -> Dict[str, Any]:
    """Resolve and configure provider dict; raise RuntimeError if invalid."""
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        allowed = ", ".join(sorted(_PROVIDERS.keys()))
        raise RuntimeError(
            "Unsupported DIAGNOSIS_LLM provider: {0} (allowed: {1})".format(
                provider_name, allowed
            )
        )
    provider = dict(provider)
    if provider_name == "ollama":
        provider["model"] = (
            os.environ.get("OLLAMA_DIAGNOSIS_MODEL")
            or os.environ.get("OLLAMA_STRUCTURING_MODEL")
            or os.environ.get("OLLAMA_MODEL", provider["model"])
        )
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])
    strict_mode = os.environ.get("LLM_PROVIDER_STRICT_MODE", "true").strip().lower() not in {
        "0", "false", "no", "off"
    }
    if strict_mode and provider_name != "ollama":
        key_env = provider["api_key_env"]
        if not os.environ.get(key_env, "").strip():
            raise RuntimeError(
                "Selected provider '{0}' requires {1}, but it is empty; strict mode blocks fallback".format(
                    provider_name, key_env,
                )
            )
    return provider


def _get_diagnosis_client(provider_name: str, provider: Dict[str, Any]) -> AsyncOpenAI:
    """Return (or create) a singleton AsyncOpenAI client for the given provider."""
    # Skip singleton cache in test environments so mock patches can intercept.
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", ""):
        return AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("DIAGNOSIS_LLM_TIMEOUT", "60")),
            max_retries=0,
        )
    if provider_name not in _DIAGNOSIS_CLIENT_CACHE:
        _DIAGNOSIS_CLIENT_CACHE[provider_name] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("DIAGNOSIS_LLM_TIMEOUT", "60")),
            max_retries=0,
        )
    return _DIAGNOSIS_CLIENT_CACHE[provider_name]


# ---------------------------------------------------------------------------
# LLM caller — mirrors structuring._make_llm_caller() exactly.
# ---------------------------------------------------------------------------

def _make_llm_caller(
    client: AsyncOpenAI,
    provider_name: str,
    system_prompt: str,
    user_content: str,
):
    """Return an async callable suitable for call_with_retry_and_fallback."""
    async def _call(model_name: str):
        with trace_block("llm", "diagnosis.chat_completion", {"provider": provider_name, "model": model_name}):
            return await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=3000,
                temperature=0,
            )
    return _call


# ---------------------------------------------------------------------------
# Cloud fallback — mirrors structuring._call_with_cloud_fallback() exactly.
# ---------------------------------------------------------------------------

async def _call_with_cloud_fallback(
    primary_call,
    provider: Dict[str, Any],
    provider_name: str,
    system_prompt: str,
    user_content: str,
    doctor_id: Optional[str],
) -> object:
    """Call LLM with retry; on failure attempt cloud fallback if configured."""
    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen3.5:9b")
    try:
        return await call_with_retry_and_fallback(
            primary_call,
            primary_model=provider["model"],
            fallback_model=fallback_model,
            max_attempts=int(os.environ.get("DIAGNOSIS_LLM_ATTEMPTS", "3")),
            op_name="diagnosis.chat_completion",
            circuit_key_suffix=doctor_id or "",
        )
    except Exception as _primary_err:
        return await _try_cloud_fallback(
            _primary_err, provider_name, system_prompt, user_content
        )


async def _try_cloud_fallback(
    original_err: Exception,
    provider_name: str,
    system_prompt: str,
    user_content: str,
) -> object:
    """Attempt cloud fallback when primary (usually ollama) fails entirely."""
    _cloud_fallback = (
        os.environ.get("OLLAMA_CLOUD_FALLBACK", "").strip() if provider_name == "ollama" else ""
    )
    if not _cloud_fallback:
        raise original_err
    from infra.llm.egress import check_cloud_egress
    check_cloud_egress(_cloud_fallback, "diagnosis", original_error=original_err)
    log(f"[diagnosis:ollama] all retries failed ({original_err}); trying cloud fallback={_cloud_fallback}")
    _cloud_provider = _PROVIDERS.get(_cloud_fallback)
    if _cloud_provider is None:
        raise original_err
    _cloud_provider = dict(_cloud_provider)
    _cloud_client = _get_diagnosis_client(_cloud_fallback, _cloud_provider)
    _cloud_call = _make_llm_caller(_cloud_client, _cloud_fallback, system_prompt, user_content)
    _cloud_timeout = float(os.environ.get("DIAGNOSIS_CLOUD_FALLBACK_TIMEOUT", "5.0"))
    try:
        return await asyncio.wait_for(
            call_with_retry_and_fallback(
                _cloud_call,
                primary_model=_cloud_provider["model"],
                max_attempts=2,
                op_name="diagnosis.chat_completion.cloud_fallback",
            ),
            timeout=_cloud_timeout,
        )
    except asyncio.TimeoutError:
        log("[diagnosis] cloud fallback timed out")
        raise


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _format_matched_cases(cases: List[Dict[str, Any]]) -> str:
    """Format matched cases for the system prompt."""
    if not cases:
        return ""
    lines = ["【类似病例参考】"]
    for i, c in enumerate(cases, 1):
        sim = round(c.get("similarity", 0) * 100)
        cc = (c.get("chief_complaint") or "")[:40]
        dx = c.get("final_diagnosis") or "未明确"
        tx = c.get("treatment") or ""
        outcome = c.get("outcome") or ""
        line = f"{i}. 相似度{sim}% — {cc} → {dx}"
        if tx:
            line += f"（治疗：{tx[:30]}）"
        if outcome:
            line += f"（转归：{outcome[:20]}）"
        lines.append(line)
    return "\n".join(lines)


def _row_to_result(row: Any) -> Dict[str, Any]:
    """Convert a DiagnosisResult ORM row to a plain dict."""
    import json as _json
    return {
        "status": row.status,
        "differentials": _json.loads(row.ai_output).get("differentials", []) if row.ai_output else [],
        "workup": _json.loads(row.ai_output).get("workup", []) if row.ai_output else [],
        "treatment": _json.loads(row.ai_output).get("treatment", []) if row.ai_output else [],
        "red_flags": _json.loads(row.red_flags) if row.red_flags else [],
        "case_references": _json.loads(row.case_references) if row.case_references else [],
        "error_message": row.error_message,
    }


def _format_structured_fields(structured: Dict[str, str]) -> str:
    """Format structured fields for the user message."""
    _FIELD_LABELS = {
        "chief_complaint":      "主诉",
        "present_illness":      "现病史",
        "past_history":         "既往史",
        "allergy_history":      "过敏史",
        "personal_history":     "个人史",
        "marital_reproductive": "婚育史",
        "family_history":       "家族史",
        "physical_exam":        "体格检查",
        "specialist_exam":      "专科检查",
        "auxiliary_exam":       "辅助检查",
        "diagnosis":            "初步诊断",
        "treatment_plan":       "治疗方案",
        "orders_followup":      "医嘱随访",
        "visit_type":           "就诊类型",
    }
    lines = []
    for key, label in _FIELD_LABELS.items():
        value = (structured.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines) if lines else "(无结构化字段)"


def _build_system_prompt(
    skill_content: Optional[str],
    cases_text: str,
    knowledge_text: str,
) -> str:
    """Assemble the system prompt from base prompt + skill + cases + knowledge."""
    from utils.prompt_loader import get_prompt_sync

    # Load the base diagnosis prompt (JSON schema + rules)
    base_prompt = get_prompt_sync("diagnosis")
    parts = [base_prompt] if base_prompt else ["你是一位神经外科AI诊断助手。"]

    # Append specialty-specific skill (must-not-miss patterns, etc.)
    if skill_content and skill_content.strip():
        parts.append(skill_content.strip())

    if cases_text:
        parts.append(cases_text)

    if knowledge_text:
        parts.append(knowledge_text)

    return "\n\n".join(parts)


def _build_user_message(structured: Dict[str, str]) -> str:
    """Build the user message from structured fields."""
    fields_text = _format_structured_fields(structured)
    return "请根据以下病历生成鉴别诊断建议（严格按系统提示中的json格式输出）：\n\n" + fields_text


# ---------------------------------------------------------------------------
# Response parsing + validation
# ---------------------------------------------------------------------------

def _coerce_confidence(value: Any) -> str:
    if isinstance(value, str) and value in _VALID_CONFIDENCE:
        return value
    return "中"


def _coerce_urgency(value: Any) -> str:
    if isinstance(value, str) and value in _VALID_URGENCY:
        return value
    return "常规"


def _coerce_intervention(value: Any) -> str:
    if isinstance(value, str) and value in _VALID_INTERVENTION:
        return value
    return "观察"


def _validate_differentials(raw: Any) -> List[Dict[str, str]]:
    """Validate and coerce differential diagnoses array."""
    if not isinstance(raw, list):
        return []
    result = []
    for i, item in enumerate(raw[:_MAX_ARRAY_ITEMS]):
        if not isinstance(item, dict):
            log(f"[diagnosis] dropping malformed differential at index {i}: not a dict", level="warning")
            continue
        condition = str(item.get("condition") or item.get("诊断名称") or "").strip()
        if not condition:
            log(f"[diagnosis] dropping differential at index {i}: missing condition", level="warning")
            continue
        result.append({
            "condition":  condition,
            "confidence": _coerce_confidence(item.get("confidence") or item.get("可能性")),
            "reasoning":  str(item.get("reasoning") or item.get("推理依据") or "").strip(),
        })
    return result


def _validate_workup(raw: Any) -> List[Dict[str, str]]:
    """Validate and coerce workup items array."""
    if not isinstance(raw, list):
        return []
    result = []
    for i, item in enumerate(raw[:_MAX_ARRAY_ITEMS]):
        if not isinstance(item, dict):
            log(f"[diagnosis] dropping malformed workup at index {i}: not a dict", level="warning")
            continue
        test = str(item.get("test") or item.get("检查名称") or "").strip()
        if not test:
            log(f"[diagnosis] dropping workup at index {i}: missing test", level="warning")
            continue
        result.append({
            "test":       test,
            "rationale":  str(item.get("rationale") or item.get("理由") or "").strip(),
            "urgency":    _coerce_urgency(item.get("urgency") or item.get("紧急程度")),
        })
    return result


def _validate_treatment(raw: Any) -> List[Dict[str, str]]:
    """Validate and coerce treatment items array."""
    if not isinstance(raw, list):
        return []
    result = []
    for i, item in enumerate(raw[:_MAX_ARRAY_ITEMS]):
        if not isinstance(item, dict):
            log(f"[diagnosis] dropping malformed treatment at index {i}: not a dict", level="warning")
            continue
        drug_class = str(item.get("drug_class") or item.get("药物类别") or "").strip()
        description = str(item.get("description") or item.get("说明") or "").strip()
        if not drug_class and not description:
            log(f"[diagnosis] dropping treatment at index {i}: missing drug_class and description", level="warning")
            continue
        result.append({
            "drug_class":    drug_class,
            "intervention":  _coerce_intervention(item.get("intervention") or item.get("干预方式")),
            "description":   description,
        })
    return result


def _parse_and_validate(raw: str, provider_name: str) -> Optional[Dict[str, Any]]:
    """Parse JSON response and validate fields.

    Returns validated dict or None if completely unparseable or empty differentials.
    """
    with trace_block("llm", "diagnosis.parse_response"):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            log(f"[diagnosis:{provider_name}] JSON parse failed ({exc}); attempting partial extraction", level="warning")
            # Attempt partial extraction by scanning for array-like substrings
            data = _attempt_partial_parse(raw)
            if data is None:
                return None

    if not isinstance(data, dict):
        log(f"[diagnosis:{provider_name}] LLM response is not a dict: {type(data)}", level="warning")
        return None

    differentials = _validate_differentials(data.get("differentials"))
    if not differentials:
        log(f"[diagnosis:{provider_name}] no valid differentials after validation", level="warning")
        return None

    workup = _validate_workup(data.get("workup"))
    treatment = _validate_treatment(data.get("treatment"))

    red_flags_raw = data.get("red_flags") or data.get("red flags") or data.get("危险信号")
    if isinstance(red_flags_raw, list):
        red_flags = [str(s) for s in red_flags_raw if s][:_MAX_ARRAY_ITEMS]
    else:
        red_flags = []

    return {
        "differentials": differentials,
        "workup":        workup,
        "treatment":     treatment,
        "red_flags":     red_flags,
    }


def _attempt_partial_parse(raw: str) -> Optional[Dict[str, Any]]:
    """Try to extract a partial dict from a malformed JSON string."""
    # Try stripping common LLM text wrappers before/after the JSON block.
    for start_marker in ("{", "["):
        idx = raw.find(start_marker)
        if idx >= 0:
            candidate = raw[idx:]
            # Try to find the matching close
            end_marker = "}" if start_marker == "{" else "]"
            last = candidate.rfind(end_marker)
            if last >= 0:
                try:
                    return json.loads(candidate[: last + 1])
                except (json.JSONDecodeError, TypeError):
                    continue
    return None


# ---------------------------------------------------------------------------
# Clinical context loading
# ---------------------------------------------------------------------------

async def _load_clinical_context_from_record(
    session,
    record_id: int,
    doctor_id: str,
) -> Optional[Dict[str, str]]:
    """Load structured fields from a DB medical record row."""
    from sqlalchemy import select as _select
    row = (await session.execute(
        _select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if row is None:
        log(f"[diagnosis] record_id={record_id} not found for doctor={doctor_id}", level="warning")
        return None
    if not row.structured:
        log(f"[diagnosis] record_id={record_id} has no structured JSON", level="warning")
        return None
    try:
        structured = json.loads(row.structured)
        if not isinstance(structured, dict):
            log(f"[diagnosis] record_id={record_id} structured is not a dict", level="warning")
            return None
        return structured
    except (json.JSONDecodeError, TypeError) as exc:
        log(f"[diagnosis] record_id={record_id} structured JSON invalid: {exc}", level="warning")
        return None


async def _load_clinical_context_from_text(
    clinical_text: str,
    doctor_id: Optional[str],
) -> Dict[str, str]:
    """Extract structured fields from raw clinical text using the structuring pipeline."""
    from domain.records.structuring import structure_medical_record
    record = await structure_medical_record(clinical_text, doctor_id)
    return record.structured or {"chief_complaint": clinical_text[:200]}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_diagnosis(
    doctor_id: str,
    record_id: Optional[int] = None,
    clinical_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full diagnosis pipeline.

    Accepts EITHER a record_id (loads structured fields from DB) OR raw
    clinical_text (from chat history). At least one must be provided.

    Returns a dict with keys: differentials, workup, treatment, red_flags.
    If record_id is provided, also saves the result to diagnosis_results table.
    If clinical_text only, returns without saving (conversational path).
    """
    if record_id is None and not clinical_text:
        raise ValueError("run_diagnosis: either record_id or clinical_text must be provided")

    # Resolve provider: DIAGNOSIS_LLM → STRUCTURING_LLM → "deepseek"
    raw_provider = (
        os.environ.get("DIAGNOSIS_LLM", "").strip()
        or os.environ.get("STRUCTURING_LLM", "").strip()
        or "deepseek"
    )
    provider_name = raw_provider
    try:
        provider = _resolve_provider(provider_name)
    except RuntimeError as exc:
        log(f"[diagnosis] provider resolution failed: {exc}", level="error")
        if record_id is not None:
            async with AsyncSessionLocal() as session:
                row = await create_pending_diagnosis(session, record_id, doctor_id)
                await session.flush()
                await save_failed_diagnosis(session, row.id, f"Provider error: {exc}")
                await session.commit()
        raise

    model_name = provider.get("model", "deepseek-chat")
    _tag = f"[diagnosis:{provider_name}:{model_name}]"
    log(f"{_tag} starting for doctor={doctor_id} record_id={record_id}")

    async with AsyncSessionLocal() as session:
        # ------------------------------------------------------------------
        # Step 1: Create pending row (if record-based path)
        # ------------------------------------------------------------------
        diagnosis_row = None
        if record_id is not None:
            # Check for existing row (re-run after failure or chat retry)
            from db.crud.diagnosis import get_diagnosis_by_record
            existing = await get_diagnosis_by_record(session, record_id, doctor_id)
            if existing and existing.status in ("completed", "confirmed"):
                log(f"{_tag} diagnosis already exists for record {record_id}, skipping")
                return _row_to_result(existing)
            if existing:
                # Reuse existing failed/pending row
                diagnosis_row = existing
                diagnosis_row.status = "pending"
                diagnosis_row.error_message = None
            else:
                diagnosis_row = await create_pending_diagnosis(session, record_id, doctor_id)
            await session.flush()

        # ------------------------------------------------------------------
        # Step 2: Load clinical context
        # ------------------------------------------------------------------
        structured: Optional[Dict[str, str]] = None
        try:
            if record_id is not None:
                structured = await _load_clinical_context_from_record(session, record_id, doctor_id)
                if structured is None:
                    # Record has no structured JSON — fall back to empty dict
                    structured = {}
            else:
                structured = await _load_clinical_context_from_text(clinical_text, doctor_id)  # type: ignore[arg-type]
        except Exception as exc:
            log(f"{_tag} clinical context load failed: {exc}", level="error")
            if diagnosis_row is not None:
                await save_failed_diagnosis(session, diagnosis_row.id, f"Context load error: {exc}")
                await session.commit()
            raise

        chief_complaint = (structured.get("chief_complaint") or clinical_text or "")[:200]

        # ------------------------------------------------------------------
        # Step 3: Match similar cases (non-blocking — empty on failure)
        # ------------------------------------------------------------------
        matched_cases: List[Dict[str, Any]] = []
        try:
            matched_cases = await match_cases(session, doctor_id, chief_complaint, limit=5)
        except Exception as exc:
            log(f"{_tag} case matching failed (non-fatal): {exc}", level="warning")

        # ------------------------------------------------------------------
        # Step 4: Load diagnosis skill
        # ------------------------------------------------------------------
        skill_content = get_diagnosis_skill("neurology")

        # ------------------------------------------------------------------
        # Step 5: Load doctor knowledge (non-blocking — empty on failure)
        # ------------------------------------------------------------------
        knowledge_text = ""
        try:
            knowledge_text = await load_knowledge_context_for_prompt(
                session, doctor_id, chief_complaint
            )
        except Exception as exc:
            log(f"{_tag} knowledge load failed (non-fatal): {exc}", level="warning")

        # ------------------------------------------------------------------
        # Step 6: Build prompt
        # ------------------------------------------------------------------
        cases_text = _format_matched_cases(matched_cases)
        system_prompt = _build_system_prompt(skill_content, cases_text, knowledge_text)
        user_message = _build_user_message(structured)

        log(f"{_tag} user_message_preview: {user_message[:120]}")
        _log_llm_io("input",
                     doctor_id=doctor_id, record_id=record_id,
                     provider=provider_name, model=model_name,
                     system_prompt=system_prompt,
                     user_message=user_message,
                     matched_cases_count=len(matched_cases))

        # ------------------------------------------------------------------
        # Step 7: Call LLM
        # ------------------------------------------------------------------
        completion = None
        llm_error: Optional[str] = None
        try:
            client = _get_diagnosis_client(provider_name, provider)
            primary_call = _make_llm_caller(client, provider_name, system_prompt, user_message)
            completion = await _call_with_cloud_fallback(
                primary_call, provider, provider_name, system_prompt, user_message, doctor_id
            )
        except Exception as exc:
            log(f"{_tag} LLM call failed: {exc}", level="error")
            llm_error = str(exc)
            _log_llm_io("error", doctor_id=doctor_id, record_id=record_id, error=str(exc))

        if llm_error or completion is None:
            err_msg = llm_error or "Empty LLM response"
            if diagnosis_row is not None:
                await save_failed_diagnosis(session, diagnosis_row.id, err_msg)
                await session.commit()
            return {"error": err_msg, "status": "failed"}

        raw = (completion.choices[0].message.content or "").strip()
        log(f"{_tag} raw response ({len(raw)} chars): {raw[:200]}")
        _log_llm_io("output",
                     doctor_id=doctor_id, record_id=record_id,
                     raw_length=len(raw), raw=raw)

        if not raw:
            err_msg = "Empty LLM response"
            if diagnosis_row is not None:
                await save_failed_diagnosis(session, diagnosis_row.id, err_msg)
                await session.commit()
            return {"error": err_msg, "status": "failed"}

        # ------------------------------------------------------------------
        # Step 8: Parse + validate
        # ------------------------------------------------------------------
        result = _parse_and_validate(raw, provider_name)

        if result is None:
            err_msg = "Invalid LLM response: no valid differentials"
            if diagnosis_row is not None:
                await save_failed_diagnosis(session, diagnosis_row.id, err_msg)
                await session.commit()
            return {"error": err_msg, "status": "failed"}

        # ------------------------------------------------------------------
        # Step 9: Save to DB (record path only)
        # ------------------------------------------------------------------
        red_flags = result.get("red_flags", [])
        # Build case_references summary for DB storage
        case_refs = [
            {
                "id":               c.get("id"),
                "chief_complaint":  (c.get("chief_complaint") or "")[:80],
                "final_diagnosis":  c.get("final_diagnosis"),
                "treatment":        c.get("treatment"),
                "outcome":          c.get("outcome"),
                "similarity":       c.get("similarity"),
            }
            for c in matched_cases
        ]

        if diagnosis_row is not None:
            # ai_output stores differentials/workup/treatment (immutable)
            ai_output_dict = {
                "differentials": result["differentials"],
                "workup":        result["workup"],
                "treatment":     result["treatment"],
            }
            await save_completed_diagnosis(
                session,
                diagnosis_id=diagnosis_row.id,
                ai_output_json=json.dumps(ai_output_dict, ensure_ascii=False),
                red_flags=json.dumps(red_flags, ensure_ascii=False) if red_flags else None,
                case_references=json.dumps(case_refs, ensure_ascii=False) if case_refs else None,
            )
            await session.commit()
            log(f"{_tag} saved completed diagnosis id={diagnosis_row.id}")

        return {
            "differentials":   result["differentials"],
            "workup":          result["workup"],
            "treatment":       result["treatment"],
            "red_flags":       red_flags,
            "case_references": case_refs,
            "status":          "completed",
        }
