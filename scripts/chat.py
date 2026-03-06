#!/usr/bin/env python3
"""
Interactive CLI chatbot for testing the doctor AI agent.

Usage:
    python scripts/chat.py                        # connects to localhost:8000
    python scripts/chat.py http://other-host:8000

Commands:
    /clear    reset conversation history
    /history  show how many turns are in context
    /quit     exit
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


def main() -> None:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else BASE_URL
    doctor_id = sys.argv[2] if len(sys.argv) > 2 else DOCTOR_ID
    history: list = []

    print(f"\n{BOLD}🩺  Doctor AI Agent — Chat Tester{RESET}")
    print(f"{GRAY}  server    : {base_url}{RESET}")
    print(f"{GRAY}  doctor_id : {doctor_id}{RESET}")
    print(f"{GRAY}  /clear  reset history  |  /history  show context size  |  /quit  exit{RESET}\n")

    while True:
        try:
            raw = input(f"{CYAN}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not raw:
            continue

        # ── built-in commands ────────────────────────────────────────────────
        if raw in ("/quit", "/exit", "quit", "exit"):
            print("Bye!")
            break

        if raw == "/clear":
            history.clear()
            print(f"{GRAY}  History cleared.{RESET}\n")
            continue

        if raw == "/history":
            turns = len(history) // 2
            print(f"{GRAY}  {turns} turn(s) in context window{RESET}\n")
            continue

        # ── send to server ───────────────────────────────────────────────────
        try:
            reply, record = _send(base_url, raw, history, doctor_id)
        except httpx.ConnectError:
            print(f"{YELLOW}  ⚠  Cannot connect to {base_url} — is the server running?{RESET}\n")
            continue
        except httpx.HTTPStatusError as e:
            print(f"{YELLOW}  ⚠  HTTP {e.response.status_code}: {e.response.text[:200]}{RESET}\n")
            continue
        except Exception as e:
            print(f"{YELLOW}  ⚠  {e}{RESET}\n")
            continue

        # ── display response ─────────────────────────────────────────────────
        print(f"{GREEN}Agent:{RESET} {reply}")
        if record:
            _print_record(record)
        print()

        # Append to local history so next turn has context
        history.append({"role": "user",      "content": raw})
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
