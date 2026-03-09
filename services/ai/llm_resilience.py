"""
LLM 调用熔断器：在多提供商间自动故障转移并执行指数退避重试。
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Sequence, TypeVar

from utils.log import log

T = TypeVar("T")


@dataclass
class _CircuitState:
    failures: int = 0
    opened_until: float = 0.0


_CIRCUITS: dict[str, _CircuitState] = {}


def _now() -> float:
    return time.monotonic()


def _failure_threshold() -> int:
    raw = (os.environ.get("LLM_CIRCUIT_FAIL_THRESHOLD") or "").strip()
    try:
        return max(1, int(raw))
    except Exception:
        return 5


def _cooldown_seconds() -> float:
    raw = (os.environ.get("LLM_CIRCUIT_COOLDOWN_SECONDS") or "").strip()
    try:
        return max(1.0, float(raw))
    except Exception:
        return 60.0


def _circuit_key(op_name: str, model: str) -> str:
    return "{0}:{1}".format(op_name, model)


def _is_circuit_open(key: str) -> bool:
    state = _CIRCUITS.get(key)
    if state is None:
        return False
    return state.opened_until > _now()


def _record_failure(key: str) -> None:
    state = _CIRCUITS.setdefault(key, _CircuitState())
    state.failures += 1
    if state.failures >= _failure_threshold():
        state.opened_until = _now() + _cooldown_seconds()


def _record_success(key: str) -> None:
    if key in _CIRCUITS:
        _CIRCUITS.pop(key, None)


def _reset_circuits_for_tests() -> None:
    _CIRCUITS.clear()


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
    circuit_key_suffix: str = "",
) -> T:
    """Retry LLM calls with exponential backoff and circuit breaker support.

    circuit_key_suffix: optional discriminator (e.g. doctor_id) for per-entity circuits.
    When set, failures from one entity cannot open the circuit for others.
    """
    attempts = max(1, int(max_attempts))
    backoff = list(backoff_seconds or (0.5, 1.0))
    last_error: Optional[Exception] = None
    _key_base = "{0}:{1}".format(op_name, primary_model)
    primary_key = "{0}:{1}".format(_key_base, circuit_key_suffix) if circuit_key_suffix else _key_base

    if _is_circuit_open(primary_key):
        last_error = RuntimeError("circuit_open model={0} op={1}".format(primary_model, op_name))
    else:
        for attempt in range(1, attempts + 1):
            try:
                result = await call_for_model(primary_model)
                _record_success(primary_key)
                return result
            except Exception as exc:
                last_error = exc
                _record_failure(primary_key)
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

    if fallback_model and fallback_model != primary_model and last_error:
        _fb_key_base = "{0}:{1}".format(op_name, fallback_model)
        fallback_key = "{0}:{1}".format(_fb_key_base, circuit_key_suffix) if circuit_key_suffix else _fb_key_base
        if _is_circuit_open(fallback_key):
            raise RuntimeError("circuit_open model={0} op={1}".format(fallback_model, op_name))

        if _looks_like_timeout_error(last_error):
            log(
                "[LLM] {0} timeout on model={1}; falling back to model={2}".format(
                    op_name,
                    primary_model,
                    fallback_model,
                )
            )

        try:
            result = await call_for_model(fallback_model)
            _record_success(fallback_key)
            return result
        except Exception as exc:
            _record_failure(fallback_key)
            raise exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("{0} failed with unknown error".format(op_name))
