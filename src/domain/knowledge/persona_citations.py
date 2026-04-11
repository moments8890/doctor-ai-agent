# src/domain/knowledge/persona_citations.py
"""Parse and log [P-xxx] persona citations from LLM output."""

import re
from typing import List

_PERSONA_CITATION_RE = re.compile(r"\[P-(ps_[a-z0-9]+)\]")


def extract_persona_citations(text: str) -> List[str]:
    """Extract persona rule IDs from [P-ps_xxx] markers in text."""
    return _PERSONA_CITATION_RE.findall(text)


def strip_persona_citations(text: str) -> str:
    """Remove [P-xxx] markers from text for user-facing display."""
    return _PERSONA_CITATION_RE.sub("", text).strip()
