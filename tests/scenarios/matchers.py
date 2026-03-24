"""Assertion matchers for scenario tests."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def assert_equals(actual: Any, expected: Any, path: str) -> None:
    assert actual == expected, f"{path}: expected {expected!r}, got {actual!r}"


def assert_exists(value: Any, path: str) -> None:
    assert value is not None and value != "", f"{path}: expected to exist, got {value!r}"


def assert_contains(text: str, keyword: str, path: str) -> None:
    assert keyword in (text or ""), f"{path}: expected to contain {keyword!r}, got {(text or '')[:200]!r}"


def assert_contains_any(text: str, keywords: List[str], path: str) -> None:
    text = text or ""
    assert any(k in text for k in keywords), f"{path}: expected any of {keywords}, got {text[:200]!r}"


def assert_not_contains_any(text: str, keywords: List[str], path: str) -> None:
    text = text or ""
    found = [k for k in keywords if k in text]
    assert not found, f"{path}: must NOT contain {found}, but found in {text[:200]!r}"


def assert_min_count(actual: int, minimum: int, path: str) -> None:
    assert actual >= minimum, f"{path}: expected >= {minimum}, got {actual}"


def check_expectation(actual: Any, op: str, expected: Any, path: str) -> None:
    """Dispatch assertion based on operator string."""
    if op == "equals":
        assert_equals(actual, expected, path)
    elif op == "exists":
        assert_exists(actual, path)
    elif op == "contains":
        assert_contains(str(actual), expected, path)
    elif op == "contains_any":
        assert_contains_any(str(actual), expected, path)
    elif op == "not_contains_any":
        assert_not_contains_any(str(actual), expected, path)
    elif op == "min_count":
        assert_min_count(int(actual), int(expected), path)
    else:
        raise ValueError(f"Unknown matcher op: {op}")
