"""LLM 韧性单元测试：覆盖重试退避、超时触发 fallback 模型和熔断器开路/短路行为。"""

from __future__ import annotations

from typing import List

import pytest

from services.ai import llm_resilience as lr


@pytest.fixture(autouse=True)
def _reset_circuits() -> None:
    lr._reset_circuits_for_tests()


@pytest.mark.asyncio
async def test_call_with_retry_and_fallback_retries_then_succeeds() -> None:
    calls: List[str] = []

    async def _call(model: str) -> str:
        calls.append(model)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "ok"

    out = await lr.call_with_retry_and_fallback(
        _call,
        primary_model="m1",
        max_attempts=3,
        backoff_seconds=(0, 0, 0),
        op_name="test_retry",
    )

    assert out == "ok"
    assert calls == ["m1", "m1", "m1"]


@pytest.mark.asyncio
async def test_call_with_retry_and_fallback_timeout_uses_fallback() -> None:
    calls: List[str] = []

    class TimeoutExc(Exception):
        pass

    async def _call(model: str) -> str:
        calls.append(model)
        if model == "m1":
            raise TimeoutExc("request timeout")
        return "fallback-ok"

    out = await lr.call_with_retry_and_fallback(
        _call,
        primary_model="m1",
        fallback_model="m2",
        max_attempts=1,
        op_name="test_timeout",
    )

    assert out == "fallback-ok"
    assert calls == ["m1", "m2"]


@pytest.mark.asyncio
async def test_call_with_retry_and_fallback_opens_circuit_and_short_circuits() -> None:
    async def _always_fail(model: str) -> str:
        raise RuntimeError("boom")

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("LLM_CIRCUIT_FAIL_THRESHOLD", "1")
        mp.setenv("LLM_CIRCUIT_COOLDOWN_SECONDS", "120")

        with pytest.raises(RuntimeError):
            await lr.call_with_retry_and_fallback(
                _always_fail,
                primary_model="m1",
                max_attempts=1,
                op_name="test_circuit",
            )

        with pytest.raises(RuntimeError, match="circuit_open"):
            await lr.call_with_retry_and_fallback(
                _always_fail,
                primary_model="m1",
                max_attempts=1,
                op_name="test_circuit",
            )


@pytest.mark.asyncio
async def test_call_with_retry_and_fallback_uses_fallback_when_primary_circuit_open() -> None:
    calls: List[str] = []

    async def _call(model: str) -> str:
        calls.append(model)
        if model == "m1":
            raise RuntimeError("primary fail")
        return "ok-fallback"

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("LLM_CIRCUIT_FAIL_THRESHOLD", "1")
        mp.setenv("LLM_CIRCUIT_COOLDOWN_SECONDS", "120")

        with pytest.raises(RuntimeError):
            await lr.call_with_retry_and_fallback(
                _call,
                primary_model="m1",
                fallback_model=None,
                max_attempts=1,
                op_name="test_open_then_fallback",
            )

        out = await lr.call_with_retry_and_fallback(
            _call,
            primary_model="m1",
            fallback_model="m2",
            max_attempts=1,
            op_name="test_open_then_fallback",
        )

    assert out == "ok-fallback"
    assert calls[-1] == "m2"
