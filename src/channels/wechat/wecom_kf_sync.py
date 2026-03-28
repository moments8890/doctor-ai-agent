"""
WeCom 企业微信客服消息轮询同步：拉取新消息并分发给意图处理器。
"""

from __future__ import annotations

from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, List, Set, Union

import httpx


LoadCursorFn = Callable[[], str]
PersistCursorFn = Callable[[str], None]
LogFn = Callable[..., None]
GetConfigFn = Callable[[], Dict[str, Any]]
GetAccessTokenFn = Callable[[str, str], Awaitable[str]]
MsgToTextFn = Callable[[Dict[str, Any]], str]
MsgProcessableFn = Callable[[Dict[str, Any]], bool]
MsgTimeFn = Callable[[Dict[str, Any]], int]
SendMessageFn = Callable[[str, str, str], Awaitable[None]]
HandleImageFn = Callable[[str, str, str], Awaitable[None]]
HandleFileFn = Callable[[str, str, str, str], Awaitable[None]]
HandleIntentFn = Callable[[str, str, str], Awaitable[None]]


async def _fetch_msg_pages(
    client: Any,
    access_token: str,
    sync_cursor: str,
    event_token: str,
    event_open_kfid: str,
    log: LogFn,
) -> tuple[List[Dict[str, Any]], str]:
    """分页拉取 WeCom KF 消息列表，返回 (msg_list, next_cursor)。"""
    cursor = sync_cursor
    next_cursor = sync_cursor
    max_pages = 5
    msg_list: List[Dict[str, Any]] = []

    for _ in range(max_pages):
        payload: Dict[str, Any] = {"limit": 100}
        if cursor:
            payload["cursor"] = cursor
        if event_token:
            payload["token"] = event_token
        if event_open_kfid:
            payload["open_kfid"] = event_open_kfid
        resp = await client.post(
            "https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg",
            params={"access_token": access_token},
            json=payload,
        )
        if hasattr(resp, "raise_for_status"):
            resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or data.get("errcode", 0) != 0:
            log(f"[WeCom KF] sync_msg failed: {data}")
            return msg_list, next_cursor

        batch = data.get("msg_list") or []
        if isinstance(batch, list):
            msg_list.extend(batch)

        batch_next_cursor = str(data.get("next_cursor") or "")
        if batch_next_cursor:
            next_cursor = batch_next_cursor
        has_more = str(data.get("has_more") or "0") in ("1", "true", "True")
        if not has_more or not batch_next_cursor or batch_next_cursor == cursor:
            break
        cursor = batch_next_cursor

    return msg_list, next_cursor


def _filter_candidates(
    msg_list: List[Dict[str, Any]],
    seen_msg_ids: Union[Set[str], Deque[str]],
    msg_is_processable: MsgProcessableFn,
) -> List[Dict[str, Any]]:
    """从消息列表中过滤出可处理的用户候选消息。"""
    candidates: List[Dict[str, Any]] = []
    for raw in msg_list:
        if raw.get("origin") not in (3, "3"):
            continue
        msg_id = str(raw.get("msgid") or "")
        if msg_id and msg_id in seen_msg_ids:
            continue
        if not msg_is_processable(raw):
            continue
        external_userid = str(raw.get("external_userid") or "")
        if not external_userid:
            continue
        candidates.append(raw)
    return candidates


def _select_message(
    candidates: List[Dict[str, Any]],
    expected_msgid: str,
    event_create_time: int,
    msg_time: MsgTimeFn,
    log: LogFn,
    sync_cursor: str,
    cursor_loaded: bool,
) -> tuple[Dict[str, Any] | None, bool]:
    """从候选消息中选出最合适的一条；返回 (selected, should_return_early)。"""
    selected = None
    if expected_msgid:
        for item in candidates:
            if str(item.get("msgid") or "") == expected_msgid:
                selected = item
                break

    timed_candidates = [m for m in candidates if msg_time(m) > 0]

    if selected is None and event_create_time > 0 and timed_candidates:
        near = sorted(timed_candidates, key=lambda item: abs(msg_time(item) - event_create_time))
        if near and abs(msg_time(near[0]) - event_create_time) <= 900:
            selected = near[0]
        else:
            log(
                "[WeCom KF] skip stale batch",
                event_create_time=event_create_time,
                closest_msg_time=msg_time(near[0]) if near else 0,
            )
            return None, True  # signal early return

    if selected is None:
        selected = max(timed_candidates, key=msg_time) if timed_candidates else candidates[-1]

    return selected, False


