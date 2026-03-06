from __future__ import annotations

from typing import Dict, List, Tuple

from services.knowledge_models import KnowledgeDocument, KnowledgeSource


def curate_knowledge_documents(
    source: KnowledgeSource,
    docs: List[KnowledgeDocument],
    min_trust_tier: int = 2,
) -> Tuple[List[KnowledgeDocument], List[str], Dict[str, int]]:
    """Filter by trust tier and dedupe by source+title+day."""
    accepted: List[KnowledgeDocument] = []
    rejected: List[str] = []
    seen = set()

    if source.trust_tier < min_trust_tier:
        return [], ["source_trust_tier_below_threshold"], {
            "accepted": 0,
            "rejected": len(docs),
            "duplicates": 0,
        }

    duplicates = 0
    for doc in docs:
        key = (doc.source_id, doc.title.strip().lower(), doc.published_at.date().isoformat())
        if key in seen:
            duplicates += 1
            rejected.append("duplicate:%s" % doc.document_id)
            continue
        seen.add(key)
        if not doc.content.strip():
            rejected.append("empty_content:%s" % doc.document_id)
            continue
        accepted.append(doc)

    summary = {
        "accepted": len(accepted),
        "rejected": len(rejected),
        "duplicates": duplicates,
    }
    return accepted, rejected, summary
