import pytest
from db.models.message_draft import MessageDraft, DraftStatus


def test_draft_status_enum():
    assert DraftStatus.generated.value == "generated"
    assert DraftStatus.sent.value == "sent"
    assert DraftStatus.stale.value == "stale"


def test_draft_status_all_values():
    expected = {"generated", "edited", "sent", "dismissed", "stale"}
    actual = {s.value for s in DraftStatus}
    assert actual == expected


def test_message_draft_creation():
    draft = MessageDraft(
        doctor_id="doc_1",
        patient_id="pat_1",
        source_message_id=1,
        draft_text="测试回复",
        status=DraftStatus.generated.value,
        ai_disclosure="AI辅助生成，经医生审核",
    )
    assert draft.draft_text == "测试回复"
    assert draft.doctor_id == "doc_1"
    assert draft.patient_id == "pat_1"
    assert draft.source_message_id == 1
    assert draft.status == "generated"
    assert draft.ai_disclosure == "AI辅助生成，经医生审核"


def test_message_draft_optional_fields():
    draft = MessageDraft(
        doctor_id="doc_1",
        patient_id="pat_1",
        source_message_id=1,
        draft_text="回复",
        status=DraftStatus.generated.value,
    )
    assert draft.edited_text is None
    assert draft.cited_knowledge_ids is None
    assert draft.confidence is None
