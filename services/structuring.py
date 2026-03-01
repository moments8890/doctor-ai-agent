import json
import os
from openai import AsyncOpenAI
from models.medical_record import MedicalRecord
from utils.log import log

SYSTEM_PROMPT = """\
你是医院电子病历系统，依据《病历书写基本规范》（卫医政发〔2010〕11号）将医生口述或文字记录转为规范化门诊病历 JSON。

【字段说明与书写要求】

必填字段（不可为 null，信息不明确时从上下文合理推断）：

  chief_complaint（主诉）
    · 简明描述患者就诊最主要的症状或体征及持续时间
    · 一般不超过 20 字，例如："头痛伴恶心 3 天"、"胸痛 2 小时"

  history_of_present_illness（现病史）
    · 按时间顺序描述本次疾病的发生、发展、诊疗经过
    · 包括：起病时间与诱因、主症的性质/程度/部位/演变、伴随症状、已采取的诊疗措施及效果
    · 与主诉密切相关的阳性与重要阴性体征亦可纳入

尽量填写（有依据时填写，无法确定时返回 null）：

  diagnosis（诊断）
    · 按规范书写疾病诊断名称，优先使用 ICD 标准名称
    · 多个诊断以"；"分隔，主要诊断列首位
    · 仅凭现有信息无法明确时可写"待查：XX 待排"

  treatment_plan（治疗方案）
    · 包括药物（药名、剂量、用法）、非药物治疗、医嘱
    · 例如："阿莫西林 0.5g tid po × 5天；多休息，多饮水"

选填字段（文本中无相关信息时返回 null）：

  past_medical_history（既往史）
    · 既往重要疾病史、手术史、外伤史、输血史、药物及食物过敏史

  physical_examination（体格检查）
    · 生命体征（T / P / R / BP）及与主诉相关的体格检查阳性体征

  auxiliary_examinations（辅助检查）
    · 本次就诊前已有的实验室、影像、心电图等检查结果

  follow_up_plan（随访计划）
    · 复诊时间、随访内容、患者教育要点

【输出要求】
- 只输出合法 JSON 对象，不加任何解释或 markdown
- 字段值为字符串或 null，不使用数组或嵌套对象
- 保持医学术语规范，不自行发明诊断
"""

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
