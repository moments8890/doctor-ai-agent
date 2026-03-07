from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from .models import KnowledgeDocument, KnowledgeSource


def crawl_knowledge_source(
    source: KnowledgeSource,
    checkpoint: datetime,
    limit: int = 10,
) -> Tuple[List[KnowledgeDocument], datetime]:
    """Deterministic mock crawl with resumable checkpoint."""
    safe_limit = max(1, min(limit, 50))
    docs: List[KnowledgeDocument] = []
    for index in range(safe_limit):
        published_at = checkpoint + timedelta(minutes=index + 1)
        doc_id = "%s-%s" % (source.source_id, published_at.strftime("%Y%m%d%H%M"))
        docs.append(
            KnowledgeDocument(
                document_id=doc_id,
                source_id=source.source_id,
                title="%s update %s" % (source.title, index + 1),
                content="Deterministic content for %s" % source.title,
                published_at=published_at,
                url=source.url,
                tags=["auto", source.source_type],
            )
        )
    return docs, docs[-1].published_at if docs else checkpoint


def crawl_knowledge_sources(
    sources: List[KnowledgeSource],
    checkpoint: datetime,
    limit_per_source: int = 10,
) -> List[KnowledgeDocument]:
    out: List[KnowledgeDocument] = []
    for source in sources:
        docs, _ = crawl_knowledge_source(source, checkpoint, limit=limit_per_source)
        out.extend(docs)
    return out
