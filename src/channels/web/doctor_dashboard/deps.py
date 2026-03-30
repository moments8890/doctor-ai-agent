"""Auth / session dependency helpers for the doctor dashboard."""

from __future__ import annotations

from infra.auth.request_auth import require_admin_token, resolve_doctor_id_from_auth_or_fallback


def _resolve_ui_doctor_id(candidate_doctor_id: str | None, authorization: str | None) -> str:
    return resolve_doctor_id_from_auth_or_fallback(
        candidate_doctor_id,
        authorization,
        fallback_env_flag="UI_ALLOW_QUERY_DOCTOR_ID",
        default_doctor_id="web_doctor",
    )


def _require_ui_admin_access(x_admin_token: str | None) -> None:
    require_admin_token(x_admin_token, env_name="UI_ADMIN_TOKEN")


def _require_ui_debug_access(x_debug_token: str | None) -> None:
    require_admin_token(x_debug_token, env_name="UI_DEBUG_TOKEN")
