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
HandleVoiceFn = Callable[[str, str, str], Awaitable[None]]
HandleImageFn = Callable[[str, str, str], Awaitable[None]]
HandleFileFn = Callable[[str, str, str, str], Awaitable[None]]
HandleIntentFn = Callable[[str, str, str], Awaitable[None]]


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
    handle_voice_bg: HandleVoiceFn,
    handle_image_bg: HandleImageFn,
    handle_file_bg: HandleFileFn,
    handle_intent_bg: HandleIntentFn,
    async_client_cls: Any = httpx.AsyncClient,
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
        cursor = sync_cursor
        next_cursor = sync_cursor
        max_pages = 5
        msg_list: List[Dict[str, Any]] = []

        async with async_client_cls(timeout=10) as client:
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
                    return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

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

        if next_cursor and next_cursor != sync_cursor:
            sync_cursor = next_cursor
            persist_cursor(next_cursor)

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

        if not candidates:
            return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

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
                return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

        if selected is None:
            selected = max(timed_candidates, key=msg_time) if timed_candidates else candidates[-1]

        msg_id = str(selected.get("msgid") or "")
        external_userid = str(selected.get("external_userid") or "")
        open_kfid = str(selected.get("open_kfid") or "")
        msgtype = str(selected.get("msgtype") or "").lower()
        text = msg_to_text(selected)
        if not external_userid:
            return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

        if msg_id:
            if isinstance(seen_msg_ids, deque):
                seen_msg_ids.append(msg_id)
            else:
                seen_msg_ids.add(msg_id)
                if len(seen_msg_ids) > 2000:
                    seen_msg_ids.clear()

        if msgtype == "voice":
            voice = selected.get("voice") or {}
            recognition = str(voice.get("recognition") or "").strip()
            media_id = str(voice.get("media_id") or "").strip()
            if recognition:
                await handle_intent_bg(recognition, external_userid, open_kfid)
                log(
                    f"[WeCom KF] queued voice(recognition) user={external_userid} kf={open_kfid} "
                    f"msgid={msg_id or 'n/a'} text={recognition[:80]!r}"
                )
                return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}
            if media_id:
                await send_customer_service_msg(external_userid, "已收到语音，正在识别，请稍候。", open_kfid)
                await handle_voice_bg(media_id, external_userid, open_kfid)
                log(
                    f"[WeCom KF] queued voice(media) user={external_userid} kf={open_kfid} "
                    f"msgid={msg_id or 'n/a'} media_id={media_id}"
                )
                return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}
            await send_customer_service_msg(
                external_userid,
                "已收到语音，但未拿到语音文件ID，暂时无法识别。请重试发送。",
                open_kfid,
            )
            return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

        if msgtype == "image":
            image = selected.get("image") or {}
            media_id = str(image.get("media_id") or "").strip()
            if media_id:
                await send_customer_service_msg(external_userid, "已收到图片，正在识别文字，请稍候。", open_kfid)
                await handle_image_bg(media_id, external_userid, open_kfid)
                log(
                    f"[WeCom KF] queued image(media) user={external_userid} kf={open_kfid} "
                    f"msgid={msg_id or 'n/a'} media_id={media_id}"
                )
                return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}
            await send_customer_service_msg(
                external_userid,
                "已收到图片，但未拿到图片文件ID，暂时无法解析。请重试发送。",
                open_kfid,
            )
            return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

        if msgtype == "file":
            filename = str((selected.get("file") or {}).get("filename") or "文件").strip()
            media_id = str((selected.get("file") or {}).get("media_id") or "").strip()
            if media_id:
                await send_customer_service_msg(
                    external_userid,
                    f"已收到文件《{filename}》，正在识别并处理，请稍候。",
                    open_kfid,
                )
                await handle_file_bg(media_id, filename, external_userid, open_kfid)
            else:
                await send_customer_service_msg(
                    external_userid,
                    f"已收到文件《{filename}》，但未拿到文件ID，暂时无法解析。请重试或改发图片/文本。",
                    open_kfid,
                )
            log(
                f"[WeCom KF] file received user={external_userid} kf={open_kfid} "
                f"msgid={msg_id or 'n/a'} filename={filename!r} media_id={media_id or 'n/a'}"
            )
            return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

        if msgtype == "video":
            await send_customer_service_msg(
                external_userid,
                "已收到视频。当前暂不支持自动转写视频，请发送关键内容文字说明，我可继续处理。",
                open_kfid,
            )
            log(f"[WeCom KF] video received user={external_userid} kf={open_kfid} msgid={msg_id or 'n/a'}")
            return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

        if not text:
            await send_customer_service_msg(
                external_userid,
                f"已收到消息类型：{msgtype or 'unknown'}，当前暂不支持自动处理，请改发文字描述。",
                open_kfid,
            )
            return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}

        await handle_intent_bg(text, external_userid, open_kfid)
        log(
            f"[WeCom KF] queued inbound text user={external_userid} kf={open_kfid} "
            f"msgid={msg_id or 'n/a'} expected_msgid={expected_msgid or 'n/a'} "
            f"event_create_time={event_create_time or 0} msg_time={msg_time(selected)} text={text!r}"
        )
        return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}
    except Exception as e:
        log(f"[WeCom KF] sync processing FAILED: {e}")
        return {"sync_cursor": sync_cursor, "cursor_loaded": cursor_loaded}
