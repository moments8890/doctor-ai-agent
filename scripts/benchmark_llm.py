#!/usr/bin/env python3
"""
Benchmark the full dispatch pipeline: fast_router + routing LLM + structuring LLM.

Fast-router pass only (no network, always works):
    python scripts/benchmark_llm.py

Including real LLM dispatch calls (requires configured provider):
    ROUTING_LLM=ollama OLLAMA_BASE_URL=http://192.168.0.123:11434/v1 \\
        python scripts/benchmark_llm.py --llm

    ROUTING_LLM=ollama OLLAMA_MODEL=qwen2.5:7b \\
    OLLAMA_STRUCTURING_MODEL=qwen2.5:14b \\
        python scripts/benchmark_llm.py --llm --structuring

Reports: p50/p95/p99, fast-route hit rate, per-tier breakdown, projected savings.
"""
from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Test corpus ───────────────────────────────────────────────────────────────

_CORPUS = [
    # Tier 1/2 fast-route (structural commands)
    ("患者列表", "list_patients"),
    ("所有患者", "list_patients"),
    ("待办", "list_tasks"),
    ("我的任务", "list_tasks"),
    ("查张三", "query_records"),
    ("张三的病历", "query_records"),
    ("新患者李明", "create_patient"),
    ("新患者张三，男，45岁", "create_patient"),
    ("删除王五", "delete_patient"),
    ("完成任务1", "complete_task"),
    ("完成任务三", "complete_task"),
    ("帮我查李明的情况", "query_records"),
    # Tier 3 fast-route (clinical keywords → add_record, skip routing LLM)
    ("张三，男，58岁，胸闷气促3天，BNP 980，EF 50%，心衰III级，予以利尿强心", "add_record"),
    ("李明发烧三天，体温38.5，咳嗽，给予对乙酰氨基酚退烧", "add_record"),
    ("王五腹痛，排除阑尾炎，建议观察48小时", "add_record"),
    ("张三心悸三天，心电图AF，给予倍他乐克12.5mg", "add_record"),
    ("患者主诉胸痛，查肌钙蛋白I 0.3，考虑急性心肌梗死，立即溶栓", "add_record"),
    ("随访：张三血糖控制良好，HbA1c 6.8%，继续二甲双胍", "add_record"),
    ("李红化疗后乏力，WBC 2.1，ANC 0.8，暂停化疗，给予G-CSF支持", "add_record"),
    # LLM required (routing LLM must decide)
    ("患者血压160/100，目前服用氨氯地平5mg，考虑加量", "llm"),
    ("王五复查，血压稳定，120/80，继续当前方案", "llm"),
    ("你好", "llm"),
    ("帮我一下", "llm"),
    ("这个患者上次的检查结果", "llm"),
]


# ── Fast router benchmark ─────────────────────────────────────────────────────

def _bench_fast_router(corpus: list[tuple[str, str]]) -> dict:
    from services.fast_router import fast_route
    from services.intent import Intent

    latencies_us: list[float] = []
    tier1_2_hits = 0
    tier3_hits = 0
    llm_required = 0
    errors: list[str] = []

    for text, expected in corpus:
        t0 = time.perf_counter_ns()
        result = fast_route(text)
        elapsed_us = (time.perf_counter_ns() - t0) / 1000
        latencies_us.append(elapsed_us)

        if result is None:
            llm_required += 1
            if expected not in ("llm",):
                errors.append(f"MISS: {text!r} → None (expected {expected})")
        else:
            intent_val = result.intent.value
            if intent_val == "add_record":
                tier3_hits += 1
            else:
                tier1_2_hits += 1
            if expected != "llm" and intent_val != expected:
                errors.append(f"WRONG: {text!r} → {intent_val} (expected {expected})")

    total = len(corpus)
    fast_hits = tier1_2_hits + tier3_hits
    return {
        "total": total,
        "tier1_2_hits": tier1_2_hits,
        "tier3_hits": tier3_hits,
        "fast_hits": fast_hits,
        "llm_required": llm_required,
        "hit_rate_pct": fast_hits / total * 100,
        "latencies_us": latencies_us,
        "errors": errors,
    }


# ── LLM dispatch benchmark (optional) ────────────────────────────────────────

async def _bench_llm_dispatch(
    texts: list[str],
    include_structuring: bool = False,
) -> dict:
    from services.agent import dispatch

    latencies_ms: list[float] = []
    errors_count = 0

    for text in texts:
        t0 = time.perf_counter()
        try:
            result = await dispatch(text)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed_ms)
            print(f"  [{elapsed_ms:6.0f}ms] {text[:60]!r} → {result.intent.value}")
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed_ms)
            errors_count += 1
            print(f"  [{elapsed_ms:6.0f}ms] {text[:60]!r} → ERROR: {e}")

    return {"latencies_ms": latencies_ms, "errors": errors_count}


