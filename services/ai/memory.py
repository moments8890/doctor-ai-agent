"""
对话压缩服务：将历史对话摘要化存储，支持跨节点会话恢复。
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from typing import TYPE_CHECKING, List, Optional

from db.crud import get_doctor_context, upsert_doctor_context, clear_conversation_turns
from db.engine import AsyncSessionLocal
from services.ai.llm_resilience import call_with_retry_and_fallback
from utils.log import log

if TYPE_CHECKING:
    from services.session import DoctorSession

# Compress when the rolling window reaches this many turns (1 turn = 2 messages)
MAX_TURNS = 10
# Compress when the doctor has been idle for this many seconds
IDLE_SECONDS = 30 * 60  # 30 minutes

_COMPRESS_PROMPT_TEMPLATE = """\
今天日期：{today}

将以下医生与AI助手的对话提炼为结构化临床摘要，供下次会话恢复上下文使用。

只输出合法JSON对象，不加任何解释或markdown。字段说明（无相关信息填null）：
{{
  "current_patient": {{"name": "姓名", "gender": "性别或null", "age": 年龄整数或null}},
  "active_diagnoses": ["诊断1", "诊断2"],
  "current_medications": [{{"name": "药名", "dose": "剂量用法"}}],
  "allergies": ["过敏源"],
  "key_lab_values": [{{"name": "指标名", "value": "数值+单位", "date": "检测日期或null"}}],
  "recent_action": "最近一次主要操作（一句话）",
  "pending": "待跟进事项或null"
}}

