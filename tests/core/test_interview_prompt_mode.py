"""Interview prompt loading — mode-aware."""
import pytest
from unittest.mock import patch


def test_get_prompt_patient_mode():
    with patch("domain.patients.interview_turn.get_prompt_sync", return_value="patient prompt"):
        from domain.patients.interview_turn import _get_prompt
        result = _get_prompt("patient")
    assert result == "patient prompt"


def test_get_prompt_doctor_mode():
    with patch("domain.patients.interview_turn.get_prompt_sync", return_value="doctor prompt"):
        from domain.patients.interview_turn import _get_prompt
        result = _get_prompt("doctor")
    assert result == "doctor prompt"


def test_get_prompt_doctor_calls_correct_name():
    with patch("domain.patients.interview_turn.get_prompt_sync") as mock:
        mock.return_value = "test"
        from domain.patients.interview_turn import _get_prompt
        _get_prompt("doctor")
    mock.assert_called_with("doctor-interview")


def test_get_prompt_patient_calls_correct_name():
    with patch("domain.patients.interview_turn.get_prompt_sync") as mock:
        mock.return_value = "test"
        from domain.patients.interview_turn import _get_prompt
        _get_prompt("patient")
    mock.assert_called_with("patient-interview")
