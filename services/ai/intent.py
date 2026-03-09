"""
意图枚举定义及基于 LLM 的意图识别（作为快速路由的兜底）。
"""

from __future__ import annotations

import json
import os
from enum import Enum
from typing import Optional
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from services.ai.llm_resilience import call_with_retry_and_fallback
from utils.log import log

_PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
    "ollama": {
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key_env": "OLLAMA_API_KEY",
        "model": "qwen2.5:14b",
    },
    "tencent_lkeap": {
        "base_url": os.environ.get("TENCENT_LKEAP_BASE_URL", "https://api.lkeap.cloud.tencent.com/v1"),
        "api_key_env": "TENCENT_LKEAP_API_KEY",
        "model": os.environ.get("TENCENT_LKEAP_MODEL", "deepseek-v3-1"),
    },
}

SYSTEM_PROMPT = (
    "你是医生助手意图识别器。分析消息并输出JSON，字段：\n"
    "- intent: 必填，值为 create_patient / add_record / query_records / list_patients / "
    "import_history / delete_patient / list_tasks / complete_task / schedule_appointment / "
    "unknown\n"
    "- patient_name: 提到的患者姓名（字符串或null）\n"
    "- gender: 性别，男/女 或 null\n"
    "- age: 年龄数字或null\n\n"
    "规则：\n"
    "- 建档/新患者/新病人 → create_patient\n"
    "- 病历记录/症状/诊断/治疗 → add_record\n"
    "- 查询/历史记录/看一下 → query_records\n"
    "- 所有患者/患者列表 → list_patients\n"
    "- 历史病历导入/多次就诊记录/PDF病历/Word文件病历 → import_history\n"
    "- 删除患者/移除病人 → delete_patient\n"
    "- 任务/待办/提醒 → list_tasks\n"
    "- 完成任务+编号 → complete_task\n"
    "- 预约/安排复诊+时间 → schedule_appointment\n"
    "- 其他 → unknown\n"
    "只输出JSON，不要解释。"
)


class Intent(str, Enum):
    create_patient = "create_patient"
    add_record = "add_record"
    update_record = "update_record"          # correct / overwrite fields in latest record
    update_patient = "update_patient"        # update patient demographics (gender / age)
    query_records = "query_records"
    list_patients = "list_patients"
    import_history = "import_history"
    delete_patient = "delete_patient"
    list_tasks = "list_tasks"
    complete_task = "complete_task"
    schedule_appointment = "schedule_appointment"
    export_records = "export_records"
    export_outpatient_report = "export_outpatient_report"
    schedule_follow_up = "schedule_follow_up"   # standalone follow-up task without a record
    postpone_task = "postpone_task"             # push a task's due date forward
    cancel_task = "cancel_task"                 # cancel a pending task
    unknown = "unknown"


class IntentResult(BaseModel):
    intent: Intent
    patient_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    is_emergency: bool = False
    extra_data: dict = Field(default_factory=dict)
    chat_reply: Optional[str] = None
    structured_fields: Optional[dict] = None  # 8 clinical fields from single LLM call
    confidence: float = 1.0  # 1.0 = high-confidence rule/LLM; 0.8 = Tier-3 keyword match


async def detect_intent(text: str) -> IntentResult:
    intent_provider = os.environ.get("INTENT_PROVIDER", "local")

    provider = _PROVIDERS[intent_provider]
    log(f"[Intent:{intent_provider}] detecting: {text[:80]}")
    extra_headers = {"anthropic-version": "2023-06-01"} if intent_provider == "claude" else {}
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        timeout=float(os.environ.get("INTENT_LLM_TIMEOUT", "30")),
        max_retries=0,
        default_headers=extra_headers,
    )

    async def _call(model_name: str):
        return await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0,
        )

    fallback_model = None
    if intent_provider == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    completion = await call_with_retry_and_fallback(
        _call,
        primary_model=provider["model"],
        fallback_model=fallback_model,
        max_attempts=int(os.environ.get("INTENT_LLM_ATTEMPTS", "3")),
        op_name="intent.chat_completion",
    )
    raw = completion.choices[0].message.content
    log(f"[Intent:{intent_provider}] result: {raw}")
    data = json.loads(raw)
    return IntentResult.model_validate(data)
