#!/usr/bin/env python
"""Stress test: send hardcoded vague patient responses to reproduce json_validate_failed.

Usage:
    PYTHONPATH=src python scripts/stress_test_interview.py [--server URL] [--turns 30] [--runs 3]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Load config for API keys
_CONFIG_PATH = _REPO_ROOT / "config" / "runtime.json"
if _CONFIG_PATH.exists():
    _cfg = json.loads(_CONFIG_PATH.read_text())
    for _cat in (_cfg.get("categories") or {}).values():
        for k, v in ((_cat.get("settings") if isinstance(_cat, dict) else None) or {}).items():
            val = v.get("value") if isinstance(v, dict) else v
            if isinstance(val, str) and val and k not in os.environ:
                os.environ[k] = val


# Hardcoded vague responses — designed to NOT provide useful clinical info
VAGUE_RESPONSES = [
    "不舒服",
    "说不清楚",
    "好几天了",
    "有时候",
    "不太记得",
    "好像有",
    "不确定",
    "应该没有吧",
    "不知道",
    "可能有一点",
    "记不清了",
    "好像是的",
    "也不太严重",
    "没注意过",
    "嗯",
    "对",
    "没有",
    "不清楚",
    "有时候会",
    "差不多吧",
    "还行",
    "不太好说",
    "反正就是不舒服",
    "头有点晕",
    "偶尔",
    "就是那种感觉",
    "不好形容",
    "时间挺长了",
    "没什么特别的",
    "一般般",
    "我儿子让我来看看的",
    "你们这里能看吗",
    "我也不太懂",
    "以前也这样过",
    "忘了",
    "好像吃过什么药",
    "那个药叫什么来着",
    "反正医生给开的",
    "血压有点高",
    "多少我不记得了",
    "检查做过好像",
    "结果不太记得",
    "没什么大问题吧",
    "我觉得还好",
    "就是来看看",
    "没有别的了",
    "你说呢",
    "这个要紧吗",
    "我也想知道怎么回事",
    "你们专业的说了算",
]


def _ensure_doctor(db_path: str, doctor_id: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO doctors (doctor_id, name, specialty, created_at, updated_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (doctor_id, "压力测试医生", "神经外科"),
        )
        conn.commit()
    finally:
        conn.close()


def run_one(server: str, db_path: str, max_turns: int, run_id: int) -> dict:
    """Run one stress session. Returns result dict."""
    doctor_id = f"stress_{uuid4().hex[:8]}"
    _ensure_doctor(db_path, doctor_id)

    client = httpx.Client(timeout=60)

    # Register
    resp = client.post(f"{server}/api/auth/unified/register/patient", json={
        "doctor_id": doctor_id,
        "name": f"压力{run_id}",
        "gender": "男",
        "year_of_birth": 1960,
        "phone": f"139{random.randint(10000000, 99999999)}",
    })
    resp.raise_for_status()
    token = resp.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    # Start interview
    resp = client.post(f"{server}/api/patient/interview/start", headers=auth)
    resp.raise_for_status()
    session_id = resp.json()["session_id"]

    # Send turns
    shuffled = list(VAGUE_RESPONSES)
    random.shuffle(shuffled)
    # Cycle if we need more turns than responses
    responses = (shuffled * ((max_turns // len(shuffled)) + 1))[:max_turns]

    errors = []
    turns_done = 0
    for i, msg in enumerate(responses):
        resp = client.post(
            f"{server}/api/patient/interview/turn",
            json={"session_id": session_id, "text": msg},
            headers=auth,
        )
        if resp.status_code != 200:
            errors.append({"turn": i + 1, "http_status": resp.status_code, "body": resp.text[:200]})
            continue

        result = resp.json()
        status = result.get("status", "?")
        reply = result.get("reply", "")
        turns_done = i + 1

        if "系统暂时繁忙" in reply or "没有理解" in reply:
            errors.append({"turn": i + 1, "type": "llm_error", "reply": reply})
            print(f"    Turn {i+1}: ERROR — {reply[:60]}")

        if status in ("reviewing", "confirmed", "error"):
            break

    # Cleanup test data
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM doctors WHERE doctor_id = ?", (doctor_id,))
        conn.execute("DELETE FROM patients WHERE doctor_id = ?", (doctor_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    return {"run": run_id, "turns": turns_done, "errors": errors, "session_id": session_id}


def main():
    parser = argparse.ArgumentParser(description="Stress test patient interview for json_validate_failed")
    parser.add_argument("--server", default="http://127.0.0.1:8001")
    parser.add_argument("--turns", type=int, default=30, help="Max turns per run")
    parser.add_argument("--runs", type=int, default=5, help="Number of sessions to run")
    args = parser.parse_args()

    db_path = str(_REPO_ROOT / "data" / "patients.db")
    print(f"Stress test: {args.runs} runs × {args.turns} max turns | Server: {args.server}")
    print()

    total_errors = 0
    for r in range(1, args.runs + 1):
        print(f"Run {r}/{args.runs}...", end=" ", flush=True)
        result = run_one(args.server, db_path, args.turns, r)
        n_err = len(result["errors"])
        total_errors += n_err
        print(f"{result['turns']} turns, {n_err} errors")

    print(f"\n{'='*50}")
    print(f"Total errors: {total_errors} across {args.runs} runs")

    # Check JSONL for logged errors
    jsonl_path = _REPO_ROOT / "logs" / "llm_calls.jsonl"
    if jsonl_path.exists():
        cutoff = time.strftime("%Y-%m-%dT%H:%M", time.gmtime(time.time() - 600))
        logged = 0
        for line in jsonl_path.read_text().split("\n")[-1000:]:
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                if e.get("status") == "error" and e.get("timestamp", "") > cutoff:
                    logged += 1
            except Exception:
                pass
        print(f"Error entries in llm_calls.jsonl (last 10min): {logged}")


if __name__ == "__main__":
    main()
