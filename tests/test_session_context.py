"""Tests for services/session.py — in-memory only, no mocking needed.

Verifies that:
- Each doctor gets an independent session
- push_turn accumulates history in the correct order
- set_current_patient / clear_current_patient update state
- Switching patients replaces context without wiping history
- pending_create state transitions work
- last_active timestamp is refreshed on push_turn
"""

import time
import pytest
import services.session as sess_mod
from services.session import (
    get_session,
    push_turn,
    set_current_patient,
    clear_current_patient,
    set_pending_create,
    clear_pending_create,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOCTOR_A = "doctor_001"
DOCTOR_B = "doctor_002"


# ---------------------------------------------------------------------------
# Session creation & isolation
# ---------------------------------------------------------------------------


def test_get_session_creates_new_session():
    sess = get_session(DOCTOR_A)
    assert sess is not None
    assert sess.conversation_history == []
    assert sess.current_patient_id is None
    assert sess.current_patient_name is None


def test_get_session_returns_same_object_for_same_doctor():
    s1 = get_session(DOCTOR_A)
    s2 = get_session(DOCTOR_A)
    assert s1 is s2


def test_two_doctors_have_independent_sessions():
    sa = get_session(DOCTOR_A)
    sb = get_session(DOCTOR_B)
    assert sa is not sb


def test_two_doctors_patient_contexts_are_independent():
    set_current_patient(DOCTOR_A, patient_id=1, name="张三")
    set_current_patient(DOCTOR_B, patient_id=2, name="李四")

    assert get_session(DOCTOR_A).current_patient_name == "张三"
    assert get_session(DOCTOR_B).current_patient_name == "李四"

    # Clearing A does not affect B
    clear_current_patient(DOCTOR_A)
    assert get_session(DOCTOR_A).current_patient_name is None
    assert get_session(DOCTOR_B).current_patient_name == "李四"


# ---------------------------------------------------------------------------
# push_turn — history accumulation
# ---------------------------------------------------------------------------


def test_push_turn_adds_two_messages():
    push_turn(DOCTOR_A, "患者头痛", "已记录")
    history = get_session(DOCTOR_A).conversation_history
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "患者头痛"}
    assert history[1] == {"role": "assistant", "content": "已记录"}


def test_push_turn_accumulates_across_multiple_calls():
    push_turn(DOCTOR_A, "第一条", "回复一")
    push_turn(DOCTOR_A, "第二条", "回复二")
    push_turn(DOCTOR_A, "第三条", "回复三")
    history = get_session(DOCTOR_A).conversation_history
    assert len(history) == 6
    assert history[0]["content"] == "第一条"
    assert history[2]["content"] == "第二条"
    assert history[4]["content"] == "第三条"


def test_push_turn_updates_last_active():
    before = time.time()
    push_turn(DOCTOR_A, "消息", "回复")
    after = time.time()
    ts = get_session(DOCTOR_A).last_active
    assert before <= ts <= after


def test_push_turn_order_is_user_then_assistant():
    push_turn(DOCTOR_A, "医生输入", "助手回复")
    history = get_session(DOCTOR_A).conversation_history
    # last two messages
    user_msg = history[-2]
    asst_msg = history[-1]
    assert user_msg["role"] == "user"
    assert asst_msg["role"] == "assistant"


# ---------------------------------------------------------------------------
# set_current_patient / switch / clear
# ---------------------------------------------------------------------------


def test_set_current_patient_stores_id_and_name():
    set_current_patient(DOCTOR_A, patient_id=42, name="贺志强")
    sess = get_session(DOCTOR_A)
    assert sess.current_patient_id == 42
    assert sess.current_patient_name == "贺志强"


def test_switching_patient_replaces_previous_context():
    set_current_patient(DOCTOR_A, patient_id=1, name="患者甲")
    set_current_patient(DOCTOR_A, patient_id=2, name="患者乙")
    sess = get_session(DOCTOR_A)
    assert sess.current_patient_id == 2
    assert sess.current_patient_name == "患者乙"


def test_history_is_preserved_when_switching_patients():
    """Switching the active patient must not wipe conversation history."""
    push_turn(DOCTOR_A, "患者甲主诉头痛", "已记录")
    set_current_patient(DOCTOR_A, patient_id=1, name="患者甲")

    push_turn(DOCTOR_A, "现在看患者乙", "已切换")
    set_current_patient(DOCTOR_A, patient_id=2, name="患者乙")

    history = get_session(DOCTOR_A).conversation_history
    # Both turns should still be in history
    assert len(history) == 4
    assert history[0]["content"] == "患者甲主诉头痛"
    assert history[2]["content"] == "现在看患者乙"


def test_clear_current_patient_sets_both_fields_to_none():
    set_current_patient(DOCTOR_A, patient_id=5, name="韩伟")
    clear_current_patient(DOCTOR_A)
    sess = get_session(DOCTOR_A)
    assert sess.current_patient_id is None
    assert sess.current_patient_name is None


def test_clear_current_patient_does_not_wipe_history():
    push_turn(DOCTOR_A, "记录一下胸痛", "已记录")
    set_current_patient(DOCTOR_A, patient_id=3, name="患者丙")
    clear_current_patient(DOCTOR_A)
    assert len(get_session(DOCTOR_A).conversation_history) == 2


# ---------------------------------------------------------------------------
# pending_create state
# ---------------------------------------------------------------------------


def test_set_pending_create_stores_name():
    set_pending_create(DOCTOR_A, "新患者陈红")
    assert get_session(DOCTOR_A).pending_create_name == "新患者陈红"


def test_clear_pending_create_removes_name():
    set_pending_create(DOCTOR_A, "临时患者")
    clear_pending_create(DOCTOR_A)
    assert get_session(DOCTOR_A).pending_create_name is None


def test_pending_create_independent_between_doctors():
    set_pending_create(DOCTOR_A, "甲患者")
    # DOCTOR_B never had pending create set
    assert get_session(DOCTOR_B).pending_create_name is None
