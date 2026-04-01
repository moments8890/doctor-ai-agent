"""
AI diagnosis pipeline — generates differential diagnoses, workup, and treatment
suggestions from a structured medical record.

Shared by APScheduler (auto-run) and the diagnose() chat tool (on-demand).
Uses structured_call (instructor) for reliable structured output from LLMs.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import select

# TODO: case_history and diagnosis CRUD removed (killed tables).
# Diagnosis pipeline now returns results without persisting to diagnosis_results.
# Case matching is disabled until migrated to medical_records-based approach.
from db.engine import AsyncSessionLocal
from db.models.records import MedicalRecordDB
from infra.llm.client import _PROVIDERS
from infra.observability.observability import trace_block
from utils.log import log

from domain.diagnosis_models import (
    DiagnosisLLMResponse,
    _VALID_CONFIDENCE,
    _VALID_URGENCY,
    _VALID_INTERVENTION,
    _MAX_ARRAY_ITEMS,
)

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
                "detail":       item.detail.strip(),
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
                "detail":       item.detail.strip(),
                "urgency":      _coerce_urgency(item.urgency),
            })

        # Validate treatment
        treatment = []
        for item in result.treatment[:_MAX_ARRAY_ITEMS]:
            drug_class = item.drug_class.strip()
            detail = item.detail.strip()
            if not drug_class and not detail:
                continue
            treatment.append({
                "drug_class":    drug_class,
                "intervention":  _coerce_intervention(item.intervention),
                "detail":        detail,
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
    if not row.has_structured_data():
        log(f"[diagnosis] record_id={record_id} has no structured data", level="warning")
        return None
    return row.structured_dict()


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
    Results are returned to the caller but not persisted to DB (diagnosis_results
    table was removed; results are stored on medical_records columns instead).
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
    except RuntimeError as resolve_err:
        log(f"[diagnosis] provider resolution failed: {resolve_err}", level="error")
        if record_id is not None:
            try:
                from db.models.records import RecordStatus as RS
                async with AsyncSessionLocal() as fail_db:
                    rec = (await fail_db.execute(
                        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id).limit(1)
                    )).scalar_one_or_none()
                    if rec is not None:
                        rec.status = RS.diagnosis_failed.value
                        await fail_db.commit()
            except Exception:
                pass
        return {"error": str(resolve_err), "status": "failed"}

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
        # Step 2: Case matching — find similar confirmed cases
        # ------------------------------------------------------------------
        try:
            from domain.knowledge.case_matching import find_similar_cases
            async with AsyncSessionLocal() as case_session:
                matched_cases = await find_similar_cases(
                    case_session, doctor_id,
                    chief_complaint=structured.get("chief_complaint", ""),
                    present_illness=structured.get("present_illness", ""),
                    structured=structured,
                )
        except Exception as exc:
            log(f"[diagnosis] case matching failed (non-fatal): {exc}", level="warning")
            matched_cases: List[Dict[str, Any]] = []

        # ------------------------------------------------------------------
        # Step 3: Load doctor knowledge (non-blocking — empty on failure)
        # ------------------------------------------------------------------
        # Step 4: Build prompt via 6-layer composer (KB auto-loaded)
        # ------------------------------------------------------------------
        from agent.prompt_composer import compose_for_review

        cases_text = _format_matched_cases(matched_cases)
        patient_ctx_parts = []
        if cases_text:
            patient_ctx_parts.append(cases_text)
        patient_ctx = "\n\n".join(patient_ctx_parts)

        user_message = _build_user_message(structured)

        # KB auto-loaded by composer when load_knowledge=True
        composed = await compose_for_review(
            doctor_id=doctor_id,
            patient_context=patient_ctx,
            doctor_message=user_message,
        )
        # Extract system_prompt for logging (first message)
        system_prompt = composed[0]["content"] if composed else ""

        log(f"{_tag} user_message_preview: {user_message[:120]}")
        log("[diagnosis] llm_io input",
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

        _DIAGNOSIS_TIMEOUT = int(os.environ.get("DIAGNOSIS_TIMEOUT", "10"))

        try:
            llm_result = await asyncio.wait_for(
                _structured_call_for_diagnosis(composed, env_var="DIAGNOSIS_LLM"),
                timeout=_DIAGNOSIS_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log(f"{_tag} LLM call timed out after {_DIAGNOSIS_TIMEOUT}s", level="error")
            llm_error = f"诊断超时（{_DIAGNOSIS_TIMEOUT}秒），请重试"
        except Exception as primary_err:
            try:
                llm_result = await asyncio.wait_for(
                    _try_cloud_fallback(primary_err, provider_name, composed),
                    timeout=_DIAGNOSIS_TIMEOUT,
                )
            except asyncio.TimeoutError:
                log(f"{_tag} cloud fallback timed out after {_DIAGNOSIS_TIMEOUT}s", level="error")
                llm_error = f"诊断超时（{_DIAGNOSIS_TIMEOUT}秒），请重试"
            except Exception as exc:
                log(f"{_tag} LLM call failed: {exc}", level="error")
                llm_error = str(exc)
                log("[diagnosis] llm_io error",
                    doctor_id=doctor_id, record_id=record_id, error=str(exc))

        if llm_error or llm_result is None:
            err_msg = llm_error or "Empty LLM response"
            # Mark record as diagnosis_failed so frontend stops polling
            if record_id is not None:
                try:
                    from db.models.records import RecordStatus as RS
                    async with AsyncSessionLocal() as fail_db:
                        rec = (await fail_db.execute(
                            select(MedicalRecordDB).where(MedicalRecordDB.id == record_id).limit(1)
                        )).scalar_one_or_none()
                        if rec is not None:
                            rec.status = RS.diagnosis_failed.value
                            await fail_db.commit()
                except Exception as status_err:
                    log(f"{_tag} failed to update record status: {status_err}", level="warning")
            return {"error": err_msg, "status": "failed"}

        log(f"{_tag} structured response: {llm_result.model_dump()}")
        log("[diagnosis] llm_io output",
            doctor_id=doctor_id, record_id=record_id,
            result=llm_result.model_dump())

        # ------------------------------------------------------------------
        # Step 7: Validate + coerce
        # ------------------------------------------------------------------
        result = _validate_and_coerce_result(llm_result)

        if result is None:
            return {"error": "Invalid LLM response: no valid differentials", "status": "failed"}

        # ------------------------------------------------------------------
        # Step 7b: Extract and log KB citations (non-fatal)
        # ------------------------------------------------------------------
        try:
            from domain.knowledge.citation_parser import extract_citations, validate_citations
            from domain.knowledge.usage_tracking import log_citations
            from db.crud.doctor import list_doctor_knowledge_items

            # Collect all text fields that might contain [KB-{id}] markers
            all_text = ""
            if llm_result:
                for d in llm_result.differentials:
                    all_text += f" {d.detail}"
                for w in llm_result.workup:
                    all_text += f" {w.detail}"
                for t in llm_result.treatment:
                    all_text += f" {t.detail}"

            citations = extract_citations(all_text)
            if citations.cited_ids:
                async with AsyncSessionLocal() as cite_session:
                    items = await list_doctor_knowledge_items(cite_session, doctor_id, limit=200)
                    valid_ids = {item.id for item in items}
                    validated = validate_citations(citations.cited_ids, valid_ids)
                    if validated.valid_ids:
                        await log_citations(
                            cite_session, doctor_id, validated.valid_ids,
                            "diagnosis", patient_id=None, record_id=record_id,
                        )
        except Exception as cite_exc:
            log(f"{_tag} citation logging failed (non-fatal): {cite_exc}", level="warning")

        # ------------------------------------------------------------------
        # Step 8: Persist diagnosis to ai_suggestions table
        # ------------------------------------------------------------------
        red_flags = result.get("red_flags", [])

        if record_id is not None:
            try:
                from db.crud.suggestions import create_suggestion
                from db.models.ai_suggestion import SuggestionSection

                async with AsyncSessionLocal() as db:
                    for d in result["differentials"]:
                        await create_suggestion(
                            db,
                            record_id=record_id,
                            doctor_id=doctor_id,
                            section=SuggestionSection.differential,
                            content=d["condition"],
                            detail=d.get("detail") or None,
                            confidence=d.get("confidence") or None,
                        )
                    for w in result["workup"]:
                        await create_suggestion(
                            db,
                            record_id=record_id,
                            doctor_id=doctor_id,
                            section=SuggestionSection.workup,
                            content=w["test"],
                            detail=w.get("detail") or None,
                            urgency=w.get("urgency") or None,
                        )
                    for t in result["treatment"]:
                        await create_suggestion(
                            db,
                            record_id=record_id,
                            doctor_id=doctor_id,
                            section=SuggestionSection.treatment,
                            content=t["drug_class"],
                            detail=t.get("detail") or None,
                            intervention=t.get("intervention") or None,
                        )
                    log(f"{_tag} diagnosis persisted to ai_suggestions for record {record_id}")
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
                                title=f"{t.intervention}：{t.detail[:50]}",
                                content=t.detail,
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
