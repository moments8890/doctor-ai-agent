from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class KnowledgeSource:
    source_id: str
    source_type: str
    title: str
    publisher: str
    trust_tier: int
    url: Optional[str] = None


@dataclass
class KnowledgeDocument:
    document_id: str
    source_id: str
    title: str
    content: str
    published_at: datetime
    url: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class KnowledgeClaim:
    claim_id: str
    document_id: str
    statement: str
    specialty: str
    evidence_level: str
    confidence: float
    published_at: datetime
    citation_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class RankedClaim:
    claim: KnowledgeClaim
    score: float
    breakdown: Dict[str, float]
    flags: List[str]
