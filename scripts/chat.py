#!/usr/bin/env python3
"""
交互式命令行聊天客户端 — 用于手动测试医生AI助手的对话接口。

用法：
    python scripts/chat.py                        # 连接到 localhost:8000
    python scripts/chat.py http://other-host:8000

内置命令：
    /clear    重置对话历史
    /history  显示当前上下文轮数
    /quit     退出

Interactive CLI chatbot for testing the doctor AI agent.
"""

import json
import sys

try:
    import httpx
except ImportError:
    print("httpx not found. Run: pip install httpx")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8000"
DOCTOR_ID = "test_doctor"

# ANSI colours
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

_RECORD_FIELDS = [
    ("主诉",   "chief_complaint"),
    ("现病史", "history_of_present_illness"),
    ("既往史", "past_medical_history"),
    ("体格检查", "physical_examination"),
    ("辅助检查", "auxiliary_examinations"),
    ("诊断",   "diagnosis"),
    ("治疗方案", "treatment_plan"),
    ("随访计划", "follow_up_plan"),
]


def _print_record(record: dict) -> None:
    print(f"\n  {YELLOW}📋 结构化病历{RESET}")
    for label, key in _RECORD_FIELDS:
        val = record.get(key)
        if val:
            print(f"  {GRAY}【{label}】{RESET} {val}")


def _send(base_url: str, text: str, history: list, doctor_id: str) -> tuple:
    resp = httpx.post(
        f"{base_url}/api/records/chat",
        json={"text": text, "history": history, "doctor_id": doctor_id},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["reply"], data.get("record")


def _handle_command(raw: str, history: list) -> bool:
    """Handle /clear, /history, /quit commands; return True if loop should continue."""
    if raw in ("/quit", "/exit", "quit", "exit"):
        print("Bye!")
        return False
    if raw == "/clear":
        history.clear()
        print(f"{GRAY}  History cleared.{RESET}\n")
        return True
    if raw == "/history":
        turns = len(history) // 2
        print(f"{GRAY}  {turns} turn(s) in context window{RESET}\n")
        return True
    return None  # not a command


def _chat_loop(base_url: str, doctor_id: str) -> None:
    """Run the interactive chat read-eval-print loop."""
    history: list = []
    while True:
        try:
            raw = input(f"{CYAN}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not raw:
            continue
        cmd_result = _handle_command(raw, history)
        if cmd_result is False:
            break
        if cmd_result is True:
            continue
        try:
            reply, record = _send(base_url, raw, history, doctor_id)
        except httpx.ConnectError:
            print(f"{YELLOW}  Cannot connect to {base_url} — is the server running?{RESET}\n")
            continue
        except httpx.HTTPStatusError as e:
            print(f"{YELLOW}  HTTP {e.response.status_code}: {e.response.text[:200]}{RESET}\n")
            continue
        except Exception as e:
            print(f"{YELLOW}  {e}{RESET}\n")
            continue
        print(f"{GREEN}Agent:{RESET} {reply}")
        if record:
            _print_record(record)
        print()
        history.append({"role": "user", "content": raw})
        history.append({"role": "assistant", "content": reply})


def main() -> None:
    """Entry point: parse args and start the chat loop."""
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else BASE_URL
    doctor_id = sys.argv[2] if len(sys.argv) > 2 else DOCTOR_ID
    print(f"\n{BOLD}Doctor AI Agent — Chat Tester{RESET}")
    print(f"{GRAY}  server={base_url}  doctor_id={doctor_id}{RESET}")
    print(f"{GRAY}  /clear  reset history  |  /history  show context size  |  /quit  exit{RESET}\n")
    _chat_loop(base_url, doctor_id)


if __name__ == "__main__":
    main()
