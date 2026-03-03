import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from utils.log import init_logging
from utils.app_config import AppConfig, load_env_from_shared_or_local

# Must run before any module reads os.environ.
_env_source_path = load_env_from_shared_or_local()
APP_CONFIG = AppConfig.from_env(env_source=str(_env_source_path))
init_logging()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

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

        client = AsyncOpenAI(
            base_url=config.ollama_base_url,
            api_key=config.ollama_api_key or "ollama",
        )
        model = config.ollama_model
        max_attempts = 3
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                )
                log.info(
                    f"Ollama startup connectivity check passed | "
                    f"base_url={config.ollama_base_url} model={model} attempt={attempt}"
                )
                break
            except Exception as e:
                last_error = e
                log.warning(
                    f"Ollama connectivity check failed | "
                    f"base_url={config.ollama_base_url} model={model} attempt={attempt}/{max_attempts} error={e}"
                )
                if attempt < max_attempts:
                    await asyncio.sleep(1)
        else:
            raise RuntimeError(
                f"Ollama startup connectivity check failed after {max_attempts} attempts "
                f"(base_url={config.ollama_base_url}, model={model})"
            ) from last_error


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
    return RedirectResponse(url="/docs")
