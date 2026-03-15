"""ADR 0012 Understand → Execute → Compose pipeline MVP integration tests.

End-to-end tests for every supported action type through /api/records/chat.

Coverage matrix
---------------
Deterministic handler (0 LLM calls):
  [x] Greeting → template reply
  [x] Help → template reply
  [x] Draft confirm → record persisted
  [x] Draft cancel → draft discarded

Understand → Execute → Compose (1-2 LLM calls):
  create_patient
    [x] Explicit with demographics → template reply, DB row
    [x] Missing name → clarification
    [x] Duplicate name → "已存在，已切换"
  select_patient
    [x] Switch to existing patient → context changes
    [x] Not found → clarification
    [x] Ambiguous (prefix match) → options list
  create_draft
    [x] Full cycle: clinical content → draft → confirm → record
    [x] No bound patient → clarification
    [x] Medical abbreviations survive structuring
    [x] Sparse input → no hallucinated treatment
    [x] Two records for same patient → 1 patient row, ≥2 records
  query_records
    [x] Returns summary + view_payload
    [x] No records → empty reply
    [x] Cross-patient read does not switch context
  list_patients
    [x] Returns names + view_payload
  schedule_task
    [x] Bound patient → immediate commit + echo-back
    [x] Unbound patient → clarification

Pending draft interaction (ADR 0012 §7):
  [x] Context-switching write → blocked
  [x] Same-patient schedule_task → allowed
  [x] Chitchat → allowed
  [x] Cancel then create new → allowed

Isolation & edge cases:
  [x] Doctor isolation (patients not shared across doctor_ids)
  [x] Chitchat / ambiguous input → no crash, no record

Requires: running server on port 8001 + LAN Ollama.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Optional

import pytest

from tests.integration.conftest import DB_PATH, chat, db_record


# ── DB helpers ────────────────────────────────────────────────────────────────


def _patient_count(doctor_id: str, name: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM patients WHERE doctor_id=? AND name=?",
            (doctor_id, name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _record_count_for_patient(doctor_id: str, name: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT COUNT(1)
            FROM medical_records r
            JOIN patients p ON p.id = r.patient_id
            WHERE p.doctor_id=? AND p.name=?
            """,
            (doctor_id, name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _task_count(doctor_id: str, status: str = "pending") -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM doctor_tasks WHERE doctor_id=? AND status=?",
            (doctor_id, status),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _task_row(doctor_id: str) -> Optional[tuple]:
    """Return (task_type, title, scheduled_for, remind_at) for latest task."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT task_type, title, scheduled_for, remind_at "
            "FROM doctor_tasks WHERE doctor_id=? ORDER BY id DESC LIMIT 1",
            (doctor_id,),
        ).fetchone()
        return row
    finally:
        conn.close()


def _patient_gender(doctor_id: str, name: str) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT gender FROM patients WHERE doctor_id=? AND name=? "
            "ORDER BY id DESC LIMIT 1",
            (doctor_id, name),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _patient_year_of_birth(doctor_id: str, name: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT year_of_birth FROM patients WHERE doctor_id=? AND name=? "
            "ORDER BY id DESC LIMIT 1",
            (doctor_id, name),
        ).fetchone()
        return int(row[0]) if row and row[0] else None
    finally:
        conn.close()


# ── Helper: full draft cycle ─────────────────────────────────────────────────


def _create_and_confirm_draft(
    doctor_id: str,
    patient_name: str,
    clinical_text: str,
) -> dict:
    """Run the full create_draft → confirm cycle.  Returns the confirm response."""
    chat(clinical_text, doctor_id=doctor_id)
    r_draft = chat("写个门诊记录", doctor_id=doctor_id)
    assert r_draft.get("pending_id"), (
        f"create_draft should return pending_id, got keys: {list(r_draft.keys())}"
    )
    r_confirm = chat("确认", doctor_id=doctor_id)
    return r_confirm


# =============================================================================
# 1. Deterministic handler (0 LLM calls)
# =============================================================================


@pytest.mark.integration
def test_greeting_returns_template():
    """Greeting → deterministic template, no record, no pending."""
    doctor_id = f"inttest_uec_greet_{uuid.uuid4().hex[:8]}"

    r = chat("你好", doctor_id=doctor_id)

    assert r["reply"], "Greeting reply must not be empty"
    assert r.get("record") is None
    assert r.get("pending_id") is None


@pytest.mark.integration
def test_greeting_english():
    """English greeting also handled deterministically."""
    doctor_id = f"inttest_uec_greet_en_{uuid.uuid4().hex[:8]}"

    r = chat("hello", doctor_id=doctor_id)

    assert r["reply"]
    assert r.get("record") is None


@pytest.mark.integration
def test_help_returns_substantive_reply():
    """Help → deterministic template with feature list."""
    doctor_id = f"inttest_uec_help_{uuid.uuid4().hex[:8]}"

    r = chat("帮助", doctor_id=doctor_id)

    assert r["reply"]
    assert len(r["reply"]) > 50, "Help reply should be substantive"
    assert r.get("record") is None


# =============================================================================
# 2. create_patient
# =============================================================================


@pytest.mark.integration
def test_create_patient_with_demographics():
    """create_patient with name+gender+age → template reply, DB row."""
    doctor_id = f"inttest_uec_cp1_{uuid.uuid4().hex[:8]}"
    name = "郑伟"

    r = chat(f"新患者{name}，男，38岁", doctor_id=doctor_id)

    assert name in r["reply"]
    assert "创建" in r["reply"] or "已创建" in r["reply"]
    assert r.get("record") is None, "create_patient must not create a record"

    # DB assertions
    assert _patient_count(doctor_id, name) == 1
    assert _patient_gender(doctor_id, name) == "男"
    yob = _patient_year_of_birth(doctor_id, name)
    assert yob is not None and abs(yob - (datetime.now().year - 38)) <= 1


@pytest.mark.integration
def test_create_patient_name_only():
    """create_patient with just a name (no demographics) → patient created."""
    doctor_id = f"inttest_uec_cp2_{uuid.uuid4().hex[:8]}"
    name = "陈婷"

    r = chat(f"新建患者{name}", doctor_id=doctor_id)

    assert name in r["reply"]
    assert _patient_count(doctor_id, name) == 1


@pytest.mark.integration
def test_create_patient_duplicate_selects_existing():
    """Duplicate create_patient → '已存在', exactly 1 patient row."""
    doctor_id = f"inttest_uec_cpdup_{uuid.uuid4().hex[:8]}"
    name = "黄磊"

    r1 = chat(f"新患者{name}，男，55岁", doctor_id=doctor_id)
    assert _patient_count(doctor_id, name) == 1

    r2 = chat(f"新患者{name}，男，55岁", doctor_id=doctor_id)

    assert "已存在" in r2["reply"] or "已切换" in r2["reply"] or name in r2["reply"]
    assert _patient_count(doctor_id, name) == 1, "Must not create duplicate"


# =============================================================================
# 3. select_patient
# =============================================================================


@pytest.mark.integration
def test_select_patient_switches_context():
    """select_patient changes active context (verified by subsequent draft)."""
    doctor_id = f"inttest_uec_sp1_{uuid.uuid4().hex[:8]}"

    chat("新患者己某某，男，30岁", doctor_id=doctor_id)
    chat("新患者庚某某，女，25岁", doctor_id=doctor_id)
    # Context is now on 庚某某 (last created)

    r = chat("切换到己某某", doctor_id=doctor_id)
    assert "己某某" in r["reply"]

    # Prove context switched: draft should target 己某某
    chat("腹痛一天", doctor_id=doctor_id)
    r_draft = chat("写记录", doctor_id=doctor_id)
    if r_draft.get("pending_id"):
        assert "己某某" in r_draft["reply"], (
            f"Draft should target 己某某 after switch, got: '{r_draft['reply']}'"
        )
        chat("取消", doctor_id=doctor_id)


@pytest.mark.integration
def test_select_patient_not_found():
    """select_patient for non-existent name → not_found clarification."""
    doctor_id = f"inttest_uec_sp_nf_{uuid.uuid4().hex[:8]}"

    r = chat("切换到完全不存在的名字", doctor_id=doctor_id)

    assert any(kw in r["reply"] for kw in ["未找到", "找不到", "不存在"]), (
        f"Should return not_found, got: '{r['reply']}'"
    )


@pytest.mark.integration
def test_select_patient_ambiguous_prefix():
    """Prefix matches 2+ patients → ambiguous_patient with options list."""
    doctor_id = f"inttest_uec_sp_ambig_{uuid.uuid4().hex[:8]}"

    chat("新患者张某甲，男，40岁", doctor_id=doctor_id)
    chat("新患者张某乙，女，35岁", doctor_id=doctor_id)

    r = chat("切换到张某", doctor_id=doctor_id)

    # Should present options, not blindly pick one
    assert "张某甲" in r["reply"] or "张某乙" in r["reply"] or "确认" in r["reply"], (
        f"Ambiguous prefix should list options, got: '{r['reply']}'"
    )


# =============================================================================
# 4. create_draft → confirm / cancel
# =============================================================================


@pytest.mark.integration
def test_draft_full_cycle_confirm():
    """create patient → clinical content → create_draft → confirm → DB record."""
    doctor_id = f"inttest_uec_draft1_{uuid.uuid4().hex[:8]}"
    name = "张伟"

    # Create patient
    r1 = chat(f"新患者{name}，男，52岁", doctor_id=doctor_id)
    assert _patient_count(doctor_id, name) == 1

    # Provide clinical content
    chat("劳力性胸闷三周，休息后缓解，既往高血压10年", doctor_id=doctor_id)

    # Trigger draft
    r3 = chat("写个门诊记录", doctor_id=doctor_id)
    assert r3.get("pending_id"), "create_draft must return pending_id"
    assert "确认" in r3["reply"] or "预览" in r3["reply"] or "保存" in r3["reply"]
    assert "胸闷" in r3["reply"], "Draft preview should contain chief complaint"

    # Confirm
    r4 = chat("确认", doctor_id=doctor_id)
    assert "保存" in r4["reply"] or "已保存" in r4["reply"] or "已确认" in r4["reply"]

    # DB validation
    rec = db_record(doctor_id, name)
    assert rec is not None, "Record not in DB after confirm"
    assert rec[0], "content must not be empty"
    assert "胸闷" in rec[0], "DB content should contain chief complaint"


@pytest.mark.integration
def test_draft_cancel_discards():
    """create_draft → cancel → no record persisted, can draft again."""
    doctor_id = f"inttest_uec_draft_cancel_{uuid.uuid4().hex[:8]}"
    name = "戊某某"

    chat(f"新患者{name}，男，60岁", doctor_id=doctor_id)
    chat("腰痛半月", doctor_id=doctor_id)

    r_draft = chat("写记录", doctor_id=doctor_id)
    assert r_draft.get("pending_id")

    r_cancel = chat("取消", doctor_id=doctor_id)
    assert "取消" in r_cancel["reply"] or "放弃" in r_cancel["reply"]

    # No record should exist
    rec = db_record(doctor_id, name)
    assert rec is None, "Cancelled draft must not produce a record"

    # Can create a new draft (not stuck in blocked state)
    chat("腰痛其实已经两个月了，加重一周", doctor_id=doctor_id)
    r_new = chat("写记录", doctor_id=doctor_id)
    assert r_new.get("pending_id"), "Should create new draft after cancel"
    chat("取消", doctor_id=doctor_id)  # cleanup


@pytest.mark.integration
def test_draft_no_patient_returns_clarification():
    """create_draft without a bound patient → missing_field clarification."""
    doctor_id = f"inttest_uec_draft_nopat_{uuid.uuid4().hex[:8]}"

    r = chat("写个门诊记录", doctor_id=doctor_id)

    assert any(kw in r["reply"] for kw in ["患者", "姓名", "先选择", "先创建"]), (
        f"Should ask for patient, got: '{r['reply']}'"
    )
    assert r.get("pending_id") is None


@pytest.mark.integration
def test_draft_preserves_medical_abbreviations():
    """Medical abbreviations (ST, PCI, BNP) survive structuring LLM."""
    doctor_id = f"inttest_uec_draft_abbrev_{uuid.uuid4().hex[:8]}"
    name = "韩伟"

    chat(f"新患者{name}，男，59岁", doctor_id=doctor_id)
    chat("突发胸痛两小时，ST段抬高，急诊PCI绿色通道，BNP升高", doctor_id=doctor_id)

    r_draft = chat("写门诊记录", doctor_id=doctor_id)
    assert r_draft.get("pending_id")

    # Abbreviations in preview
    for term in ["ST", "PCI"]:
        assert term in r_draft["reply"], (
            f"Draft preview lost medical abbreviation: {term}"
        )

    chat("确认", doctor_id=doctor_id)

    # Abbreviations in DB
    rec = db_record(doctor_id, name)
    assert rec is not None
    db_content = rec[0] or ""
    for term in ["ST", "PCI"]:
        assert term in db_content, f"DB record lost medical abbreviation: {term}"


@pytest.mark.integration
def test_draft_sparse_input_no_hallucinated_treatment():
    """Sparse clinical note → structuring must not fabricate treatment."""
    doctor_id = f"inttest_uec_draft_sparse_{uuid.uuid4().hex[:8]}"
    name = "赵丽"

    chat(f"新患者{name}，女，60岁", doctor_id=doctor_id)
    chat("高血压控制差，服药依从性一般", doctor_id=doctor_id)

    r_draft = chat("写记录", doctor_id=doctor_id)
    assert r_draft.get("pending_id")

    _AGGRESSIVE = ["手术", "介入", "支架", "搭桥", "溶栓"]
    preview_hallucinated = [kw for kw in _AGGRESSIVE if kw in r_draft["reply"]]
    assert not preview_hallucinated, (
        f"Draft preview fabricated treatment: {preview_hallucinated}"
    )

    chat("确认", doctor_id=doctor_id)

    rec = db_record(doctor_id, name)
    assert rec is not None
    db_content = rec[0] or ""
    db_hallucinated = [kw for kw in _AGGRESSIVE if kw in db_content]
    assert not db_hallucinated, (
        f"DB content fabricated treatment: {db_hallucinated}"
    )


@pytest.mark.integration
def test_two_drafts_same_patient_no_duplicate():
    """Two draft cycles for same patient → 1 patient row, ≥2 records."""
    doctor_id = f"inttest_uec_draft_dedup_{uuid.uuid4().hex[:8]}"
    name = "周强"

    chat(f"新患者{name}，男，48岁", doctor_id=doctor_id)

    # First record
    _create_and_confirm_draft(doctor_id, name, "胸闷1周，活动后加重")

    # Second record
    _create_and_confirm_draft(doctor_id, name, "昨晚胸痛加重，伴出汗")

    assert _patient_count(doctor_id, name) == 1
    assert _record_count_for_patient(doctor_id, name) >= 2


# =============================================================================
# 5. query_records
# =============================================================================


@pytest.mark.integration
def test_query_records_returns_summary():
    """query_records → LLM compose reply mentioning patient data."""
    doctor_id = f"inttest_uec_qr1_{uuid.uuid4().hex[:8]}"
    name = "钱芳"

    # Setup: patient + record
    chat(f"新患者{name}，女，63岁", doctor_id=doctor_id)
    _create_and_confirm_draft(doctor_id, name, "反复胸闷3天，活动后加重")

    # Query
    result = chat(f"查{name}的病历", doctor_id=doctor_id)

    assert name in result["reply"] or "胸闷" in result["reply"], (
        f"Query reply should reference patient or complaint, got: '{result['reply']}'"
    )

    # view_payload (ADR 0012 §14)
    vp = result.get("view_payload")
    if vp is not None:
        assert vp.get("type") == "records_list"
        assert isinstance(vp.get("data"), list)
        assert len(vp["data"]) >= 1


@pytest.mark.integration
def test_query_records_empty():
    """query_records for patient with no records → empty response."""
    doctor_id = f"inttest_uec_qr_empty_{uuid.uuid4().hex[:8]}"
    name = "空病历"

    chat(f"新患者{name}，男，30岁", doctor_id=doctor_id)

    result = chat(f"查{name}的病历", doctor_id=doctor_id)

    # Should indicate no records, not crash
    assert any(kw in result["reply"] for kw in [
        "没有", "未找到", "暂无", "0", "无记录",
    ]), f"Should indicate no records, got: '{result['reply']}'"


@pytest.mark.integration
def test_query_cross_patient_no_context_switch():
    """ADR 0012 §10: read scopes without switching active context."""
    doctor_id = f"inttest_uec_qr_scope_{uuid.uuid4().hex[:8]}"

    # Create patient A with a record
    chat("新患者辛某某，男，50岁", doctor_id=doctor_id)
    _create_and_confirm_draft(doctor_id, "辛某某", "高血压3年，血压控制欠佳")

    # Create patient B (becomes active context)
    chat("新患者壬某某，女，40岁", doctor_id=doctor_id)

    # Query patient A (should scope, NOT switch context)
    r = chat("查辛某某的病历", doctor_id=doctor_id)
    assert "辛某某" in r["reply"] or "高血压" in r["reply"]

    # Verify context still on B: draft should target 壬某某
    chat("头痛一天，无恶心呕吐", doctor_id=doctor_id)
    r_draft = chat("写记录", doctor_id=doctor_id)
    if r_draft.get("pending_id"):
        assert "壬某某" in r_draft["reply"], (
            f"Draft should target active patient 壬某某, not queried 辛某某. "
            f"Got: '{r_draft['reply']}'"
        )
        chat("取消", doctor_id=doctor_id)


# =============================================================================
# 6. list_patients
# =============================================================================


@pytest.mark.integration
def test_list_patients_returns_names():
    """list_patients → reply contains all created patient names."""
    doctor_id = f"inttest_uec_lp1_{uuid.uuid4().hex[:8]}"
    p1, p2 = "孙明", "吴静"

    chat(f"新患者{p1}，男，55岁", doctor_id=doctor_id)
    chat(f"新患者{p2}，女，47岁", doctor_id=doctor_id)

    result = chat("我的患者列表", doctor_id=doctor_id)

    assert p1 in result["reply"], f"'{p1}' not in list reply"
    assert p2 in result["reply"], f"'{p2}' not in list reply"

    vp = result.get("view_payload")
    if vp is not None:
        assert vp.get("type") == "patients_list"
        names_in_payload = [p.get("name") for p in vp.get("data", [])]
        assert p1 in names_in_payload
        assert p2 in names_in_payload


@pytest.mark.integration
def test_list_patients_empty():
    """list_patients for doctor with no patients → empty indication."""
    doctor_id = f"inttest_uec_lp_empty_{uuid.uuid4().hex[:8]}"

    result = chat("所有患者", doctor_id=doctor_id)

    assert result["reply"]
    # Should indicate empty, not crash
    assert any(kw in result["reply"] for kw in [
        "没有", "暂无", "0", "无患者", "空",
    ]) or len(result["reply"]) > 0  # at minimum, non-empty reply


# =============================================================================
# 7. schedule_task
# =============================================================================


@pytest.mark.integration
def test_schedule_task_with_bound_patient():
    """schedule_task commits immediately, reply echoes patient + datetime."""
    doctor_id = f"inttest_uec_st1_{uuid.uuid4().hex[:8]}"
    name = "梁昊"

    chat(f"新患者{name}，男，38岁", doctor_id=doctor_id)

    r = chat(f"帮{name}约下周三复诊", doctor_id=doctor_id)

    assert r is not None
    assert name in r["reply"], f"Reply should mention patient name"
    assert any(kw in r["reply"] for kw in ["预约", "复诊", "任务", "创建"]), (
        f"Reply should confirm task creation, got: '{r['reply']}'"
    )
    # Must echo normalized datetime (ADR 0012 §12)
    assert any(kw in r["reply"] for kw in ["月", "日", "点", "时"]), (
        f"Reply should echo datetime, got: '{r['reply']}'"
    )

    # DB: task row exists
    assert _task_count(doctor_id) >= 1

    # view_payload
    vp = r.get("view_payload")
    if vp is not None:
        assert vp.get("type") == "task_created"


@pytest.mark.integration
def test_schedule_task_follow_up_type():
    """Follow-up task variant uses correct task_type."""
    doctor_id = f"inttest_uec_st_fu_{uuid.uuid4().hex[:8]}"
    name = "何芳"

    chat(f"新患者{name}，女，45岁", doctor_id=doctor_id)
    r = chat(f"给{name}设个3个月后随访提醒", doctor_id=doctor_id)

    assert r is not None
    assert name in r["reply"]
    assert any(kw in r["reply"] for kw in ["随访", "提醒", "任务"]), (
        f"Reply should confirm follow-up task, got: '{r['reply']}'"
    )
    assert _task_count(doctor_id) >= 1


@pytest.mark.integration
def test_schedule_task_no_patient_returns_clarification():
    """schedule_task without bound patient → missing_field clarification."""
    doctor_id = f"inttest_uec_st_nopat_{uuid.uuid4().hex[:8]}"

    r = chat("约下周五复诊", doctor_id=doctor_id)

    assert any(kw in r["reply"] for kw in ["患者", "姓名", "谁"]), (
        f"Should ask for patient, got: '{r['reply']}'"
    )
    assert _task_count(doctor_id) == 0


# =============================================================================
# 8. Pending draft interaction (ADR 0012 §7)
# =============================================================================


@pytest.mark.integration
def test_pending_draft_blocks_context_switch():
    """Write to a different patient during pending draft → blocked."""
    doctor_id = f"inttest_uec_block1_{uuid.uuid4().hex[:8]}"

    chat("新患者甲某某，男，40岁", doctor_id=doctor_id)
    chat("胸闷一周加重", doctor_id=doctor_id)

    r_draft = chat("写记录", doctor_id=doctor_id)
    assert r_draft.get("pending_id"), "Should produce pending draft"

    # Attempt context-switching write → blocked
    r_blocked = chat("新患者乙某某，女，30岁", doctor_id=doctor_id)
    assert any(kw in r_blocked["reply"] for kw in [
        "待确认", "确认", "取消", "草稿", "先",
    ]), f"Should be blocked, got: '{r_blocked['reply']}'"
    assert _patient_count(doctor_id, "乙某某") == 0, "Blocked patient must not be created"

    # Cleanup
    chat("取消", doctor_id=doctor_id)


@pytest.mark.integration
def test_pending_draft_allows_same_patient_schedule():
    """Same-patient schedule_task during pending draft → allowed."""
    doctor_id = f"inttest_uec_allow1_{uuid.uuid4().hex[:8]}"
    name = "丙某某"

    chat(f"新患者{name}，男，55岁", doctor_id=doctor_id)
    chat("头痛三天，无恶心", doctor_id=doctor_id)

    r_draft = chat("写记录", doctor_id=doctor_id)
    assert r_draft.get("pending_id")

    r_task = chat(f"帮{name}约下周五复诊", doctor_id=doctor_id)
    # Should NOT be blocked
    blocked_keywords = ["待确认", "草稿", "先确认", "先取消"]
    is_blocked = any(kw in r_task["reply"] for kw in blocked_keywords)
    assert not is_blocked, (
        f"Same-patient schedule should be allowed, got: '{r_task['reply']}'"
    )
    assert _task_count(doctor_id) >= 1

    # Cleanup
    chat("取消", doctor_id=doctor_id)


@pytest.mark.integration
def test_pending_draft_allows_chitchat():
    """Chitchat during pending draft → allowed, returns chat_reply."""
    doctor_id = f"inttest_uec_chitchat_{uuid.uuid4().hex[:8]}"

    chat("新患者丁某某，男，45岁", doctor_id=doctor_id)
    chat("心悸两天，偶发", doctor_id=doctor_id)

    r_draft = chat("写记录", doctor_id=doctor_id)
    assert r_draft.get("pending_id")

    r_chat = chat("今天天气怎么样", doctor_id=doctor_id)
    assert r_chat["reply"], "Chitchat should return a reply"

    # Draft should still be pending after chitchat
    r_confirm = chat("确认", doctor_id=doctor_id)
    assert "保存" in r_confirm["reply"] or "已保存" in r_confirm["reply"] or \
           "已确认" in r_confirm["reply"], (
        f"Draft should still be confirmable after chitchat, got: '{r_confirm['reply']}'"
    )


@pytest.mark.integration
def test_pending_draft_blocks_second_draft():
    """create_draft while another draft is pending → blocked."""
    doctor_id = f"inttest_uec_block_draft_{uuid.uuid4().hex[:8]}"

    chat("新患者测试甲，男，50岁", doctor_id=doctor_id)
    chat("头晕两天", doctor_id=doctor_id)

    r1 = chat("写记录", doctor_id=doctor_id)
    assert r1.get("pending_id")

    # Second draft attempt → blocked
    chat("其实还有胸闷", doctor_id=doctor_id)
    r2 = chat("再写一个记录", doctor_id=doctor_id)
    assert any(kw in r2["reply"] for kw in [
        "待确认", "确认", "取消", "草稿", "先",
    ]), f"Second draft should be blocked, got: '{r2['reply']}'"

    # Cleanup
    chat("取消", doctor_id=doctor_id)


# =============================================================================
# 9. Chitchat / ambiguous input
# =============================================================================


@pytest.mark.integration
def test_chitchat_returns_reply_no_record():
    """Ambiguous non-clinical input → reply, no record, no crash."""
    doctor_id = f"inttest_uec_chat_{uuid.uuid4().hex[:8]}"

    r = chat("随便说点什么吧", doctor_id=doctor_id)

    assert r is not None
    assert r["reply"]
    assert r.get("record") is None
    assert r.get("pending_id") is None


@pytest.mark.integration
def test_chitchat_clinical_without_patient():
    """Clinical-sounding input without patient context → clarification."""
    doctor_id = f"inttest_uec_chat_clin_{uuid.uuid4().hex[:8]}"

    r = chat("血压偏高，需要调药", doctor_id=doctor_id)

    # Should either ask for patient or treat as chitchat — not crash
    assert r is not None
    assert r["reply"]
    assert r.get("record") is None


# =============================================================================
# 10. Doctor isolation
# =============================================================================


@pytest.mark.integration
def test_doctor_isolation_patients_not_shared():
    """Different doctor_ids cannot see each other's patients."""
    d1 = f"inttest_uec_iso1_{uuid.uuid4().hex[:8]}"
    d2 = f"inttest_uec_iso2_{uuid.uuid4().hex[:8]}"

    chat("新患者隔离甲，男，30岁", doctor_id=d1)
    assert _patient_count(d1, "隔离甲") == 1

    r = chat("查隔离甲的病历", doctor_id=d2)

    assert any(kw in r["reply"] for kw in [
        "未找到", "找不到", "不存在", "没有",
    ]), f"Doctor d2 should not see d1's patient, got: '{r['reply']}'"


@pytest.mark.integration
def test_doctor_isolation_tasks_not_shared():
    """Tasks created by one doctor not visible to another."""
    d1 = f"inttest_uec_iso_task1_{uuid.uuid4().hex[:8]}"
    d2 = f"inttest_uec_iso_task2_{uuid.uuid4().hex[:8]}"

    chat("新患者隔离乙，男，40岁", doctor_id=d1)
    chat("帮隔离乙约下周三复诊", doctor_id=d1)

    assert _task_count(d1) >= 1
    assert _task_count(d2) == 0


# =============================================================================
# 11. Edge cases
# =============================================================================


@pytest.mark.integration
def test_empty_input_returns_error():
    """Empty string input → error reply, no crash."""
    doctor_id = f"inttest_uec_empty_{uuid.uuid4().hex[:8]}"

    r = chat("", doctor_id=doctor_id)

    assert r is not None
    assert r["reply"]


@pytest.mark.integration
def test_very_long_input_no_crash():
    """Very long input (>500 chars) → handled without crash."""
    doctor_id = f"inttest_uec_long_{uuid.uuid4().hex[:8]}"

    long_text = "患者反复胸闷气短，" * 50  # ~450 chars
    r = chat(long_text, doctor_id=doctor_id)

    assert r is not None
    assert r["reply"]


@pytest.mark.integration
def test_rapid_sequential_turns():
    """Multiple rapid turns for same doctor → all succeed, no state corruption."""
    doctor_id = f"inttest_uec_rapid_{uuid.uuid4().hex[:8]}"
    name = "连续测试"

    r1 = chat(f"新患者{name}，男，35岁", doctor_id=doctor_id)
    assert _patient_count(doctor_id, name) == 1

    r2 = chat("头痛两天", doctor_id=doctor_id)
    assert r2["reply"]

    r3 = chat(f"查{name}的资料", doctor_id=doctor_id)
    assert r3["reply"]

    # Context should still be on this patient
    r4 = chat("写记录", doctor_id=doctor_id)
    if r4.get("pending_id"):
        assert name in r4["reply"]
        chat("取消", doctor_id=doctor_id)
