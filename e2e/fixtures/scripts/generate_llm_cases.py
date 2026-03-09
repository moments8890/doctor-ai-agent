#!/usr/bin/env python3
"""
Generate diverse e2e test cases using LLMs (Claude CLI + Codex CLI + Claude API).

Usage:
    # Claude CLI + Codex (recommended — run from your terminal, not inside Claude Code):
    python e2e/fixtures/scripts/generate_llm_cases.py --claude-cli

    # Codex only:
    python e2e/fixtures/scripts/generate_llm_cases.py --codex-only

    # Claude API + Codex (requires ANTHROPIC_API_KEY with credits):
    ANTHROPIC_API_KEY=sk-ant-... python e2e/fixtures/scripts/generate_llm_cases.py

    # Dry-run: print first batch prompt without calling any LLM:
    python e2e/fixtures/scripts/generate_llm_cases.py --dry-run

Output: e2e/fixtures/data/realworld_doctor_agent_chatlogs_llm_generated.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_llm_generated.json"

# ── Prompt ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are generating a DIVERSE benchmark dataset of Chinese doctor WeChat messages to a medical AI assistant.
Each case must feel like a DIFFERENT real doctor with their own style, specialty, and workflow habits.

MANDATORY STYLE DIVERSITY — assign each case a random style from:
  A) Ultra-terse: 3-5 word messages, no punctuation ("李明 胸痛 2h 建档")
  B) Telegraphic with abbrevs: ("58M STEMI下壁, hs-cTnI 2.8, NRS8, PCI准备")
  C) Mixed Chinese-English: ("先记一下：BP 92/58, HR 64, SpO2 93%, consider STEMI inferior leads")
  D) Verbose and formal: complete sentences, structured ("患者王XX，男，58岁，因突发胸骨后压榨性疼痛2小时入院...")
  E) Stream-of-consciousness: multiple quick messages, self-corrections ("等下，刚才说错了" mid-flow)
  F) Dictation style: sounds like spoken notes ("就这样，下壁STEMI，PCI，血压92比58，记上")
  G) Query-first: checks history before adding anything
  H) Task-manager style: checks todos, marks done, then records

MANDATORY USE-CASE DIVERSITY — each case must exercise a different workflow:
  Operations available: add_record, create_patient, query_records, list_patients, list_tasks,
  complete_task, update_patient, update_record, schedule_follow_up, postpone_task, cancel_task, export_records
  Each case should use 2-4 DIFFERENT operations. No two cases in the same batch should have the same operation sequence.

MANDATORY CLINICAL DIVERSITY — within each batch use varied:
  - Specialties: cardiology, neurology, oncology, ICU, nephrology, psychiatry, surgery, etc.
  - Patient demographics: age 20-90, male/female, inpatient/outpatient/emergency
  - Note types: admission note, progress note, discharge summary, correction, addendum, lab update

HARD RULES:
1. Doctor messages only — never include AI/assistant replies
2. 3-6 turns per case, with turn length varying (some turns are 5 words, some are 5 sentences)
3. Each case must have a unique opening line — no two cases start the same way
4. Include realistic numbers: actual drug doses, lab values, clinical scores (NIHSS, PHQ-9, NRS, etc.)
5. Some turns should have in-message self-corrections ("不对，应该是...") or addenda
6. Vary the Chinese: some cases use 口语 (colloquial), some use 书面语 (formal), some mix both"""

BATCH_PROMPT_TEMPLATE = """Generate exactly {n} distinct doctor-agent test cases.

Batch theme: {theme}

For EACH case output a JSON object (one per line, no array wrapper):
{{
  "chatlog": [
    {{"text": "..."}},
    {{"text": "..."}},
    {{"text": "..."}}
  ],
  "intent_sequence": ["create_patient", "add_record"],
  "clinical_domain": "cardiology",
  "keywords": ["BNP", "EF", "胸痛", "复查"],
  "expected_table_min_counts_by_doctor": {{"patients": 1, "medical_records": 1}}
}}

Requirements:
- {n} cases, one JSON object per line
- Vary clinical domains: {domains}
- Vary operation sequences: {ops}
- Make the phrasing feel like real WeChat messages (casual, abbreviated, sometimes fragmented)
- Include realistic values (lab numbers, drug doses, clinical scores like NIHSS/PHQ-9/NRS)
- No two cases with identical opening lines"""

# ── Clinical themes per batch ──────────────────────────────────────────────────

