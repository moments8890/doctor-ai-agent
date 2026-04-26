"""Interview turn module — verify key exports still exist."""


def test_interview_turn_exports_field_labels():
    from domain.patients.interview_turn import FIELD_LABELS
    assert "chief_complaint" in FIELD_LABELS
    assert "present_illness" in FIELD_LABELS


def test_interview_turn_exports_build_progress():
    from domain.patients.interview_turn import _build_progress
    progress = _build_progress({"chief_complaint": "头痛"}, mode="patient")
    assert progress["filled"] == 1
    assert progress["total"] > 0


def test_build_progress_doctor_mode_includes_all_fields():
    from domain.patients.interview_turn import _build_progress
    progress = _build_progress({}, mode="doctor")
    # Doctor mode should include all 13 clinical fields
    assert progress["total"] == 13


def test_build_progress_patient_mode_limited_fields():
    from domain.patients.interview_turn import _build_progress
    progress = _build_progress({}, mode="patient")
    # Patient mode shows only the 7 subjective fields
    assert progress["total"] == 7
