from __future__ import annotations

import json
import os
from typing import List, Optional
from openai import AsyncOpenAI
from services.intent import Intent, IntentResult
from utils.log import log

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

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_patient",
            "description": (
                "当医生介绍或登记新患者，且消息中没有临床症状时调用。"
                "示例：'我有个病人叫张三'、'新患者李明35岁男'、'建档'、'新病人'。"
                "如果消息同时含有症状或诊断，则改用 add_medical_record。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "患者姓名。只填写当前消息中明确出现的姓名，绝不从上下文推断，不确定时省略。",
                    },
                    "gender": {
                        "type": "string",
                        "description": "性别，填男或女。只在当前消息中明确提到时填写，否则省略。",
                    },
                    "age": {
                        "type": "integer",
                        "description": "患者年龄整数。只在当前消息中明确提到时填写，否则省略。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_medical_record",
            "description": (
                "当医生描述任何临床内容时调用，包括：\n"
                "- 症状体征：头痛、发烧、胸痛、胸闷、气短、水肿等\n"
                "- 检查结果：心电图、血压、心率、BNP、EF值、血脂、肌钙蛋白等\n"
                "- 诊断：心绞痛、心衰、房颤、STEMI、高血压、肿瘤等\n"
                "- 用药/治疗：开药、处方、手术、化疗、靶向治疗、放疗等\n"
                "- 专科内容：心血管（PCI术后、消融术后、支架、Holter）"
                "或肿瘤（化疗周期、CEA、白细胞、ANC、EGFR、HER2等）\n"
                '- 以"记录一下"或引号开头的口述病历\n'
                "纯粹的患者介绍（无任何临床信息）不调用此工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {
                        "type": "string",
                        "description": "患者姓名。只填写当前消息中明确出现的姓名，否则省略。",
                    },
                    "gender": {
                        "type": "string",
                        "description": "性别，填男或女。只在当前消息中明确提到时填写，否则省略。",
                    },
                    "age": {
                        "type": "integer",
                        "description": "患者年龄整数。只在当前消息中明确提到时填写，否则省略。",
                    },
                    "is_emergency": {
                        "type": "boolean",
                        "description": (
                            "是否为紧急/急诊情况，默认false。"
                            "遇到以下情况设为true：STEMI、ST段抬高、急诊PCI、绿色通道、"
                            "休克、血压90/60以下、心跳骤停、呼吸骤停、室颤。"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_records",
            "description": "查询患者历史病历记录。当医生要查看、查询、调取病历时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {
                        "type": "string",
                        "description": "要查询的患者姓名。只在明确提到时填写，否则省略此字段。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_patients",
            "description": "列出所有患者。当医生要查看患者列表、所有病人时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

_SYSTEM_PROMPT = (
    "你是医生助手。根据医生当前消息选择工具：\n"
    "- 消息含症状/体征/诊断/用药等临床信息 → add_medical_record\n"
    "- 消息只介绍患者身份（无临床内容）或明确说建档 → create_patient\n"
    "- 要查看历史病历 → query_records\n"
    "- 要看所有患者列表 → list_patients\n"
    "- 普通对话/问候 → 直接回复，不调用工具\n\n"
    "特殊规则：若上一条助手消息询问了患者姓名（如'请问这位患者叫什么名字'），"
    "医生的回复即为患者姓名，应调用 add_medical_record 并将该姓名填入 patient_name，"
    "不要调用 create_patient。\n\n"
    "工具参数只填写当前消息或上下文中明确出现的信息，不确定时省略该字段。"
)

_INTENT_MAP = {
    "create_patient": Intent.create_patient,
    "add_medical_record": Intent.add_record,
    "query_records": Intent.query_records,
    "list_patients": Intent.list_patients,
}


async def dispatch(text: str, history: Optional[List[dict]] = None) -> IntentResult:
    """Call LLM with function-calling tools and return an IntentResult.

    Args:
        text: The current user message.
        history: Optional prior turns as [{"role": "user"|"assistant", "content": "..."}].
    """
    provider_name = os.environ.get("ROUTING_LLM") or os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = dict(_PROVIDERS[provider_name])
    if provider_name == "ollama":
        provider["model"] = os.environ.get("OLLAMA_MODEL", provider["model"])
    log(f"[Agent:{provider_name}] dispatching: {text[:80]}")

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": text})

    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
    )
    completion = await client.chat.completions.create(
        model=provider["model"],
        messages=messages,
        tools=_TOOLS,
        tool_choice="auto",
        max_tokens=300,
        temperature=0,
    )

    message = completion.choices[0].message
    if not message.tool_calls:
        chat_reply = message.content or "您好！有什么可以帮您？"
        log(f"[Agent:{provider_name}] no tool call → chat reply: {chat_reply[:80]}")
        return IntentResult(intent=Intent.unknown, chat_reply=chat_reply)

    tool_call = message.tool_calls[0]
    fn_name = tool_call.function.name
    intent = _INTENT_MAP.get(fn_name, Intent.unknown)

    try:
        args = json.loads(tool_call.function.arguments)
        if not isinstance(args, dict):
            args = {}
    except (json.JSONDecodeError, TypeError):
        args = {}

    log(f"[Agent:{provider_name}] tool_call: {fn_name}({args})")

    # Validate extracted values — drop any non-integer age or non-gender gender
    age = args.get("age")
    if not isinstance(age, int):
        age = None

    gender = args.get("gender")
    if gender not in ("男", "女"):
        gender = None

    return IntentResult(
        intent=intent,
        patient_name=args.get("patient_name") or args.get("name"),
        gender=gender,
        age=age,
        is_emergency=args.get("is_emergency", False),
    )