BATCHES = [
    {
        "theme": "Cardiology and chest emergencies — MI, CHF, arrhythmia, chest pain",
        "domains": "cardiology, cardiac ICU, emergency",
        "ops": "add_record, create_patient+add_record, query+add_record, complete_task+add_record",
    },
    {
        "theme": "Neurology — stroke, NIHSS scoring, TIA, epilepsy, dementia",
        "domains": "neurology, stroke unit, emergency neurology",
        "ops": "create_patient+add_record+schedule_follow_up, update_record, add_record+query_records",
    },
    {
        "theme": "Diabetes and metabolic — HbA1c management, insulin adjustment, hypertension combo",
        "domains": "endocrinology, internal medicine, outpatient chronic disease",
        "ops": "add_record, query+add_record+schedule_follow_up, list_patients+add_record",
    },
    {
        "theme": "Oncology — chemo toxicity, bone marrow suppression, tumor markers, KPS scoring",
        "domains": "oncology, hematology, palliative care",
        "ops": "create_patient+add_record, update_patient+add_record, add_record+export_records",
    },
    {
        "theme": "Respiratory — COPD exacerbation, pneumonia, pulmonary embolism, HFNC",
        "domains": "pulmonology, respiratory ICU, emergency",
        "ops": "add_record+schedule_follow_up, create_patient+add_record, update_record+add_record",
    },
    {
        "theme": "Post-op and surgical follow-up — wound care, drain output, pain NRS, rehab",
        "domains": "general surgery, orthopedics, urology, post-anesthesia",
        "ops": "add_record, list_tasks+complete_task+add_record, add_record+schedule_follow_up",
    },
    {
        "theme": "ICU and sepsis — PCT, lactate, vasopressors, bundle care, ventilator",
        "domains": "ICU, sepsis management, critical care",
        "ops": "create_patient+add_record, add_record+update_record, add_record+postpone_task",
    },
    {
        "theme": "Chronic kidney disease and renal — creatinine, eGFR, dialysis, EPO, electrolytes",
        "domains": "nephrology, dialysis unit, transplant",
        "ops": "query_records+add_record, add_record+schedule_follow_up, cancel_task+add_record",
    },
    {
        "theme": "Mental health — PHQ-9, GAD-7, YMRS, antidepressants, follow-up scheduling",
        "domains": "psychiatry, psychology, outpatient mental health",
        "ops": "create_patient+add_record+schedule_follow_up, update_patient+add_record, add_record+export_records",
    },
    {
        "theme": "Multi-intent complex — mix of operations: patient management, tasks, corrections, exports",
        "domains": "any specialty, doctor workflow management",
        "ops": "list_patients+create_patient+add_record, list_tasks+complete_task+schedule_follow_up, "
               "create_patient(duplicate)+add_record+delete, update_patient+update_record+export_records",
    },
]

# ── LLM callers ────────────────────────────────────────────────────────────────

def _build_prompt(batch: dict, n: int) -> str:
    return BATCH_PROMPT_TEMPLATE.format(n=n, **batch)


def call_codex(prompt: str, system: str) -> str:
    """Call codex exec and return its text output.

    Codex output format varies by prompt length:
    - Short prompts: full header with 'codex' / 'tokens used' markers
    - Long prompts: raw JSON lines only (no header)
    Strategy: collect all lines starting with '{' after deduplication.
    """
    full_prompt = f"{system}\n\n---\n\n{prompt}"
    result = subprocess.run(
        ["codex", "exec", "--full-auto", full_prompt],
        capture_output=True, text=True, timeout=180,
    )
    # Deduplicate lines (codex sometimes echoes response twice)
    seen: set[str] = set()
    json_lines: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and stripped not in seen:
            seen.add(stripped)
            json_lines.append(stripped)
    return "\n".join(json_lines)


