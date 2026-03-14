"""Knowledge management: PDF extraction and per-doctor knowledge items."""
from services.knowledge.pdf_extract import extract_text_from_pdf
from services.knowledge.word_extract import extract_text_from_docx


def __getattr__(name: str):
    """Lazy-load doctor_knowledge to avoid import-time DB engine side effects."""
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
    "extract_text_from_docx",
    "extract_text_from_pdf",
    "invalidate_knowledge_cache",
    "knowledge_limits",
    "load_knowledge_context_for_prompt",
    "maybe_auto_learn_knowledge",
    "parse_add_to_knowledge_command",
    "render_knowledge_context",
    "save_knowledge_item",
]
