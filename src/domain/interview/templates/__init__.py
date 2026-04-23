"""Template registry. Populated by templates/medical_general.py + future variants."""
from __future__ import annotations

from domain.interview.protocols import Template


class UnknownTemplate(KeyError):
    """Raised when a session references a template id not in TEMPLATES."""


TEMPLATES: dict[str, Template] = {}


def get_template(template_id: str) -> Template:
    if template_id not in TEMPLATES:
        raise UnknownTemplate(template_id)
    return TEMPLATES[template_id]