def call_claude_api(prompt: str, system: str) -> str:
    """Call Claude API via anthropic SDK."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def call_claude_cli(prompt: str, system: str) -> str:
    """Call Claude via the `claude -p` CLI (run from outside Claude Code session).

    Uses `env -u CLAUDECODE` to strip the nested-session guard. Works when called
    from a normal terminal; will fail if run inside an active Claude Code session.
    """
    full_prompt = f"{system}\n\n---\n\n{prompt}"
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        ["claude", "-p", "--output-format", "text", full_prompt],
        capture_output=True, text=True, timeout=300, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed (exit {result.returncode}): {result.stderr[:200]}")
    return result.stdout.strip()


# ── JSON parser ────────────────────────────────────────────────────────────────

def parse_cases(text: str, source: str, batch_idx: int, start_id: int) -> list[dict]:
    """Extract JSON objects from LLM output, one per line."""
    cases = []
    case_num = start_id

    # Try to parse each line as JSON
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            # Try to fix common LLM JSON issues
            try:
                # Remove trailing commas
                fixed = re.sub(r",\s*([}\]])", r"\1", line)
                obj = json.loads(fixed)
            except json.JSONDecodeError:
                continue

        chatlog = obj.get("chatlog", [])
        if not chatlog or len(chatlog) < 2:
            continue

        keywords = obj.get("keywords", [])
        intent_seq = obj.get("intent_sequence", [])
        domain = obj.get("clinical_domain", "general")
        db_counts = obj.get("expected_table_min_counts_by_doctor", {"patients": 1, "medical_records": 1})

        case_id = f"LLM-GEN-{source.upper()[:6]}-{case_num:03d}"
        case_num += 1

        cases.append({
            "case_id": case_id,
            "title": f"LLM-generated ({source}) batch {batch_idx + 1}: {domain}",
            "source": source,
            "batch": batch_idx,
            "intent_sequence": intent_seq,
            "clinical_domain": domain,
            "chatlog": [{"speaker": "doctor", "text": t["text"]} for t in chatlog if t.get("text")],
            "expectations": {
                "must_not_timeout": True,
                "expected_table_min_counts_global": {"system_prompts": 1},
                "expected_table_min_counts_by_doctor": db_counts,
                "must_include_any_of": [keywords] if keywords else [],
            },
        })

    return cases


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-only", action="store_true",
                        help="Use only codex (skip Claude even if API key is set)")
    parser.add_argument("--claude-only", action="store_true",
                        help="Use only Claude API (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--claude-cli", action="store_true",
                        help="Use `claude -p` CLI instead of Anthropic SDK (no API key needed, "
                             "run from a normal terminal outside Claude Code)")
    parser.add_argument("--cases-per-batch", type=int, default=10,
                        help="Cases to request per batch per model (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print first batch prompt and exit without calling LLMs")
    parser.add_argument("--out", default=str(OUT_PATH),
                        help="Output file path")
    args = parser.parse_args()

    has_claude_cli = args.claude_cli and not args.codex_only
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY")) and not args.codex_only and not args.claude_cli
    has_codex = not args.claude_only

    if not has_claude_cli and not has_anthropic and not has_codex:
        print("ERROR: No LLM available. Use --claude-cli, set ANTHROPIC_API_KEY, or ensure 'codex' is in PATH.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN: First batch prompt ===")
        print(SYSTEM_PROMPT)
        print()
        print(_build_prompt(BATCHES[0], args.cases_per_batch))
        return

    models = []
    if has_claude_cli:
        models.append("claude-cli")
    if has_anthropic:
        models.append("claude")
    if has_codex:
        models.append("codex")

    print(f"Models: {', '.join(models)}")
    print(f"Batches: {len(BATCHES)} × {args.cases_per_batch} cases per model")
    print(f"Target total: {len(BATCHES) * args.cases_per_batch * len(models)} cases")
    print()

    all_cases: list[dict] = []
    global_id = 1

    for batch_idx, batch in enumerate(BATCHES):
        prompt = _build_prompt(batch, args.cases_per_batch)
        print(f"  Batch {batch_idx + 1:2d}/10  theme: {batch['theme'][:60]}")

        for model in models:
            print(f"           [{model}] calling...", end=" ", flush=True)
            t0 = time.time()
            try:
                if model == "claude-cli":
                    raw = call_claude_cli(prompt, SYSTEM_PROMPT)
                elif model == "claude":
                    raw = call_claude_api(prompt, SYSTEM_PROMPT)
                else:
                    raw = call_codex(prompt, SYSTEM_PROMPT)

                source_label = "claude" if model == "claude-cli" else model
                parsed = parse_cases(raw, source_label, batch_idx, global_id)
                global_id += len(parsed)
                all_cases.extend(parsed)
                elapsed = time.time() - t0
                print(f"{len(parsed)} cases ({elapsed:.1f}s)")
            except Exception as exc:
                print(f"FAILED: {exc}")

        # Small delay between batches to avoid rate limits
        if batch_idx < len(BATCHES) - 1:
            time.sleep(1)

    print()
    print(f"Total cases generated: {len(all_cases)}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_cases, ensure_ascii=False, indent=2))
    print(f"Saved to: {out_path}")

    # Quick stats
    by_model = {}
    by_domain = {}
    for c in all_cases:
        by_model[c["source"]] = by_model.get(c["source"], 0) + 1
        by_domain[c["clinical_domain"]] = by_domain.get(c["clinical_domain"], 0) + 1
    print("\nBy model:", by_model)
    print("Top domains:", sorted(by_domain.items(), key=lambda x: -x[1])[:10])


if __name__ == "__main__":
    main()
