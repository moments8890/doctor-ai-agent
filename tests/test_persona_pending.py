from db.models.persona_pending import PersonaPendingItem


def test_pending_item_defaults():
    item = PersonaPendingItem(
        doctor_id="doc_1",
        field="reply_style",
        proposed_rule="口语化回复",
        summary="偏好口语化",
        evidence_summary="把正式表达改成了口语化",
    )
    assert item.field == "reply_style"
    assert item.proposed_rule == "口语化回复"


def test_pending_item_fields():
    item = PersonaPendingItem(
        doctor_id="doc_1",
        field="avoid",
        proposed_rule="不提风险",
        summary="回避风险描述",
        evidence_summary="删除了风险段落",
        confidence="high",
        pattern_hash="abc123",
        status="pending",
    )
    assert item.confidence == "high"
    assert item.pattern_hash == "abc123"
    assert item.status == "pending"
