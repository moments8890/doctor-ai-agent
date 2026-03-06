from __future__ import annotations

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
将以下医生与AI助手的对话提炼为简洁的临床工作摘要，供下次会话恢复上下文使用。

严格按以下格式输出，不超过120字，不要解释：
当前患者：[姓名（性别，年龄）或「无」]
最近处理：[主要病历或操作，一行]
待跟进：[未完成事项或「无」]"""


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
    return (completion.choices[0].message.content or "").strip()


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
    return {
        "role": "system",
        "content": (
            "【上次会话摘要 — 仅供参考，医生尚未发言】\n"
            f"{ctx.summary}\n"
            "请基于以上摘要继续协助医生，无需主动提及摘要内容。"
        ),
    }
