"""
基于关键词、正则和临床启发式规则的快速意图路由，无需调用 LLM，90% 以上的指令在 1ms 内响应。

Package re-exports the same public API as the old ``services/ai/fast_router.py`` module.
All keyword frozensets are now static immutable literals compiled into _keywords.py.
The only mutable global remaining is ``_mined_rules._MINED_RULES``, which is proxied
via a minimal custom module class so that ``fr._MINED_RULES`` still works in tests.
"""

from __future__ import annotations

import sys
import types

# ── Sub-module imports (order matters for dependency graph) ───────────────────
from . import _keywords
from . import _patterns
from . import _patient_guard
from . import _tier3
from . import _mined_rules
from . import _session
from . import _router

# ── Public API re-exports ─────────────────────────────────────────────────────
from ._keywords import (
    _EMERGENCY_KW,
    _CLINICAL_KW_TIER3,
    _IMPORT_KEYWORDS,
    _LIST_PATIENTS_EXACT,
    _LIST_PATIENTS_SHORT,
    _LIST_TASKS_EXACT,
    _LIST_TASKS_SHORT,
    _NON_NAME_KEYWORDS,
    _TIER3_BAD_NAME,
)
from ._mined_rules import load_mined_rules, reload_mined_rules
from ._router import fast_route, fast_route_label, _fast_route_core
from ._session import _apply_session_context, _PATIENT_NAME_INTENTS
from ._tier3 import _is_clinical_tier3, _extract_tier3_demographics
from ._patient_guard import _is_patient_question
from ._patterns import _normalise, _extract_demographics


# ── Transparent proxy for the one remaining mutable global ────────────────────
# Tests do ``fr._MINED_RULES = [...]`` and ``x = fr._MINED_RULES`` to inject
# fixtures. Since _MINED_RULES is the only mutable global left, a minimal custom
# module class handles both get and set.

class _FastRouterPackage(types.ModuleType):
    def __getattr__(self, name: str):
        if name == '_MINED_RULES':
            from . import _mined_rules as _mr
            return _mr._MINED_RULES
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value):
        if name == '_MINED_RULES':
            from . import _mined_rules as _mr
            _mr._MINED_RULES = value
        else:
            super().__setattr__(name, value)


# MUST be last — after all module-level assignments are done
sys.modules[__name__].__class__ = _FastRouterPackage
