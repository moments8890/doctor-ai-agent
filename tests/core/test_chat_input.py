"""ChatInput model — action_hint validation."""
import pytest
from pydantic import ValidationError


def test_chat_input_accepts_valid_action_hint():
    from channels.web.chat import ChatInput
    body = ChatInput(text="张三", action_hint="create_record")
    assert body.action_hint.value == "create_record"


def test_chat_input_allows_no_hint():
    from channels.web.chat import ChatInput
    body = ChatInput(text="hello")
    assert body.action_hint is None


def test_chat_input_rejects_unknown_hint():
    from channels.web.chat import ChatInput
    with pytest.raises(ValidationError):
        ChatInput(text="hello", action_hint="invalid_action")
