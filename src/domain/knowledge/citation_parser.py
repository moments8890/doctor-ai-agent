"""Citation parser — extract and validate [KB-{id}] markers from LLM output."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set

from utils.log import log

# Matches [KB-123] but NOT \[KB-123] (escaped by sanitizer).
_CITATION_RE = re.compile(r"(?<!\\)\[KB-(\d+)\]")


@dataclass
class CitationResult:
    cited_ids: List[int] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class ValidationResult:
    valid_ids: List[int] = field(default_factory=list)
    hallucinated_ids: List[int] = field(default_factory=list)


def extract_citations(text: str) -> CitationResult:
    """Extract deduplicated KB citation IDs from *text*, preserving first-occurrence order.

    Works on free text and JSON-embedded strings (the regex operates on the raw
    character stream so citations inside JSON string values are matched too).
    """
    seen: Set[int] = set()
    ids: List[int] = []
    for m in _CITATION_RE.finditer(text):
        kb_id = int(m.group(1))
        if kb_id not in seen:
            seen.add(kb_id)
            ids.append(kb_id)
    return CitationResult(cited_ids=ids, raw_text=text)


def validate_citations(
    extracted_ids: List[int],
    valid_kb_ids: Set[int],
) -> ValidationResult:
    """Partition *extracted_ids* into valid (exist in doctor's KB) and hallucinated."""
    valid: List[int] = []
    hallucinated: List[int] = []
    for kb_id in extracted_ids:
        if kb_id in valid_kb_ids:
            valid.append(kb_id)
        else:
            hallucinated.append(kb_id)
    if hallucinated:
        log("Hallucinated KB citations", level="warning", ids=hallucinated)
    return ValidationResult(valid_ids=valid, hallucinated_ids=hallucinated)
