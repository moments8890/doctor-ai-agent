"""Test that draft_reply generates drafts even without KB citations."""
from domain.patient_lifecycle.draft_reply import DraftReplyResult


def test_draft_result_allows_empty_citations():
    """DraftReplyResult can be created with empty cited_knowledge_ids."""
    result = DraftReplyResult(
        text="恢复情况不错，继续观察。",
        cited_knowledge_ids=[],
        confidence=0.9,
    )
    assert result.text == "恢复情况不错，继续观察。"
    assert result.cited_knowledge_ids == []


def test_draft_result_with_citations():
    """DraftReplyResult with citations still works."""
    result = DraftReplyResult(
        text="头痛是正常的。 [KB-3]",
        cited_knowledge_ids=[3],
        confidence=0.9,
    )
    assert result.cited_knowledge_ids == [3]
