"""
管理后台配置与可观测性端点：runtime config、可观测性、隧道 URL、过滤选项和关键词管理。
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import (
    Doctor,
    DoctorContext,
    DoctorTask,
    MedicalRecordDB,
    Patient,
    PatientLabel,
)
from services.observability.observability import (
    clear_traces,
    get_latency_summary_scoped,
    get_recent_spans_scoped,
    get_recent_traces_scoped,
    get_slowest_spans_scoped,
    get_trace_timeline,
)
from utils.runtime_config import (
    apply_runtime_config,
    load_runtime_config_dict,
    runtime_config_categories,
    runtime_config_source_path,
    save_runtime_config_dict,
    validate_runtime_config,
)
from channels.web.ui._utils import (
    _extract_tunnel_url_from_log,
    _normalize_query_str,
    _require_ui_admin_access,
    apply_exclude_test_doctors,
)
from channels.web.ui.admin_handlers import admin_seed_samples_logic as _admin_seed_samples_logic

router = APIRouter(tags=["ui"], include_in_schema=False)


class RuntimeConfigUpdate(BaseModel):
    config: dict


@router.get("/api/admin/observability")
async def admin_observability(
    trace_limit: int = 100,
    summary_limit: int = 500,
    span_limit: int = 200,
    slow_span_limit: int = 30,
    scope: str = "all",
    trace_id: str | None = None,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    safe_scope = scope if scope in {"all", "public", "internal"} else "all"
    payload = {
        "scope": safe_scope,
        "summary": get_latency_summary_scoped(limit=summary_limit, scope=safe_scope),
        "recent_traces": get_recent_traces_scoped(limit=trace_limit, scope=safe_scope),
        "recent_spans": get_recent_spans_scoped(limit=span_limit, trace_id=trace_id, scope=safe_scope),
        "slow_spans": get_slowest_spans_scoped(limit=slow_span_limit, scope=safe_scope),
        "split": {
            "public": get_latency_summary_scoped(limit=summary_limit, scope="public"),
            "internal": get_latency_summary_scoped(limit=summary_limit, scope="internal"),
        },
    }
    if trace_id:
        payload["trace_timeline"] = get_trace_timeline(trace_id=trace_id, limit=span_limit)
    return payload


@router.delete("/api/admin/observability/traces")
async def admin_clear_observability_traces(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    clear_traces()
    return {"ok": True}


@router.get("/api/admin/routing-metrics")
async def admin_routing_metrics(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Fast-router vs LLM hit counts since last process start."""
    _require_ui_admin_access(x_admin_token)
    from services.observability.routing_metrics import get_metrics
    return get_metrics()


@router.post("/api/admin/routing-metrics/reset")
async def admin_routing_metrics_reset(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Reset routing counters to zero."""
    _require_ui_admin_access(x_admin_token)
    from services.observability.routing_metrics import reset
    reset()
    return {"ok": True}


@router.post("/api/admin/observability/sample")
async def admin_seed_observability_samples(
    count: int = Query(default=3, ge=1, le=20),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    return await _admin_seed_samples_logic(count)


@router.get("/api/admin/config")
async def admin_get_runtime_config(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    config = await load_runtime_config_dict()
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(config)
    return {"source": source, "config": config, "categories": categories}


@router.put("/api/admin/config")
async def admin_update_runtime_config(
    body: RuntimeConfigUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    if not isinstance(body.config, dict):
        raise HTTPException(status_code=400, detail="config must be a JSON object")
    saved = await save_runtime_config_dict(body.config)
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(saved)
    return {"ok": True, "applied": False, "source": source, "config": saved, "categories": categories}


@router.post("/api/admin/config/verify")
async def admin_verify_runtime_config(
    body: RuntimeConfigUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    result = validate_runtime_config(body.config)
    categories = runtime_config_categories(result.get("sanitized", {}))
    return {
        "ok": result.get("ok", False),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
        "config": result.get("sanitized", {}),
        "categories": categories,
    }


@router.post("/api/admin/config/apply")
async def admin_apply_runtime_config(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    saved = await load_runtime_config_dict()
    await apply_runtime_config(saved)
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(saved)
    return {"ok": True, "applied": True, "source": source, "config": saved, "categories": categories}


@router.get("/api/admin/dev/tunnel-url")
async def admin_get_tunnel_url(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    _app_root = Path(__file__).resolve().parents[3]  # src/routers/ui/ → project root
    log_path_raw = (
        os.environ.get("CLOUDFLARED_LOG_PATH")
        or os.environ.get("TUNNEL_LOG_PATH")
        or str(_app_root / "logs" / "tunnel.log")
    )
    log_path = Path(log_path_raw).expanduser()
    if not log_path.exists():
        return {"ok": False, "url": None, "source": str(log_path), "detail": "log file not found"}
    try:
        content = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return {"ok": False, "url": None, "source": str(log_path), "detail": "read failed"}
    url = _extract_tunnel_url_from_log(content)
    mtime = datetime.fromtimestamp(log_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "ok": bool(url),
        "url": url,
        "source": str(log_path),
        "updated_at": mtime,
        "detail": None if url else "no public tunnel url found in log",
    }


@router.get("/api/admin/filter-options")
async def admin_filter_options(
    doctor_id: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    doctor_id = _normalize_query_str(doctor_id)

    async with AsyncSessionLocal() as db:
        doctor_candidates: set[str] = set()
        doctor_sources = [
            Doctor.doctor_id,
            Patient.doctor_id,
            MedicalRecordDB.doctor_id,
            DoctorTask.doctor_id,
            DoctorContext.doctor_id,
            PatientLabel.doctor_id,
        ]
        for col in doctor_sources:
            stmt = select(col).where(col.is_not(None))
            stmt = apply_exclude_test_doctors(stmt, col)
            rows = (await db.execute(stmt)).scalars().all()
            for value in rows:
                if isinstance(value, str) and value.strip():
                    doctor_candidates.add(value.strip())

        patient_stmt = select(Patient.name).where(Patient.name.is_not(None))
        if doctor_id:
            patient_stmt = patient_stmt.where(Patient.doctor_id == doctor_id)
        else:
            patient_stmt = apply_exclude_test_doctors(patient_stmt, Patient.doctor_id)
        patient_rows = (await db.execute(patient_stmt)).scalars().all()

    return {
        "doctor_ids": sorted(doctor_candidates),
        "patient_names": sorted({p.strip() for p in patient_rows if isinstance(p, str) and p.strip()}),
        "selected_doctor_id": doctor_id,
    }


@router.get("/api/admin/fast-router/keywords")
async def admin_get_keywords(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Removed — fast router replaced by ADR 0011 conversation model."""
    _require_ui_admin_access(x_admin_token)
    return {"note": "Fast router removed. Conversation model handles intent classification (ADR 0011)."}
