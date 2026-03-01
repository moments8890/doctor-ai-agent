import json
import os
from openai import AsyncOpenAI
from models.medical_record import MedicalRecord
from utils.log import log

SYSTEM_PROMPT = (
    "将医疗文本转为JSON病历。\n"
    "必填字段（不可为null，信息不明确时从上下文推断）：\n"
    "  chief_complaint, history_of_present_illness, diagnosis, treatment_plan\n"
    "选填字段（无相关信息时返回null）：\n"
    "  past_medical_history, physical_examination, auxiliary_examinations, follow_up_plan\n"
    "只输出JSON，不要解释。"
)

_PROVIDERS = {
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
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "model": "qwen2.5:7b",
    },
}


async def structure_medical_record(text: str) -> MedicalRecord:
    provider_name = os.environ.get("LLM_PROVIDER", "deepseek")
    provider = _PROVIDERS[provider_name]
    log(f"[LLM:{provider_name}] calling API: {text[:80]}")

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
        max_tokens=800,
        temperature=0,
    )
    raw = completion.choices[0].message.content
    log(f"[LLM:{provider_name}] response: {raw}")
    data = json.loads(raw)
    return MedicalRecord.model_validate(data)
