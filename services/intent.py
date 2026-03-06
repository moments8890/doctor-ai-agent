import json
import os
from enum import Enum
from typing import Optional
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
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
}

SYSTEM_PROMPT = (
    "你是医生助手意图识别器。分析消息并输出JSON，字段：\n"
    "- intent: 必填，值为 create_patient / add_record / query_records / list_patients / delete_patient / unknown\n"
    "- patient_name: 提到的患者姓名（字符串或null）\n"
    "- gender: 性别，男/女 或 null\n"
    "- age: 年龄数字或null\n\n"
    "规则：\n"
    "- 建档/新患者/新病人 → create_patient\n"
    "- 病历记录/症状/诊断/治疗 → add_record\n"
    "- 查询/历史记录/看一下 → query_records\n"
    "- 所有患者/患者列表 → list_patients\n"
    "- 删除患者/移除病人 → delete_patient\n"
    "- 其他 → unknown\n"
    "只输出JSON，不要解释。"
)


class Intent(str, Enum):
    create_patient = "create_patient"
    add_record = "add_record"
    query_records = "query_records"
    list_patients = "list_patients"
    delete_patient = "delete_patient"
    list_tasks = "list_tasks"
    complete_task = "complete_task"
    schedule_appointment = "schedule_appointment"
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


async def detect_intent(text: str) -> IntentResult:
    intent_provider = os.environ.get("INTENT_PROVIDER", "local")

    if intent_provider == "local":
        from services.intent_rules import detect_intent_rules
        result = detect_intent_rules(text)
        log(f"[Intent:local] {result.intent} patient={result.patient_name}")
        return result

    provider = _PROVIDERS[intent_provider]
    log(f"[Intent:{intent_provider}] detecting: {text[:80]}")
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
    )
    completion = await client.chat.completions.create(
        model=provider["model"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        max_tokens=200,
        temperature=0,
    )
    raw = completion.choices[0].message.content
    log(f"[Intent:{intent_provider}] result: {raw}")
    data = json.loads(raw)
    return IntentResult.model_validate(data)
