"""Smoke tests for the patient chat dispatcher.

Catches the class of bug where a deleted helper is still referenced from
an active branch — exactly what happened when _legacy_triage_dispatch was
removed but chat.py kept calling it from the idle non-intake path.

These tests import chat.py and walk its AST for unresolved local-looking
function references, accounting for both module-level and function-local
imports.
"""
from __future__ import annotations

import ast


def test_chat_module_imports() -> None:
    """The patient chat dispatcher module must import without error."""
    from channels.web.patient_portal import chat

    assert hasattr(chat, "post_chat")
    assert hasattr(chat, "_intake_dispatch")
    assert hasattr(chat, "chat_router")


def _collect_imported_or_defined_names(tree: ast.AST) -> set[str]:
    """Walk the tree and collect every name that's imported or defined.

    Handles module-level and function-local imports, function/class defs,
    and assignment targets. Best-effort — covers the realistic patterns
    used in chat.py.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_chat_module_has_no_undefined_local_calls() -> None:
    """Every underscore-prefixed Name call in chat.py must resolve."""
    import channels.web.patient_portal.chat as chat_mod

    src_path = chat_mod.__file__
    assert src_path is not None
    with open(src_path) as f:
        tree = ast.parse(f.read())

    known = _collect_imported_or_defined_names(tree) | set(dir(chat_mod))

    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name.startswith("_") and name not in known:
                issues.append(f"line {node.lineno}: undefined call to {name!r}")

    assert not issues, "chat.py has undefined references: " + "; ".join(issues)


def test_chat_router_endpoint_contract() -> None:
    """Lock the chat router's public endpoints + response shapes.

    Catches regressions where an endpoint gets dropped (like the
    ``_legacy_triage_dispatch`` deletion that lost the idle non-intake
    fallback) or a response model loses fields the frontend depends on
    (like ``ChatResponse.suggestions`` / ``session_id`` for the chips
    + banner UI).
    """
    from channels.web.patient_portal.chat import (
        ChatResponse,
        IntakeStatusResponse,
        chat_router,
    )

    paths = sorted({route.path for route in chat_router.routes})
    expected_paths = {
        "/chat",
        "/chat/messages",
        "/chat/intake/status",
        "/chat/confirm",
        "/chat/intake/update_field",
        "/chat/intake/confirm_all_carry_forward",
        "/messages/{message_id}/read",
    }
    missing = expected_paths - set(paths)
    assert not missing, f"chat router lost endpoints: {missing}"

    # ChatResponse must carry the fields the frontend banner + chips read.
    chat_resp_fields = set(ChatResponse.model_fields.keys())
    required_chat_fields = {
        "reply", "triage_category", "ai_handled",
        "suggestions", "session_id", "turn_count", "intake_active",
    }
    assert required_chat_fields.issubset(chat_resp_fields), (
        f"ChatResponse missing frontend-required fields: "
        f"{required_chat_fields - chat_resp_fields}"
    )

    # IntakeStatusResponse must let the frontend rehydrate after reload.
    status_fields = set(IntakeStatusResponse.model_fields.keys())
    assert status_fields.issuperset({"has_active", "session_id", "turn_count", "status"})


def test_chat_module_does_not_reference_dead_modules() -> None:
    """Forbid imports of modules deleted in the intake redesign.

    After alembic 6a5d3c2e1f47 + the chat.py rewire, these modules are gone:
      - domain.patient_lifecycle.signal_flag
      - domain.patient_lifecycle.chat_state
      - domain.patient_lifecycle.chat_state_store
      - domain.patient_lifecycle.retraction
    Plus FieldEntryDB is dropped from db.models.records. Any ImportError
    here means we re-introduced a dead reference and prod will break on
    the import (much like the original _legacy_triage_dispatch bug).
    """
    import channels.web.patient_portal.chat as chat_mod

    src_path = chat_mod.__file__
    assert src_path is not None
    with open(src_path) as f:
        source = f.read()

    forbidden = [
        "domain.patient_lifecycle.signal_flag",
        "domain.patient_lifecycle.chat_state",
        "domain.patient_lifecycle.chat_state_store",
        "domain.patient_lifecycle.retraction",
        "FieldEntryDB",
    ]
    issues: list[str] = []
    for needle in forbidden:
        if needle in source:
            issues.append(f"chat.py references deleted symbol: {needle!r}")
    assert not issues, "; ".join(issues)
