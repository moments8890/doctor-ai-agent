"""PII redaction in the Sentry / GlitchTip body-attachment hook.

Patient names, free-text clinical content, and credentials must not land
in error telemetry. The redactor walks request JSON and replaces values
of sensitive keys with "<redacted>" before the body is attached.
"""
from __future__ import annotations

import json

from app_middleware import _redact_pii_in_json


def test_top_level_keys_redacted() -> None:
    out = _redact_pii_in_json(json.dumps({
        "nickname": "alice",
        "passcode": "112233",
        "doctor_id": "inv_xyz",
    }))
    obj = json.loads(out)
    assert obj["nickname"] == "<redacted>"
    assert obj["passcode"] == "<redacted>"
    assert obj["doctor_id"] == "inv_xyz"  # not in redact list


def test_nested_keys_redacted() -> None:
    out = _redact_pii_in_json(json.dumps({
        "task": {"title": "follow-up", "notes": "patient reports headache"},
    }))
    obj = json.loads(out)
    assert obj["task"]["title"] == "follow-up"  # not in list
    assert obj["task"]["notes"] == "<redacted>"


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


def test_arrays_walked() -> None:
    out = _redact_pii_in_json(json.dumps({
        "messages": [
            {"role": "patient", "content": "I feel sick"},
            {"role": "doctor", "content": "Take rest"},
        ],
    }))
    obj = json.loads(out)
    assert obj["messages"][0]["content"] == "<redacted>"
    assert obj["messages"][0]["role"] == "patient"  # not redacted
    assert obj["messages"][1]["content"] == "<redacted>"


def test_case_insensitive_match() -> None:
    out = _redact_pii_in_json(json.dumps({"Name": "Bob", "PASSCODE": "1234"}))
    obj = json.loads(out)
    assert obj["Name"] == "<redacted>"
    assert obj["PASSCODE"] == "<redacted>"


def test_invalid_json_passes_through() -> None:
    """Non-JSON or malformed JSON returns unchanged so we don't break the
    error path. The 2KB truncation cap still applies upstream."""
    raw = "not json at all"
    assert _redact_pii_in_json(raw) == raw


def test_no_redaction_for_unknown_keys() -> None:
    out = _redact_pii_in_json(json.dumps({
        "doctor_id": "inv_xyz",
        "patient_id": 42,
        "task_type": "followup",
    }))
    obj = json.loads(out)
    assert obj == {"doctor_id": "inv_xyz", "patient_id": 42, "task_type": "followup"}
