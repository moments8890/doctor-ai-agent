"""Startup warmup: jieba, Ollama model preload, LKEAP connectivity."""

import asyncio
import logging
import os
from typing import List

from utils.app_config import AppConfig, ollama_base_url_candidates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ollama_warmup_timeout_seconds() -> float:
    raw = os.environ.get("OLLAMA_WARMUP_TIMEOUT_SECONDS", "10").strip()
    try:
        value = float(raw)
        return value if value > 0 else 10.0
    except ValueError:
        return 10.0


def _ollama_warmup_backoff_seconds(attempt: int) -> float:
    # attempt is 1-based; retries use 1s, 2s, 4s...
    return float(2 ** max(0, int(attempt) - 1))


def _is_connectivity_error(exc: Exception) -> bool:
    """True when warmup failure indicates endpoint connectivity issues."""
    try:
        from openai import APIConnectionError, APITimeoutError
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return True
    except Exception:
        pass
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


# ---------------------------------------------------------------------------
# Individual warmup routines
# ---------------------------------------------------------------------------

async def _warmup_jieba(log: logging.Logger) -> None:
    """Pre-load jieba segmentation dictionary (builds prefix dict on first import)."""
    import jieba
    jieba.initialize()
    log.info("jieba initialised")


async def _ping_ollama_candidate(
    candidate_url: str, model: str, api_key: str, timeout: float, max_attempts: int, log: logging.Logger
) -> bool:
    """Try to ping a single candidate URL; return True on success, False on connection failure."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=candidate_url, api_key=api_key, timeout=timeout, max_retries=0)
    for attempt in range(1, max_attempts + 1):
        try:
            await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=1,
            )
            return True
        except Exception as e:
            if _is_connectivity_error(e):
                log.warning(
                    f"Ollama connectivity check failed | "
                    f"base_url={candidate_url} model={model} attempt={attempt}/{max_attempts} error={e}"
                )
            else:
                raise RuntimeError(
                    f"Ollama startup warmup failed with non-connectivity error "
                    f"(base_url={candidate_url}, model={model}): {e}"
                ) from e
            if attempt < max_attempts:
                await asyncio.sleep(_ollama_warmup_backoff_seconds(attempt))
    return False


def _apply_ollama_url_override(config: AppConfig, chosen_url: str, log: logging.Logger) -> None:
    """Write the chosen candidate URL into env vars when it differs from the configured URL."""
    if chosen_url != config.ollama_base_url:
        os.environ["OLLAMA_BASE_URL"] = chosen_url
        if os.environ.get("OLLAMA_VISION_BASE_URL", "").strip() == config.ollama_base_url:
            os.environ["OLLAMA_VISION_BASE_URL"] = chosen_url
        log.warning(
            f"Ollama startup fallback selected | original_base_url={config.ollama_base_url} "
            f"effective_base_url={chosen_url} model={config.ollama_model}"
        )
    else:
        log.info(
            f"Ollama startup connectivity check passed | "
            f"base_url={chosen_url} model={config.ollama_model}"
        )


async def _warmup_ollama(config: AppConfig, log: logging.Logger) -> None:
    """Ping Ollama to preload the model into VRAM and select a reachable base_url."""
    model = config.ollama_model
    max_attempts = 3
    warmup_timeout = _ollama_warmup_timeout_seconds()
    candidates = ollama_base_url_candidates(config.ollama_base_url)
    api_key = config.ollama_api_key or "ollama"
    chosen_url = None

    for candidate_url in candidates:
        if await _ping_ollama_candidate(candidate_url, model, api_key, warmup_timeout, max_attempts, log):
            chosen_url = candidate_url
            break

    if chosen_url:
        _apply_ollama_url_override(config, chosen_url, log)
    else:
        log.error(
            f"Ollama unavailable on startup | attempted_base_urls={candidates} "
            f"model={model}. Continuing without warmup."
        )


async def _warmup_lkeap(log: logging.Logger) -> None:
    """Pre-establish LKEAP TCP/TLS connection for faster first request."""
    lkeap_key = os.environ.get("TENCENT_LKEAP_API_KEY", "").strip()
    if not lkeap_key:
        return
    try:
        from openai import AsyncOpenAI
        from infra.llm.client import _PROVIDERS
        lkeap_provider = _PROVIDERS.get("tencent_lkeap", {})
        if lkeap_provider:
            client = AsyncOpenAI(
                base_url=lkeap_provider["base_url"],
                api_key=lkeap_key,
                timeout=10, max_retries=0,
            )
            model = os.environ.get("TENCENT_LKEAP_MODEL", lkeap_provider.get("model", "deepseek-v3-1"))
            await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            log.info("[Warmup] LKEAP connection established")
    except Exception as e:
        log.warning("[Warmup] LKEAP warmup failed (non-fatal): %s", e)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_warmup(config: AppConfig) -> None:
    """Run all warmup routines: jieba, Ollama (background), LKEAP (background)."""
    log = logging.getLogger("warmup")
    await _warmup_jieba(log)
    # Ollama/LKEAP warmup runs in background -- don't block app startup
    if config.routing_llm == "ollama" or config.structuring_llm == "ollama":
        asyncio.create_task(_warmup_ollama(config, log))
        log.info("Ollama warmup started (background -- app ready immediately)")
    if config.routing_llm == "tencent_lkeap" or config.structuring_llm == "tencent_lkeap":
        asyncio.create_task(_warmup_lkeap(log))
        log.info("LKEAP warmup started (background)")
