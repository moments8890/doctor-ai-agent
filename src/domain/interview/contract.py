"""LLM structured-output contract synthesis.

Spec §3e. This is the single point where FieldSpec becomes a Pydantic class
for validating an LLM response. The class is throwaway — every caller
converts the validated instance back to dict before returning.

Vocabulary is frozen. To add a new type, update `_SPEC_TO_PY_TYPE` here and
add a FieldSpec.type literal + a test.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model

from domain.interview.protocols import FieldSpec

# Frozen mapping. Widen only via PR + tests.
_SPEC_TO_PY_TYPE: dict[str, type] = {
    "string": str,
    "text": str,      # same validation; distinction is an LLM hint
    "number": int,
}


def _enum_type(name: str, values: tuple[str, ...]) -> type:
    """Build a str-Enum so Pydantic validates inputs to the vocabulary set."""
    return Enum(f"{name}_enum", {v: v for v in values}, type=str)


def build_response_schema(fields: list[FieldSpec]) -> type[BaseModel]:
    """Return a throwaway Pydantic class whose attributes mirror `fields`.

    Required tier fields become non-nullable; recommended/optional are
    `Optional[...]` with `None` default. The class is created fresh on every
    call — no caching — so that repeated builds never alias each other.
    """
    attrs: dict[str, Any] = {}
    for f in fields:
        if f.type == "enum":
            assert f.enum_values is not None  # FieldSpec validator guarantees
            py_type: type = _enum_type(f.name, f.enum_values)
        else:
            try:
                py_type = _SPEC_TO_PY_TYPE[f.type]
            except KeyError as e:
                raise ValueError(
                    f"build_response_schema: unsupported type {f.type!r} on "
                    f"field {f.name!r}. Add it to _SPEC_TO_PY_TYPE."
                ) from e

        if f.tier == "required":
            default = ...
            anno = py_type
        else:
            default = None
            anno = Optional[py_type]

        attrs[f.name] = (anno, Field(default, description=f.description))

    return create_model("ExtractedFields", **attrs)
