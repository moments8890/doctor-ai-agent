from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .models import MatchResult
from .normalizer import expand_aliases, normalize

# ---------------------------------------------------------------------------
# Generic matchers
# ---------------------------------------------------------------------------


def eq(actual: Any, expected: Any) -> MatchResult:
    """Exact equality."""
    passed = actual == expected
    detail = f"expected {expected!r}, got {actual!r}"
    return MatchResult(passed, detail)


def not_empty(actual: Any) -> MatchResult:
    """Actual is truthy (not None, not '', not 0)."""
    passed = bool(actual)
    detail = f"expected truthy value, got {actual!r}"
    return MatchResult(passed, detail)


def empty(actual: Any) -> MatchResult:
    """Actual is falsy."""
    passed = not bool(actual)
    detail = f"expected falsy value, got {actual!r}"
    return MatchResult(passed, detail)


def contains(actual: Any, text: str) -> MatchResult:
    """Text is a substring of str(actual)."""
    haystack = str(actual)
    passed = text in haystack
    detail = f"{'found' if passed else 'did not find'} {text!r} in value"
    return MatchResult(passed, detail)


def contains_any(actual: Any, texts: List[str]) -> MatchResult:
    """Any of texts is a substring of str(actual)."""
    haystack = str(actual)
    found = [t for t in texts if t in haystack]
    passed = len(found) > 0
    if passed:
        detail = f"found {found!r} in value"
    else:
        detail = f"none of {texts!r} found in value"
    return MatchResult(passed, detail)


def not_contains_any(actual: Any, texts: List[str]) -> MatchResult:
    """None of texts is a substring of str(actual)."""
    haystack = str(actual)
    found = [t for t in texts if t in haystack]
    passed = len(found) == 0
    if passed:
        detail = "none of the forbidden texts found"
    else:
        detail = f"unexpectedly found {found!r} in value"
    return MatchResult(passed, detail)


def regex_match(actual: Any, pattern: str) -> MatchResult:
    """re.search(pattern, str(actual)) succeeds."""
    haystack = str(actual)
    match = re.search(pattern, haystack)
    passed = match is not None
    detail = f"pattern {pattern!r} {'matched' if passed else 'did not match'}"
    return MatchResult(passed, detail)


def min_val(actual: Any, n: Any) -> MatchResult:
    """actual >= n (numeric)."""
    try:
        passed = float(actual) >= float(n)
    except (TypeError, ValueError):
        return MatchResult(False, f"cannot compare {actual!r} >= {n!r}")
    detail = f"{actual} {'>='}  {n}" if passed else f"{actual} < {n}"
    return MatchResult(passed, detail)


def max_val(actual: Any, n: Any) -> MatchResult:
    """actual <= n (numeric)."""
    try:
        passed = float(actual) <= float(n)
    except (TypeError, ValueError):
        return MatchResult(False, f"cannot compare {actual!r} <= {n!r}")
    detail = f"{actual} {'<='} {n}" if passed else f"{actual} > {n}"
    return MatchResult(passed, detail)


def count_eq(actual: Any, n: Any) -> MatchResult:
    """len(actual) == n."""
    try:
        length = len(actual)
    except TypeError:
        return MatchResult(False, f"cannot get len() of {type(actual).__name__}")
    expected = int(n)
    passed = length == expected
    detail = f"length {length}, expected {expected}"
    return MatchResult(passed, detail)


# ---------------------------------------------------------------------------
# Clinical matchers
# ---------------------------------------------------------------------------


def _non_empty_field_values(record_fields: Dict[str, str]) -> Dict[str, str]:
    """Return only fields with non-empty values."""
    return {k: v for k, v in record_fields.items() if v}


def fact_present(
    text: str, aliases: List[str], record_fields: Dict[str, str]
) -> MatchResult:
    """Check if fact text (or any alias) appears in ANY record field value.

    Uses normalize() + expand_aliases(). Searches all non-empty field values.
    """
    forms = expand_aliases(text, aliases)
    fields = _non_empty_field_values(record_fields)

    for form in forms:
        for field_name, field_val in fields.items():
            if form in normalize(field_val):
                return MatchResult(True, f"found {form!r} in field {field_name!r}")

    return MatchResult(False, f"fact {text!r} (forms: {forms}) not found in any field")


def fact_in_field(
    text: str,
    allowed_fields: List[str],
    aliases: List[str],
    record_fields: Dict[str, str],
) -> MatchResult:
    """fact_present + verify it's in one of allowed_fields specifically.

    First check if fact is present at all, then check field routing.
    """
    forms = expand_aliases(text, aliases)
    fields = _non_empty_field_values(record_fields)

    # Find which fields contain the fact
    matched_fields: List[str] = []
    matched_form: Optional[str] = None
    for form in forms:
        for field_name, field_val in fields.items():
            if form in normalize(field_val):
                if field_name not in matched_fields:
                    matched_fields.append(field_name)
                if matched_form is None:
                    matched_form = form

    if not matched_fields:
        return MatchResult(
            False, f"fact {text!r} (forms: {forms}) not found in any field"
        )

    # Check if at least one match is in an allowed field
    correct = [f for f in matched_fields if f in allowed_fields]
    if correct:
        return MatchResult(
            True,
            f"found {matched_form!r} in allowed field(s) {correct!r}",
        )

    return MatchResult(
        False,
        f"fact {text!r} found in {matched_fields!r} but not in allowed {allowed_fields!r}",
    )


