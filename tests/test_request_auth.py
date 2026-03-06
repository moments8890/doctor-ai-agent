from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.miniprogram_auth import MiniProgramAuthError
from services.request_auth import resolve_doctor_id_from_auth_or_fallback


def test_resolve_doctor_id_prefers_token_principal() -> None:
    with patch("services.request_auth.parse_bearer_token", return_value="tok"), \
         patch("services.request_auth.verify_miniprogram_token", return_value=SimpleNamespace(doctor_id="doc_from_token")):
        got = resolve_doctor_id_from_auth_or_fallback(
            "body_doc",
            "Bearer abc",
            fallback_env_flag="ANY_FALLBACK_FLAG",
            default_doctor_id="default_doc",
        )

    assert got == "doc_from_token"


def test_resolve_doctor_id_invalid_token_returns_401() -> None:
    with patch("services.request_auth.parse_bearer_token", side_effect=MiniProgramAuthError("bad token")):
        with pytest.raises(HTTPException) as exc_info:
            resolve_doctor_id_from_auth_or_fallback(
                "body_doc",
                "Bearer bad",
                fallback_env_flag="ANY_FALLBACK_FLAG",
                default_doctor_id="default_doc",
            )

    assert exc_info.value.status_code == 401


def test_resolve_doctor_id_uses_candidate_when_fallback_enabled() -> None:
    with patch.dict("os.environ", {"ALLOW_X": "true"}, clear=True):
        got = resolve_doctor_id_from_auth_or_fallback(
            "body_doc",
            None,
            fallback_env_flag="ALLOW_X",
            default_doctor_id="default_doc",
        )

    assert got == "body_doc"


def test_resolve_doctor_id_uses_default_when_candidate_empty_and_fallback_enabled() -> None:
    with patch.dict("os.environ", {"ALLOW_X": "1"}, clear=True):
        got = resolve_doctor_id_from_auth_or_fallback(
            "",
            None,
            fallback_env_flag="ALLOW_X",
            default_doctor_id="default_doc",
        )

    assert got == "default_doc"


def test_resolve_doctor_id_missing_auth_and_fallback_disabled_returns_401() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            resolve_doctor_id_from_auth_or_fallback(
                "body_doc",
                None,
                fallback_env_flag="ALLOW_X",
                default_doctor_id="default_doc",
            )

    assert exc_info.value.status_code == 401
