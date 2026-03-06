from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional, Sequence, TypeVar

from utils.log import log

T = TypeVar("T")


def _looks_like_timeout_error(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    if "timeout" in name or "timed out" in msg or "timeout" in msg:
        return True
    return "apitimeouterror" in name


async def call_with_retry_and_fallback(
    call_for_model: Callable[[str], Awaitable[T]],
    *,
    primary_model: str,
    fallback_model: Optional[str] = None,
    max_attempts: int = 3,
    backoff_seconds: Optional[Sequence[float]] = None,
    op_name: str = "llm_call",
) -> T:
    """Retry LLM calls with exponential backoff and optional timeout fallback model."""
    attempts = max(1, int(max_attempts))
    backoff = list(backoff_seconds or (1.0, 2.0, 4.0))
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            return await call_for_model(primary_model)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = backoff[min(attempt - 1, len(backoff) - 1)]
            log(
                "[LLM] {0} retrying model={1} attempt={2}/{3} delay={4}s error={5}".format(
                    op_name,
                    primary_model,
                    attempt,
                    attempts,
                    delay,
                    exc,
                )
            )
            await asyncio.sleep(delay)

    if fallback_model and fallback_model != primary_model and last_error and _looks_like_timeout_error(last_error):
        log(
            "[LLM] {0} timeout on model={1}; falling back to model={2}".format(
                op_name,
                primary_model,
                fallback_model,
            )
        )
        return await call_for_model(fallback_model)

    if last_error is not None:
        raise last_error
    raise RuntimeError("{0} failed with unknown error".format(op_name))
