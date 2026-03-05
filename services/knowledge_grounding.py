from __future__ import annotations

from typing import Dict, List

from services.knowledge_models import RankedClaim


def build_chat_grounding_bundle(question: str, ranked_claims: List[RankedClaim], limit: int = 3) -> Dict[str, object]:
    snippets: List[Dict[str, object]] = []
    warnings: List[str] = []

    for item in ranked_claims[:max(1, limit)]:
        claim = item.claim
        snippets.append(
            {
                "statement": claim.statement,
                "citation": claim.citation_url,
                "score": item.score,
                "flags": item.flags,
            }
        )
        for flag in item.flags:
            if flag == "stale_evidence":
                warnings.append("Contains stale evidence; verify latest guideline.")
            if flag == "low_confidence":
                warnings.append("Contains low-confidence claim; require doctor review.")

    context_lines = ["Grounding for: %s" % question]
    for idx, snip in enumerate(snippets, start=1):
        context_lines.append("%s) %s (cite: %s)" % (idx, snip["statement"], snip["citation"] or "n/a"))

    return {
        "context_message": "\n".join(context_lines),
        "snippets": snippets,
        "warnings": sorted(set(warnings)),
    }
