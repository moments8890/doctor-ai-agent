from __future__ import annotations

import json
import os
import re
from typing import List, Optional, Tuple
from openai import AsyncOpenAI
from services.intent import Intent, IntentResult
from services.observability import trace_block
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


_NAME_PATTERNS = [
    re.compile(r"(?:新患者|新病人|查询)\s*[:：，,\s]*([\u4e00-\u9fff]{2,4})"),
    re.compile(r"(?:患者|病人)\s*([\u4e00-\u9fff]{2,4})(?:[，,。:：\s]|男|女)"),
    re.compile(r"^([\u4e00-\u9fff]{2,4})(?:门诊记录|复查|，|,|。|\s)"),
    re.compile(r"([\u4e00-\u9fff]{2,4})门诊记录"),
]
_BAD_NAME_TOKENS = {
    "患者", "病人", "新患者", "新病人", "门诊", "复查", "记录", "查询", "提醒",
    "胸痛", "胸闷", "心悸", "咳嗽", "头痛", "发热", "化疗", "术后", "治疗", "安排",
}


def _extract_embedded_tool_call(content: Optional[str]) -> Tuple[Optional[str], dict]:
    """Best-effort parser for providers that return tool-calls in text content."""
    if not content:
        return None, {}

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(content):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(content[idx:])
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        fn_name = obj.get("name")
        if not isinstance(fn_name, str) or not fn_name:
            continue
        args = obj.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                args = {}
        if not isinstance(args, dict):
            args = {}
        return fn_name, args
    return None, {}


def _looks_like_tool_markup(content: Optional[str]) -> bool:
    if not content:
        return False
    lowered = content.lower()
    if "tool_call" in lowered or "</tool_call>" in lowered:
        return True
    stripped = content.strip()
    if stripped.startswith("{") and '"name"' in stripped and '"arguments"' in stripped:
        return True
    return False


def _intent_result_from_tool_call(fn_name: str, args: dict, chat_reply: Optional[str]) -> IntentResult:
    intent = _INTENT_MAP.get(fn_name, Intent.unknown)

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


def _extract_name_gender_age(text: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    name = None
    for pattern in _NAME_PATTERNS:
        m = pattern.search(text)
        if m:
            candidate = m.group(1)
            if candidate and candidate not in _BAD_NAME_TOKENS:
                name = candidate
                break
    gender_m = re.search(r"(男|女)", text)
    age_m = re.search(r"(\d{1,3})\s*岁", text)
    gender = gender_m.group(1) if gender_m else None
    age = int(age_m.group(1)) if age_m else None
    return name, gender, age


def _fallback_intent_from_text(text: str) -> IntentResult:
    lower = text.lower()
    name, gender, age = _extract_name_gender_age(text)

    clinical_keywords = [
        "胸痛", "胸闷", "心悸", "气短", "头痛", "发热", "咳嗽",
        "心电图", "CT", "MRI", "BNP", "EF", "ST", "PCI", "化疗", "靶向", "诊断",
        "治疗", "复查", "门诊", "术后", "高血压", "肿瘤", "肺癌",
    ]
    # Clinical content takes precedence even when the message also contains
    # "查询"/"提醒" phrasing in natural doctor speech.
    if any(k in text for k in clinical_keywords):
        return IntentResult(intent=Intent.add_record, patient_name=name, gender=gender, age=age)

    if any(k in text for k in ["所有患者", "患者列表", "病人列表", "全部患者"]):
        return IntentResult(intent=Intent.list_patients, patient_name=name)
    if any(k in text for k in ["任务", "待办", "提醒"]):
        return IntentResult(intent=Intent.list_tasks, patient_name=name)
    if re.search(r"(完成|标记完成)\s*\d+", text):
        task_id_m = re.search(r"(\d+)", text)
        return IntentResult(
            intent=Intent.complete_task,
            patient_name=name,
            extra_data={"task_id": int(task_id_m.group(1)) if task_id_m else None},
        )
    if any(k in text for k in ["查询", "历史病历", "病历记录", "调取病历"]):
        return IntentResult(intent=Intent.query_records, patient_name=name)

    if any(k in text for k in ["建档", "新患者", "新病人"]):
        return IntentResult(intent=Intent.create_patient, patient_name=name, gender=gender, age=age)

    if any(k in lower for k in ["hello", "hi", "你好"]):
        return IntentResult(intent=Intent.unknown, chat_reply="您好！有什么可以帮您？")

    return IntentResult(intent=Intent.unknown, patient_name=name, gender=gender, age=age)


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
        timeout=float(os.environ.get("AGENT_LLM_TIMEOUT", "45")),
        max_retries=int(os.environ.get("AGENT_LLM_RETRIES", "1")),
    )
    try:
        with trace_block("llm", "agent.chat_completion", {"provider": provider_name, "model": provider["model"]}):
            completion = await client.chat.completions.create(
                model=provider["model"],
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                max_tokens=300,
                temperature=0,
            )
    except Exception as e:
        if provider_name == "ollama":
            log(f"[Agent:ollama] tool-call failed, using local fallback: {e}")
            with trace_block("agent", "agent.local_fallback", {"reason": "ollama_error"}):
                return _fallback_intent_from_text(text)
        raise

    message = completion.choices[0].message
    # Capture natural reply regardless of whether a tool was called
    chat_reply = message.content or None

    if not message.tool_calls:
        embedded_fn, embedded_args = _extract_embedded_tool_call(chat_reply)
        if embedded_fn:
            log(f"[Agent:{provider_name}] embedded tool_call: {embedded_fn}({embedded_args})")
            # Avoid returning raw tool-call markup back to users.
            cleaned_reply = chat_reply
            if _looks_like_tool_markup(cleaned_reply):
                cleaned_reply = None
            return _intent_result_from_tool_call(embedded_fn, embedded_args, cleaned_reply)
        if provider_name == "ollama" and (not chat_reply or _looks_like_tool_markup(chat_reply)):
            log("[Agent:ollama] no formal tool call, using local fallback")
            with trace_block("agent", "agent.local_fallback", {"reason": "no_tool_call"}):
                return _fallback_intent_from_text(text)
        reply_text = chat_reply or "您好！有什么可以帮您？"
        log(f"[Agent:{provider_name}] no tool call → chat reply: {reply_text[:80]}")
        return IntentResult(intent=Intent.unknown, chat_reply=reply_text)

    tool_call = message.tool_calls[0]
    fn_name = tool_call.function.name

    try:
        args = json.loads(tool_call.function.arguments)
        if not isinstance(args, dict):
            args = {}
    except (json.JSONDecodeError, TypeError):
        args = {}

    log(f"[Agent:{provider_name}] tool_call: {fn_name}({args})")

    return _intent_result_from_tool_call(fn_name, args, chat_reply)
