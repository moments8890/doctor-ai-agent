#!/usr/bin/env python3
"""
交互式命令行聊天客户端 — 用于手动测试医生AI助手的对话接口。

用法：
    python scripts/chat.py                        # 连接到 localhost:8000
    python scripts/chat.py http://other-host:8000
    python scripts/chat.py http://other-host:8000 --token <bearer-token>

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


def _print_record(record: dict) -> None:
    """Pretty-print a chat-first MedicalRecord (content + tags)."""
    print(f"\n  {YELLOW}📋 结构化病历{RESET}")
    content = record.get("content")
    if content:
        # Show first 200 chars of content
        preview = content[:200] + ("…" if len(content) > 200 else "")
        print(f"  {GRAY}【内容】{RESET} {preview}")
    tags = record.get("tags")
    if tags:
        tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        print(f"  {GRAY}【标签】{RESET} {tag_str}")
    record_type = record.get("record_type")
    if record_type:
        print(f"  {GRAY}【类型】{RESET} {record_type}")


def _send(base_url: str, text: str, history: list, doctor_id: str, token: str | None) -> tuple:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.post(
        f"{base_url}/api/records/chat",
        json={"text": text, "history": history, "doctor_id": doctor_id},
        headers=headers,
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


def _chat_loop(base_url: str, doctor_id: str, token: str | None) -> None:
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
            reply, record = _send(base_url, raw, history, doctor_id, token)
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
    import argparse
    parser = argparse.ArgumentParser(description="Interactive chat client for doctor AI agent")
    parser.add_argument("base_url", nargs="?", default=BASE_URL, help="Server base URL")
    parser.add_argument("--doctor-id", default=DOCTOR_ID, help="Doctor ID to use")
    parser.add_argument("--token", default=None, help="Bearer token for authentication")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    auth_info = "  token=set" if args.token else "  token=none (dev fallback)"
    print(f"\n{BOLD}Doctor AI Agent — Chat Tester{RESET}")
    print(f"{GRAY}  server={base_url}  doctor_id={args.doctor_id}{auth_info}{RESET}")
    print(f"{GRAY}  /clear  reset history  |  /history  show context size  |  /quit  exit{RESET}\n")
    _chat_loop(base_url, args.doctor_id, args.token)


if __name__ == "__main__":
    main()
