"""Template registry. Populated on import."""
from __future__ import annotations

from domain.interview.protocols import Template
from domain.interview.templates.medical_general import GeneralMedicalTemplate
from domain.interview.templates.form_satisfaction import FormSatisfactionTemplate


class UnknownTemplate(KeyError):
    """Raised when a session references a template id not in TEMPLATES."""


TEMPLATES: dict[str, Template] = {
    "medical_general_v1": GeneralMedicalTemplate(),
    "form_satisfaction_v1": FormSatisfactionTemplate(),
}


def get_template(template_id: str) -> Template:
    if template_id not in TEMPLATES:
        raise UnknownTemplate(template_id)
    return TEMPLATES[template_id]
