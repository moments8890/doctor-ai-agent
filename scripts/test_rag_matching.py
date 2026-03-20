#!/usr/bin/env python
"""
Interactive RAG case matching test — type a patient's symptoms, see matched cases.

Usage:
    ENVIRONMENT=development PYTHONPATH=src python scripts/test_rag_matching.py

Prerequisites:
    1. pip install sentence-transformers langchain-huggingface langchain-community
    2. python scripts/seed_cases.py  (seeds 24 neurosurgery cases)

Type symptoms in Chinese, get matched cases. Type 'quit' to exit.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault("ENVIRONMENT", "development")

from utils.runtime_config import load_runtime_json
load_runtime_json()

from db.engine import AsyncSessionLocal
from db.crud.case_history import match_cases
from domain.knowledge.embedding import preload_embedding_model


EXAMPLE_QUERIES = [
    "头痛2周伴恶心呕吐",
    "突发剧烈头痛像被雷击",
    "右侧手脚没力气说话不清楚",
    "腰痛腿也痛走路困难",
    "手指麻木晚上更严重",
    "反复抽搐意识丧失",
    "走路不稳记忆力差还尿裤子",
    "脸部一阵一阵电击样疼",
]


async def run_query(query: str):
    async with AsyncSessionLocal() as session:
        matches = await match_cases(session, "test_doctor", query, limit=5, threshold=0.3)
    if not matches:
        print("  (无匹配结果)")
        return
    for i, m in enumerate(matches, 1):
        score = m["similarity"]
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  {i}. {bar} {score:.2f}")
        print(f"     主诉: {m['chief_complaint'][:50]}")
        print(f"     诊断: {m['final_diagnosis']}")
        if m["treatment"]:
            print(f"     治疗: {m['treatment'][:60]}")
        if m["key_symptoms"]:
            print(f"     关键: {', '.join(m['key_symptoms'][:5])}")
        print()


async def main():
    print("Loading BGE-M3 embedding model...")
    preload_embedding_model()
    print("Model ready!\n")

    print("=" * 60)
    print("  RAG 病例匹配测试")
    print("  输入患者症状（中文），查看匹配的历史病例")
    print("  输入 'quit' 退出, 'examples' 查看示例")
    print("=" * 60)

    while True:
        print()
        query = input("🔍 症状: ").strip()
        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        if query.lower() in ("examples", "eg", "示例"):
            print("\n示例查询:")
            for i, eg in enumerate(EXAMPLE_QUERIES, 1):
                print(f"  {i}. {eg}")
            continue

        print(f"\n{'─' * 60}")
        await run_query(query)


if __name__ == "__main__":
    asyncio.run(main())
