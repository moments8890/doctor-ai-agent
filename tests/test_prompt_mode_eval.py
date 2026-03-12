"""
Prompt-mode evaluation: compare `full` vs `compact` routing prompt under identical context assembly.

Calls dispatch() against the real LLM (ROUTING_LLM) with each prompt mode and scores:
  - Intent selection accuracy
  - Patient name extraction
  - Tool choice correctness
  - Clarification / false-positive behavior

Skipped automatically when no LLM is reachable (same guard as E2E integration tests).

Usage:
  # Run with default ROUTING_LLM provider:
  .venv/bin/python -m pytest tests/test_prompt_mode_eval.py -v --tb=short

  # Force a specific provider:
  ROUTING_LLM=deepseek .venv/bin/python -m pytest tests/test_prompt_mode_eval.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.ai.intent import Intent


# ---------------------------------------------------------------------------
# Skip guard: require a reachable LLM
# ---------------------------------------------------------------------------

def _llm_available() -> bool:
    """Return True if the routing LLM is configured and likely reachable."""
    provider = os.environ.get("ROUTING_LLM") or os.environ.get("STRUCTURING_LLM", "")
    if not provider:
        return False
    # For API-based providers, check that the key is set
    key_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "groq": "GROQ_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_key = key_map.get(provider)
    if env_key and not os.environ.get(env_key):
        return False
    return True


def _prompt_mode_eval_enabled() -> bool:
    return os.environ.get("RUN_PROMPT_MODE_EVAL", "").strip().lower() in {"1", "true", "yes"}


pytestmark = [
    pytest.mark.skipif(
        not _prompt_mode_eval_enabled(),
        reason="Prompt-mode benchmark is opt-in; set RUN_PROMPT_MODE_EVAL=1 to run against a real LLM",
    ),
    pytest.mark.skipif(
        _prompt_mode_eval_enabled() and not _llm_available(),
        reason="No reachable ROUTING_LLM configured (set ROUTING_LLM + API key)",
    ),
]


# ---------------------------------------------------------------------------
# Evaluation case definition
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    id: str
    text: str
    expected_intent: str  # Intent enum name (e.g. "add_record")
    expected_patient: Optional[str] = None  # expected patient_name if any
    history: Optional[List[dict]] = None
    knowledge_context: Optional[str] = None
    notes: str = ""


EVAL_CASES: List[EvalCase] = [
    # --- Core routing ---
    EvalCase(
        id="note_capture",
        text="张三，男45岁，反复胸闷一周，活动后加重，休息后缓解",
        expected_intent="add_record",
        expected_patient="张三",
        notes="Standard clinical note with demographics",
    ),
    EvalCase(
        id="followup_note",
        text="张三今天复查，胸闷好转，血压130/80，继续阿司匹林",
        expected_intent="add_record",
        expected_patient="张三",
        notes="Follow-up visit for existing patient",
    ),
    EvalCase(
        id="patient_lookup",
        text="查询张三的病历",
        expected_intent="query_records",
        expected_patient="张三",
        notes="Explicit query signal should override any clinical vocab",
    ),
    EvalCase(
        id="query_with_clinical_vocab",
        text="看一下张三上次的心电图结果",
        expected_intent="query_records",
        expected_patient="张三",
        notes="Query with clinical terms — query signal must win",
    ),
    EvalCase(
        id="task_complete",
        text="完成 3",
        expected_intent="complete_task",
        expected_patient=None,
        notes="Simple task action with ID",
    ),
    EvalCase(
        id="followup_schedule",
        text="张三三个月后随访",
        expected_intent="schedule_follow_up",
        expected_patient="张三",
        notes="Follow-up scheduling — not add_record",
    ),

    # --- Clarification / name resolution ---
    EvalCase(
        id="clarification_name_reply",
        text="陈明",
        expected_intent="add_record",
        expected_patient="陈明",
        history=[
            {"role": "user", "content": "突发胸痛两小时，伴大汗"},
            {"role": "assistant", "content": "请问这位患者叫什么名字？"},
        ],
        notes="Bare name after clarification question → add_record with patient_name",
    ),

    # --- Create patient ---
    EvalCase(
        id="create_patient_only",
        text="新患者李明，男，30岁",
        expected_intent="create_patient",
        expected_patient="李明",
        notes="Patient creation without clinical content",
    ),

    # --- Correction ---
    EvalCase(
        id="record_correction",
        text="刚才写错了，诊断应该是高血压三级",
        expected_intent="update_record",
        expected_patient=None,
        notes="Correction signal must be recognized",
    ),

    # --- Edge cases ---
    EvalCase(
        id="greeting_no_tool",
        text="你好",
        expected_intent="unknown",
        expected_patient=None,
        notes="Greeting should NOT invoke any tool",
    ),
    EvalCase(
        id="list_patients",
        text="所有患者",
        expected_intent="list_patients",
        expected_patient=None,
        notes="Patient list request",
    ),
    EvalCase(
        id="list_tasks",
        text="待办任务",
        expected_intent="list_tasks",
        expected_patient=None,
        notes="Task list request",
    ),
    EvalCase(
        id="delete_patient",
        text="删除患者王五",
        expected_intent="delete_patient",
        expected_patient="王五",
        notes="Delete intent with patient name",
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    case_id: str
    mode: str
    actual_intent: str
    actual_patient: Optional[str]
    intent_match: bool
    patient_match: bool
    notes: str = ""


async def _run_case(case: EvalCase, mode: str) -> EvalResult:
    """Run one evaluation case with the given prompt mode."""
    os.environ["AGENT_ROUTING_PROMPT_MODE"] = mode

    from services.ai.agent import dispatch

    result = await dispatch(
        text=case.text,
        history=case.history,
        knowledge_context=case.knowledge_context,
    )

    actual_intent = result.intent.name if result.intent else "none"
    actual_patient = result.patient_name

    intent_ok = actual_intent == case.expected_intent
    patient_ok = (
        (actual_patient or "") == (case.expected_patient or "")
        if case.expected_patient is not None
        else True  # don't check patient if not specified
    )

    return EvalResult(
        case_id=case.id,
        mode=mode,
        actual_intent=actual_intent,
        actual_patient=actual_patient,
        intent_match=intent_ok,
        patient_match=patient_ok,
        notes="" if intent_ok and patient_ok else f"expected={case.expected_intent}/{case.expected_patient}",
    )


# ---------------------------------------------------------------------------
# Parametrized tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["full", "compact"])
@pytest.mark.parametrize("case", EVAL_CASES, ids=[c.id for c in EVAL_CASES])
@pytest.mark.asyncio
async def test_prompt_mode_routing(case: EvalCase, mode: str):
    """Evaluate intent routing accuracy for each prompt mode."""
    result = await _run_case(case, mode)
    assert result.intent_match, (
        f"[{mode}] {case.id}: expected intent={case.expected_intent}, "
        f"got={result.actual_intent}"
    )


@pytest.mark.parametrize("mode", ["full", "compact"])
@pytest.mark.parametrize(
    "case",
    [c for c in EVAL_CASES if c.expected_patient is not None],
    ids=[c.id for c in EVAL_CASES if c.expected_patient is not None],
)
@pytest.mark.asyncio
async def test_prompt_mode_patient_binding(case: EvalCase, mode: str):
    """Evaluate patient name extraction accuracy for each prompt mode."""
    result = await _run_case(case, mode)
    assert result.patient_match, (
        f"[{mode}] {case.id}: expected patient={case.expected_patient}, "
        f"got={result.actual_patient}"
    )


# ---------------------------------------------------------------------------
# Summary report (run as standalone)
# ---------------------------------------------------------------------------

async def _run_full_evaluation():
    """Run all cases in both modes and print a comparison table."""
    results: List[EvalResult] = []
    for mode in ("full", "compact"):
        for case in EVAL_CASES:
            try:
                r = await _run_case(case, mode)
            except Exception as e:
                r = EvalResult(
                    case_id=case.id, mode=mode,
                    actual_intent="ERROR", actual_patient=None,
                    intent_match=False, patient_match=False,
                    notes=str(e)[:60],
                )
            results.append(r)
            status = "OK" if r.intent_match and r.patient_match else "FAIL"
            print(f"  [{mode:7s}] {case.id:30s} intent={r.actual_intent:20s} patient={r.actual_patient or '-':8s} {status}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for mode in ("full", "compact"):
        mode_results = [r for r in results if r.mode == mode]
        intent_acc = sum(1 for r in mode_results if r.intent_match) / len(mode_results) * 100
        patient_results = [r for r in mode_results if r.case_id in {c.id for c in EVAL_CASES if c.expected_patient is not None}]
        patient_acc = sum(1 for r in patient_results if r.patient_match) / max(len(patient_results), 1) * 100
        print(f"  {mode:7s}: intent={intent_acc:.0f}% ({sum(1 for r in mode_results if r.intent_match)}/{len(mode_results)})  "
              f"patient={patient_acc:.0f}% ({sum(1 for r in patient_results if r.patient_match)}/{len(patient_results)})")

    # Show failures
    failures = [r for r in results if not r.intent_match or not r.patient_match]
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for r in failures:
            print(f"  [{r.mode}] {r.case_id}: got intent={r.actual_intent} patient={r.actual_patient} | {r.notes}")
    else:
        print("\nAll cases passed in both modes.")


if __name__ == "__main__":
    asyncio.run(_run_full_evaluation())
