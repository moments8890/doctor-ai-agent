"""Doctor interview endpoint contracts."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_first_turn_calls_endpoint_without_patient_name():
    """The endpoint no longer takes patient_name — it is extracted by the LLM.
    Verify the endpoint signature accepts the current parameters."""
    from channels.web.doctor_interview import interview_turn_endpoint
    import inspect
    sig = inspect.signature(interview_turn_endpoint)
    param_names = list(sig.parameters.keys())
    assert "patient_name" not in param_names
    assert "text" in param_names
    assert "session_id" in param_names
    assert "doctor_id" in param_names


@pytest.mark.asyncio
async def test_verify_session_wrong_doctor():
    from channels.web.doctor_interview import _verify_session
    from domain.patients.interview_session import InterviewSession

    mock_session = InterviewSession(
        id="s1", doctor_id="dr_other", patient_id=1, mode="doctor",
    )
    with patch("domain.patients.interview_session.load_session", new_callable=AsyncMock, return_value=mock_session):
        with pytest.raises(HTTPException) as exc:
            await _verify_session("s1", "dr_test")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_session_not_found():
    from channels.web.doctor_interview import _verify_session
    with patch("domain.patients.interview_session.load_session", new_callable=AsyncMock, return_value=None):
        with pytest.raises(HTTPException) as exc:
            await _verify_session("nonexistent", "dr_test")
    assert exc.value.status_code == 404


def test_build_clinical_text():
    from channels.web.doctor_interview import _build_clinical_text
    collected = {"chief_complaint": "头痛", "present_illness": "三天"}
    result = _build_clinical_text(collected)
    assert "主诉：头痛" in result
    assert "现病史：三天" in result


def test_compute_progress_incomplete():
    from channels.web.doctor_interview import _compute_progress
    collected = {"chief_complaint": "头痛"}
    result = _compute_progress(collected)
    assert result["progress"]["filled"] == 1
    assert result["status"] == "interviewing"
    assert len(result["missing"]) > 0


def test_compute_progress_complete():
    from channels.web.doctor_interview import _compute_progress
    # In doctor mode, recommended fields include physical_exam, diagnosis,
    # treatment_plan — so 6 subjective fields alone are not enough.
    # Provide all doctor-recommended fields to get ready_for_confirm.
    collected = {
        "chief_complaint": "头痛",
        "present_illness": "三天",
        "past_history": "无",
        "allergy_history": "无",
        "family_history": "无",
        "personal_history": "无",
        "physical_exam": "正常",
        "diagnosis": "偏头痛",
        "treatment_plan": "口服止痛药",
    }
    result = _compute_progress(collected)
    assert result["status"] == "ready_for_confirm"
    assert result["missing"] == []