重要：key_lab_values 保留所有关键检验数值（BNP、EF、HbA1c、CEA、肌钙蛋白、血压等），
不可省略，这些值是下次会话的重要上下文。"""


async def _build_compress_prompt() -> str:
    from utils.prompt_loader import get_prompt
    template = await get_prompt("memory.compress", _COMPRESS_PROMPT_TEMPLATE)
    return template.format(today=date.today().isoformat())


_REQUIRED_SUMMARY_FIELDS = frozenset({
    "current_patient", "active_diagnoses", "current_medications",
    "allergies", "key_lab_values", "recent_action", "pending",
})
_JSON_FORMAT_PROVIDERS = frozenset({"deepseek", "openai", "gemini", "tencent_lkeap"})


async def _build_summarise_call(
    client,
    provider_name: str,
    turns_text: str,
    specialty: Optional[str],
):
    """构造并返回用于压缩摘要的 LLM 调用协程工厂。"""
    async def _call(model_name: str):
        _prompt = await _build_compress_prompt()
        if specialty and specialty.strip():
            _prompt = f"【医生专科：{specialty.strip()}】\n" + _prompt
        kwargs: dict = dict(
            model=model_name,
            messages=[
                {"role": "system", "content": _prompt},
                {"role": "user", "content": turns_text},
            ],
            max_tokens=int(os.environ.get("MEMORY_MAX_TOKENS", "400")),
            temperature=0,
        )
        if provider_name in _JSON_FORMAT_PROVIDERS:
            kwargs["response_format"] = {"type": "json_object"}
        return await client.chat.completions.create(**kwargs)
    return _call


def _validate_summary_json(raw: str) -> str:
    """验证压缩摘要 JSON 格式，返回原始字符串（校验失败则抛出 ValueError）。"""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            _missing = _REQUIRED_SUMMARY_FIELDS - set(parsed.keys())
            if _missing:
                log(f"[Memory] compression output missing fields {_missing}; keeping raw")
            if "key_lab_values" not in parsed or not parsed.get("key_lab_values"):
                log("[Memory] WARNING: key_lab_values absent from compression output — lab values may be lost")
            return raw
        raise ValueError(f"[Memory] compression produced non-dict JSON; raw={raw[:200]!r}")
    except (json.JSONDecodeError, TypeError, ValueError) as _e:
        raise ValueError(f"[Memory] compression produced invalid JSON: {_e}; raw={raw[:200]!r}") from _e


async def _summarise(history: List[dict], specialty: Optional[str] = None, doctor_id: Optional[str] = None) -> str:
    """Call LLM to compress a conversation into a structured clinical context."""
    from services.ai.llm_client import _PROVIDERS  # shared provider registry
    from services.ai.agent import _get_client  # reuse singleton client
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _PROVIDERS[provider_name]
    client = _get_client(provider_name, provider)
    turns_text = "\n".join(
        f"{'医生' if m['role'] == 'user' else '助手'}：{m['content']}"
        for m in history
    )
    _call = await _build_summarise_call(client, provider_name, turns_text, specialty)
    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    completion = await call_with_retry_and_fallback(
        _call,
        primary_model=provider["model"],
        fallback_model=fallback_model,
        max_attempts=int(os.environ.get("MEMORY_LLM_ATTEMPTS", "3")),
        op_name="memory.chat_completion",
        circuit_key_suffix=doctor_id or "",
    )
    raw = (completion.choices[0].message.content or "").strip()
    return _validate_summary_json(raw)


async def maybe_compress(doctor_id: str, sess: "DoctorSession") -> None:
    """Compress and flush the rolling window when the turn limit or idle timeout is hit.

    After compression the in-memory history is cleared; the summary is persisted
    to DB so it can be injected as context at the start of the next session.
    """
    history = sess.conversation_history
    if not history:
        return

    full = len(history) >= MAX_TURNS * 2   # each turn = 2 messages
    # Also compress when estimated token count exceeds budget (~3 chars per token, 4K window)
    _TOKEN_BUDGET = int(os.environ.get("MEMORY_TOKEN_BUDGET", "3600"))
    _est_tokens = sum(len(m.get("content") or "") for m in history) // 3
    token_full = _est_tokens >= _TOKEN_BUDGET
    idle = (time.time() - sess.last_active) > IDLE_SECONDS

    if not full and not token_full and not idle:
        return

    reason = "full" if full else ("token_budget" if token_full else "idle")
    log(f"[Memory:{doctor_id}] compressing ({reason}): {len(history)} messages")
    try:
        summary = await _summarise(history, specialty=sess.specialty, doctor_id=doctor_id)
        async with AsyncSessionLocal() as db:
            await upsert_doctor_context(db, doctor_id, summary)
            await clear_conversation_turns(db, doctor_id)
        log(f"[Memory:{doctor_id}] saved summary: {summary[:80]}")
        # Only clear in-memory AFTER both DB ops succeed atomically
        sess.conversation_history = []
        sess.last_active = time.time()
        log("[Memory] compressed conversation history successfully")
    except Exception as e:
        log(f"[Memory] WARNING: compression failed for {doctor_id}: {e}")
        # DO NOT clear history here — but hard-cap to prevent unbounded growth
        if len(sess.conversation_history) > MAX_TURNS * 3:
            log(f"[Memory:{doctor_id}] hard-capping history at {MAX_TURNS * 2} turns after repeated compression failures")
            sess.conversation_history = sess.conversation_history[-(MAX_TURNS * 2):]


def _render_structured_summary(data: dict) -> str:
    """Convert structured summary JSON to a readable context string."""
    lines = []
    cp = data.get("current_patient")
    if cp and isinstance(cp, dict) and cp.get("name"):
        parts = [cp["name"]]
        if cp.get("gender"):
            parts.append(cp["gender"])
        if cp.get("age"):
            parts.append(f"{cp['age']}岁")
        lines.append("当前患者：" + "，".join(parts))
    diagnoses = data.get("active_diagnoses")
    if diagnoses and isinstance(diagnoses, list):
        lines.append("诊断：" + "；".join(str(d) for d in diagnoses if d))
    meds = data.get("current_medications")
    if meds and isinstance(meds, list):
        med_strs = [
            f"{m.get('name', '')} {m.get('dose', '')}".strip()
            for m in meds if isinstance(m, dict) and m.get("name")
        ]
        if med_strs:
            lines.append("用药：" + "；".join(med_strs))
    allergies = data.get("allergies")
    if allergies and isinstance(allergies, list):
        lines.append("过敏：" + "；".join(str(a) for a in allergies if a))
    labs = data.get("key_lab_values")
    if labs and isinstance(labs, list):
        lab_strs = []
        for lab in labs:
            if not isinstance(lab, dict) or not lab.get("name"):
                continue
            entry = f"{lab['name']} {lab.get('value', '')}".strip()
            if lab.get("date"):
                entry += f"（{lab['date']}）"
            lab_strs.append(entry)
        if lab_strs:
            lines.append("关键检验：" + "；".join(lab_strs))
    recent = data.get("recent_action")
    if recent:
        lines.append("最近操作：" + str(recent))
    pending = data.get("pending")
    if pending:
        lines.append("待跟进：" + str(pending))
    return "\n".join(lines)


async def load_context_message(doctor_id: str) -> Optional[dict]:
    """Return the persisted summary as an injected system message, or None.

    Injected only when the rolling window is empty (i.e. fresh session).
    The message is formatted so the LLM treats it as background knowledge,
    not as something it said itself.
    """
    async with AsyncSessionLocal() as db:
        ctx = await get_doctor_context(db, doctor_id)
    if not ctx or not ctx.summary:
        return None
    summary_text = ctx.summary.strip()
    try:
        parsed = json.loads(summary_text)
        if isinstance(parsed, dict):
            summary_text = _render_structured_summary(parsed)
    except (json.JSONDecodeError, TypeError):
        pass  # plain-text fallback
    if not summary_text:
        return None
    return {
        "role": "system",
        "content": (
            "【上次会话摘要 — 仅供参考，医生尚未发言】\n"
            f"{summary_text}\n"
            "请基于以上摘要继续协助医生，无需主动提及摘要内容。"
        ),
    }
