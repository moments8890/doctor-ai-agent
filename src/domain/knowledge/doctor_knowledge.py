"""
医生个人知识库管理：thin re-export hub.

All public symbols are defined in the focused sub-modules:
  - knowledge_crud.py     — save/invalidate, encode/decode, parse command, limits
  - knowledge_context.py  — render context, load, cache
  - knowledge_ingest.py   — extract document, LLM process, save uploaded
"""

from domain.knowledge.knowledge_crud import (
    extract_title_from_text,
    invalidate_knowledge_cache,
    knowledge_limits,
    parse_add_to_knowledge_command,
    save_knowledge_item,
)
from domain.knowledge.knowledge_context import (
    load_knowledge,
    load_knowledge_context_for_prompt,
    render_knowledge_context,
)
from domain.knowledge.knowledge_ingest import (
    extract_and_process_document,
    process_knowledge_text,
    save_uploaded_knowledge,
)

__all__ = [
    # crud
    "extract_title_from_text",
    "invalidate_knowledge_cache",
    "knowledge_limits",
    "parse_add_to_knowledge_command",
    "save_knowledge_item",
    # context
    "load_knowledge",
    "load_knowledge_context_for_prompt",
    "render_knowledge_context",
    # ingest
    "extract_and_process_document",
    "process_knowledge_text",
    "save_uploaded_knowledge",
]
