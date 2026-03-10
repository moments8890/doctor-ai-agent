"""运行时状态持久化测试：验证运行时游标、Token 及会话对话轮次的数据库读写与清理操作。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db.crud import (
    get_runtime_cursor,
    upsert_runtime_cursor,
    get_runtime_token,
    upsert_runtime_token,
    append_conversation_turns,
    get_recent_conversation_turns,
    clear_conversation_turns,
    purge_conversation_turns_before,
)


async def test_runtime_cursor_upsert_and_get(db_session):
    assert await get_runtime_cursor(db_session, "kf") is None

    await upsert_runtime_cursor(db_session, "kf", "cursor-1")
    assert await get_runtime_cursor(db_session, "kf") == "cursor-1"

    await upsert_runtime_cursor(db_session, "kf", "cursor-2")
    assert await get_runtime_cursor(db_session, "kf") == "cursor-2"


async def test_runtime_token_upsert_and_get(db_session):
    assert await get_runtime_token(db_session, "tk") is None

    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    await upsert_runtime_token(db_session, "tk", "token-1", expires)

    row = await get_runtime_token(db_session, "tk")
    assert row is not None
    assert row.token_value == "token-1"
    assert row.expires_at is not None


async def test_conversation_turns_append_limit_and_clear(db_session):
    for i in range(14):
        await append_conversation_turns(
            db_session,
            doctor_id="doc-runtime",
            turns=[{"role": "user", "content": f"u{i}"}, {"role": "assistant", "content": f"a{i}"}],
            max_turns=5,
        )

    turns = await get_recent_conversation_turns(db_session, "doc-runtime", limit=40)
    assert len(turns) == 10
    assert turns[0].content == "u9"
    assert turns[-1].content == "a13"

    await clear_conversation_turns(db_session, "doc-runtime")
    turns_after_clear = await get_recent_conversation_turns(db_session, "doc-runtime", limit=10)
    assert turns_after_clear == []


async def test_conversation_turns_purge_by_timestamp(db_session):
    await append_conversation_turns(
        db_session,
        doctor_id="doc-old",
        turns=[{"role": "user", "content": "old-u"}, {"role": "assistant", "content": "old-a"}],
        max_turns=10,
    )
    cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)
    deleted = await purge_conversation_turns_before(db_session, cutoff)
    assert deleted >= 2
