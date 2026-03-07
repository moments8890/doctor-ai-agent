from __future__ import annotations

from datetime import datetime
from typing import List

from .models import KnowledgeClaim, RankedClaim


_EVIDENCE_WEIGHT = {
    "high": 1.0,
    "moderate": 0.7,
    "low": 0.4,
}


def rank_knowledge_claims(
    claims: List[KnowledgeClaim],
    specialty: str,
    now: datetime,
) -> List[RankedClaim]:
    ranked: List[RankedClaim] = []
    for claim in claims:
        specialty_match = 1.0 if claim.specialty == specialty else 0.4
        evidence_quality = _EVIDENCE_WEIGHT.get(claim.evidence_level, 0.3)
        age_days = max(0.0, (now - claim.published_at).total_seconds() / 86400.0)
        freshness = max(0.0, 1.0 - min(age_days, 365.0) / 365.0)
        confidence = max(0.0, min(1.0, claim.confidence))
        score = round(40 * evidence_quality + 30 * specialty_match + 20 * freshness + 10 * confidence, 3)

        flags: List[str] = []
        if age_days > 180:
            flags.append("stale_evidence")
        if confidence < 0.6:
            flags.append("low_confidence")

        ranked.append(
            RankedClaim(
                claim=claim,
                score=score,
                breakdown={
                    "evidence_quality": evidence_quality,
                    "specialty_match": specialty_match,
                    "freshness": freshness,
                    "confidence": confidence,
                },
                flags=flags,
            )
        )

    return sorted(ranked, key=lambda item: item.score, reverse=True)
