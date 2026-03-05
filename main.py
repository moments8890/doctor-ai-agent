import logging
import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from utils.log import init_logging
from utils.app_config import AppConfig, load_env_from_shared_or_local, ollama_base_url_candidates

# Must run before any module reads os.environ.
_env_source_path = load_env_from_shared_or_local()
APP_CONFIG = AppConfig.from_env(env_source=str(_env_source_path))
init_logging()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import Response

from routers.records import router as records_router
from routers.wechat import router as wechat_router
from routers.ui import router as ui_router
from routers.neuro import router as neuro_router
from routers.tasks import router as tasks_router
from routers.voice import router as voice_router
from db.init_db import create_tables, seed_prompts
from db.engine import engine, AsyncSessionLocal
from db.models import Patient, MedicalRecordDB, DoctorContext, SystemPrompt, NeuroCaseDB, DoctorTask
from db.crud import get_due_tasks
from services.tasks import check_and_send_due_tasks
from services.observability import (
    add_trace,
    reset_current_span_id,
    reset_current_trace_id,
    set_current_span_id,
    set_current_trace_id,
)


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------

class PatientAdmin(ModelView, model=Patient):
    name = "Patient"
    name_plural = "Patients"
    icon = "fa-solid fa-user"
    column_list = [
        Patient.id,
        Patient.name,
        Patient.gender,
        Patient.year_of_birth,
        Patient.records,          # shows linked records count + clickable list
        Patient.doctor_id,
        Patient.created_at,
    ]
    column_searchable_list = [Patient.name, Patient.doctor_id]
    column_sortable_list = [Patient.id, Patient.name, Patient.created_at]
    column_default_sort = [(Patient.created_at, True)]


class MedicalRecordAdmin(ModelView, model=MedicalRecordDB):
    name = "Medical Record"
    name_plural = "Medical Records"
    icon = "fa-solid fa-file-medical"
    column_list = [
        MedicalRecordDB.id,
        MedicalRecordDB.patient,  # shows patient name as a link instead of raw id
        MedicalRecordDB.chief_complaint,
        MedicalRecordDB.diagnosis,
        MedicalRecordDB.treatment_plan,
        MedicalRecordDB.doctor_id,
        MedicalRecordDB.created_at,
    ]
    column_details_list = [
        MedicalRecordDB.id,
        MedicalRecordDB.patient,
        MedicalRecordDB.chief_complaint,
        MedicalRecordDB.history_of_present_illness,
        MedicalRecordDB.past_medical_history,
        MedicalRecordDB.physical_examination,
        MedicalRecordDB.auxiliary_examinations,
        MedicalRecordDB.diagnosis,
        MedicalRecordDB.treatment_plan,
        MedicalRecordDB.follow_up_plan,
        MedicalRecordDB.doctor_id,
        MedicalRecordDB.created_at,
    ]
    column_searchable_list = [MedicalRecordDB.chief_complaint, MedicalRecordDB.diagnosis]
    column_sortable_list = [MedicalRecordDB.id, MedicalRecordDB.created_at]
    column_default_sort = [(MedicalRecordDB.created_at, True)]


class SystemPromptAdmin(ModelView, model=SystemPrompt):
    name = "System Prompt"
    name_plural = "System Prompts"
    icon = "fa-solid fa-wand-magic-sparkles"
    column_list = [SystemPrompt.key, SystemPrompt.updated_at]
    column_details_list = [SystemPrompt.key, SystemPrompt.content, SystemPrompt.updated_at]
    form_include_pk = True          # allow setting the key on create
    column_sortable_list = [SystemPrompt.updated_at]


class DoctorContextAdmin(ModelView, model=DoctorContext):
    name = "Doctor Context"
    name_plural = "Doctor Contexts"
    icon = "fa-solid fa-brain"
    column_list = [
        DoctorContext.doctor_id,
        DoctorContext.summary,
        DoctorContext.updated_at,
    ]
    column_details_list = [
        DoctorContext.doctor_id,
        DoctorContext.summary,
        DoctorContext.updated_at,
    ]
    column_searchable_list = [DoctorContext.doctor_id]
    column_sortable_list = [DoctorContext.updated_at]
    column_default_sort = [(DoctorContext.updated_at, True)]


class NeuroCaseAdmin(ModelView, model=NeuroCaseDB):
    name = "Neuro Case"
    name_plural = "Neuro Cases"
    icon = "fa-solid fa-brain-circuit"
    column_list = [
        NeuroCaseDB.id,
        NeuroCaseDB.patient_name,
        NeuroCaseDB.chief_complaint,
        NeuroCaseDB.primary_diagnosis,
        NeuroCaseDB.nihss,
        NeuroCaseDB.doctor_id,
        NeuroCaseDB.created_at,
    ]
    column_details_list = [
        NeuroCaseDB.id,
        NeuroCaseDB.patient_name,
        NeuroCaseDB.gender,
        NeuroCaseDB.age,
        NeuroCaseDB.encounter_type,
        NeuroCaseDB.chief_complaint,
        NeuroCaseDB.primary_diagnosis,
        NeuroCaseDB.nihss,
        NeuroCaseDB.raw_json,
        NeuroCaseDB.extraction_log_json,
        NeuroCaseDB.doctor_id,
        NeuroCaseDB.created_at,
    ]
    column_searchable_list = [NeuroCaseDB.patient_name, NeuroCaseDB.primary_diagnosis]
    column_sortable_list = [NeuroCaseDB.id, NeuroCaseDB.created_at]
    column_default_sort = [(NeuroCaseDB.created_at, True)]


