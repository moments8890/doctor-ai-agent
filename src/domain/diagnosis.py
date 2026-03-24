"""
AI diagnosis pipeline — generates differential diagnoses, workup, and treatment
suggestions from a structured medical record.

Shared by APScheduler (auto-run) and the diagnose() chat tool (on-demand).
Uses structured_call (instructor) for reliable structured output from LLMs.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select

# TODO: case_history and diagnosis CRUD removed (killed tables).
# Diagnosis pipeline now returns results without persisting to diagnosis_results.
# Case matching is disabled until migrated to medical_records-based approach.
from db.engine import AsyncSessionLocal
from db.models.records import MedicalRecordDB
from infra.llm.client import _PROVIDERS
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
# Pydantic response models for structured LLM output
# ---------------------------------------------------------------------------

class DiagnosisDifferential(BaseModel):
    condition: str = Field(description="Diagnosis name")
    confidence: str = Field(default="中", description="Confidence level: 低/中/高")
    reasoning: str = Field(default="", description="Clinical reasoning")
    patient_note: str = Field(default="", description="Patient-facing note")


class DiagnosisWorkup(BaseModel):
    test: str = Field(description="Test/examination name")
    rationale: str = Field(default="", description="Rationale for the test")
    urgency: str = Field(default="常规", description="Urgency: 常规/紧急/急诊")
    patient_note: str = Field(default="", description="Patient-facing note")


class DiagnosisTreatment(BaseModel):
    drug_class: str = Field(default="", description="Drug class")
    intervention: str = Field(default="观察", description="Intervention type: 手术/药物/观察/转诊")
    description: str = Field(default="", description="Description")
    patient_note: str = Field(default="", description="Patient-facing note")


class DiagnosisLLMResponse(BaseModel):
    """Structured response from the diagnosis LLM."""
    differentials: List[DiagnosisDifferential] = Field(default_factory=list)
    workup: List[DiagnosisWorkup] = Field(default_factory=list)
    treatment: List[DiagnosisTreatment] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)


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


# ---------------------------------------------------------------------------
# Structured LLM call via shared helper
# ---------------------------------------------------------------------------

async def _structured_call_for_diagnosis(
    messages: List[Dict[str, str]],
    env_var: str = "DIAGNOSIS_LLM",
) -> DiagnosisLLMResponse:
    """Call the LLM via shared structured_call helper."""
    from agent.llm import structured_call

    return await structured_call(
        response_model=DiagnosisLLMResponse,
        messages=messages,
        op_name="diagnosis",
        env_var=env_var,
        temperature=0,
        max_tokens=3000,
    )


async def _try_cloud_fallback(
    original_err: Exception,
    provider_name: str,
    composed_messages: List[Dict[str, str]],
) -> DiagnosisLLMResponse:
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

    _cloud_timeout = float(os.environ.get("DIAGNOSIS_CLOUD_FALLBACK_TIMEOUT", "5.0"))
    try:
        old_val = os.environ.get("_DIAGNOSIS_CLOUD_FALLBACK", "")
        os.environ["_DIAGNOSIS_CLOUD_FALLBACK"] = _cloud_fallback
        try:
            return await asyncio.wait_for(
                _structured_call_for_diagnosis(
                    composed_messages,
                    env_var="_DIAGNOSIS_CLOUD_FALLBACK",
                ),
                timeout=_cloud_timeout,
            )
        finally:
            if old_val:
                os.environ["_DIAGNOSIS_CLOUD_FALLBACK"] = old_val
            else:
                os.environ.pop("_DIAGNOSIS_CLOUD_FALLBACK", None)
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


def _build_user_message(structured: Dict[str, str]) -> str:
    """Build the user message from structured fields."""
    fields_text = _format_structured_fields(structured)
    return "请根据以下病历生成鉴别诊断建议（严格按系统提示中的json格式输出）：\n\n" + fields_text


# ---------------------------------------------------------------------------
# Response validation / coercion (post-processing after structured_call)
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


def _validate_and_coerce_result(result: DiagnosisLLMResponse) -> Optional[Dict[str, Any]]:
    """Validate and coerce the structured LLM response.

    Returns validated dict or None if empty differentials.
    """
    with trace_block("llm", "diagnosis.validate_response"):
        # Validate differentials
        differentials = []
        for item in result.differentials[:_MAX_ARRAY_ITEMS]:
            condition = item.condition.strip()
            if not condition:
                continue
            differentials.append({
                "condition":    condition,
                "confidence":   _coerce_confidence(item.confidence),
                "reasoning":    item.reasoning.strip(),
                "patient_note": item.patient_note.strip(),
            })

        if not differentials:
            log("[diagnosis] no valid differentials after validation", level="warning")
            return None

        # Validate workup
        workup = []
        for item in result.workup[:_MAX_ARRAY_ITEMS]:
            test = item.test.strip()
            if not test:
                continue
            workup.append({
                "test":         test,
                "rationale":    item.rationale.strip(),
                "urgency":      _coerce_urgency(item.urgency),
                "patient_note": item.patient_note.strip(),
            })

        # Validate treatment
        treatment = []
        for item in result.treatment[:_MAX_ARRAY_ITEMS]:
            drug_class = item.drug_class.strip()
            description = item.description.strip()
            if not drug_class and not description:
                continue
            treatment.append({
                "drug_class":    drug_class,
                "intervention":  _coerce_intervention(item.intervention),
                "description":   description,
                "patient_note":  item.patient_note.strip(),
            })

        # Validate red flags
        red_flags = [str(s) for s in result.red_flags if s][:_MAX_ARRAY_ITEMS]

        return {
            "differentials": differentials,
            "workup":        workup,
            "treatment":     treatment,
            "red_flags":     red_flags,
        }


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
    if not row.has_soap_data():
        log(f"[diagnosis] record_id={record_id} has no SOAP data", level="warning")
        return None
    return row.soap_dict()


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
    provider = _resolve_provider(provider_name)

    model_name = provider.get("model", "deepseek-chat")
    _tag = f"[diagnosis:{provider_name}:{model_name}]"
    log(f"{_tag} starting for doctor={doctor_id} record_id={record_id}")

    async with AsyncSessionLocal() as session:
        # ------------------------------------------------------------------
        # Step 1: Load clinical context
        # ------------------------------------------------------------------
        structured: Optional[Dict[str, str]] = None
        try:
            if record_id is not None:
                structured = await _load_clinical_context_from_record(session, record_id, doctor_id)
                if structured is None:
                    structured = {}
            else:
                structured = await _load_clinical_context_from_text(clinical_text, doctor_id)  # type: ignore[arg-type]
        except Exception as exc:
            log(f"{_tag} clinical context load failed: {exc}", level="error")
            raise

        chief_complaint = (structured.get("chief_complaint") or clinical_text or "")[:200]

        # ------------------------------------------------------------------
        # Step 2: Case matching disabled (CaseHistory table removed)
        # TODO: migrate case matching to medical_records-based approach
        # ------------------------------------------------------------------
        matched_cases: List[Dict[str, Any]] = []

        # ------------------------------------------------------------------
        # Step 3: Load doctor knowledge (non-blocking — empty on failure)
        # ------------------------------------------------------------------
        knowledge_text = ""
        from domain.knowledge.doctor_knowledge import load_knowledge_by_categories
        from agent.prompt_config import REVIEW_LAYERS

        try:
            knowledge_text = await load_knowledge_by_categories(
                doctor_id, REVIEW_LAYERS.knowledge_categories, query=chief_complaint,
            )
        except Exception as exc:
            log(f"{_tag} knowledge load failed (non-fatal): {exc}", level="warning")

        # ------------------------------------------------------------------
        # Step 5: Build prompt via 6-layer composer
        # ------------------------------------------------------------------
        from agent.prompt_composer import compose_for_review

        cases_text = _format_matched_cases(matched_cases)
        doctor_kb = knowledge_text or ""
        patient_ctx_parts = []
        if cases_text:
            patient_ctx_parts.append(cases_text)
        patient_ctx = "\n\n".join(patient_ctx_parts)

        user_message = _build_user_message(structured)

        composed = compose_for_review(
            doctor_id=doctor_id,
            doctor_knowledge=doctor_kb,
            patient_context=patient_ctx,
            doctor_message=user_message,
        )
        # Extract system_prompt for logging (first message)
        system_prompt = composed[0]["content"] if composed else ""

        log(f"{_tag} user_message_preview: {user_message[:120]}")
        _log_llm_io("input",
                     doctor_id=doctor_id, record_id=record_id,
                     provider=provider_name, model=model_name,
                     system_prompt=system_prompt,
                     user_message=user_message,
                     matched_cases_count=len(matched_cases))

        # ------------------------------------------------------------------
        # Step 6: Call LLM via structured_call (instructor)
        # ------------------------------------------------------------------
        llm_result: Optional[DiagnosisLLMResponse] = None
        llm_error: Optional[str] = None

        # Set DIAGNOSIS_LLM env var for structured_call provider resolution.
        # The env var may already be set; if not, use the resolved provider_name.
        if not os.environ.get("DIAGNOSIS_LLM"):
            os.environ["DIAGNOSIS_LLM"] = provider_name

        try:
            llm_result = await _structured_call_for_diagnosis(
                composed, env_var="DIAGNOSIS_LLM",
            )
        except Exception as primary_err:
            try:
                llm_result = await _try_cloud_fallback(
                    primary_err, provider_name, composed,
                )
            except Exception as exc:
                log(f"{_tag} LLM call failed: {exc}", level="error")
                llm_error = str(exc)
                _log_llm_io("error", doctor_id=doctor_id, record_id=record_id, error=str(exc))

        if llm_error or llm_result is None:
            err_msg = llm_error or "Empty LLM response"
            return {"error": err_msg, "status": "failed"}

        log(f"{_tag} structured response: {llm_result.model_dump()}")
        _log_llm_io("output",
                     doctor_id=doctor_id, record_id=record_id,
                     result=llm_result.model_dump())

        # ------------------------------------------------------------------
        # Step 7: Validate + coerce
        # ------------------------------------------------------------------
        result = _validate_and_coerce_result(llm_result)

        if result is None:
            return {"error": "Invalid LLM response: no valid differentials", "status": "failed"}

        # ------------------------------------------------------------------
        # Step 8: Persist diagnosis to medical_records.ai_diagnosis
        # ------------------------------------------------------------------
        red_flags = result.get("red_flags", [])

        try:
            async with AsyncSessionLocal() as db:
                rec = (await db.execute(
                    select(MedicalRecordDB).where(MedicalRecordDB.id == record_id).limit(1)
                )).scalar_one_or_none()
                if rec:
                    rec.ai_diagnosis = json.dumps(result, ensure_ascii=False)
                    await db.commit()
                    log(f"{_tag} diagnosis persisted to record {record_id}")
        except Exception as persist_err:
            log(f"{_tag} diagnosis persist failed (non-fatal): {persist_err}", level="warning")

        # ------------------------------------------------------------------
        # Step 9: Auto-create tasks from diagnosis treatment items
        # ------------------------------------------------------------------
        if record_id and llm_result and llm_result.treatment:
            try:
                from db.crud.tasks import create_task as db_create_task

                async with AsyncSessionLocal() as db:
                    # Get patient_id from the record
                    rec = (await db.execute(
                        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id).limit(1)
                    )).scalar_one_or_none()
                    _patient_id = rec.patient_id if rec else None

                    for t in llm_result.treatment[:5]:
                        if t.intervention in ("手术", "转诊"):
                            await db_create_task(
                                db, doctor_id=doctor_id, task_type="general",
                                title=f"{t.intervention}：{t.description[:50]}",
                                content=t.description,
                                patient_id=_patient_id,
                                record_id=record_id,
                            )
                    log(f"{_tag} auto-created tasks from diagnosis treatment")
            except Exception as task_err:
                log(f"{_tag} auto-task creation failed (non-fatal): {task_err}", level="warning")

        return {
            "differentials":   result["differentials"],
            "workup":          result["workup"],
            "treatment":       result["treatment"],
            "red_flags":       red_flags,
            "case_references": [],
            "status":          "completed",
        }
