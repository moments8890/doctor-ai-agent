"""Tests for services/session.py — pure in-memory, no async needed."""
import pytest
from services.session import get_session, set_current_patient, clear_current_patient, DoctorSession

DOCTOR = "doc_001"
OTHER = "doc_002"


def test_get_session_creates_empty_session():
    sess = get_session(DOCTOR)
    assert isinstance(sess, DoctorSession)
    assert sess.current_patient_id is None
    assert sess.current_patient_name is None


def test_get_session_returns_same_object_on_repeat_call():
    sess1 = get_session(DOCTOR)
    sess2 = get_session(DOCTOR)
    assert sess1 is sess2


def test_set_current_patient_updates_session():
    set_current_patient(DOCTOR, patient_id=42, name="李明")
    sess = get_session(DOCTOR)
    assert sess.current_patient_id == 42
    assert sess.current_patient_name == "李明"


def test_clear_current_patient_resets_to_none():
    set_current_patient(DOCTOR, patient_id=42, name="李明")
    clear_current_patient(DOCTOR)
    sess = get_session(DOCTOR)
    assert sess.current_patient_id is None
    assert sess.current_patient_name is None


def test_sessions_are_isolated_per_doctor():
    set_current_patient(DOCTOR, patient_id=1, name="李明")
    set_current_patient(OTHER, patient_id=2, name="张三")

    assert get_session(DOCTOR).current_patient_id == 1
    assert get_session(OTHER).current_patient_id == 2


def test_clear_one_doctor_does_not_affect_another():
    set_current_patient(DOCTOR, patient_id=1, name="李明")
    set_current_patient(OTHER, patient_id=2, name="张三")
    clear_current_patient(DOCTOR)

    assert get_session(DOCTOR).current_patient_id is None
    assert get_session(OTHER).current_patient_id == 2


def test_set_current_patient_overwrites_previous():
    set_current_patient(DOCTOR, patient_id=1, name="李明")
    set_current_patient(DOCTOR, patient_id=99, name="王五")
    sess = get_session(DOCTOR)
    assert sess.current_patient_id == 99
    assert sess.current_patient_name == "王五"
