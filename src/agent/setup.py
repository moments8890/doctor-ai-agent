"""LangChain/LangGraph agent configuration."""
from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from typing import Any, List

from langchain_core.tools import BaseTool
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from agent.tools.doctor import DOCTOR_TOOLS
from agent.tools.patient import PATIENT_TOOLS
from agent.tools.diagnosis import diagnose
from infra.auth import UserRole
from utils.prompt_loader import get_prompt_sync

_log = logging.getLogger("agent")


# ── Observability callback ────────────────────────────────────────────


class AgentTracer(BaseCallbackHandler):
    """Log each LLM call and tool invocation for debugging."""

    def on_llm_start(self, serialized: Any, prompts: Any, **kwargs: Any) -> None:
        self._llm_start = time.time()
        model = kwargs.get("invocation_params", {}).get("model", "?")

        # Detect which prompt is being used from the system message
        prompt_tag = "unknown"
        messages = kwargs.get("invocation_params", {}).get("messages", [])
        if not messages and isinstance(prompts, list) and prompts:
            # Text-mode prompts
            first = prompts[0][:120] if prompts else ""
            prompt_tag = _detect_prompt_tag(first)
        else:
            # Chat-mode messages
            for m in messages:
                if isinstance(m, dict) and m.get("role") == "system":
                    prompt_tag = _detect_prompt_tag(m.get("content", "")[:120])
                    break

        self._prompt_tag = prompt_tag
        _log.info("[agent] LLM call start | prompt=%s model=%s messages=%d",
                  prompt_tag, model, len(messages or prompts or []))

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        elapsed = time.time() - getattr(self, "_llm_start", time.time())
        text = ""
        if response and response.generations:
            gen = response.generations[0][0]
            text = getattr(gen, "text", "")[:100]
        prompt_tag = getattr(self, "_prompt_tag", "?")
        _log.info("[agent] LLM call done | prompt=%s %.1fs | response=%s",
                  prompt_tag, elapsed, text)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        _log.error("[agent] LLM call FAILED | %s", error)

    def on_tool_start(self, serialized: Any, input_str: str, **kwargs: Any) -> None:
        self._tool_start = time.time()
        name = serialized.get("name", "?")
        _log.info("[agent] Tool call start | tool=%s input=%s", name, input_str[:200])

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        elapsed = time.time() - getattr(self, "_tool_start", time.time())
        _log.info("[agent] Tool call done | %.1fs | output=%s", elapsed, str(output)[:200])

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        _log.error("[agent] Tool call FAILED | %s", error)


def _detect_prompt_tag(text: str) -> str:
    """Identify which prompt is being used from the first ~120 chars."""
    t = text.lower()
    if "医生" in t and ("AI" in text or "临床助手" in t or "ai" in t):
        return "doctor-agent"
    if "患者" in t and ("预问诊" in t or "助手" in t):
        return "patient-agent"
    if "结构化" in t or "意图识别" in t or "structur" in t:
        return "structuring"
    if "问诊" in t and "流程" in t:
        return "patient-interview"
    if "vision" in t or "ocr" in t or "图像" in t:
        return "vision"
    if "报告" in t and "提取" in t:
        return "report-extract"
    return "unknown"


_tracer = AgentTracer()


# ── LangFuse integration (optional) ──────────────────────────────────

def _get_langfuse_handler():
    """Create LangFuse callback handler if configured. Returns None if not."""
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return None
    try:
        from langfuse.langchain import CallbackHandler
        handler = CallbackHandler()
        _log.info("[agent] LangFuse tracing enabled")
        return handler
    except Exception as e:
        _log.warning("[agent] LangFuse init failed: %s", e)
        return None

_langfuse_handler = _get_langfuse_handler()


# ── Callbacks list ────────────────────────────────────────────────────

def _get_callbacks() -> list:
    """Collect all active callback handlers."""
    cbs = [_tracer]
    if _langfuse_handler:
        cbs.append(_langfuse_handler)
    return cbs


# Enable LangChain global debug when LOG_LEVEL=DEBUG
if os.environ.get("LOG_LEVEL", "").upper() == "DEBUG":
    from langchain_core.globals import set_debug
    set_debug(True)
    _log.info("[agent] LangChain debug mode enabled")


