from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.auth.miniprogram_auth import MiniProgramAuthError
from services.auth.request_auth import require_admin_token, resolve_doctor_id_from_auth_or_fallback


def test_resolve_doctor_id_prefers_token_principal() -> None:
    with patch("services.auth.request_auth.parse_bearer_token", return_value="tok"), \
         patch("services.auth.request_auth.verify_miniprogram_token", return_value=SimpleNamespace(doctor_id="doc_from_token")):
        got = resolve_doctor_id_from_auth_or_fallback(
            "body_doc",
            "Bearer abc",
            fallback_env_flag="ANY_FALLBACK_FLAG",
            default_doctor_id="default_doc",
        )

    assert got == "doc_from_token"


def test_resolve_doctor_id_invalid_token_returns_401() -> None:
    with patch("services.auth.request_auth.parse_bearer_token", side_effect=MiniProgramAuthError("bad token")):
        with pytest.raises(HTTPException) as exc_info:
            resolve_doctor_id_from_auth_or_fallback(
                "body_doc",
                "Bearer bad",
                fallback_env_flag="ANY_FALLBACK_FLAG",
                default_doctor_id="default_doc",
            )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid authorization token"


def test_resolve_doctor_id_uses_candidate_when_fallback_enabled() -> None:
    with patch.dict("os.environ", {"ALLOW_X": "true"}, clear=True), \
         patch("services.auth.request_auth.logging.getLogger") as get_logger:
        got = resolve_doctor_id_from_auth_or_fallback(
            "body_doc",
            None,
            fallback_env_flag="ALLOW_X",
            default_doctor_id="default_doc",
        )

    assert got == "body_doc"
    get_logger.return_value.warning.assert_called_once()


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


def test_require_admin_token_allows_when_value_matches() -> None:
    with patch.dict("os.environ", {"UI_ADMIN_TOKEN": "secret-token"}, clear=True):
        require_admin_token("secret-token", env_name="UI_ADMIN_TOKEN")


def test_require_admin_token_rejects_when_mismatch() -> None:
    with patch.dict("os.environ", {"UI_ADMIN_TOKEN": "secret-token"}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            require_admin_token("wrong-token", env_name="UI_ADMIN_TOKEN")

    assert exc_info.value.status_code == 403


def test_require_admin_token_rejects_when_not_configured() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            require_admin_token("anything", env_name="UI_ADMIN_TOKEN")

    assert exc_info.value.status_code == 503


def test_require_admin_token_skips_check_in_pytest_context() -> None:
    with patch.dict("os.environ", {"PYTEST_CURRENT_TEST": "x", "UI_ADMIN_TOKEN": "secret-token"}, clear=True):
        require_admin_token(None, env_name="UI_ADMIN_TOKEN")
