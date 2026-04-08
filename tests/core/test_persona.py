"""Test persona lifecycle: lazy creation, extraction trigger."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from db.models.doctor import KnowledgeCategory


def test_persona_template_has_sections():
    from domain.knowledge.teaching import PERSONA_TEMPLATE
    assert "## 回复风格" in PERSONA_TEMPLATE
    assert "## 常用结尾语" in PERSONA_TEMPLATE
    assert "## 回避内容" in PERSONA_TEMPLATE
    assert "## 常见修改" in PERSONA_TEMPLATE


@pytest.mark.asyncio
async def test_get_or_create_persona_creates_when_missing():
    from domain.knowledge.teaching import get_or_create_persona

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.flush = AsyncMock()

    persona = await get_or_create_persona(mock_session, "doc1")

    assert persona is not None
    assert persona.category == KnowledgeCategory.persona.value
    assert persona.persona_status == "draft"
    assert "回复风格" in persona.content
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_persona_returns_existing():
    from domain.knowledge.teaching import get_or_create_persona

    existing = MagicMock()
    existing.category = KnowledgeCategory.persona.value
    existing.persona_status = "active"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    mock_session.execute = AsyncMock(return_value=mock_result)

    persona = await get_or_create_persona(mock_session, "doc1")

    assert persona is existing
    mock_session.add.assert_not_called()