def forbidden_absent(text: str, record_fields: Dict[str, str]) -> MatchResult:
    """Text does NOT appear in any field (hallucination guard).

    Uses normalize() for matching.
    """
    needle = normalize(text)
    fields = _non_empty_field_values(record_fields)

    for field_name, field_val in fields.items():
        if needle in normalize(field_val):
            return MatchResult(
                False, f"forbidden text {text!r} found in field {field_name!r}"
            )

    return MatchResult(True, f"forbidden text {text!r} absent from all fields")


def numeric_preserved(token: str, record_fields: Dict[str, str]) -> MatchResult:
    """A specific numeric token (e.g. 'EF 45%', 'BP 130/80') appears unmodified in some field.

    Searches raw (unnormalized) field values since numbers must be exact.
    """
    fields = _non_empty_field_values(record_fields)

    for field_name, field_val in fields.items():
        if token in field_val:
            return MatchResult(
                True, f"numeric token {token!r} preserved in field {field_name!r}"
            )

    return MatchResult(
        False, f"numeric token {token!r} not found verbatim in any field"
    )


def _char_overlap_ratio(a: str, b: str) -> float:
    """Compute character-level overlap ratio between two strings."""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    shorter = min(len(set_a), len(set_b))
    if shorter == 0:
        return 0.0
    return len(intersection) / shorter


def duplicate_absent(field_text: str) -> MatchResult:
    """No repeated clause segments within a field (>80% char overlap between segments).

    Split by Chinese comma/period/semicolon, compare each pair.
    """
    if not field_text:
        return MatchResult(True, "empty field, no duplicates")

    # Split by Chinese sentence delimiters
    segments = re.split(r"[，。；]", field_text)
    segments = [s.strip() for s in segments if s.strip()]

    if len(segments) < 2:
        return MatchResult(True, "fewer than 2 segments, no duplicates possible")

    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            ratio = _char_overlap_ratio(segments[i], segments[j])
            if ratio > 0.80:
                return MatchResult(
                    False,
                    f"duplicate detected ({ratio:.0%} overlap): "
                    f"{segments[i]!r} vs {segments[j]!r}",
                )

    return MatchResult(True, f"no duplicate segments among {len(segments)} clauses")


_NEGATION_PREFIXES = ["无", "否认", "未见"]


def negation_present(text: str, record_fields: Dict[str, str]) -> MatchResult:
    """A negation pattern ('无'/'否认'/'未见' + text) appears in some field.

    E.g. text='发热' should match '无发热' or '否认发热'.
    """
    fields = _non_empty_field_values(record_fields)
    patterns = [prefix + text for prefix in _NEGATION_PREFIXES]

    for pattern in patterns:
        norm_pattern = normalize(pattern)
        for field_name, field_val in fields.items():
            if norm_pattern in normalize(field_val):
                return MatchResult(
                    True,
                    f"negation {pattern!r} found in field {field_name!r}",
                )

    return MatchResult(
        False,
        f"no negation of {text!r} (tried {patterns!r}) found in any field",
    )


def brand_generic_match(
    brand: str, generic: str, record_fields: Dict[str, str]
) -> MatchResult:
    """Either brand name or generic name appears in some field.

    E.g. brand='波立维', generic='氯吡格雷' -- either is acceptable.
    """
    fields = _non_empty_field_values(record_fields)
    norm_brand = normalize(brand)
    norm_generic = normalize(generic)

    for field_name, field_val in fields.items():
        norm_val = normalize(field_val)
        if norm_brand in norm_val:
            return MatchResult(
                True, f"brand {brand!r} found in field {field_name!r}"
            )
        if norm_generic in norm_val:
            return MatchResult(
                True, f"generic {generic!r} found in field {field_name!r}"
            )

    return MatchResult(
        False,
        f"neither brand {brand!r} nor generic {generic!r} found in any field",
    )


# ---------------------------------------------------------------------------
# Dispatcher for JSON-driven generic assertions
# ---------------------------------------------------------------------------

MATCHER_DISPATCH = {
    "eq": lambda actual, expected: eq(actual, expected),
    "not_empty": lambda actual, expected: not_empty(actual),
    "empty": lambda actual, expected: empty(actual),
    "contains": lambda actual, expected: contains(actual, expected),
    "contains_any": lambda actual, expected: contains_any(actual, expected),
    "not_contains_any": lambda actual, expected: not_contains_any(actual, expected),
    "regex": lambda actual, expected: regex_match(actual, expected),
    "min": lambda actual, expected: min_val(actual, expected),
    "max": lambda actual, expected: max_val(actual, expected),
    "count_eq": lambda actual, expected: count_eq(actual, expected),
}


def run_matcher(name: str, actual: Any, expected: Any = None) -> MatchResult:
    """Look up a generic matcher by name and run it."""
    fn = MATCHER_DISPATCH.get(name)
    if fn is None:
        return MatchResult(False, f"Unknown matcher: {name}")
    return fn(actual, expected)