def get_tools_for_role(role: str) -> List[BaseTool]:
    if role == UserRole.doctor:
        # Include diagnose() alongside the core doctor tools.
        # diagnose() is gated here rather than in DOCTOR_TOOLS to keep
        # the base list small and avoid token overhead on providers that
        # don't need the diagnosis capability.
        return [*DOCTOR_TOOLS, diagnose]
    return PATIENT_TOOLS


def get_llm() -> BaseChatModel:
    """Create LLM using provider-specific LangChain client.

    Uses dedicated LangChain packages (ChatDeepSeek, ChatGroq, ChatOllama)
    for providers that have them — these handle tool-calling wire format
    correctly. Falls back to ChatOpenAI for OpenAI-compatible providers.
    """
    from infra.llm.client import _get_providers

    provider_name = (
        os.environ.get("CONVERSATION_LLM")
        or os.environ.get("ROUTING_LLM", "groq")
    )
    providers = _get_providers()
    provider = providers.get(provider_name, providers.get("groq"))

    model_name = provider.get("model", "deepseek-chat")
    base_url = provider["base_url"]
    api_key = os.environ.get(provider.get("api_key_env", ""), "nokeyneeded")
    callbacks = _get_callbacks()

    _log.info("[agent] LLM config | provider=%s model=%s base_url=%s", provider_name, model_name, base_url)

    # Provider-specific clients handle tool-calling protocol correctly.
    # ChatOpenAI works for OpenAI-compatible APIs but mishandles
    # provider-specific extensions (reasoning_content, stop signals).

    if provider_name == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            model=model_name,
            api_key=api_key,
            api_base="https://api.deepseek.com/beta",  # beta endpoint for strict tool-calling
            temperature=0.1,
            max_retries=0,
            callbacks=callbacks,
        )

    if provider_name == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model_name,
            api_key=api_key,
            temperature=0.1,
            max_retries=0,
            callbacks=callbacks,
        )

    if provider_name == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model_name,
            base_url=base_url.replace("/v1", ""),  # ChatOllama uses native API, not /v1
            temperature=0.1,
            callbacks=callbacks,
        )

    # All other providers (sambanova, cerebras, siliconflow, openrouter,
    # tencent_lkeap) are OpenAI-compatible — ChatOpenAI works correctly.
    return ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1,
        max_retries=0,
        callbacks=callbacks,
    )


def _build_tools_section(role: str) -> str:
    """Generate tool listing from actual tool definitions."""
    tools = get_tools_for_role(role)
    lines = ["## 可用工具\n"]
    for t in tools:
        # First sentence of docstring as description
        desc = (t.description or "").split("。")[0]
        lines.append(f"- {t.name} — {desc}")
    return "\n".join(lines)


def _build_system_prompt(role: str) -> str:
    """Load and render the system prompt for a given role."""
    prompt_name = "doctor-agent" if role == UserRole.doctor else "patient-agent"
    system_text = get_prompt_sync(prompt_name)
    system_text = system_text.replace("{current_date}", datetime.now().strftime("%Y-%m-%d"))
    system_text = system_text.replace("{timezone}", os.environ.get("TZ", "Asia/Shanghai"))
    system_text = system_text.replace("{tools_section}", _build_tools_section(role))
    return system_text


def _is_deepseek() -> bool:
    provider = os.environ.get("CONVERSATION_LLM") or os.environ.get("ROUTING_LLM", "groq")
    return provider == "deepseek"


def get_agent(role: str) -> Any:
    """Create a LangGraph ReAct agent for the given role.

    Uses ``langgraph.prebuilt.create_react_agent`` which internally uses
    the LLM's native JSON tool calls (not text-based ReAct parsing).
    Returns a compiled LangGraph that is invoked with ``.ainvoke()``.

    For DeepSeek: uses beta endpoint + strict=True on bind_tools so the
    model adheres to tool JSON schemas without inventing extra fields.
    """
    llm = get_llm()
    tools = get_tools_for_role(role)
    system_prompt = _build_system_prompt(role)

    if _is_deepseek():
        # Pre-bind tools with strict=True so DeepSeek uses strict schema
        # validation. create_agent will use this pre-bound model.
        llm = llm.bind_tools(tools, strict=True)
        return create_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
        )

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )
