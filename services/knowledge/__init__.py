"""services.knowledge 包初始化：临床知识管理子模块。

Knowledge management submodule.

Provides clinical knowledge crawling, curation, ranking, grounding,
guideline diffing, PDF extraction, and doctor-level knowledge management.

doctor_knowledge imports are lazy to avoid pulling DB engine at import time.
"""

from .models import KnowledgeClaim, KnowledgeDocument, KnowledgeSource, RankedClaim
from .crawl import crawl_knowledge_source, crawl_knowledge_sources
from .curation import curate_knowledge_documents
from .digest import build_knowledge_digest
from .grounding import build_chat_grounding_bundle
from .ranker import rank_knowledge_claims
from .guideline_diff import diff_guideline_snapshots
from .pdf_extract import extract_text_from_pdf


def __getattr__(name: str):
    """Lazy-load doctor_knowledge symbols to avoid import-time DB engine side effects."""
    _DOCTOR_KNOWLEDGE_NAMES = {
        "maybe_auto_learn_knowledge",
        "save_knowledge_item",
        "load_knowledge_context_for_prompt",
        "invalidate_knowledge_cache",
        "parse_add_to_knowledge_command",
        "render_knowledge_context",
        "knowledge_limits",
    }
    if name in _DOCTOR_KNOWLEDGE_NAMES:
        from . import doctor_knowledge
        return getattr(doctor_knowledge, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "KnowledgeClaim",
    "KnowledgeDocument",
    "KnowledgeSource",
    "RankedClaim",
    "crawl_knowledge_source",
    "crawl_knowledge_sources",
    "curate_knowledge_documents",
    "build_knowledge_digest",
    "build_chat_grounding_bundle",
    "rank_knowledge_claims",
    "diff_guideline_snapshots",
    "extract_text_from_pdf",
    "load_knowledge_context_for_prompt",
    "invalidate_knowledge_cache",
    "parse_add_to_knowledge_command",
    "render_knowledge_context",
    "knowledge_limits",
    "save_knowledge_item",
    "maybe_auto_learn_knowledge",
]
