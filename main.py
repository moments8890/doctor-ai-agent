import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()  # must run before any module reads os.environ

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from routers.records import router as records_router
from routers.wechat import router as wechat_router
from routers.ui import router as ui_router
from routers.neuro import router as neuro_router
from db.init_db import create_tables, seed_prompts
from db.engine import engine
from db.models import Patient, MedicalRecordDB, DoctorContext, SystemPrompt, NeuroCaseDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
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


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

async def _warmup():
    import os
    # Warm up jieba (builds prefix dict on first import)
    import jieba
    jieba.initialize()
    log = logging.getLogger("warmup")
    log.info("jieba initialised")

    # Warm up Ollama — ping the model so it's loaded into memory
    if os.environ.get("ROUTING_LLM") == "ollama" or os.environ.get("STRUCTURING_LLM") == "ollama":
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url="http://localhost:11434/v1",
                api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
            )
            model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
            await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            log.info(f"Ollama model '{model}' warmed up")
        except Exception as e:
            log.warning(f"Ollama warmup failed (is ollama running?): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await seed_prompts()
    await _warmup()
    yield


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

app.include_router(records_router)
app.include_router(wechat_router)
app.include_router(ui_router)
app.include_router(neuro_router)


@app.get("/")
def root():
    return RedirectResponse(url="/chat")
