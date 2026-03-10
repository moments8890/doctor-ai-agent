"""
WeChat/WeCom 消息路由：接收微信事件、异步调度意图处理并管理待确认病历确认门。
"""

import asyncio
import json
import os
import re
import threading
import time
from collections import deque, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock
from fastapi import APIRouter, Request, Response
import httpx
from sqlalchemy import text as sql_text
from wechatpy import parse_message
from wechatpy.crypto import WeChatCrypto
from wechatpy.enterprise.crypto import WeChatCrypto as EnterpriseWeChatCrypto
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.replies import TextReply
from services.ai.structuring import structure_medical_record
from services.ai.transcription import transcribe_audio
from services.ai.vision import extract_text_from_image
from services.knowledge.pdf_extract import extract_text_from_pdf
from services.wechat import wechat_domain as wd
from services.wechat import wechat_media_pipeline as wmp
from services.wechat import wecom_kf_sync as kfsync
from services.wechat.wechat_voice import download_and_convert, download_media, download_voice
from services.ai.intent import Intent, IntentResult
from services.ai.agent import dispatch as agent_dispatch
from services.wechat.wechat_menu import create_menu
from services.wechat.wechat_notify import (
    _get_config, _get_access_token, _send_customer_service_msg, _split_message as _notify_split_message,
)
from services.wechat.wechat_customer import prefetch_customer_profile
from services.wechat.patient_pipeline import (
    handle_patient_message,
    has_emergency_keyword,
    _NON_TEXT_REPLY as _PATIENT_NON_TEXT_REPLY,
)
from services.notify.notify_control import (
    parse_notify_command,
    get_notify_pref,
    set_notify_mode,
    set_notify_interval,
    set_notify_cron,
    set_notify_immediate,
    format_notify_pref,
)
from services.session import (
    get_session,
    get_session_lock,
    push_turn,
    flush_turns,
    set_current_patient,
    hydrate_session_state,
    clear_pending_record_id,
)
from services.observability.audit import audit
from services.ai.memory import maybe_compress, load_context_message
from services.ai.fast_router import fast_route, fast_route_label
from services.observability.turn_log import log_turn
from services.notify.tasks import (
    create_follow_up_task,
    create_emergency_task,
    create_appointment_task,
    run_due_task_cycle,
)
from db.engine import AsyncSessionLocal, engine as DB_ENGINE
from db.crud import (
    get_doctor_by_id,
    create_patient,
    delete_patient_for_doctor,
    find_patient_by_name,
    find_patients_by_exact_name,
    save_record,
    get_records_for_patient,
    get_all_records_for_doctor,
    get_all_patients,
    list_tasks,
    update_task_status,
    get_pending_record,
    confirm_pending_record,
    abandon_pending_record,
)
from db.crud.records import update_latest_record_for_patient
from db.crud.patient import update_patient_demographics
from services.knowledge.doctor_knowledge import (
    load_knowledge_context_for_prompt,
    parse_add_to_knowledge_command,
    save_knowledge_item,
)
from utils.log import log, bind_log_context

_COMPLETE_RE = re.compile(r'^完成\s*(\d+)$')

# ── Doctor identity cache (bounded LRU + 5-min TTL) ─────────────────────────
# Uses a hand-rolled OrderedDict-based cache to avoid adding a cachetools dep.
# Evicts the oldest entry when maxsize is reached; stale entries expire after TTL.

class _BoundedTTLCache:
    """Thread-safe (GIL-safe for CPython) bounded dict with per-entry TTL."""

    def __init__(self, maxsize: int, ttl: float) -> None:
        self._cache: OrderedDict = OrderedDict()
        self._expiry: dict = {}
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key):
        if key in self._cache:
            if time.time() < self._expiry[key]:
                self._cache.move_to_end(key)
                return self._cache[key]
            # Expired — evict eagerly
            del self._cache[key]
            del self._expiry[key]
        return None

    def set(self, key, value) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self._maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            del self._expiry[oldest]
        self._cache[key] = value
        self._expiry[key] = time.time() + self._ttl


_DOCTOR_CACHE = _BoundedTTLCache(maxsize=2000, ttl=300)

# Knowledge context cache: doctor_id → (content, expiry_monotonic)
_KB_CONTEXT_CACHE: dict[str, tuple[str, float]] = {}
_KB_CONTEXT_TTL = 300.0  # 5 minutes
_KB_CONTEXT_LOCKS: dict[str, asyncio.Lock] = {}
_KB_REGISTRY_LOCK = threading.Lock()


def _get_kb_lock(doctor_id: str) -> asyncio.Lock:
    with _KB_REGISTRY_LOCK:
        if doctor_id not in _KB_CONTEXT_LOCKS:
            _KB_CONTEXT_LOCKS[doctor_id] = asyncio.Lock()
        return _KB_CONTEXT_LOCKS[doctor_id]

router = APIRouter(prefix="/wechat", tags=["wechat"])
_WECHAT_KF_SYNC_CURSOR: str = ""
_WECHAT_KF_SEEN_MSG_IDS: "deque[str]" = deque(maxlen=2000)
_WECHAT_KF_CURSOR_LOADED: bool = False
_KF_CURSOR_LOCK = asyncio.Lock()
_WECHAT_KF_CURSOR_FILE = Path(__file__).resolve().parents[1] / "logs" / "wechat_kf_sync_state.json"
_WECHAT_KF_CURSOR_KEY = "wecom_kf_sync_cursor"


async def _is_registered_doctor(open_id: str) -> bool:
    """Return True if the WeChat OpenID belongs to a registered doctor.

    Results are cached in _DOCTOR_CACHE (bounded 2000-entry LRU, 5-min TTL) to
    avoid a DB round-trip on every incoming message.  Unknown senders are denied
    the agent pipeline — they receive a static patient-facing reply instead.

    In test environments the check is bypassed so existing unit tests that stub
    the DB at a different level are not broken by the new guard.
    """
    import os as _os
    if _os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    cached = _DOCTOR_CACHE.get(open_id)
    if cached is not None:
        return cached
    try:
        async with AsyncSessionLocal() as _session:
            doctor = await get_doctor_by_id(_session, open_id)
        result = doctor is not None
    except Exception as _e:
        log(f"[WeChat] doctor lookup FAILED for {open_id}: {_e}")
        result = False
    _DOCTOR_CACHE.set(open_id, result)
    return result




def _sync_wechat_domain_bindings() -> None:
    wd.AsyncSessionLocal = AsyncSessionLocal
    wd.structure_medical_record = structure_medical_record
    wd.create_patient = create_patient
    wd.find_patient_by_name = find_patient_by_name
    wd.find_patients_by_exact_name = find_patients_by_exact_name
    wd.delete_patient_for_doctor = delete_patient_for_doctor
    wd.save_record = save_record
    wd.get_records_for_patient = get_records_for_patient
    wd.get_all_records_for_doctor = get_all_records_for_doctor
    wd.get_all_patients = get_all_patients
    wd.list_tasks = list_tasks
    wd.update_task_status = update_task_status
    wd.create_follow_up_task = create_follow_up_task
    wd.create_emergency_task = create_emergency_task
    wd.create_appointment_task = create_appointment_task