async def _bench_structuring(texts: list[str]) -> dict:
    from services.structuring import structure_medical_record

    latencies_ms: list[float] = []
    errors_count = 0

    for text in texts:
        t0 = time.perf_counter()
        try:
            record = await structure_medical_record(text)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed_ms)
            print(f"  [{elapsed_ms:6.0f}ms] {text[:50]!r} → cc={record.chief_complaint!r}")
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed_ms)
            errors_count += 1
            print(f"  [{elapsed_ms:6.0f}ms] {text[:50]!r} → ERROR: {e}")

    return {"latencies_ms": latencies_ms, "errors": errors_count}


# ── Formatting ────────────────────────────────────────────────────────────────

def _percentiles(data: list[float]) -> tuple[float, float, float]:
    if not data:
        return 0.0, 0.0, 0.0
    s = sorted(data)
    n = len(s)
    p50 = s[n // 2]
    p95 = s[int(n * 0.95)]
    p99 = s[min(int(n * 0.99), n - 1)]
    return p50, p95, p99


def _print_latency(label: str, data: list[float], unit: str = "µs") -> None:
    if not data:
        return
    p50, p95, p99 = _percentiles(data)
    avg = statistics.mean(data)
    print(f"  {label}: avg={avg:.1f}{unit}  p50={p50:.1f}  p95={p95:.1f}  p99={p99:.1f}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    run_llm = "--llm" in sys.argv
    run_structuring = "--structuring" in sys.argv

    W = 62
    print("=" * W)
    print(f"  Doctor AI — Dispatch Pipeline Benchmark")
    print(f"  ROUTING_LLM   : {os.environ.get('ROUTING_LLM', '(not set)')}")
    print(f"  OLLAMA_MODEL  : {os.environ.get('OLLAMA_MODEL', '(not set)')}")
    print(f"  OLLAMA_STRUCTURING_MODEL: {os.environ.get('OLLAMA_STRUCTURING_MODEL', '(not set)')}")
    print(f"  OLLAMA_BASE_URL: {os.environ.get('OLLAMA_BASE_URL', 'http://192.168.0.123:11434/v1')}")
    print("=" * W)

    # ── Fast router ──────────────────────────────────────────────────────────
    print("\n[1] Fast Router (no LLM)")
    fr = _bench_fast_router(_CORPUS)
    if fr["errors"]:
        for e in fr["errors"]:
            print(f"  ⚠ {e}")
    total = fr["total"]
    print(f"  Corpus size   : {total}")
    print(f"  Tier 1/2 hits : {fr['tier1_2_hits']}  ({fr['tier1_2_hits']/total*100:.0f}%)")
    print(f"  Tier 3 hits   : {fr['tier3_hits']}  ({fr['tier3_hits']/total*100:.0f}%  clinical fast-route)")
    print(f"  LLM required  : {fr['llm_required']}  ({fr['llm_required']/total*100:.0f}%)")
    print(f"  Total hit rate: {fr['hit_rate_pct']:.1f}%")
    _print_latency("Fast-router latency", fr["latencies_us"])
    saved_per_session = fr["fast_hits"] * 6
    print(f"  Projected LLM savings: {fr['fast_hits']} × 6s = {saved_per_session}s per {total}-turn session")

    # ── Routing LLM ──────────────────────────────────────────────────────────
    if run_llm:
        llm_texts = [text for text, label in _CORPUS if label == "llm"]
        print(f"\n[2] Routing LLM — {len(llm_texts)} messages")
        print(f"  Provider: {os.environ.get('ROUTING_LLM', 'deepseek')}  model: {os.environ.get('OLLAMA_MODEL', 'default')}")
        llm_result = await _bench_llm_dispatch(llm_texts)
        _print_latency("Routing LLM latency", llm_result["latencies_ms"], unit="ms")

    # ── Structuring LLM ──────────────────────────────────────────────────────
    if run_structuring:
        clinical_texts = [text for text, label in _CORPUS if label == "add_record"]
        print(f"\n[3] Structuring LLM — {len(clinical_texts)} messages")
        struct_model = os.environ.get("OLLAMA_STRUCTURING_MODEL") or os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
        print(f"  Provider: {os.environ.get('STRUCTURING_LLM', 'deepseek')}  model: {struct_model}")
        struct_result = await _bench_structuring(clinical_texts)
        _print_latency("Structuring LLM latency", struct_result["latencies_ms"], unit="ms")

    print("\n" + "=" * W)


if __name__ == "__main__":
    asyncio.run(main())
