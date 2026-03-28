"""
Re-export hub for the diagnosis package.

Existing importers (e.g. ``from domain.diagnosis import run_diagnosis``) work
unchanged.  New code should import directly from:

- ``domain.diagnosis_models``   — Pydantic models & validation constants
- ``domain.diagnosis_pipeline`` — context loaders, LLM helpers, run_diagnosis
"""

from domain.diagnosis_models import (  # noqa: F401
    DiagnosisDifferential,
    DiagnosisWorkup,
    DiagnosisTreatment,
    DiagnosisLLMResponse,
    _VALID_CONFIDENCE,
    _VALID_URGENCY,
    _VALID_INTERVENTION,
    _MAX_ARRAY_ITEMS,
)

from domain.diagnosis_pipeline import (  # noqa: F401
    run_diagnosis,
    _resolve_provider,
    _structured_call_for_diagnosis,
    _try_cloud_fallback,
    _format_matched_cases,
    _row_to_result,
    _format_structured_fields,
    _build_user_message,
    _coerce_confidence,
    _coerce_urgency,
    _coerce_intervention,
    _validate_and_coerce_result,
    _load_clinical_context_from_record,
    _load_clinical_context_from_text,
)
