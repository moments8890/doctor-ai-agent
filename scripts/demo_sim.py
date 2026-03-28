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
    doctor_id = doctor["doctor_id"]

    # Ensure the demo doctor exists — register via direct DB insert
    # (unified auth requires invite codes, so we bypass that).
    await _ensure_demo_doctor(doctor)

    state = _load_state()
    state["seed_time"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("patients", {})
    state["kb_seeded"] = False

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


async def _ensure_demo_doctor(doctor: Dict[str, Any]) -> None:
    """Insert the demo doctor directly into the database if not present."""
    try:
        import sqlite3

        db_path = os.environ.get("DATABASE_URL", "data/doctor_agent.db")
        if db_path.startswith("sqlite:///"):
            db_path = db_path[len("sqlite:///"):]
        elif db_path.startswith("sqlite+aiosqlite:///"):
            db_path = db_path[len("sqlite+aiosqlite:///"):]

        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO doctors
                    (doctor_id, name, specialty, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    doctor["doctor_id"],
                    doctor.get("name", "Demo Doctor"),
                    doctor.get("specialty", ""),
                ),
            )
            conn.commit()
            logger.info("医生账户已就绪: %s (%s)", doctor.get("name"), doctor["doctor_id"])
        finally:
            conn.close()
    except Exception as exc:
        logger.error("创建医生账户失败: %s", exc)


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
    doctor_id = config["doctor"]["doctor_id"]
    prefix = doctor_id.rsplit("_", 1)[0] + "_" if "_" in doctor_id else "demo_"

    logger.info("正在清理演示数据 (prefix=%s) ...", prefix)

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

    print(f"=== 演示状态 ===")
    print(f"Seed 时间: {seed_time}")
    print(f"知识库已导入: {'是' if kb_seeded else '否'}")

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
