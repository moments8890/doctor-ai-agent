"""PII redaction in the Sentry / GlitchTip body-attachment hook.

Patient names, free-text clinical content, and credentials must not land
in error telemetry. The redactor walks request JSON and replaces values
of sensitive keys with "<redacted>" before the body is attached.
"""
from __future__ import annotations

import json

from app_middleware import _redact_pii_in_json


def test_unknown_keys_redacted_by_default() -> None:
    """Allowlist semantics: anything not on _EXC_BODY_SAFE_KEYS is redacted."""
    out = _redact_pii_in_json(json.dumps({
        "nickname": "alice",
        "passcode": "112233",
        "doctor_id": "inv_xyz",
    }))
    obj = json.loads(out)
    assert obj["nickname"] == "<redacted>"
    assert obj["passcode"] == "<redacted>"
    assert obj["doctor_id"] == "inv_xyz"  # synthetic ID — on allowlist


def test_nested_user_content_redacted() -> None:
    out = _redact_pii_in_json(json.dumps({
        "task": {"title": "follow-up", "notes": "patient reports headache"},
    }))
    obj = json.loads(out)
    # "task" is not safe — its whole value is redacted at the outer level.
    assert obj["task"] == "<redacted>"


def test_clinical_content_redacted() -> None:
    out = _redact_pii_in_json(json.dumps({
        "chief_complaint": "headache for 3 days",
        "diagnosis": "tension-type headache",
        "key_symptoms": "throbbing, photophobia",
    }))
    obj = json.loads(out)
    assert obj["chief_complaint"] == "<redacted>"
    assert obj["diagnosis"] == "<redacted>"
    assert obj["key_symptoms"] == "<redacted>"


def test_safe_keys_recurse_into_nested_dicts() -> None:
    """A safe key keeps its value, but if that value is a dict, the inner
    keys are still allowlist-checked."""
    out = _redact_pii_in_json(json.dumps({
        "status": {"ok": True, "secret": "should-redact"},
    }))
    obj = json.loads(out)
    assert obj["status"]["ok"] is True
    assert obj["status"]["secret"] == "<redacted>"


def test_case_insensitive_match() -> None:
    out = _redact_pii_in_json(json.dumps({"DOCTOR_ID": "inv_xyz", "PASSCODE": "1234"}))
    obj = json.loads(out)
    assert obj["DOCTOR_ID"] == "inv_xyz"  # case-insensitive allowlist hit
    assert obj["PASSCODE"] == "<redacted>"


def test_invalid_json_passes_through() -> None:
    """Non-JSON or malformed JSON returns unchanged so we don't break the
    error path. The 2KB truncation cap still applies upstream."""
    raw = "not json at all"
    assert _redact_pii_in_json(raw) == raw


def test_safe_synthetic_ids_retained() -> None:
    out = _redact_pii_in_json(json.dumps({
        "doctor_id": "inv_xyz",
        "patient_id": 42,
        "task_id": 7,
    }))
    obj = json.loads(out)
    assert obj == {"doctor_id": "inv_xyz", "patient_id": 42, "task_id": 7}


def test_credentials_shaped_keys_redacted() -> None:
    """N3 — keys that LOOK like IDs but actually carry credentials must
    not slip through the allowlist. invite_code mints doctor accounts;
    session_id / access_code are auth handles."""
    out = _redact_pii_in_json(json.dumps({
        "invite_code": "WELCOME",
        "session_id": "abc123",
        "access_code": "482901",
    }))
    obj = json.loads(out)
    assert obj["invite_code"] == "<redacted>"
    assert obj["session_id"] == "<redacted>"
    assert obj["access_code"] == "<redacted>"
