#!/usr/bin/env python3
"""Demo simulation engine — seed patients, schedule messages, manage demo lifecycle.

Usage:
    python scripts/demo_sim.py --seed
    python scripts/demo_sim.py --tick
    python scripts/demo_sim.py --skip-to 李大爷 3
    python scripts/demo_sim.py --reset
    python scripts/demo_sim.py --status
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Ensure scripts/ and src/ are importable
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from patient_sim.http_client import (
    cleanup_demo_data,
    register_patient,
    seed_knowledge_item,
    send_patient_chat,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("demo_sim")

# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------

_STATE_FILE = _SCRIPT_DIR / ".demo_state.json"


def _load_state() -> Dict[str, Any]:
    if _STATE_FILE.exists():
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Seed command
# ---------------------------------------------------------------------------

async def cmd_seed(config: Dict[str, Any], server: str) -> None:
    """Register all patients and seed all KB entries from YAML config."""
    doctor = config["doctor"]

    state = _load_state()
    state["seed_time"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("patients", {})
    state["kb_seeded"] = False

    # Ensure the demo doctor exists via proper auth flow
    doctor_id = await _ensure_demo_doctor(doctor, server, state)
    if not doctor_id:
        logger.error("无法创建医生账户，终止。")
        _save_state(state)
        return

    # Store the actual doctor_id (may differ from config)
    state["config_doctor_id"] = config["doctor"]["doctor_id"]
    state["actual_doctor_id"] = doctor_id
    _save_state(state)

    # --- Register patients ---
    patients = config.get("patients", [])
    for p in patients:
        name = p["name"]
        if name in state["patients"] and state["patients"][name].get("patient_id"):
            logger.info("跳过已注册患者: %s", name)
            continue

        logger.info("正在注册患者: %s ...", name)
        try:
            result = await register_patient(
                server_url=server,
                doctor_id=doctor_id,
                name=name,
                gender=p.get("gender", ""),
                year_of_birth=p.get("year_of_birth", 1970),
                phone=p.get("phone"),
            )
            patient_id = result.get("patient_id")
            token = result.get("token", "")
            state["patients"][name] = {
                "patient_id": patient_id,
                "token": token,
                "sent_messages": [],
            }
            logger.info("  ✓ 注册成功: %s (patient_id=%s)", name, patient_id)
        except Exception as exc:
            logger.error("  ✗ 注册失败: %s — %s", name, exc)

    _save_state(state)

    # --- Seed knowledge base ---
    knowledge = config.get("knowledge", [])
    if knowledge:
        logger.info("正在导入知识库 (%d 条) ...", len(knowledge))
        success_count = 0
        for idx, kb in enumerate(knowledge, 1):
            title = kb.get("title", f"KB-{idx}")
            logger.info("  [%d/%d] %s", idx, len(knowledge), title)
            try:
                await seed_knowledge_item(
                    server_url=server,
                    doctor_id=doctor_id,
                    text=kb["content"],
                    category=kb.get("category", "custom"),
                    source=kb.get("source", "demo"),
                    source_url=kb.get("source_url"),
                    title=title,
                )
                success_count += 1
                logger.info("    ✓ 导入成功")
            except Exception as exc:
                logger.error("    ✗ 导入失败: %s", exc)

        state["kb_seeded"] = True
        _save_state(state)
        logger.info("知识库导入完成: %d/%d 成功", success_count, len(knowledge))

    logger.info("Seed 完成。")


def _find_db_path() -> str:
    """Locate the SQLite database file."""
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///"):]
    if db_url.startswith("sqlite+aiosqlite:///"):
        return db_url[len("sqlite+aiosqlite:///"):]
    for candidate in ["data/patients.db", "data/doctor_agent.db", "data/doctor_ai.db"]:
        if os.path.exists(candidate):
            return candidate
    return "data/patients.db"


async def _ensure_demo_doctor(doctor: Dict[str, Any], server: str, state: Dict[str, Any]) -> Optional[str]:
    """Create the demo doctor via the proper auth flow.

    Steps:
    1. Check if doctor already exists (from previous seed)
    2. Create an invite code in the DB
    3. Register the doctor via the HTTP API
    4. Store credentials in state for future login
    5. Return the actual doctor_id assigned by the auth system

    This works for any sim config, not just a specific doctor.
    """
    import sqlite3

    config_id = doctor["doctor_id"]
    name = doctor.get("name", "Demo Doctor")
    specialty = doctor.get("specialty", "")
    phone = doctor.get("phone", f"138{abs(hash(config_id)) % 100000000:08d}")
    year_of_birth = doctor.get("year_of_birth", 1970)

    # Check if already seeded from a previous run
    if state.get("doctor_token") and state.get("doctor_id"):
        # Verify the token still works
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{server.rstrip('/')}/api/auth/unified/me",
                    headers={"Authorization": f"Bearer {state['doctor_token']}"},
                )
                if resp.status_code == 200:
                    logger.info("医生账户已就绪: %s (doctor_id=%s)", name, state["doctor_id"])
                    return state["doctor_id"]
        except Exception:
            pass  # Token invalid, re-register

    # Try to login first (doctor may exist from manual registration)
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{server.rstrip('/')}/api/auth/unified/login",
                json={"phone": phone, "year_of_birth": year_of_birth},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("role") == "doctor":
                    state["doctor_id"] = data["doctor_id"]
                    state["doctor_token"] = data["token"]
                    state["doctor_phone"] = phone
                    state["doctor_year_of_birth"] = year_of_birth
                    logger.info("医生账户已就绪 (已有账户): %s (doctor_id=%s)", name, data["doctor_id"])
                    return data["doctor_id"]
    except Exception:
        pass

    # Create invite code + register via API
    db_path = _find_db_path()
    invite_code = f"sim_{abs(hash(config_id + name)) % 10000000:07d}"

    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO invite_codes
                    (code, doctor_id, doctor_name, active, created_at, max_uses, used_count)
                VALUES (?, NULL, ?, 1, datetime('now'), 99, 0)
                """,
                (invite_code, name),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.error("创建邀请码失败: %s", exc)
        return None

    # Register doctor via API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{server.rstrip('/')}/api/auth/unified/register/doctor",
                json={
                    "invite_code": invite_code,
                    "name": name,
                    "phone": phone,
                    "year_of_birth": year_of_birth,
                    "specialty": specialty,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        actual_doctor_id = data["doctor_id"]
        state["doctor_id"] = actual_doctor_id
        state["doctor_token"] = data["token"]
        state["doctor_phone"] = phone
        state["doctor_year_of_birth"] = year_of_birth
        state["invite_code"] = invite_code
        logger.info("医生账户已创建: %s (doctor_id=%s)", name, actual_doctor_id)
        logger.info("  登录方式: 手机号=%s 口令=%d", phone, year_of_birth)
        logger.info("  邀请码: %s (可在登录页使用)", invite_code)
        return actual_doctor_id
    except Exception as exc:
        logger.error("医生注册失败: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Tick command
# ---------------------------------------------------------------------------

async def cmd_tick(config: Dict[str, Any], server: str) -> None:
    """Send messages whose delay has elapsed since seed time."""
    state = _load_state()
    if not state.get("seed_time"):
        logger.error("尚未执行 --seed，请先运行 --seed 命令。")
        return

    seed_time = datetime.fromisoformat(state["seed_time"])
    now = datetime.now(timezone.utc)
    elapsed_hours = (now - seed_time).total_seconds() / 3600.0

    patients_config = config.get("patients", [])
    patients_state = state.get("patients", {})

    sent_any = False

    for p in patients_config:
        name = p["name"]
        p_state = patients_state.get(name)
        if not p_state or not p_state.get("token"):
            logger.warning("跳过未注册患者: %s", name)
            continue

        token = p_state["token"]
        sent_indices = set(p_state.get("sent_messages", []))
        messages = p.get("messages", [])

        for idx, msg in enumerate(messages):
            if idx in sent_indices:
                continue

            delay = msg.get("delay_hours", 0)
            if elapsed_hours < delay:
                continue

            # Message is due — send it
            content = msg["content"]
            logger.info("发送消息: %s [%d] (延迟 %dh, 已过 %.1fh)", name, idx, delay, elapsed_hours)
            try:
                result = await send_patient_chat(
                    server_url=server,
                    patient_token=token,
                    content=content,
                )
                triage = result.get("triage_category", "unknown")
                logger.info("  ✓ 发送成功 (triage=%s)", triage)
                sent_indices.add(idx)
                sent_any = True
            except Exception as exc:
                logger.error("  ✗ 发送失败: %s", exc)

        p_state["sent_messages"] = sorted(sent_indices)

    _save_state(state)

    if not sent_any:
        logger.info("没有新消息需要发送。")
    else:
        logger.info("Tick 完成。")


# ---------------------------------------------------------------------------
# Skip-to command
# ---------------------------------------------------------------------------

async def cmd_skip_to(
    config: Dict[str, Any],
    server: str,
    patient_name: str,
    msg_num: int,
) -> None:
    """Force-send a specific message immediately."""
    state = _load_state()
    if not state.get("seed_time"):
        logger.error("尚未执行 --seed，请先运行 --seed 命令。")
        return

    patients_state = state.get("patients", {})
    p_state = patients_state.get(patient_name)
    if not p_state or not p_state.get("token"):
        logger.error("未找到患者: %s（请先执行 --seed）", patient_name)
        return

    # Find the patient config
    p_config = None
    for p in config.get("patients", []):
        if p["name"] == patient_name:
            p_config = p
            break

    if p_config is None:
        logger.error("配置文件中未找到患者: %s", patient_name)
        return

    messages = p_config.get("messages", [])
    # msg_num is 1-based for user convenience
    idx = msg_num - 1
    if idx < 0 or idx >= len(messages):
        logger.error("消息编号 %d 超出范围 (该患者共 %d 条消息)", msg_num, len(messages))
        return

    sent_indices = set(p_state.get("sent_messages", []))
    if idx in sent_indices:
        logger.warning("消息 %d 已发送过，将重新发送。", msg_num)

    msg = messages[idx]
    content = msg["content"]
    token = p_state["token"]

    logger.info("强制发送: %s 消息 #%d", patient_name, msg_num)
    logger.info("  内容: %s", content[:60] + ("..." if len(content) > 60 else ""))

    try:
        result = await send_patient_chat(
            server_url=server,
            patient_token=token,
            content=content,
        )
        triage = result.get("triage_category", "unknown")
        logger.info("  ✓ 发送成功 (triage=%s)", triage)
        sent_indices.add(idx)
        p_state["sent_messages"] = sorted(sent_indices)
        _save_state(state)
    except Exception as exc:
        logger.error("  ✗ 发送失败: %s", exc)


# ---------------------------------------------------------------------------
# Reset command
# ---------------------------------------------------------------------------

async def cmd_reset(config: Dict[str, Any], server: str) -> None:
    """Delete all demo simulation data."""
    state = _load_state()
    # Use actual doctor_id from state if available, otherwise fall back to config
    doctor_id = state.get("actual_doctor_id") or config["doctor"]["doctor_id"]
    # Clean up by exact doctor_id match (more precise than prefix)
    prefix = doctor_id

    logger.info("正在清理演示数据 (doctor_id=%s) ...", doctor_id)

    result = await cleanup_demo_data(server_url=server, doctor_id_prefix=prefix)
    deleted = result.get("deleted_rows", 0)
    logger.info("  数据库清理完成: 删除 %d 行", deleted)

    if _STATE_FILE.exists():
        _STATE_FILE.unlink()
        logger.info("  状态文件已删除")

    logger.info("Reset 完成。")


# ---------------------------------------------------------------------------
# Status command
# ---------------------------------------------------------------------------

def cmd_status(config: Dict[str, Any]) -> None:
    """Print current demo status."""
    state = _load_state()
    if not state:
        print("状态: 未初始化 (请先运行 --seed)")
        return

    seed_time = state.get("seed_time", "未知")
    kb_seeded = state.get("kb_seeded", False)
    doctor_id = state.get("actual_doctor_id", "未知")
    phone = state.get("doctor_phone", "未知")
    yob = state.get("doctor_year_of_birth", "未知")

    print(f"=== 演示状态 ===")
    print(f"Seed 时间: {seed_time}")
    print(f"知识库已导入: {'是' if kb_seeded else '否'}")
    print()
    print(f"=== 医生登录信息 ===")
    print(f"Doctor ID: {doctor_id}")
    print(f"手机号: {phone}")
    print(f"口令 (出生年份): {yob}")
    if state.get("invite_code"):
        print(f"邀请码: {state['invite_code']}")

    if seed_time and seed_time != "未知":
        try:
            st = datetime.fromisoformat(seed_time)
            now = datetime.now(timezone.utc)
            elapsed = (now - st).total_seconds() / 3600.0
            print(f"已运行时间: {elapsed:.1f} 小时")
        except Exception:
            pass

    print()

    patients_config = config.get("patients", [])
    patients_state = state.get("patients", {})

    for p in patients_config:
        name = p["name"]
        messages = p.get("messages", [])
        p_state = patients_state.get(name, {})
        patient_id = p_state.get("patient_id", "未注册")
        sent = set(p_state.get("sent_messages", []))

        registered = "✓" if p_state.get("patient_id") else "✗"
        print(f"[{registered}] {name} (patient_id={patient_id})")

        for idx, msg in enumerate(messages):
            delay = msg.get("delay_hours", 0)
            status_icon = "✓" if idx in sent else "○"
            content_preview = msg["content"][:50] + ("..." if len(msg["content"]) > 50 else "")
            print(f"    {status_icon} [{idx + 1}] +{delay}h: {content_preview}")

        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demo simulation engine — seed patients, schedule messages, manage demo lifecycle.",
    )
    parser.add_argument(
        "--config",
        default=str(_SCRIPT_DIR / "demo_config.yaml"),
        help="Path to YAML config file (default: scripts/demo_config.yaml)",
    )
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )

    # Mutually exclusive commands
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true", help="注册患者并导入知识库")
    group.add_argument("--tick", action="store_true", help="发送已到期的消息")
    group.add_argument("--skip-to", nargs=2, metavar=("PATIENT", "MSG_NUM"), help="强制发送指定消息")
    group.add_argument("--reset", action="store_true", help="清除所有演示数据")
    group.add_argument("--status", action="store_true", help="显示当前演示状态")

    args = parser.parse_args()

    # Load config
    config_path = args.config
    if not os.path.isfile(config_path):
        logger.error("配置文件不存在: %s", config_path)
        sys.exit(1)

    config = _load_config(config_path)

    # Dispatch
    if args.seed:
        asyncio.run(cmd_seed(config, args.server))
    elif args.tick:
        asyncio.run(cmd_tick(config, args.server))
    elif args.skip_to:
        patient_name = args.skip_to[0]
        try:
            msg_num = int(args.skip_to[1])
        except ValueError:
            logger.error("消息编号必须是整数: %s", args.skip_to[1])
            sys.exit(1)
        asyncio.run(cmd_skip_to(config, args.server, patient_name, msg_num))
    elif args.reset:
        asyncio.run(cmd_reset(config, args.server))
    elif args.status:
        cmd_status(config)


if __name__ == "__main__":
    main()
