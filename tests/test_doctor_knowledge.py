"""医生知识库单元测试：覆盖知识条目的解析、渲染、自动学习和错误降级逻辑。"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from db.models import DoctorKnowledgeItem
from services.knowledge import doctor_knowledge as dk


def _item(item_id: int, content: str) -> DoctorKnowledgeItem:
    now = datetime.now(timezone.utc)
    return DoctorKnowledgeItem(
        id=item_id,
        doctor_id="doc-1",
        content=content,
        created_at=now,
        updated_at=now,
    )


def test_parse_add_to_knowledge_command():
    assert dk.parse_add_to_knowledge_command("add_to_knowledge_base 胸痛先排除ACS") == "胸痛先排除ACS"
    assert dk.parse_add_to_knowledge_command("添加知识库：高血压先评估靶器官损害") == "高血压先评估靶器官损害"
    assert dk.parse_add_to_knowledge_command("add_to_knowledge_base") == ""
    assert dk.parse_add_to_knowledge_command("你好") is None


def test_render_knowledge_context_limits(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MAX_ITEMS", "2")
    monkeypatch.setenv("KNOWLEDGE_MAX_CHARS", "90")
    monkeypatch.setenv("KNOWLEDGE_MAX_ITEM_CHARS", "16")
    items = [
        _item(1, "胸痛患者优先完成心电图和肌钙蛋白评估，必要时绿色通道。"),
        _item(2, "慢性咳嗽先做胸片排除感染。"),
        _item(3, "糖尿病足换药周期按渗出情况调整。"),
    ]

    rendered = dk.render_knowledge_context("胸痛伴出汗", items)
    assert "医生知识库" in rendered
    assert "胸痛患者优先完成" in rendered
    assert len(rendered.splitlines()) <= 3  # header + up to 2 items
    assert len(rendered) <= 90


async def test_load_knowledge_context_for_prompt_uses_db_limit(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_CANDIDATE_LIMIT", "12")
    mocked_items = [SimpleNamespace(content="胸痛优先排除ACS")]
    with patch("services.knowledge.doctor_knowledge.list_doctor_knowledge_items", new=AsyncMock(return_value=mocked_items)) as mocked:
        rendered = await dk.load_knowledge_context_for_prompt(object(), "doc-1", "胸痛")
    mocked.assert_awaited_once()
    assert mocked.await_args.kwargs["limit"] == 12
    assert "胸痛优先排除ACS" in rendered


def test_decode_payload_supports_plain_and_json():
    text, source, confidence = dk._decode_knowledge_payload("普通知识")
    assert text == "普通知识"
    assert source == "doctor"
    assert confidence == 1.0

    raw = dk._encode_knowledge_payload("自动知识", source="agent_auto", confidence=0.6)
    text2, source2, confidence2 = dk._decode_knowledge_payload(raw)
    assert text2 == "自动知识"
    assert source2 == "agent_auto"
    assert confidence2 == 0.6


def test_decode_payload_logs_and_falls_back_on_malformed_json():
    malformed = '{"text":"abc",'
    with patch("services.knowledge.doctor_knowledge.log") as mocked_log:
        text, source, confidence = dk._decode_knowledge_payload(malformed)
    assert text == malformed
    assert source == "doctor"
    assert confidence == 1.0
    assert mocked_log.called


def test_extract_auto_candidates_from_text_and_fields():
    fields = {"diagnosis": "高血压3级", "treatment_plan": "先口服降压药", "follow_up_plan": "两周复查血压"}
    out = dk._extract_auto_candidates("建议先低盐饮食再调整用药。", fields)
    assert len(out) >= 2
    assert any("临床处理经验" in x for x in out)
    assert any("随访要点" in x for x in out)


async def test_maybe_auto_learn_knowledge_logs_and_continues_on_save_error(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_AUTO_LEARN_ENABLED", "true")
    monkeypatch.setenv("KNOWLEDGE_AUTO_MAX_NEW_PER_TURN", "1")
    with patch(
        "services.knowledge.doctor_knowledge.save_knowledge_item",
        new=AsyncMock(side_effect=RuntimeError("db fail")),
    ), patch("services.knowledge.doctor_knowledge.log") as mocked_log:
        inserted = await dk.maybe_auto_learn_knowledge(
            object(),
            "doc-1",
            "建议先复查心电图",
            structured_fields={},
        )
    assert inserted == 0
    assert mocked_log.called