class DoctorTaskAdmin(ModelView, model=DoctorTask):
    name = "Doctor Task"
    name_plural = "Doctor Tasks"
    icon = "fa-solid fa-list-check"
    column_list = [
        DoctorTask.id,
        DoctorTask.doctor_id,
        DoctorTask.task_type,
        DoctorTask.title,
        DoctorTask.status,
        DoctorTask.due_at,
        DoctorTask.created_at,
    ]
    column_searchable_list = [DoctorTask.doctor_id, DoctorTask.title]
    column_sortable_list = [DoctorTask.id, DoctorTask.due_at, DoctorTask.created_at]
    column_default_sort = [(DoctorTask.created_at, True)]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

async def _warmup(config: AppConfig):
    # Warm up jieba (builds prefix dict on first import)
    import jieba
    jieba.initialize()
    log = logging.getLogger("warmup")
    log.info("jieba initialised")

    # Verify/warm up Ollama — ping the model so it's loaded into memory.
    if config.routing_llm == "ollama" or config.structuring_llm == "ollama":
        from openai import AsyncOpenAI

        model = config.ollama_model
        max_attempts = 3
        candidates = ollama_base_url_candidates(config.ollama_base_url)
        chosen_url = None
        last_error = None

        for candidate_url in candidates:
            client = AsyncOpenAI(
                base_url=candidate_url,
                api_key=config.ollama_api_key or "ollama",
            )
            for attempt in range(1, max_attempts + 1):
                try:
                    await client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=1,
                    )
                    chosen_url = candidate_url
                    break
                except Exception as e:
                    last_error = e
                    if _is_connectivity_error(e):
                        log.warning(
                            f"Ollama connectivity check failed | "
                            f"base_url={candidate_url} model={model} attempt={attempt}/{max_attempts} error={e}"
                        )
                    else:
                        raise RuntimeError(
                            f"Ollama startup warmup failed with non-connectivity error "
                            f"(base_url={candidate_url}, model={model}): {e}"
                        ) from e
                    if attempt < max_attempts:
                        await asyncio.sleep(1)
            if chosen_url:
                break

        if chosen_url:
            if chosen_url != config.ollama_base_url:
                os.environ["OLLAMA_BASE_URL"] = chosen_url
                if os.environ.get("OLLAMA_VISION_BASE_URL", "").strip() == config.ollama_base_url:
                    os.environ["OLLAMA_VISION_BASE_URL"] = chosen_url
                log.warning(
                    f"Ollama startup fallback selected | original_base_url={config.ollama_base_url} "
                    f"effective_base_url={chosen_url} model={model}"
                )
            else:
                log.info(
                    f"Ollama startup connectivity check passed | "
                    f"base_url={chosen_url} model={model}"
                )
        else:
            # Keep startup alive; runtime calls can still fallback or fail with explicit errors.
            log.error(
                f"Ollama unavailable on startup | attempted_base_urls={candidates} "
                f"model={model} error={last_error}. Continuing without warmup."
            )


def _is_connectivity_error(exc: Exception) -> bool:
    """True when warmup failure indicates endpoint connectivity issues."""
    try:
        from openai import APIConnectionError, APITimeoutError
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return True
    except Exception:
        pass
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


_scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup_log = logging.getLogger("startup")
    _startup_log.info("[Config] loaded environment\n%s", APP_CONFIG.to_pretty_log())
    await create_tables()
    await seed_prompts()
    await _warmup(APP_CONFIG)

    # Log pending unnotified tasks on startup
    try:
        async with AsyncSessionLocal() as _session:
            _pending = await get_due_tasks(_session, datetime.utcnow())
            _startup_log.info(f"[Tasks] {len(_pending)} pending unnotified task(s) at startup")
    except Exception as _e:
        _startup_log.warning(f"[Tasks] startup task count failed: {_e}")

    _scheduler.add_job(check_and_send_due_tasks, "interval", minutes=1)
    _scheduler.start()
    yield
    _scheduler.shutdown()


app = FastAPI(
    title="专科医师AI智能体",
    description="Phase 2 MVP — 患者管理 + 语音/文字录入 → 结构化病历生成",
    version="0.2.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def trace_requests_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    trace_token = set_current_trace_id(trace_id)
    span_token = set_current_span_id(None)
    started_at = datetime.utcnow()
    start_clock = time.perf_counter()

    try:
        try:
            response = await call_next(request)
            status_code = int(getattr(response, "status_code", 200))
        except Exception:
            latency_ms = (time.perf_counter() - start_clock) * 1000.0
            add_trace(
                trace_id=trace_id,
                started_at=started_at,
                method=request.method,
                path=request.url.path,
                status_code=500,
                latency_ms=latency_ms,
            )
            raise

        latency_ms = (time.perf_counter() - start_clock) * 1000.0
        add_trace(
            trace_id=trace_id,
            started_at=started_at,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            latency_ms=latency_ms,
        )
        if isinstance(response, Response):
            response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        reset_current_span_id(span_token)
        reset_current_trace_id(trace_token)


admin = Admin(app, engine, title="DB Admin")
admin.add_view(SystemPromptAdmin)
admin.add_view(PatientAdmin)
admin.add_view(MedicalRecordAdmin)
admin.add_view(DoctorContextAdmin)
admin.add_view(NeuroCaseAdmin)
admin.add_view(DoctorTaskAdmin)

app.include_router(records_router)
app.include_router(wechat_router)
app.include_router(ui_router)
app.include_router(neuro_router)
app.include_router(tasks_router)
app.include_router(voice_router)


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}
