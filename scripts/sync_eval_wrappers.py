#!/usr/bin/env python3
"""Regenerate tests/prompts/wrappers/*.md from src/agent/prompts/**/*.md.

Why this script exists:
    Before this script, tests/prompts/wrappers/*.md were hand-copies of the
    production prompts under src/agent/prompts/. They drifted silently:
    someone would edit the source prompt, and the eval harness (which reads
    the wrapper, not the source) would keep running the stale copy.

What it does:
    For each production prompt that has an eval wrapper, rebuild the wrapper
    by (a) stripping /no_think, (b) converting source template syntax to
    promptfoo's {{var}} syntax, (c) appending per-wrapper test scaffolding
    (the message/context slot that production code injects at call time but
    the eval harness provides via YAML vars).

Modes:
    --check  : diff each pair, exit 1 if any wrapper is out of sync (CI guard)
    --diff   : print the diff but do not write
    --write  : regenerate wrappers to disk

Unpaired files are listed as a warning:
    - wrapper-only (no source): general, query, routing — eval-only scaffolds
      for prompts composed programmatically in production
    - source-only (no wrapper): prompts without eval coverage yet
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "src" / "agent" / "prompts"
WRAPPER_DIR = ROOT / "tests" / "prompts" / "wrappers"

Convention = Literal["replace", "format"]


@dataclass(frozen=True)
class WrapperSpec:
    # Production prompt path, relative to src/agent/prompts
    source: str
    # How production code injects template vars:
    #   "replace" — `.replace("{var}", val)` or `.replace("{{var}}", val)`,
    #               braces are literal markers, JSON examples need no escaping
    #   "format"  — Python `template.format(**vars)`, so JSON examples in the
    #               source file are written with doubled braces `{{ ... }}`
    convention: Convention
    # Known template vars — single-brace `{var}` in the source becomes
    # `{{var}}` in the wrapper (for every name in this set).
    vars: frozenset[str]
    # Raw text appended after source content — the "test harness" portion
    # that production composes separately (patient message, context, etc.).
    # Leave empty when the source already ends with every slot the YAML needs.
    append: str = ""


# ─── Per-wrapper configuration ───────────────────────────────────────────
# Keys are wrapper filenames (without .md). Order matches ls output for
# reviewability.

WRAPPERS: dict[str, WrapperSpec] = {
    "diagnosis": WrapperSpec(
        source="intent/diagnosis.md",
        convention="replace",
        vars=frozenset({"clinical_data"}),
        append="\n---\n\n{{clinical_data}}\n",
    ),
    "doctor-extract": WrapperSpec(
        source="intent/doctor-extract.md",
        convention="replace",
        vars=frozenset({"name", "gender", "age", "transcript"}),
        # doctor-extract source ends with examples; the harness YAML vars
        # name/gender/age/transcript are injected via the scaffolding block.
        append=(
            "\n---\n\n"
            "患者姓名：{{name}}\n"
            "性别：{{gender}}\n"
            "年龄：{{age}}\n\n"
            "---\n\n"
            "{{transcript}}\n"
        ),
    ),
    "followup_reply": WrapperSpec(
        source="intent/followup_reply.md",
        convention="replace",
        vars=frozenset({"doctor_knowledge", "patient_name", "patient_message"}),
        append=(
            "\n---\n\n"
            "doctor_knowledge:\n{{doctor_knowledge}}\n\n"
            "患者姓名：{{patient_name}}\n"
            "患者消息：{{patient_message}}\n"
        ),
    ),
    "intake": WrapperSpec(
        source="intent/intake.md",
        convention="replace",
        vars=frozenset({"collected", "doctor_input"}),
        append=(
            "\n---\n\n"
            "已收集字段：\n{{collected}}\n\n"
            "医生输入：{{doctor_input}}\n\n"
            "输出JSON，包含 extracted（本轮提取的字段）和 reply（中文回复）。\n"
        ),
    ),
    "knowledge-ingest": WrapperSpec(
        source="knowledge_ingest.md",
        convention="replace",
        vars=frozenset({"document_text"}),
        # Source already ends with 【待整理文档】\n{{document_text}}; we
        # replace that tail with the wrapper's canonical trailer.
        append="",
    ),
    "patient-extract": WrapperSpec(
        source="intent/patient-extract.md",
        convention="replace",
        vars=frozenset({"name", "gender", "age", "transcript"}),
        append=(
            "\n---\n\n"
            "患者姓名：{{name}}\n"
            "性别：{{gender}}\n"
            "年龄：{{age}}\n\n"
            "---\n\n"
            "{{transcript}}\n"
        ),
    ),
    "patient-intake": WrapperSpec(
        source="intent/patient-intake.md",
        convention="replace",
        vars=frozenset({"collected", "patient_input"}),
        append=(
            "\n---\n\n"
            "已收集字段：\n{{collected}}\n\n"
            "患者输入：{{patient_input}}\n\n"
            "输出JSON，包含 extracted（本轮提取的字段）、reply（中文回复）和 complete（布尔值）。\n"
        ),
    ),
    "persona-classify": WrapperSpec(
        source="persona-classify.md",
        convention="format",
        vars=frozenset({"original", "edited"}),
        append="",
    ),
    "triage-classify": WrapperSpec(
        source="intent/triage-classify.md",
        convention="replace",
        vars=frozenset({"patient_context", "message"}),
        # Production uses structured_call(response_model=...) to enforce schema.
        # The eval harness runs promptfoo without structured output, so the
        # wrapper needs explicit format instructions that production doesn't.
        append=(
            "\n\n## 输出格式\n\n"
            "严格输出 JSON，不要输出任何其他内容：\n"
            "{\"category\": \"<类别>\", \"confidence\": <0.0-1.0>}\n"
            "\n---\n\n患者消息：{{message}}\n"
        ),
    ),
    "triage-escalation": WrapperSpec(
        source="intent/triage-escalation.md",
        convention="replace",
        vars=frozenset({"patient_context", "message"}),
        append="\n\n---\n\n患者消息：{{message}}\n",
    ),
    "triage-informational": WrapperSpec(
        source="intent/triage-informational.md",
        convention="replace",
        vars=frozenset({"patient_context", "message"}),
        append="\n\n---\n\n患者消息：{{message}}\n",
    ),
    "vision-ocr": WrapperSpec(
        source="intent/vision-ocr.md",
        convention="replace",
        vars=frozenset({"text_input"}),
        append="\n\n---\n\n以下是需要提取文字的临床文档内容：\n{{text_input}}\n",
    ),
    "voice-to-rule": WrapperSpec(
        source="voice_to_rule.md",
        convention="replace",
        vars=frozenset({"transcript", "specialty"}),
        append="",
    ),
}

# Wrappers that exist but have no paired source prompt (composed
# programmatically or eval-only). Left untouched by this script.
WRAPPER_ONLY = {"general", "query", "routing"}


# ─── Transforms ──────────────────────────────────────────────────────────

_NO_THINK_RE = re.compile(r"\A/no_think\s*\n")


def strip_no_think(text: str) -> str:
    return _NO_THINK_RE.sub("", text, count=1)


def single_to_double_braces(text: str, names: frozenset[str]) -> str:
    """Convert every `{name}` to `{{name}}` for names in *names*.

    Skips matches that are already doubled (`{{name}}`).
    """
    for name in names:
        # Match `{name}` not preceded by `{` and not followed by `}`.
        pattern = re.compile(r"(?<!\{)\{" + re.escape(name) + r"\}(?!\})")
        text = pattern.sub("{{" + name + "}}", text)
    return text


def format_to_replace(text: str, names: frozenset[str]) -> str:
    """Convert a Python `.format()`-style source into promptfoo `{{var}}` form.

    Three-pass approach to avoid cross-interference:
      1. Protect template vars: `{name}` → ``<TVAR:name>`` sentinel
      2. Halve remaining braces: `{{` → `{`, `}}` → `}`
      3. Unprotect with doubled braces: sentinel → `{{name}}`
    """
    protected = text
    for name in names:
        pattern = re.compile(r"(?<!\{)\{" + re.escape(name) + r"\}(?!\})")
        protected = pattern.sub(f"\x00TVAR:{name}\x01", protected)

    halved = protected.replace("{{", "{").replace("}}", "}")

    def restore(m: re.Match[str]) -> str:
        return "{{" + m.group(1) + "}}"

    return re.sub(r"\x00TVAR:([^\x01]+)\x01", restore, halved)


def build_wrapper(spec: WrapperSpec) -> str:
    raw = (SOURCE_DIR / spec.source).read_text(encoding="utf-8")
    body = strip_no_think(raw).rstrip()

    if spec.convention == "format":
        body = format_to_replace(body, spec.vars)
    else:
        body = single_to_double_braces(body, spec.vars)

    if spec.append:
        return body.rstrip() + spec.append
    return body + "\n"


# ─── Driver ──────────────────────────────────────────────────────────────

def diff_one(name: str, spec: WrapperSpec) -> tuple[str, str, list[str]]:
    """Return (current, generated, unified_diff_lines)."""
    wrapper_path = WRAPPER_DIR / f"{name}.md"
    current = wrapper_path.read_text(encoding="utf-8") if wrapper_path.exists() else ""
    generated = build_wrapper(spec)
    if current == generated:
        return current, generated, []
    diff = list(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile=f"current/{name}.md",
            tofile=f"generated/{name}.md",
            n=3,
        )
    )
    return current, generated, diff


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 if any wrapper is out of sync")
    mode.add_argument("--diff", action="store_true", help="print diffs, do not write")
    mode.add_argument("--write", action="store_true", help="regenerate wrappers to disk")
    ap.add_argument("--only", help="limit to one wrapper name (e.g. triage-escalation)")
    args = ap.parse_args()

    # Default mode: --diff (safest)
    if not any([args.check, args.diff, args.write]):
        args.diff = True

    wrappers = (
        {args.only: WRAPPERS[args.only]} if args.only else WRAPPERS
    )
    if args.only and args.only not in WRAPPERS:
        print(f"Unknown wrapper '{args.only}'. Known: {sorted(WRAPPERS)}", file=sys.stderr)
        return 2

    diverged: list[str] = []
    for name, spec in sorted(wrappers.items()):
        _, generated, diff = diff_one(name, spec)
        if not diff:
            if args.diff:
                print(f"OK  {name}")
            continue
        diverged.append(name)
        if args.check:
            print(f"DIFF {name}")
        elif args.diff:
            print(f"\n=== {name} ===")
            sys.stdout.writelines(diff)
        elif args.write:
            (WRAPPER_DIR / f"{name}.md").write_text(generated, encoding="utf-8")
            print(f"WROTE {name}")

    # Warn about unpaired files (never fatal — informational)
    existing_wrappers = {p.stem for p in WRAPPER_DIR.glob("*.md") if not p.is_symlink()}
    orphan_wrappers = existing_wrappers - set(WRAPPERS) - WRAPPER_ONLY
    if orphan_wrappers:
        print(f"\nOrphan wrappers (no spec): {sorted(orphan_wrappers)}", file=sys.stderr)

    if args.check and diverged:
        print(f"\n{len(diverged)} wrapper(s) out of sync. Run: scripts/sync_eval_wrappers.py --write")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
