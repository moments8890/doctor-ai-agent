from __future__ import annotations

from typing import List

from services.knowledge_models import RankedClaim


def build_knowledge_digest(ranked_claims: List[RankedClaim], top_k: int = 5) -> str:
    lines = ["# Knowledge Digest", ""]
    for idx, item in enumerate(ranked_claims[:max(1, top_k)], start=1):
        claim = item.claim
        cite = claim.citation_url or "citation_unavailable"
        flags = ", ".join(item.flags) if item.flags else "none"
        lines.append("%s. %s" % (idx, claim.statement))
        lines.append("   - Score: %.3f" % item.score)
        lines.append("   - Evidence: %s | Flags: %s" % (claim.evidence_level, flags))
        lines.append("   - Citation: %s" % cite)
    lines.append("")
    lines.append("Safety note: verify against local policy and patient context before action.")
    return "\n".join(lines)
