from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, List, Optional

from openai import AsyncOpenAI

from db.crud import get_doctor_context, upsert_doctor_context, clear_conversation_turns
from db.engine import AsyncSessionLocal
from services.llm_resilience import call_with_retry_and_fallback
from utils.log import log

if TYPE_CHECKING:
    from services.session import DoctorSession

# Compress when the rolling window reaches this many turns (1 turn = 2 messages)
MAX_TURNS = 10
# Compress when the doctor has been idle for this many seconds
IDLE_SECONDS = 30 * 60  # 30 minutes

_COMPRESS_PROMPT = """\
将以下医生与AI助手的对话提炼为结构化临床摘要，供下次会话恢复上下文使用。

只输出合法JSON对象，不加任何解释或markdown。字段说明（无相关信息填null）：
{
  "current_patient": {"name": "姓名", "gender": "性别或null", "age": 年龄整数或null},
  "active_diagnoses": ["诊断1", "诊断2"],
  "current_medications": [{"name": "药名", "dose": "剂量用法"}],
  "allergies": ["过敏源"],
  "recent_action": "最近一次主要操作（一句话）",
  "pending": "待跟进事项或null"
}"""


async def _summarise(history: List[dict]) -> str:
    """Call LLM to compress a conversation into a compact context string."""
    from services.agent import _PROVIDERS  # reuse same provider map
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _PROVIDERS[provider_name]
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        timeout=float(os.environ.get("MEMORY_LLM_TIMEOUT", "30")),
        max_retries=0,
    )
    turns_text = "\n".join(
        f"{'医生' if m['role'] == 'user' else '助手'}：{m['content']}"
        for m in history
    )
    async def _call(model_name: str):
        return await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": _COMPRESS_PROMPT},
                {"role": "user", "content": turns_text},
            ],
            max_tokens=150,
            temperature=0,
        )

    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    completion = await call_with_retry_and_fallback(
        _call,
        primary_model=provider["model"],
        fallback_model=fallback_model,
        max_attempts=int(os.environ.get("MEMORY_LLM_ATTEMPTS", "3")),
        op_name="memory.chat_completion",
    )
    raw = (completion.choices[0].message.content or "").strip()
    # Validate that the LLM returned JSON; if not, keep as plain-text fallback.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return raw  # valid structured summary
    except (json.JSONDecodeError, TypeError):
        pass
    return raw  # plain-text fallback (older format or model variance)


async def maybe_compress(doctor_id: str, sess: "DoctorSession") -> None:
    """Compress and flush the rolling window when the turn limit or idle timeout is hit.

    After compression the in-memory history is cleared; the summary is persisted
    to DB so it can be injected as context at the start of the next session.
    """
    history = sess.conversation_history
    if not history:
        return

    full = len(history) >= MAX_TURNS * 2   # each turn = 2 messages
    idle = (time.time() - sess.last_active) > IDLE_SECONDS

    if not full and not idle:
        return

    reason = "full" if full else "idle"
    log(f"[Memory:{doctor_id}] compressing ({reason}): {len(history)} messages")
    try:
        summary = await _summarise(history)
        async with AsyncSessionLocal() as db:
            await upsert_doctor_context(db, doctor_id, summary)
        log(f"[Memory:{doctor_id}] saved summary: {summary[:80]}")
    except Exception as e:
        log(f"[Memory:{doctor_id}] compression FAILED: {e}")
    finally:
        # Always clear the window so we don't retry on every subsequent message
        sess.conversation_history = []
        sess.last_active = time.time()
        try:
            async with AsyncSessionLocal() as db:
                await clear_conversation_turns(db, doctor_id)
        except Exception as e:
            log(f"[Memory:{doctor_id}] clear persisted turns FAILED: {e}")


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
