"""Intent types for the Plan-and-Act routing pipeline."""
from __future__ import annotations

from agent.types import IntentType

# Backwards compat alias
Action = IntentType

# UI chip actions — subset exposed to frontend for quick-action buttons
CHIP_ACTIONS = {
    IntentType.create_record,
    IntentType.query_patient,
}
