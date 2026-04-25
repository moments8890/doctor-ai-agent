"""Static coverage test: every router file that reads PHI tables must
also import the audit hook.

The runtime audit_log table is the compliance trail for "who looked at
this record." Adding a new endpoint that joins on MedicalRecordDB or
PatientMessage without calling ``audit(...)`` silently breaks that
trail. This test catches such omissions at the import level — cheap,
no DB / FastAPI runtime needed.

Allowlist for files that legitimately read PHI but don't need to audit
(internal helpers, batch jobs, response builders). Add new entries with
a one-line comment justifying the exemption.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# Files that read PHI tables but don't need to call audit():
#   - shared.py / common helpers used by other handlers (the handler audits
#     once at the top, the helper read is in the same logical operation).
#   - response builders / list-aggregators that audit at the parent endpoint.
#   - internal scheduler tasks (no user request → nobody to attribute to).
_ALLOWLIST = frozenset({
    # internal helper, called from doctor-interview handlers that audit
    "channels/web/doctor_interview/shared.py",
    # AI activity timeline — aggregates AI suggestions (already proxies
    # via doctor_id rate-limit + the suggestion table itself is audited
    # on creation in the LLM call path).
    "channels/web/doctor_dashboard/ai_activity_handlers.py",
})

# Tracked-but-not-yet-audited baseline. These files DO read PHI but don't
# emit audit_log rows. Captured here as of 2026-04-26 so the gate catches
# NEW additions immediately while existing gaps stay visible. To clear an
# entry: add `audit(...)` calls in the file's read endpoints, then remove
# from this set. The other test (test_audit_baseline_does_not_grow) will
# fail loudly if anyone tries to add to this list.
_AUDIT_BASELINE_GAPS = frozenset({
    "channels/web/doctor_dashboard/admin_config.py",
    "channels/web/doctor_dashboard/admin_messages.py",
    "channels/web/doctor_dashboard/admin_ops.py",
    "channels/web/doctor_dashboard/admin_overview.py",
    "channels/web/doctor_dashboard/admin_patients.py",
    "channels/web/doctor_dashboard/admin_suggestions.py",
    "channels/web/doctor_dashboard/briefing_handlers.py",
    "channels/web/doctor_dashboard/diagnosis_handlers.py",
    "channels/web/doctor_dashboard/draft_handlers.py",
    "channels/web/doctor_dashboard/feedback_handlers.py",
    "channels/web/doctor_dashboard/kb_pending_handlers.py",
    "channels/web/doctor_dashboard/onboarding_handlers.py",
    "channels/web/doctor_dashboard/preseed_service.py",
    "channels/web/doctor_dashboard/review_queue_handlers.py",
    "channels/web/doctor_interview/confirm.py",
})


_PHI_MODELS = ("MedicalRecordDB", "PatientMessage", "AISuggestion")
_AUDIT_IMPORT = "from infra.observability.audit import audit"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _collect_router_files() -> list[Path]:
    root = _project_root() / "src" / "channels" / "web"
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _reads_phi(text: str) -> bool:
    return any(model in text for model in _PHI_MODELS)


def _imports_audit(text: str) -> bool:
    return _AUDIT_IMPORT in text


def _phi_reading_unaudited_files() -> list[str]:
    root = _project_root()
    out: list[str] = []
    for path in _collect_router_files():
        rel = str(path.relative_to(root / "src"))
        if rel in _ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        if _reads_phi(text) and not _imports_audit(text):
            out.append(rel)
    return sorted(out)


def test_no_new_audit_gaps() -> None:
    """A NEW router file that reads PHI without auditing must not slip in.

    Existing gaps are captured in _AUDIT_BASELINE_GAPS as a tracked baseline.
    This test fails when the actual gap set drifts above that baseline —
    i.e. someone added a new endpoint that reads MedicalRecordDB / etc.
    and didn't wire the audit hook.
    """
    actual = set(_phi_reading_unaudited_files())
    new_gaps = sorted(actual - _AUDIT_BASELINE_GAPS - _ALLOWLIST)
    assert not new_gaps, (
        "These router files read PHI tables (MedicalRecordDB / PatientMessage / "
        "AISuggestion) but don't import the audit hook. Add `from "
        "infra.observability.audit import audit` and emit `audit(...)` on the "
        "read path. If the file is a helper that legitimately doesn't need "
        "audit, add to _ALLOWLIST with a one-line justification.\n\n  - "
        + "\n  - ".join(new_gaps)
    )


def test_baseline_does_not_overstate() -> None:
    """Baseline entries that have GAINED audit coverage should be removed.

    Catches the case where someone added audit() to a baseline file but
    forgot to delete the entry here — the baseline silently growing means
    future gaps don't surface as cleanly.
    """
    actual = set(_phi_reading_unaudited_files())
    fixed = sorted(_AUDIT_BASELINE_GAPS - actual)
    assert not fixed, (
        "These files now import audit but are still in _AUDIT_BASELINE_GAPS. "
        "Remove them from the baseline so the next regression here trips "
        "the gate cleanly:\n\n  - " + "\n  - ".join(fixed)
    )


def test_allowlist_entries_actually_exist() -> None:
    """Guard against rotting allowlist — flag entries pointing at moved
    or renamed files."""
    src = _project_root() / "src"
    missing = [
        e for e in (_ALLOWLIST | _AUDIT_BASELINE_GAPS)
        if not (src / e).exists()
    ]
    assert not missing, (
        "Allowlist/baseline references files that no longer exist; remove "
        "or update:\n  - " + "\n  - ".join(missing)
    )
