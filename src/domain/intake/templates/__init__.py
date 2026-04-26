"""Template registry. Populated on import."""
from __future__ import annotations

from domain.intake.protocols import Template
from domain.intake.templates.medical_general import GeneralMedicalTemplate
from domain.intake.templates.medical_neuro import GeneralNeuroTemplate
from domain.intake.templates.form_satisfaction import FormSatisfactionTemplate


class UnknownTemplate(KeyError):
    """Raised when a session references a template id not in TEMPLATES."""


TEMPLATES: dict[str, Template] = {
    "medical_general_v1": GeneralMedicalTemplate(),
    "medical_neuro_v1": GeneralNeuroTemplate(),
    "form_satisfaction_v1": FormSatisfactionTemplate(),
}


def get_template(template_id: str) -> Template:
    if template_id not in TEMPLATES:
        raise UnknownTemplate(template_id)
    return TEMPLATES[template_id]
