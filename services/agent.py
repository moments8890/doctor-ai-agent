from __future__ import annotations

import json
import os
from typing import List, Optional
from openai import AsyncOpenAI
from services.intent import Intent, IntentResult
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
                    "chief_complaint": {
                        "type": "string",
                        "description": "主诉：患者最主要的症状或就诊原因（不超过20字）。必须填写，不可省略。",
                    },
                    "history_of_present_illness": {
                        "type": ["string", "null"],
                        "description": "现病史：症状发展过程、伴随症状、加重/缓解因素、已做检查结果。未提及则为null。",
                    },
                    "past_medical_history": {
                        "type": ["string", "null"],
                        "description": "既往史：既往疾病、手术、过敏史、长期用药。未提及则为null。",
                    },
                    "physical_examination": {
                        "type": ["string", "null"],
                        "description": "体格检查：体征、生命体征（BP、HR等）、听诊触诊结果。未提及则为null。",
                    },
                    "auxiliary_examinations": {
                        "type": ["string", "null"],
                        "description": "辅助检查：已出结果的化验、影像、心电图。保留数值和单位（BNP 980pg/mL）。未提及则为null。",
                    },
                    "diagnosis": {
                        "type": ["string", "null"],
                        "description": "诊断：明确诊断或考虑诊断。保留缩写（STEMI、PCI、HER2、EGFR）。未提及则为null。",
                    },
                    "treatment_plan": {
                        "type": ["string", "null"],
                        "description": "治疗方案：用药、手术、处置措施。未提及则为null。",
                    },
                    "follow_up_plan": {
                        "type": ["string", "null"],
                        "description": "随访计划：随访时间和安排。未提及则为null。",
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
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "查看医生的待办任务/提醒列表。当医生说「我的任务」、「待办」、「提醒」时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "标记任务为已完成。当医生说「完成任务X」、「完成X」（X为数字编号）时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "要标记完成的任务编号。",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_appointment",
            "description": "安排患者预约。当医生说「预约」、「安排复诊」、「约诊」并提到时间时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {
                        "type": "string",
                        "description": "患者姓名。",
                    },
                    "appointment_time": {
                        "type": "string",
                        "description": "预约时间，ISO 8601格式，例如：2026-03-15T14:00:00。",
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注信息（可选）。",
                    },
                },
                "required": ["patient_name", "appointment_time"],
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
    "- 查看任务/待办/提醒 → list_tasks\n"
    "- 完成任务/标记完成 + 编号 → complete_task\n"
    "- 预约/安排/约诊 + 时间 → schedule_appointment\n"
    "- 普通对话/问候 → 直接回复，不调用工具\n\n"
    "特殊规则：若上一条助手消息询问了患者姓名（如'请问这位患者叫什么名字'），"
    "医生的回复即为患者姓名，应调用 add_medical_record 并将该姓名填入 patient_name，"
    "不要调用 create_patient。\n\n"
    "工具参数只填写当前消息或上下文中明确出现的信息，不确定时省略该字段。\n\n"
    "【回复要求】\n"
    "调用工具时，同时在 message content 中用1-2句口语化中文告知医生你的理解和操作。\n"
    "不要使用模板格式或列举字段名称。\n"
    "示例：add_medical_record → \"好的，张三头痛两天的情况记下来了，开了布洛芬，两周后复查。\"\n"
    "示例：create_patient → \"李明的档案建好了。\"\n"
    "示例：query_records → \"来看看张三的历史记录。\""
)

_INTENT_MAP = {
    "create_patient": Intent.create_patient,
    "add_medical_record": Intent.add_record,
    "query_records": Intent.query_records,
    "list_patients": Intent.list_patients,
    "list_tasks": Intent.list_tasks,
    "complete_task": Intent.complete_task,
    "schedule_appointment": Intent.schedule_appointment,
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
    # Capture natural reply regardless of whether a tool was called
    chat_reply = message.content or None

    if not message.tool_calls:
        reply_text = chat_reply or "您好！有什么可以帮您？"
        log(f"[Agent:{provider_name}] no tool call → chat reply: {reply_text[:80]}")
        return IntentResult(intent=Intent.unknown, chat_reply=reply_text)

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

    extra_data: dict = {}
    if fn_name == "complete_task":
        extra_data["task_id"] = args.get("task_id")
    elif fn_name == "schedule_appointment":
        extra_data["appointment_time"] = args.get("appointment_time")
        extra_data["notes"] = args.get("notes")

    # Extract 8 clinical fields when add_medical_record is called
    structured_fields: Optional[dict] = None
    if fn_name == "add_medical_record":
        _CLINICAL_KEYS = {
            "chief_complaint", "history_of_present_illness", "past_medical_history",
            "physical_examination", "auxiliary_examinations",
            "diagnosis", "treatment_plan", "follow_up_plan",
        }
        extracted = {k: args[k] for k in _CLINICAL_KEYS if args.get(k)}
        if extracted:
            structured_fields = extracted

    return IntentResult(
        intent=intent,
        patient_name=args.get("patient_name") or args.get("name"),
        gender=gender,
        age=age,
        is_emergency=args.get("is_emergency", False),
        extra_data=extra_data,
        chat_reply=chat_reply,
        structured_fields=structured_fields,
    )