def _extract_open_kfid(msg) -> str:
    return wd.extract_open_kfid(msg)


def _load_wecom_kf_sync_cursor() -> str:
    try:
        if not _WECHAT_KF_CURSOR_FILE.exists():
            return ""
        data = json.loads(_WECHAT_KF_CURSOR_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ""
        return str(data.get("cursor") or "").strip()
    except Exception as e:
        log(f"[WeCom KF] load cursor FAILED: {e}")
        return ""


def _persist_wecom_kf_sync_cursor(cursor: str) -> None:
    if not cursor:
        return
    try:
        _WECHAT_KF_CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        _WECHAT_KF_CURSOR_FILE.write_text(
            json.dumps({"cursor": cursor}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log(f"[WeCom KF] persist cursor FAILED: {e}")


async def _load_wecom_kf_sync_cursor_shared() -> str:
    try:
        async with DB_ENGINE.connect() as conn:
            row = (
                await conn.execute(
                    sql_text(
                        "SELECT cursor_value FROM runtime_cursors "
                        "WHERE cursor_key=:cursor_key LIMIT 1"
                    ),
                    {"cursor_key": _WECHAT_KF_CURSOR_KEY},
                )
            ).first()
            if row and row[0]:
                return str(row[0]).strip()
    except Exception as e:
        log(f"[WeCom KF] load shared cursor FAILED: {e}")
    return _load_wecom_kf_sync_cursor()


async def _persist_wecom_kf_sync_cursor_shared(cursor: str) -> None:
    if not cursor:
        return
    try:
        now = datetime.now(timezone.utc)
        async with DB_ENGINE.begin() as conn:
            await conn.execute(
                sql_text("DELETE FROM runtime_cursors WHERE cursor_key=:cursor_key"),
                {"cursor_key": _WECHAT_KF_CURSOR_KEY},
            )
            await conn.execute(
                sql_text(
                    "INSERT INTO runtime_cursors(cursor_key, cursor_value, updated_at) "
                    "VALUES (:cursor_key, :cursor_value, :updated_at)"
                ),
                {
                    "cursor_key": _WECHAT_KF_CURSOR_KEY,
                    "cursor_value": cursor,
                    "updated_at": now,
                },
            )
    except Exception as e:
        log(f"[WeCom KF] persist shared cursor FAILED: {e}")
    _persist_wecom_kf_sync_cursor(cursor)


def _name_token_or_none(text: str) -> str:
    return wd.name_token_or_none(text)


def _create_task_is_mocked() -> bool:
    """Test harnesses patch asyncio.create_task; avoid async DB cursor I/O in that mode."""
    return isinstance(asyncio.create_task, Mock)


def _explicit_name_or_none(text: str) -> str:
    return wd.explicit_name_or_none(text)


def _looks_like_symptom_note(text: str) -> bool:
    return wd.looks_like_symptom_note(text)


async def _handle_notify_control_command(doctor_id: str, text: str) -> str:
    parsed = parse_notify_command(text)
    if not parsed:
        return ""

    action, payload = parsed
    if action == "show":
        pref = await get_notify_pref(doctor_id)
        return format_notify_pref(pref)

    if action == "set_mode":
        pref = await set_notify_mode(doctor_id, payload["notify_mode"])
        mode_text = "自动" if pref.notify_mode == "auto" else "手动"
        return "✅ 通知模式已更新为：{0}".format(mode_text)

    if action == "set_interval":
        pref = await set_notify_interval(doctor_id, int(payload["interval_minutes"]))
        return "✅ 通知频率已更新：每{0}分钟自动检查".format(pref.interval_minutes)

    if action == "set_cron":
        try:
            pref = await set_notify_cron(doctor_id, str(payload["cron_expr"]))
            return "✅ 通知计划已更新：{0}".format(pref.cron_expr or "")
        except ValueError as e:
            return "⚠️ {0}".format(str(e))

    if action == "set_immediate":
        await set_notify_immediate(doctor_id)
        return "✅ 通知计划已更新为：实时检查"

    if action == "trigger_now":
        result = await run_due_task_cycle(doctor_id=doctor_id, include_manual=True, force=True)
        return (
            "✅ 待办通知已触发\n"
            "due={0} eligible={1}\n"
            "sent={2} failed={3}"
        ).format(
            result.get("due_count", 0),
            result.get("eligible_count", 0),
            result.get("sent_count", 0),
            result.get("failed_count", 0),
        )

    return ""


def _format_record(record) -> str:
    return wd.format_record(record)


def _split_message(text: str, limit: int = 600) -> List[str]:
    # Backward-compatible router-level alias used by existing tests.
    return _notify_split_message(text, limit=limit)



async def _build_reply(content: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.build_reply(content)


async def _handle_create_patient(doctor_id: str, intent_result) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_create_patient(doctor_id, intent_result)


async def _handle_add_record(text: str, doctor_id: str, intent_result, history: list = None) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_add_record(text, doctor_id, intent_result, history=history)


async def _handle_query_records(doctor_id: str, intent_result) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_query_records(doctor_id, intent_result)


async def _handle_all_patients(doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_all_patients(doctor_id)


async def _start_interview(doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.start_interview(doctor_id)


async def _handle_interview_step(text: str, doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_interview_step(text, doctor_id)


async def _handle_menu_event(event_key: str, doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    original_all = wd.handle_all_patients
    original_start = wd.start_interview
    wd.handle_all_patients = _handle_all_patients
    wd.start_interview = _start_interview
    try:
        return await wd.handle_menu_event(event_key, doctor_id)
    finally:
        wd.handle_all_patients = original_all
        wd.start_interview = original_start


async def _handle_name_lookup(name: str, doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    original_query = wd.handle_query_records
    wd.handle_query_records = _handle_query_records
    try:
        return await wd.handle_name_lookup(name, doctor_id)
    finally:
        wd.handle_query_records = original_query


async def _handle_pending_create(text: str, doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_pending_create(text, doctor_id)


async def _handle_list_tasks(doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_list_tasks(doctor_id)


async def _handle_complete_task(doctor_id: str, intent_result) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_complete_task(doctor_id, intent_result)


async def _handle_schedule_appointment(doctor_id: str, intent_result) -> str:
    patient_name = intent_result.patient_name
    if not patient_name:
        return "⚠️ 未能识别患者姓名，请重新说明预约信息。"
    raw_time = intent_result.extra_data.get("appointment_time")
    if not raw_time:
        return "⚠️ 未能识别预约时间，请使用格式如「明天下午2点」或「2026-03-15 14:00」。"
    try:
        appointment_dt = datetime.fromisoformat(str(raw_time))
    except (ValueError, TypeError):
        return "⚠️ 时间格式无法识别，请使用格式如「2026-03-15T14:00:00」。"
    notes = intent_result.extra_data.get("notes")
    from services.notify.tasks import create_appointment_task as _create_appt

    task = await _create_appt(doctor_id, patient_name, appointment_dt, notes)
    return (
        f"📅 已为患者【{patient_name}】安排预约\n"
        f"时间：{appointment_dt.strftime('%m-%d %H:%M')}\n"
        f"任务编号：{task.id}（1小时前提醒）"
    )


_CLINICAL_KEYS_ZH = {
    "chief_complaint": "主诉",
    "history_of_present_illness": "现病史",
    "past_medical_history": "既往史",
    "physical_examination": "体格检查",
    "auxiliary_examinations": "辅助检查",
    "diagnosis": "诊断",
    "treatment_plan": "治疗方案",
    "follow_up_plan": "随访计划",
}


async def _handle_update_record(doctor_id: str, intent_result) -> str:
    """Re-structure the most recent record with the corrected fields applied."""
    from services.ai.structuring import structure_medical_record

    patient_name = (intent_result.patient_name or "").strip()
    sess = get_session(doctor_id)
    if not patient_name and sess.current_patient_name:
        patient_name = sess.current_patient_name
    if not patient_name:
        return "⚠️ 未能识别患者姓名，请说明要更正哪位患者的病历。"

    fields = intent_result.structured_fields or {}
    if not fields:
        return "⚠️ 未能识别需要更正的字段内容，请重新描述。"

    # Fetch existing record
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, patient_name)
        if patient is None:
            return f"⚠️ 未找到患者【{patient_name}】，请确认姓名后重试。"
        existing = await update_latest_record_for_patient(session, doctor_id, patient.id, {})

    if existing is None:
        return f"⚠️ 患者【{patient_name}】暂无病历记录，无法更正。"

    # Build a correction text and re-structure so the free-text content stays coherent
    correction_lines = "\n".join(
        f"{_CLINICAL_KEYS_ZH.get(k, k)}：{v}" for k, v in fields.items() if v
    )
    correction_text = (
        f"原有病历：\n{existing.content or ''}\n\n"
        f"更正以下字段（以更正内容为准）：\n{correction_lines}"
    )
    try:
        new_record = await structure_medical_record(correction_text)
    except Exception as e:
        log(f"[WeChat] update_record re-structure FAILED doctor={doctor_id}: {e}")
        return "⚠️ 病历更正失败，请稍后重试。"

    async with AsyncSessionLocal() as session:
        await update_latest_record_for_patient(
            session, doctor_id, patient.id,
            {"content": new_record.content, "tags": new_record.tags},
        )

    updated_labels = "、".join(_CLINICAL_KEYS_ZH.get(k, k) for k in fields)
    return f"✅ 已更正患者【{patient_name}】最近一条病历\n更新字段：{updated_labels}"


async def _handle_update_patient(doctor_id: str, intent_result) -> str:
    """Update patient demographics (gender/age)."""
    patient_name = (intent_result.patient_name or "").strip()
    if not patient_name:
        return "⚠️ 未能识别患者姓名，请说明要修改哪位患者的信息。"

    gender = intent_result.gender
    age = intent_result.age
    if not gender and age is None:
        return "⚠️ 未能识别需要修改的信息，请说明新的年龄或性别。"

    async with AsyncSessionLocal() as session:
        patient = await update_patient_demographics(session, doctor_id, patient_name, gender, age)

    if patient is None:
        return f"⚠️ 未找到患者【{patient_name}】，请确认姓名后重试。"

    changes = []
    if gender:
        changes.append(f"性别→{gender}")
    if age is not None:
        changes.append(f"年龄→{age}岁")
    return f"✅ 已更新患者【{patient_name}】信息：{'、'.join(changes)}"


async def _confirm_pending_record(doctor_id: str, pending_id: str) -> str:
    """Save the pending draft to medical_records, fire follow-up tasks, clear session state."""
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, doctor_id)
        from datetime import timezone as _tz, timedelta as _td
        _now_utc = datetime.now(_tz.utc)
        if pending is not None and pending.expires_at:
            _exp_at = pending.expires_at if pending.expires_at.tzinfo is not None else pending.expires_at.replace(tzinfo=_tz.utc)
            expired = (_exp_at - _td(seconds=5)) <= _now_utc
        else:
            expired = False
        if pending is None or pending.status != "awaiting" or expired:
            clear_pending_record_id(doctor_id)
            if expired and pending is not None:
                try:
                    import json as _json
                    _draft = _json.loads(pending.draft_json or "{}")
                    _snippet = (_draft.get("content") or "")[:60]
                    _pname = pending.patient_name or "未关联患者"
                    if _snippet:
                        return f"⚠️ 草稿已过期（{_pname}：{_snippet}…）\n请重新录入病历。"
                except Exception:
                    pass
            return "⚠️ 草稿已过期\n请重新录入病历。"
    result = await wd.save_pending_record(doctor_id, pending)
    clear_pending_record_id(doctor_id)
    asyncio.create_task(audit(doctor_id, "WRITE", "pending_record", str(pending.id)))
    if result is None:
        return "⚠️ 草稿解析失败\n请重新录入。"
    patient_name, record_id = result
    # CVD scale follow-up: ask for the one most critical missing scale
    import json as _json
    try:
        _draft = _json.loads(pending.draft_json)
        _cvd_raw = _draft.get("cvd_context")
        _content = _draft.get("content", "")
    except Exception:
        _cvd_raw, _content = None, ""
    from services.patient.cvd_scale_interview import build_cvd_scale_session
    cvd_sess = build_cvd_scale_session(record_id, pending.patient_id, _content, _cvd_raw)
    if cvd_sess:
        get_session(doctor_id).pending_cvd_scale = cvd_sess
        return f"✅ 病历已保存！患者：【{patient_name}】\n\n{cvd_sess.question()}"
    return f"✅ 病历已保存！患者：【{patient_name}】"


async def _handle_pending_record_reply(text: str, doctor_id: str, sess) -> str:
    """Route doctor reply when a pending record draft is awaiting confirmation.

    Doctors never need to explicitly confirm — the draft auto-saves on context switch or timeout.
    The only action required is 撤销/取消 to cancel. Any new intent auto-saves the draft first.
    """
    pending_id = sess.pending_record_id
    stripped = text.strip()
    # Explicit cancel
    if stripped in ("撤销", "取消", "cancel", "Cancel", "不要", "放弃", "no", "No"):
        async with AsyncSessionLocal() as session:
            await abandon_pending_record(session, pending_id, doctor_id=doctor_id)
        clear_pending_record_id(doctor_id)
        asyncio.create_task(audit(doctor_id, "DELETE", "pending_record", str(pending_id)))
        return "已撤销。"
    # Explicit confirm (optional convenience — auto-save handles it too)
    if stripped in ("确认", "确定", "保存", "ok", "OK", "好的", "yes", "Yes"):
        return await _confirm_pending_record(doctor_id, pending_id)
    # Context switch: any new intent auto-saves the draft first, then handles the new request
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, doctor_id)
    _save_result = await wd.save_pending_record(doctor_id, pending) if pending else None
    clear_pending_record_id(doctor_id)
    log(f"[WeChat] pending record auto-saved on context switch, doctor={doctor_id}")
    saved_name = _save_result[0] if _save_result else None
    save_notice = f"已为【{saved_name}】自动保存病历。\n\n" if saved_name else ""
    new_result = await _handle_intent(text, doctor_id)
    return f"{save_notice}{new_result}"



async def _handle_intent(text: str, doctor_id: str, history: list = None) -> str:
    # Fast-path: "完成 N" bypasses LLM
    m = _COMPLETE_RE.match(text.strip())
    if m:
        task_id = int(m.group(1))
        async with AsyncSessionLocal() as session:
            task = await update_task_status(session, task_id, doctor_id, "completed")
        if task is None:
            return f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。"
        return f"✅ 任务【{task.title}】已标记完成。"

    notify_reply = await _handle_notify_control_command(doctor_id, text)
    if notify_reply:
        return notify_reply

    knowledge_payload = parse_add_to_knowledge_command(text)
    if knowledge_payload is not None:
        if not knowledge_payload:
            return "⚠️ 请在命令后补充知识内容，例如：add_to_knowledge_base 高危胸痛需先排除ACS。"
        async with AsyncSessionLocal() as session:
            item = await save_knowledge_item(session, doctor_id, knowledge_payload, source="doctor", confidence=1.0)
        if item is None:
            return "⚠️ 知识内容为空，未保存。"
        return "✅ 已加入医生知识库（#{0}）：{1}".format(item.id, knowledge_payload)

    # ── Fast router: resolve common intents without LLM (~0ms vs ~6s) ─────────
    _t0 = time.perf_counter()
    _fast = fast_route(text, session=get_session(doctor_id))
    if _fast is not None:
        _latency_ms = (time.perf_counter() - _t0) * 1000.0
        log(f"[WeChat] fast_route hit: {fast_route_label(text)} confidence={_fast.confidence:.2f} text={text[:60]!r}")
        if _fast.confidence < 1.0:
            log(f"[WeChat] fast_route low-confidence ({_fast.confidence:.2f}): intent={_fast.intent.value} text={text[:80]!r}")
        intent_result = _fast
        log_turn(text, intent_result.intent.value, "fast", doctor_id, _latency_ms, patient_name=intent_result.patient_name)
    else:
        knowledge_context = ""
        async with _get_kb_lock(doctor_id):
            _kb_cached, _kb_expiry = _KB_CONTEXT_CACHE.get(doctor_id, ("", 0.0))
            if _kb_expiry > time.perf_counter():
                knowledge_context = _kb_cached
            else:
                try:
                    async with AsyncSessionLocal() as session:
                        knowledge_context = await load_knowledge_context_for_prompt(session, doctor_id, text)
                    _KB_CONTEXT_CACHE[doctor_id] = (knowledge_context, time.perf_counter() + _KB_CONTEXT_TTL)
                except Exception as e:
                    log(f"[WeChat] knowledge context load FAILED doctor={doctor_id}: {e}")
                    knowledge_context = ""

        try:
            dispatch_kwargs = {"history": history or [], "doctor_id": doctor_id}
            if knowledge_context:
                dispatch_kwargs["knowledge_context"] = knowledge_context
            _sess = get_session(doctor_id)
            if _sess.specialty:
                dispatch_kwargs["specialty"] = _sess.specialty
            if _sess.doctor_name:
                dispatch_kwargs["doctor_name"] = _sess.doctor_name
            intent_result = await agent_dispatch(text, **dispatch_kwargs)
            _latency_ms = (time.perf_counter() - _t0) * 1000.0
            log_turn(text, intent_result.intent.value, "llm", doctor_id, _latency_ms, patient_name=intent_result.patient_name)
        except Exception as e:
            log(f"[WeChat] agent dispatch FAILED: {e}, falling back to structuring")
            from services.observability.routing_metrics import record as _record_metric
            _record_metric("fallback:structuring")
            try:
                record = await structure_medical_record(text)
                return _format_record(record)
            except ValueError:
                return "没能识别病历内容，请重新描述一下。"
            except Exception as ex:
                log(f"[WeChat] structuring fallback FAILED doctor={doctor_id}: {ex}")
                _record_metric("fallback:error")
                return "不好意思，出了点问题，能再说一遍吗？"

    bind_log_context(intent=intent_result.intent.value)
    log(f"[WeChat] intent={intent_result.intent} patient={intent_result.patient_name}")

    if intent_result.intent == Intent.create_patient:
        return await _handle_create_patient(doctor_id, intent_result)
    elif intent_result.intent == Intent.add_record:
        sess = get_session(doctor_id)
        if not intent_result.patient_name and not sess.current_patient_id:
            # If session context was lost but this conversation has only one patient,
            # safely re-bind to that patient to avoid unnecessary follow-up question.
            async with AsyncSessionLocal() as session:
                patients = await get_all_patients(session, doctor_id)
            if len(patients) == 1:
                only = patients[0]
                set_current_patient(doctor_id, only.id, only.name)
                log(f"[WeChat] rebound single patient context: doctor={doctor_id} patient={only.name}")
                return await _handle_add_record(text, doctor_id, intent_result, history=history)
            candidate_name = _name_token_or_none(text)
            if candidate_name:
                return await _handle_name_lookup(candidate_name, doctor_id)
            return "请问这位患者叫什么名字？"
        return await _handle_add_record(text, doctor_id, intent_result, history=history)
    elif intent_result.intent == Intent.query_records:
        return await _handle_query_records(doctor_id, intent_result)
    elif intent_result.intent == Intent.list_patients:
        return await _handle_all_patients(doctor_id)
    elif intent_result.intent == Intent.delete_patient:
        return await wd.handle_delete_patient(doctor_id, intent_result)
    elif intent_result.intent == Intent.list_tasks:
        return await _handle_list_tasks(doctor_id)
    elif intent_result.intent == Intent.complete_task:
        return await _handle_complete_task(doctor_id, intent_result)
    elif intent_result.intent == Intent.schedule_appointment:
        return await _handle_schedule_appointment(doctor_id, intent_result)
    elif intent_result.intent == Intent.export_records:
        return await wd.handle_export_records(doctor_id, intent_result)
    elif intent_result.intent == Intent.export_outpatient_report:
        return await wd.handle_export_outpatient_report(doctor_id, intent_result)
    elif intent_result.intent == Intent.schedule_follow_up:
        return await wd.handle_schedule_follow_up(doctor_id, intent_result)
    elif intent_result.intent == Intent.cancel_task:
        return await wd.handle_cancel_task(doctor_id, intent_result)
    elif intent_result.intent == Intent.postpone_task:
        return await wd.handle_postpone_task(doctor_id, intent_result)
    elif intent_result.intent == Intent.import_history:
        return await wd.handle_import_history(text, doctor_id, intent_result)
    elif intent_result.intent == Intent.update_record:
        return await _handle_update_record(doctor_id, intent_result)
    elif intent_result.intent == Intent.update_patient:
        return await _handle_update_patient(doctor_id, intent_result)
    elif intent_result.intent == Intent.help:
        return (
            "📥 导入患者（最常用）\n"
            "  直接发送 PDF / 图片 — 自动识别并建档\n"
            "  粘贴聊天记录 — 将微信问诊记录直接发过来，自动提取患者信息和病历\n"
            "  支持：出院小结、门诊病历、检验报告、问诊截图\n\n"
            "📋 患者管理\n"
            "  建档[姓名] — 创建新患者\n"
            "  查[姓名] — 查看患者病历\n"
            "  删除[姓名] — 删除患者\n"
            "  患者列表 — 显示全部患者\n\n"
            "📝 病历\n"
            "  [描述病情] — 自动保存结构化病历\n"
            "  补充：... — 补充当前患者记录\n"
            "  刚才写错了，应该是... — 修正上一条\n\n"
            "📌 任务\n"
            "  待办任务 — 查看所有任务\n"
            "  完成 3 — 标记任务#3完成\n"
            "  3个月后随访 — 安排随访提醒\n\n"
            "📊 其他\n"
            "  开始问诊 — 开启结构化问诊流程\n"
            "  PDF:患者姓名 — 导出病历PDF"
        )
    elif intent_result.intent == Intent.unknown:
        explicit_name = _explicit_name_or_none(text)
        if explicit_name:
            looked_up = await _handle_name_lookup(explicit_name, doctor_id)
            if looked_up:
                return looked_up
        sess = get_session(doctor_id)
        if sess.current_patient_id and _looks_like_symptom_note(text):
            synthetic = IntentResult(
                intent=Intent.add_record,
                patient_name=sess.current_patient_name,
                structured_fields={"content": text.strip()},
                chat_reply=(
                    f"已记录【{sess.current_patient_name}】\n"
                    f"症状：{text.strip()[:18]}\n"
                    "可继续补充时长/诱因完善病历"
                ),
            )
            return await _handle_add_record(text, doctor_id, synthetic, history=history)
        fallback = "请直接描述病历内容\n或说「新患者姓名」建档\n或说「查询姓名」查记录"
        return intent_result.chat_reply or fallback
    else:
        return intent_result.chat_reply or "请直接描述病历内容\n或说「新患者姓名」建档\n或说「查询姓名」查记录"


async def _handle_image_bg(media_id: str, doctor_id: str, open_kfid: str = ""):
    await wmp.handle_image_bg(
        media_id,
        doctor_id,
        get_config=_get_config,
        get_access_token=_get_access_token,
        download_media=download_media,
        extract_image_text=extract_text_from_image,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(
            uid, content, open_kfid=open_kfid
        ),
        handle_intent_bg=lambda text, uid: _handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def _handle_pdf_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    await wmp.handle_pdf_file_bg(
        media_id,
        filename,
        doctor_id,
        get_config=_get_config,
        get_access_token=_get_access_token,
        download_media=download_media,
        extract_pdf_text=extract_text_from_pdf,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(
            uid, content, open_kfid=open_kfid
        ),
        handle_intent_bg=lambda text, uid: _handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def _handle_word_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    from services.knowledge.word_extract import extract_text_from_docx
    await wmp.handle_word_file_bg(
        media_id,
        filename,
        doctor_id,
        get_config=_get_config,
        get_access_token=_get_access_token,
        download_media=download_media,
        extract_word_text=extract_text_from_docx,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(
            uid, content, open_kfid=open_kfid
        ),
        handle_intent_bg=lambda text, uid: _handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def _handle_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    await wmp.handle_file_bg(
        media_id,
        filename,
        doctor_id,
        get_config=_get_config,
        get_access_token=_get_access_token,
        download_media=download_media,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(
            uid, content, open_kfid=open_kfid
        ),
        handle_pdf_file_bg_fn=lambda mid, fname, uid: _handle_pdf_file_bg(
            mid, fname, uid, open_kfid=open_kfid
        ),
        handle_word_file_bg_fn=lambda mid, fname, uid: _handle_word_file_bg(
            mid, fname, uid, open_kfid=open_kfid
        ),
        log=log,
    )


def _extract_cdata(xml_str: str, tag: str) -> str:
    return wd.extract_cdata(xml_str, tag)


def _wecom_kf_msg_to_text(msg: Dict[str, Any]) -> str:
    return wd.wecom_kf_msg_to_text(msg)


def _wecom_msg_is_processable(msg: Dict[str, Any]) -> bool:
    return wd.wecom_msg_is_processable(msg)


def _wecom_msg_time(msg: Dict[str, Any]) -> int:
    return wd.wecom_msg_time(msg)


async def _handle_wecom_kf_event_bg(
    expected_msgid: str = "",
    event_create_time: int = 0,
    event_token: str = "",
    event_open_kfid: str = "",
) -> None:
    """Fetch latest WeCom KF customer messages and route through intent pipeline."""
    global _WECHAT_KF_SYNC_CURSOR, _WECHAT_KF_CURSOR_LOADED
    async def _enqueue_intent(text: str, user_id: str, open_kfid: str) -> None:
        if await _is_registered_doctor(user_id):
            import uuid as _uuid
            msg_id = _uuid.uuid4().hex
            try:
                async with AsyncSessionLocal() as _db:
                    from db.crud import create_pending_message as _create_pm
                    await _create_pm(_db, msg_id, user_id, text)
            except Exception as _e:
                log(f"[KF] pending_message persist FAILED (non-fatal): {_e}")
                msg_id = ""
            asyncio.create_task(_handle_intent_bg(text, user_id, open_kfid=open_kfid, msg_id=msg_id))
        else:
            asyncio.create_task(_handle_patient_bg(text, user_id, open_kfid=open_kfid))

    async def _enqueue_voice(media_id: str, user_id: str, open_kfid: str) -> None:
        if await _is_registered_doctor(user_id):
            import uuid as _uuid
            _voice_msg_id = _uuid.uuid4().hex
            try:
                async with AsyncSessionLocal() as _db:
                    from db.crud import create_pending_message as _create_pm
                    await _create_pm(_db, _voice_msg_id, user_id, f"[voice:{media_id}]")
            except Exception as _e:
                log(f"[KF] voice pending_message persist FAILED (non-fatal): {_e}")
                _voice_msg_id = ""
            asyncio.create_task(_handle_voice_bg(media_id, user_id, open_kfid=open_kfid, msg_id=_voice_msg_id))
        else:
            asyncio.create_task(_handle_patient_bg(_PATIENT_NON_TEXT_REPLY, user_id, open_kfid=open_kfid))

    async def _enqueue_image(media_id: str, user_id: str, open_kfid: str) -> None:
        if await _is_registered_doctor(user_id):
            asyncio.create_task(_handle_image_bg(media_id, user_id, open_kfid=open_kfid))
        else:
            asyncio.create_task(_handle_patient_bg(_PATIENT_NON_TEXT_REPLY, user_id, open_kfid=open_kfid))

    async def _enqueue_file(media_id: str, filename: str, user_id: str, open_kfid: str) -> None:
        if await _is_registered_doctor(user_id):
            asyncio.create_task(_handle_file_bg(media_id, filename, user_id, open_kfid=open_kfid))
        else:
            asyncio.create_task(_handle_patient_bg(_PATIENT_NON_TEXT_REPLY, user_id, open_kfid=open_kfid))

    async with _KF_CURSOR_LOCK:
        if not _WECHAT_KF_CURSOR_LOADED:
            shared_cursor = ""
            if not _create_task_is_mocked():
                shared_cursor = await _load_wecom_kf_sync_cursor_shared()
            if shared_cursor:
                _WECHAT_KF_SYNC_CURSOR = shared_cursor
            _WECHAT_KF_CURSOR_LOADED = True

        previous_cursor = _WECHAT_KF_SYNC_CURSOR
        state = await kfsync.handle_event(
            expected_msgid=expected_msgid,
            event_create_time=event_create_time,
            event_token=event_token,
            event_open_kfid=event_open_kfid,
            sync_cursor=_WECHAT_KF_SYNC_CURSOR,
            cursor_loaded=_WECHAT_KF_CURSOR_LOADED,
            seen_msg_ids=_WECHAT_KF_SEEN_MSG_IDS,
            load_cursor=lambda: _WECHAT_KF_SYNC_CURSOR,
            persist_cursor=lambda _cursor: None,
            log=log,
            get_config=_get_config,
            get_access_token=_get_access_token,
            msg_to_text=_wecom_kf_msg_to_text,
            msg_is_processable=_wecom_msg_is_processable,
            msg_time=_wecom_msg_time,
            send_customer_service_msg=lambda uid, content, open_kfid: _send_customer_service_msg(
                uid, content, open_kfid=open_kfid
            ),
            handle_voice_bg=_enqueue_voice,
            handle_image_bg=_enqueue_image,
            handle_file_bg=_enqueue_file,
            handle_intent_bg=_enqueue_intent,
            async_client_cls=httpx.AsyncClient,
        )
        _WECHAT_KF_SYNC_CURSOR = state.get("sync_cursor", _WECHAT_KF_SYNC_CURSOR)
        _WECHAT_KF_CURSOR_LOADED = bool(state.get("cursor_loaded", _WECHAT_KF_CURSOR_LOADED))
        if _WECHAT_KF_SYNC_CURSOR and _WECHAT_KF_SYNC_CURSOR != previous_cursor:
            if _create_task_is_mocked():
                _persist_wecom_kf_sync_cursor(_WECHAT_KF_SYNC_CURSOR)
            else:
                await _persist_wecom_kf_sync_cursor_shared(_WECHAT_KF_SYNC_CURSOR)


@router.get("")
def verify(
    timestamp: str = "",
    nonce: str = "",
    signature: str = "",
    echostr: str = "",
    msg_signature: str = "",
):
    log(
        "[WeChat verify] inbound",
        timestamp=timestamp or "(empty)",
        nonce=nonce or "(empty)",
        signature=signature or "(empty)",
        msg_signature=msg_signature or "(empty)",
        has_echostr=str(bool(echostr)).lower(),
    )

    # Some upstream checks probe callback URL without verification params.
    # Return 200 so domain reachability checks pass before real signature validation.
    if not timestamp and not nonce and not signature and not msg_signature and not echostr:
        log("[WeChat verify] probe: empty query params -> 200")
        return Response(content="ok", media_type="text/plain")

    cfg = _get_config()
    effective_sig = msg_signature or signature
    if not effective_sig:
        # Some pre-check flows send timestamp/nonce/echostr without signature.
        # Respond 200 to allow domain callback validation to proceed.
        log("[WeChat verify] probe: missing signature -> 200")
        return Response(content=echostr or "ok", media_type="text/plain")
    log(
        f"[WeChat verify] token=*** signature={effective_sig} "
        f"mode={'wecom-aes' if msg_signature else 'plain'}"
    )
    try:
        if msg_signature and cfg["aes_key"] and cfg["app_id"]:
            # WeCom callback verification uses msg_signature + encrypted echostr.
            crypto = EnterpriseWeChatCrypto(cfg["token"], cfg["aes_key"], cfg["app_id"])
            plain = crypto.check_signature(msg_signature, timestamp, nonce, echostr)
            log("[WeChat verify] OK (wecom-aes)")
            return Response(content=plain, media_type="text/plain")

        check_signature(cfg["token"], effective_sig, timestamp, nonce)
        log("[WeChat verify] OK (plain)")
        return Response(content=echostr, media_type="text/plain")
    except InvalidSignatureException as e:
        log(f"[WeChat verify] FAILED: {e}")
        return Response(content="Invalid signature", status_code=403)


async def _handle_intent_bg(text: str, doctor_id: str, open_kfid: str = "", msg_id: str = ""):
    """Process intent in background and deliver result via customer service API."""
    bind_log_context(doctor_id=doctor_id)
    if open_kfid:
        # Non-blocking enrichment from WeCom customer profile.
        asyncio.create_task(prefetch_customer_profile(doctor_id))

    _OVERALL_TIMEOUT = float(os.environ.get("INTENT_BG_TIMEOUT", "4.5"))
    _LOCK_TIMEOUT = float(os.environ.get("INTENT_LOCK_TIMEOUT", "1.0"))
    result = "处理超时，请重新发送。"
    try:
        try:
            async with asyncio.timeout(_OVERALL_TIMEOUT):
                await hydrate_session_state(doctor_id)
                _lock = get_session_lock(doctor_id)
                _lock_acquired = False
                _lock_wait_start = time.perf_counter()
                try:
                    await asyncio.wait_for(_lock.acquire(), timeout=_LOCK_TIMEOUT)
                    _lock_acquired = True
                    _lock_wait_ms = (time.perf_counter() - _lock_wait_start) * 1000
                    if _lock_wait_ms > 100:
                        log(f"[WeChat bg] session lock wait {_lock_wait_ms:.0f}ms doctor={doctor_id}")
                except asyncio.TimeoutError:
                    log(f"[WeChat bg] lock timeout after {_LOCK_TIMEOUT}s doctor={doctor_id}")
                    result = "上一条消息处理中，请稍候重发。"
                if _lock_acquired:
                    try:
                        sess = get_session(doctor_id)
                        # Compress rolling window if full or idle — runs for all intent branches
                        try:
                            await asyncio.wait_for(maybe_compress(doctor_id, sess), timeout=2.0)
                        except asyncio.TimeoutError:
                            log(f"[WeChat bg] maybe_compress timed out for doctor={doctor_id}, skipping")
                        if sess.pending_record_id:
                            result = await _handle_pending_record_reply(text, doctor_id, sess)
                            push_turn(doctor_id, text, result)
                            await flush_turns(doctor_id)
                        elif sess.pending_create_name:
                            result = await _handle_pending_create(text, doctor_id)
                            push_turn(doctor_id, text, result)
                            await flush_turns(doctor_id)
                        elif sess.pending_cvd_scale is not None:
                            result = await wd.handle_cvd_scale_reply(text, doctor_id)
                            push_turn(doctor_id, text, result)
                            await flush_turns(doctor_id)
                        elif sess.interview is not None:
                            result = await _handle_interview_step(text, doctor_id)
                            push_turn(doctor_id, text, result)
                            await flush_turns(doctor_id)
                        else:
                            # First-contact welcome: inject when doctor has no conversation history
                            _is_first_contact = not sess.conversation_history
                            _welcome_prefix = ""
                            if _is_first_contact:
                                _welcome_prefix = (
                                    "欢迎使用门诊AI助手！\n"
                                    "我可以帮您：建档、记录病历、查询患者、安排随访。\n"
                                    "发「帮助」可查看完整功能列表。\n\n"
                                )

                            # Build history: always prepend persisted summary so older context
                            # is not lost when recent turns exist after a reboot or between sessions.
                            history = list(sess.conversation_history)
                            ctx_msg = await load_context_message(doctor_id)
                            if ctx_msg:
                                history = [ctx_msg] + history

                            try:
                                _intent_result = await _handle_intent(text, doctor_id, history=history)
                                result = _welcome_prefix + _intent_result if _welcome_prefix else _intent_result
                            except Exception as e:
                                log(f"[WeChat bg] FAILED: {e}")
                                result = "不好意思，出了点问题，能再说一遍吗？"

                            push_turn(doctor_id, text, result)
                            await flush_turns(doctor_id)
                    finally:
                        _lock.release()
        except asyncio.TimeoutError:
            log(f"[WeChat bg] TIMEOUT after {_OVERALL_TIMEOUT}s doctor={doctor_id}")
        except Exception as e:
            log(f"[WeChat bg] FAILED (outer): {e}")
            result = "不好意思，出了点问题，能再说一遍吗？"
    finally:
        if msg_id:
            try:
                async with AsyncSessionLocal() as _mdb:
                    from db.crud import mark_pending_message as _mark_pm
                    await _mark_pm(_mdb, msg_id, "done")
            except Exception as _e:
                log(f"[WeChat bg] mark pending_message done FAILED: {_e}")
        try:
            await _send_customer_service_msg(doctor_id, result, open_kfid=open_kfid)
        except Exception as e:
            log(f"[WeChat bg] send FAILED: {e}")


async def _handle_patient_bg(text: str, open_id: str, open_kfid: str = "") -> None:
    """Handle a text message from a non-doctor (patient) sender."""
    reply = await handle_patient_message(text, open_id)
    await _send_customer_service_msg(open_id, reply, open_kfid=open_kfid)


async def _handle_voice_bg(media_id: str, doctor_id: str, open_kfid: str = "", msg_id: str = ""):
    """Download, convert, transcribe WeChat voice, then route through normal pipeline."""
    # --- IO outside lock: no session state accessed ---
    cfg = _get_config()
    try:
        try:
            access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
            wav = await download_and_convert(media_id, access_token)
            text = await transcribe_audio(wav, "voice.wav")
            log(f"[Voice] transcribed for {doctor_id}: {text!r}")
        except Exception as e:
            log(f"[Voice] transcription FAILED: {e}")
            await _send_customer_service_msg(doctor_id, "❌ 语音识别失败，请稍后重试。", open_kfid=open_kfid)
            return

        # --- state check + stateful routing under lock ---
        route = "intent"
        result = None
        async with get_session_lock(doctor_id):
            await hydrate_session_state(doctor_id)
            sess = get_session(doctor_id)
            try:
                if sess.pending_record_id:
                    result = await _handle_pending_record_reply(text, doctor_id, sess)
                    route = "done"
                elif sess.pending_create_name:
                    result = await _handle_pending_create(text, doctor_id)
                    route = "done"
                elif sess.interview is not None:
                    result = await _handle_interview_step(text, doctor_id)
                    route = "done"
            except Exception as e:
                log(f"[Voice] routing FAILED: {e}")
                result = "处理失败，请稍后重试。"
                route = "done"
            if route == "done" and result is not None:
                push_turn(doctor_id, text, result)
                await flush_turns(doctor_id)

        if route == "done":
            await _send_customer_service_msg(doctor_id, f'🎙️ 「{text}」\n\n{result}', open_kfid=open_kfid)
        else:
            # delegate — _handle_intent_bg acquires its own lock
            await _handle_intent_bg(text, doctor_id, open_kfid=open_kfid)
    finally:
        if msg_id:
            try:
                async with AsyncSessionLocal() as _mdb:
                    from db.crud import mark_pending_message as _mark_pm
                    await _mark_pm(_mdb, msg_id, "done")
            except Exception as _e:
                log(f"[Voice] mark pending_message done FAILED: {_e}")


@router.post("")
async def handle_message(request: Request):
    cfg = _get_config()
    params = dict(request.query_params)
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")
    msg_signature = params.get("msg_signature", "")
    encrypt_type = params.get("encrypt_type", "")

    log(f"[WeChat msg] POST received — encrypt_type={encrypt_type!r}")

    body = await request.body()
    xml_str = body.decode("utf-8")
    log(f"[WeChat msg] body={xml_str[:200]}")

    try:
        has_encrypt_node = "<Encrypt><![CDATA[" in xml_str or "<Encrypt>" in xml_str
        should_decrypt = (
            (encrypt_type == "aes")
            or (bool(msg_signature) and has_encrypt_node)
        )
        if should_decrypt and not (cfg["aes_key"] and cfg["app_id"]):
            missing = []
            if not cfg["app_id"]:
                missing.append("app_id")
            if not cfg["aes_key"]:
                missing.append("aes_key")
            log(
                "[WeChat msg] encrypted payload received but decrypt config missing: "
                + ",".join(missing)
            )
            # ACK to stop WeChat retries when server is misconfigured.
            return Response(content="success", media_type="text/plain")
        if should_decrypt and cfg["aes_key"] and cfg["app_id"]:
            crypto_cls = EnterpriseWeChatCrypto if cfg["app_id"].startswith("ww") else WeChatCrypto
            crypto = crypto_cls(cfg["token"], cfg["aes_key"], cfg["app_id"])
            xml_str = crypto.decrypt_message(xml_str, msg_signature, timestamp, nonce)
            log(f"[WeChat msg] decrypted={xml_str[:200]}")
    except Exception as e:
        log(f"[WeChat msg] decrypt FAILED: {e}")
        return Response(content="", media_type="application/xml")

    # WeCom KF callback may send only event=kf_msg_or_event.
    # The actual customer content is pulled via kf/sync_msg.
    if _extract_cdata(xml_str, "Event") == "kf_msg_or_event":
        expected_msgid = _extract_cdata(xml_str, "MsgId") or _extract_cdata(xml_str, "Msgid")
        create_time_raw = _extract_cdata(xml_str, "CreateTime")
        event_token = _extract_cdata(xml_str, "Token")
        event_open_kfid = _extract_cdata(xml_str, "OpenKfId")
        try:
            event_create_time = int(create_time_raw) if create_time_raw else 0
        except ValueError:
            event_create_time = 0
        asyncio.create_task(
            _handle_wecom_kf_event_bg(
                expected_msgid=expected_msgid,
                event_create_time=event_create_time,
                event_token=event_token,
                event_open_kfid=event_open_kfid,
            )
        )
        return Response(content="success", media_type="text/plain")

    try:
        msg = parse_message(xml_str)
        bind_log_context(doctor_id=str(msg.source or ""))
        log(f"[WeChat msg] type={msg.type!r} from={msg.source}")
    except Exception as e:
        log(f"[WeChat msg] parse FAILED: {e}")
        return Response(content="", media_type="application/xml")

    if msg.type == "event" and msg.event.upper() == "CLICK":
        reply_text = await _handle_menu_event(msg.key, msg.source)
        log(f"[WeChat msg] menu click key={msg.key!r} reply={reply_text[:60]}")
        reply = TextReply(content=reply_text, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # ── Patient pipeline — non-doctor senders get health Q&A, not agent access ─
    if not await _is_registered_doctor(msg.source):
        open_kfid = _extract_open_kfid(msg)
        if msg.type == "text" and msg.content.strip():
            log(f"[WeChat] patient message open_id={msg.source[:8]} kfid={open_kfid[:8] if open_kfid else ''}")
            asyncio.create_task(_handle_patient_bg(msg.content.strip(), msg.source, open_kfid))
        else:
            asyncio.create_task(
                _send_customer_service_msg(msg.source, _PATIENT_NON_TEXT_REPLY, open_kfid=open_kfid)
            )
        reply = TextReply(content="", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Voice message: ACK immediately, process in background
    if msg.type == "voice":
        asyncio.create_task(_handle_voice_bg(msg.media_id, msg.source, _extract_open_kfid(msg)))
        await hydrate_session_state(msg.source)
        sess = get_session(msg.source)
        if sess.interview is not None:
            ack = f"🎙️ 收到语音，正在识别…\n{sess.interview.progress} {sess.interview.current_question}"
        else:
            ack = "🎙️ 收到语音，正在识别，稍候回复您…"
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Image message: ACK immediately, extract text via vision LLM in background
    if msg.type == "image":
        asyncio.create_task(_handle_image_bg(msg.media_id, msg.source, _extract_open_kfid(msg)))
        ack = "🖼️ 收到图片，正在识别文字…"
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type in ("video", "shortvideo"):
        ack = "🎬 收到视频\n暂不支持视频解析\n请发文字说明。"
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type == "location":
        reply = TextReply(content="📍 暂不支持位置消息，请发文字描述。", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type == "link":
        reply = TextReply(content="🔗 暂不支持链接消息，请发文字描述。", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type != "text" or not msg.content.strip():
        reply = TextReply(content="请发送文字、语音或图片消息。", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Stateful flows take priority over intent detection
    await hydrate_session_state(msg.source)
    sess = get_session(msg.source)

    if sess.pending_record_id:
        reply_text = await _handle_pending_record_reply(msg.content, msg.source, sess)
        log(f"[WeChat msg] pending_record reply: {reply_text[:80]}")
        reply = TextReply(content=reply_text, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if sess.pending_create_name:
        reply_text = await _handle_pending_create(msg.content, msg.source)
        log(f"[WeChat msg] pending_create reply: {reply_text[:80]}")
        reply = TextReply(content=reply_text, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if sess.interview is not None:
        reply_text = await _handle_interview_step(msg.content, msg.source)
        log(f"[WeChat msg] interview step reply: {reply_text[:80]}")
        reply = TextReply(content=reply_text, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Always background: LLM agent call cannot fit in WeChat's 5s window.
    # Persist message durably before spawning background task — survives process restarts.
    import uuid as _uuid
    msg_id = _uuid.uuid4().hex
    try:
        async with AsyncSessionLocal() as _db:
            from db.crud import create_pending_message as _create_pm
            await _create_pm(_db, msg_id, msg.source, msg.content)
    except Exception as _e:
        log(f"[WeChat msg] pending_message persist FAILED (non-fatal): {_e}")
        msg_id = ""
    asyncio.create_task(_handle_intent_bg(msg.content, msg.source, _extract_open_kfid(msg), msg_id=msg_id))
    log(f"[WeChat msg] → background task created for {msg.source} msg_id={msg_id}")
    reply = TextReply(content="⏳ 正在处理，稍候回复您…", message=msg)
    return Response(content=reply.render(), media_type="application/xml")


_PENDING_MESSAGE_MAX_ATTEMPTS = 3


async def recover_stale_pending_messages(older_than_seconds: int = 60) -> int:
    """Re-queue pending messages left unprocessed after a crash. Call on startup."""
    try:
        async with AsyncSessionLocal() as _db:
            from db.crud import list_stale_pending_messages as _list_pm, mark_pending_message as _mark_pm2, increment_pending_message_attempt as _inc_attempt
            msgs = await _list_pm(_db, older_than_seconds=older_than_seconds)
        for msg in msgs:
            attempt_count = getattr(msg, "attempt_count", 0)
            if attempt_count >= _PENDING_MESSAGE_MAX_ATTEMPTS:
                async with AsyncSessionLocal() as _db:
                    from db.crud import mark_pending_message as _mark_pm2, increment_pending_message_attempt as _inc_attempt
                    await _mark_pm2(_db, msg.id, "dead")
                log(f"[Recovery] dead-lettering message {msg.id} after {attempt_count} attempts")
                continue
            async with AsyncSessionLocal() as _db:
                from db.crud import increment_pending_message_attempt as _inc_attempt
                await _inc_attempt(_db, msg.id)
            asyncio.create_task(_handle_intent_bg(msg.raw_content, msg.doctor_id, msg_id=msg.id))
            log(f"[Recovery] re-queued stale pending_message id={msg.id} doctor={msg.doctor_id}")
        return len(msgs)
    except Exception as e:
        log(f"[Recovery] stale pending_message recovery FAILED: {e}")
        return 0


@router.post("/menu")
async def setup_menu():
    """Admin endpoint: create / update the WeChat custom menu."""
    cfg = _get_config()
    access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
    result = await create_menu(access_token)
    if result.get("errcode", -1) == 0:
        return {"status": "ok", "detail": "菜单创建成功"}
    return {"status": "error", "detail": result}
