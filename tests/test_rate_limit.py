from __future__ import annotations

import pytest
from fastapi import HTTPException

from services import rate_limit as rl


def test_enforce_doctor_rate_limit_allows_under_limit() -> None:
    rl.clear_rate_limits_for_tests()
    for _ in range(3):
        rl.enforce_doctor_rate_limit("doc_a", scope="x", max_requests=3, window_seconds=60)


def test_enforce_doctor_rate_limit_raises_429_over_limit() -> None:
    rl.clear_rate_limits_for_tests()
    rl.enforce_doctor_rate_limit("doc_a", scope="x", max_requests=1, window_seconds=60)
    with pytest.raises(HTTPException) as exc_info:
        rl.enforce_doctor_rate_limit("doc_a", scope="x", max_requests=1, window_seconds=60)
    assert exc_info.value.status_code == 429


def test_enforce_doctor_rate_limit_isolated_by_scope_and_doctor() -> None:
    rl.clear_rate_limits_for_tests()
    rl.enforce_doctor_rate_limit("doc_a", scope="x", max_requests=1, window_seconds=60)
    # different scope
    rl.enforce_doctor_rate_limit("doc_a", scope="y", max_requests=1, window_seconds=60)
    # different doctor
    rl.enforce_doctor_rate_limit("doc_b", scope="x", max_requests=1, window_seconds=60)