def _track_seen(msg_id: str, seen_msg_ids: Union[Set[str], Deque[str]]) -> None:
    """将消息 ID 加入已处理集合，防重复投递。"""
    if not msg_id:
        return
    if isinstance(seen_msg_ids, deque):
        seen_msg_ids.append(msg_id)
    else:
        seen_msg_ids.add(msg_id)
        if len(seen_msg_ids) > 2000:
            seen_msg_ids.clear()


async def _sync_messages(
    access_token: str,
    sync_cursor: str,
    event_token: str,
    event_open_kfid: str,
    persist_cursor: PersistCursorFn,
    seen_msg_ids: Union[Set[str], Deque[str]],
    msg_is_processable: MsgProcessableFn,
    async_client_cls: Any,
    log: LogFn,
) -> tuple[list, str]:
    """拉取消息页并更新游标；返回 (candidates, sync_cursor)。"""
    async with async_client_cls(timeout=10) as client:
        msg_list, next_cursor = await _fetch_msg_pages(
            client, access_token, sync_cursor, event_token, event_open_kfid, log
        )
    if next_cursor and next_cursor != sync_cursor:
        sync_cursor = next_cursor
        persist_cursor(next_cursor)
    candidates = _filter_candidates(msg_list, seen_msg_ids, msg_is_processable)
    return candidates, sync_cursor


async def _select_and_dispatch(
    candidates: List[Dict[str, Any]],
    expected_msgid: str,
    event_create_time: int,
    msg_time: MsgTimeFn,
    log: LogFn,
    seen_msg_ids: Union[Set[str], Deque[str]],
    send_customer_service_msg: SendMessageFn,
    handle_image_bg: HandleImageFn,
    handle_file_bg: HandleFileFn,
    handle_intent_bg: HandleIntentFn,
    msg_to_text: MsgToTextFn,
) -> None:
    """选出最合适的消息并分发到对应处理函数。"""
    from channels.wechat.wecom_kf_handlers import dispatch_message

    selected, early_return = _select_message(
        candidates, expected_msgid, event_create_time, msg_time, log, "", True,
    )
    if early_return or selected is None:
        return
    msg_id = str(selected.get("msgid") or "")
    external_userid = str(selected.get("external_userid") or "")
    open_kfid = str(selected.get("open_kfid") or "")
    if not external_userid:
        return
    _track_seen(msg_id, seen_msg_ids)
    await dispatch_message(
        selected, msg_id, external_userid, open_kfid,
        expected_msgid, event_create_time, msg_time,
        send_customer_service_msg, handle_image_bg,
        handle_file_bg, handle_intent_bg, msg_to_text, log,
    )


async def handle_event(
    *,
    expected_msgid: str,
    event_create_time: int,
    event_token: str,
    event_open_kfid: str,
    sync_cursor: str,
    cursor_loaded: bool,
    seen_msg_ids: Union[Set[str], Deque[str]],
    load_cursor: LoadCursorFn,
    persist_cursor: PersistCursorFn,
    log: LogFn,
    get_config: GetConfigFn,
    get_access_token: GetAccessTokenFn,
    msg_to_text: MsgToTextFn,
    msg_is_processable: MsgProcessableFn,
    msg_time: MsgTimeFn,
    send_customer_service_msg: SendMessageFn,
    handle_image_bg: HandleImageFn,
    handle_file_bg: HandleFileFn,
    handle_intent_bg: HandleIntentFn,
    async_client_cls: Any = httpx.AsyncClient,
    **_kwargs: Any,
) -> Dict[str, Any]:
    """Handle one WeCom KF callback event by syncing, selecting and dispatching one message."""
    cfg = get_config()
    if not cfg.get("app_id") or not cfg.get("app_secret"):
        log("[WeCom KF] skipped sync: app_id/app_secret missing")
        return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}
    if not cursor_loaded:
        sync_cursor = load_cursor() or sync_cursor
        cursor_loaded = True
    try:
        access_token = await get_access_token(cfg["app_id"], cfg["app_secret"])
        candidates, sync_cursor = await _sync_messages(
            access_token, sync_cursor, event_token, event_open_kfid,
            persist_cursor, seen_msg_ids, msg_is_processable, async_client_cls, log,
        )
        ret = {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}
        if not candidates:
            return ret
        await _select_and_dispatch(
            candidates, expected_msgid, event_create_time, msg_time, log,
            seen_msg_ids, send_customer_service_msg,
            handle_image_bg, handle_file_bg, handle_intent_bg, msg_to_text,
        )
        return ret
    except Exception as e:
        log(f"[WeCom KF] sync processing FAILED: {e}")
        return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}
