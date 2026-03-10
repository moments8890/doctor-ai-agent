#!/usr/bin/env python3
"""
离线LLM规则挖掘脚本 — 从 turn_log.jsonl 中读取 LLM 路由的对话轮次，
按意图分组，让 LLM 生成适用于 fast_router 的正则/关键词规则，
精度达标的规则写入输出文件。

用法：
    python scripts/mine_routing_rules.py \\
      --input logs/turn_log.jsonl \\
      --output data/mined_rules.json \\
      --min-examples 10 \\
      --min-precision 0.95 \\
      --provider deepseek

Offline LLM rule mining script for the fast_router.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow running from repo root or scripts/ directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from openai import AsyncOpenAI
from services.ai.llm_client import _PROVIDERS


MINE_PROMPT = """
你是一个为中文医疗AI助手生成路由规则的系统。

以下消息均被分类为意图：{intent}

示例（共{n}条）：
{examples}

请生成Python正则表达式和关键词规则，用于在不调用LLM的情况下识别此类消息。
要求：
1. 使用结构性锚点（前缀、后缀、助词），不要依赖具体患者姓名或症状词
2. 高精度优先（宁可漏掉，不要误判）
3. 患者姓名用 [\\u4e00-\\u9fff]{{2,4}} 表示

仅输出JSON，格式如下：
{{
  "intent": "{intent}",
  "patterns": ["regex1", "regex2"],
  "keywords_any": ["关键词1", "关键词2"],
  "min_length": 4,
  "precision_estimate": 0.95,
  "coverage_estimate": 0.60,
  "notes": "说明结构性信号"
}}
"""


def load_turn_log(path: Path) -> List[Dict[str, Any]]:
    """Read all entries from a turn log JSONL file."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def _get_client(provider_name: str) -> tuple[AsyncOpenAI, str]:
    """Return (AsyncOpenAI client, model name) for the given provider."""
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        allowed = ", ".join(sorted(_PROVIDERS.keys()))
        raise RuntimeError(f"Unknown provider: {provider_name!r} (allowed: {allowed})")
    provider = dict(provider)
    if provider_name == "ollama":
        provider["model"] = os.environ.get("OLLAMA_MODEL", provider["model"])
    elif provider_name == "openai":
        provider["model"] = os.environ.get("OPENAI_MODEL", provider.get("model", "gpt-4o-mini"))
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])
    api_key = os.environ.get(provider["api_key_env"], "nokeyneeded")
    client = AsyncOpenAI(base_url=provider["base_url"], api_key=api_key)
    return client, provider["model"]


async def ask_llm_for_rules(
    intent: str,
    examples: List[str],
    client: AsyncOpenAI,
    model: str,
    max_examples: int = 30,
) -> Optional[Dict[str, Any]]:
    """Call the LLM and parse its JSON response."""
    sample = examples[:max_examples]
    examples_text = "\n".join(f"- {e}" for e in sample)
    prompt = MINE_PROMPT.format(intent=intent, n=len(sample), examples=examples_text)

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=800,
        )
    except Exception as e:
        print(f"  [LLM error] {e}", file=sys.stderr)
        return None

    raw = resp.choices[0].message.content or ""
    # Extract JSON from the response (may be wrapped in markdown fences).
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        print(f"  [parse error] no JSON found in LLM response for intent={intent}", file=sys.stderr)
        return None
    try:
        return json.loads(json_match.group(0))
    except Exception as e:
        print(f"  [parse error] {e}", file=sys.stderr)
        return None


def _compile_rule(rule_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compile a raw rule dict (patterns as strings) into one with compiled regexes.

    Returns None if intent is invalid or patterns fail to compile.
    """
    try:
        compiled_patterns = [re.compile(p) for p in rule_dict.get("patterns", [])]
    except re.error as e:
        print(f"  [regex error] {e}", file=sys.stderr)
        return None
    return {
        "intent": rule_dict["intent"],
        "patterns": compiled_patterns,
        "keywords_any": list(rule_dict.get("keywords_any") or []),
        "min_length": int(rule_dict.get("min_length", 0)),
        "enabled": True,
    }


def _apply_rule(rule: Dict[str, Any], text: str) -> bool:
    """Return True if the compiled rule matches text."""
    stripped = text.strip()
    if len(stripped) < rule.get("min_length", 0):
        return False
    if any(p.search(stripped) for p in rule["patterns"]):
        return True
    if any(k in stripped for k in rule.get("keywords_any", [])):
        return True
    return False


def validate_rule(
    rule_dict: Dict[str, Any],
    all_turns: List[Dict[str, Any]],
    target_intent: str,
    min_precision: float,
) -> tuple[float, float, bool]:
    """Validate rule against the full labeled set.

    Returns (precision, coverage, approved).
    """
    compiled = _compile_rule(rule_dict)
    if compiled is None:
        return 0.0, 0.0, False

    target_turns = [t for t in all_turns if t.get("intent") == target_intent]
    total_with_target = len(target_turns)
    if total_with_target == 0:
        return 0.0, 0.0, False

    matched_total = 0
    matched_correct = 0
    matched_target = 0

    for turn in all_turns:
        text = turn.get("text", "")
        if _apply_rule(compiled, text):
            matched_total += 1
            if turn.get("intent") == target_intent:
                matched_correct += 1

    for turn in target_turns:
        if _apply_rule(compiled, turn.get("text", "")):
            matched_target += 1

    precision = matched_correct / matched_total if matched_total > 0 else 0.0
    coverage = matched_target / total_with_target if total_with_target > 0 else 0.0
    approved = precision >= min_precision

    return precision, coverage, approved


def _rule_to_serializable(rule_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a rule dict (with compiled patterns) to a JSON-serializable form."""
    patterns = rule_dict.get("patterns", [])
    # Patterns may be compiled regexes or raw strings.
    patterns_str = [p.pattern if hasattr(p, "pattern") else str(p) for p in patterns]
    return {
        "intent": rule_dict["intent"],
        "patterns": patterns_str,
        "keywords_any": list(rule_dict.get("keywords_any") or []),
        "min_length": int(rule_dict.get("min_length", 0)),
        "enabled": bool(rule_dict.get("enabled", True)),
    }


def load_existing_rules(path: Path) -> List[Dict[str, Any]]:
    """Load existing rules from the output file, or return empty list."""
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def merge_rules(
    existing: List[Dict[str, Any]], new_rules: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Merge new rules into existing, replacing any rule with the same intent."""
    existing_by_intent = {r["intent"]: i for i, r in enumerate(existing)}
    result = list(existing)
    for rule in new_rules:
        intent = rule["intent"]
        if intent in existing_by_intent:
            result[existing_by_intent[intent]] = rule
        else:
            result.append(rule)
    return result


async def _mine_intent_rules(
    eligible: Dict[str, List[str]], all_turns: List[Dict[str, Any]],
    client: Any, model: str, min_precision: float,
) -> List[Dict[str, Any]]:
    """Mine and validate rules for each eligible intent; return approved rules."""
    approved: List[Dict[str, Any]] = []
    header = f"{'Intent':<20} {'Examples':>8} {'Patterns':>8} {'Precision':>9} {'Coverage':>8}  Status"
    print(header)
    print("-" * len(header))
    for intent, examples in sorted(eligible.items()):
        rule_dict = await ask_llm_for_rules(intent, examples, client, model)
        if rule_dict is None:
            print(f"{'  ' + intent:<20} {len(examples):>8}  {'?':>8}  {'?':>9}  {'?':>8}  LLM error")
            continue
        precision, coverage, approved_flag = validate_rule(rule_dict, all_turns, intent, min_precision)
        n_patterns = len(rule_dict.get("patterns", []))
        status = "approved" if approved_flag else "below threshold"
        print(f"{intent:<20} {len(examples):>8} {n_patterns:>8} {precision:>9.2f} {coverage:>8.2f}  {status}")
        if approved_flag:
            approved.append(_rule_to_serializable(rule_dict))
    return approved


async def _write_approved_rules(approved_rules: List[Dict[str, Any]], output_path: Path) -> None:
    """Merge approved rules with existing and write to file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing_rules(output_path)
    merged = merge_rules(existing, approved_rules)
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(approved_rules)} rule(s) approved. Written to {output_path} ({len(merged)} total rules).")


async def main(args: argparse.Namespace) -> None:
    """Async entry point: load turn log, mine rules, write output."""
    input_path = Path(args.input)
    output_path = Path(args.output)
    print(f"Loading turn log from {input_path} ...")
    all_turns = load_turn_log(input_path)
    print(f"  {len(all_turns)} total turns loaded.")
    llm_turns = [t for t in all_turns if t.get("routing") == "llm"]
    print(f"  {len(llm_turns)} LLM-routed turns.")
    by_intent: Dict[str, List[str]] = defaultdict(list)
    for t in llm_turns:
        intent = t.get("intent", "")
        text = t.get("text", "")
        if intent and text:
            by_intent[intent].append(text)
    eligible = {k: v for k, v in by_intent.items() if len(v) >= args.min_examples}
    if not eligible:
        print(f"No intents with >= {args.min_examples} LLM-routed examples. Exiting.")
        return
    print(f"\n{len(eligible)} eligible intent(s): {', '.join(sorted(eligible.keys()))}")
    client, model = _get_client(args.provider)
    print(f"Using provider={args.provider!r} model={model!r}\n")
    approved_rules = await _mine_intent_rules(eligible, all_turns, client, model, args.min_precision)
    if not approved_rules:
        print("\nNo rules approved. Output file not modified.")
        return
    await _write_approved_rules(approved_rules, output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine fast-router rules from turn log using LLM.")
    parser.add_argument("--input", default="logs/turn_log.jsonl", help="Turn log JSONL file")
    parser.add_argument("--output", default="data/mined_rules.json", help="Output rules JSON file")
    parser.add_argument("--min-examples", type=int, default=10, help="Minimum LLM-routed examples per intent")
    parser.add_argument("--min-precision", type=float, default=0.95, help="Minimum precision threshold (0-1)")
    parser.add_argument("--provider", default="deepseek", help="LLM provider name")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
