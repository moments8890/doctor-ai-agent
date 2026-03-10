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


def _versioned_path(base: Path) -> Path:
    """Return next available versioned path: _v1.json, _v2.json, …

    Strips any existing _vN suffix first so passing --out _v1.json still increments correctly.
    """
    stem = re.sub(r"_v\d+$", "", base.stem)
    suffix = base.suffix
    parent = base.parent
    v = 1
    while True:
        candidate = parent / f"{stem}_v{v}{suffix}"
        if not candidate.exists():
            return candidate
        v += 1

# ── Prompts ─────────────────────────────────────────────────────────────────────

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

# ── 神经/脑血管专科提示词（中文）───────────────────────────────────────────────

NEURO_SYSTEM_PROMPT_ZH = """你正在为一个医疗AI助手生成多样化的中文医生微信消息基准数据集。
每个案例必须体现不同真实医生的风格、专科和工作习惯，聚焦于神经科/脑血管科。

强制风格多样性 — 每个案例随机分配以下风格之一：
  A) 极简电报式：3-5字消息，无标点（"李明 偏瘫 2h 建档"）
  B) 缩写混合式：（"62F 大面积脑梗，NIHSS 18，DNT 41min，取栓准备"）
  C) 中英混用式：（"先记录：BP 178/102, NIHSS 14, DWI阳性，左侧MCA区域"）
  D) 正式书面式：完整句子，结构化（"患者张XX，男，68岁，因突发言语不清伴右侧肢体无力3小时入院..."）
  E) 流水意识式：多条快速消息，自我纠正（中间出现"等下，刚才说错了"）
  F) 口述记录式：像语音记录（"就这样，左侧大脑中动脉闭塞，NIHSS 14，血压178，记上"）
  G) 查询优先式：先查历史再添加记录
  H) 任务管理式：查待办、标完成、再记录

强制操作多样性 — 每个案例必须涵盖不同工作流：
  可用操作：add_record、create_patient、query_records、list_patients、list_tasks、
  complete_task、update_patient、update_record、schedule_follow_up、postpone_task、cancel_task、export_records
  每个案例使用2-4个不同操作。同批次内不得有相同操作序列。

强制临床多样性 — 每批次内变化：
  - 具体疾病：涵盖指定神经/脑血管主题的多种病种
  - 患者人口学：年龄30-90岁、男女混合、住院/急诊/门诊
  - 记录类型：入院记录、病程记录、出院小结、神经评分、影像解读、用药调整

硬性规则：
1. 只有医生消息 — 绝不包含AI/助手回复
2. 每案例1-4轮对话，轮次长度各异（有些5字，有些5句话）
3. 每案例必须有唯一开场白 — 不得有两个案例以相同方式开始
4. 包含真实数字：具体药物剂量、化验值、临床评分（NIHSS、mRS、GCS、MMSE、CDR、UPDRS等）
5. 部分轮次应有消息内自我纠正（"不对，应该是..."）或补充记录
6. 中文用语多样：部分案例用口语，部分用书面语，部分两者混用
7. 体现神经科工作真实场景：急性期处理、慢病管理、康复随访、患者教育"""

NEURO_BATCH_PROMPT_TEMPLATE_ZH = """请生成恰好 {n} 个不同的医生-AI助手测试案例。

批次主题：{theme}

每个案例输出一个JSON对象（每行一个，不需要数组包装）：
{{
  "chatlog": [
    {{"text": "..."}},
    {{"text": "..."}},
    {{"text": "..."}}
  ],
  "intent_sequence": ["create_patient", "add_record"],
  "clinical_domain": "neurology",
  "keywords": ["NIHSS", "溶栓", "卒中", "mRS"],
  "expected_table_min_counts_by_doctor": {{"patients": 1, "medical_records": 1}}
}}

要求：
- 恰好 {n} 个案例，每行一个JSON对象
- 临床领域多样化：{domains}
- 操作序列多样化：{ops}
- 消息风格要像真实微信消息（随意、简写、有时不完整）
- 包含真实数值（化验结果、药物剂量、{score_hint}等神经科评分）
- 不得有两个案例以相同开场白开始
- 所有对话内容必须使用中文（可适当混入英文医学缩写）"""

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

# ── 神经/脑血管专科批次（中文主题，共10批）─────────────────────────────────────

NEURO_CEREBRO_SPECIALTY_BATCHES = [
    {
        "theme": "急性缺血性卒中 — 静脉溶栓（tPA/阿替普酶）、机械取栓、DNT/DPT时间窗、NIHSS评分动态变化",
        "domains": "神经内科、卒中单元、急诊神经科",
        "ops": "create_patient+add_record+schedule_follow_up, add_record+query_records, update_record+add_record",
        "score_hint": "NIHSS、mRS、DNT",
    },
    {
        "theme": "出血性卒中 — 脑出血血肿扩大、蛛网膜下腔出血、颅内压管理、GCS评分、手术适应证",
        "domains": "神经外科、神经重症监护、急诊",
        "ops": "create_patient+add_record, add_record+update_patient+schedule_follow_up, add_record+postpone_task",
        "score_hint": "GCS、Hunt-Hess、Fisher",
    },
    {
        "theme": "短暂性脑缺血发作（TIA）— ABCD2评分、早期卒中风险分层、抗血小板双联启动、影像评估",
        "domains": "神经内科、卒中门诊、急诊",
        "ops": "create_patient+add_record+schedule_follow_up, query_records+add_record, add_record+export_records",
        "score_hint": "ABCD2、NIHSS",
    },
    {
        "theme": "癫痫 — 发作类型分类、抗癫痫药物调整（丙戊酸/左乙拉西坦/卡马西平）、癫痫持续状态处理",
        "domains": "神经内科、癫痫专科门诊、急诊",
        "ops": "add_record+schedule_follow_up, update_patient+add_record, create_patient+add_record+schedule_follow_up",
        "score_hint": "发作频率、药物血药浓度",
    },
    {
        "theme": "帕金森病与运动障碍 — 左旋多巴剂量调整、开关期管理、UPDRS/H&Y评分、DBS术后随访",
        "domains": "神经内科、运动障碍专科、门诊",
        "ops": "add_record+schedule_follow_up, query_records+add_record, update_patient+add_record+schedule_follow_up",
        "score_hint": "UPDRS、H&Y分期",
    },
    {
        "theme": "认知障碍与痴呆 — MMSE/MoCA评分、CDR分期、阿尔茨海默病与血管性痴呆鉴别、照料者沟通",
        "domains": "神经内科、记忆门诊、老年科",
        "ops": "create_patient+add_record+schedule_follow_up, update_patient+add_record, add_record+export_records",
        "score_hint": "MMSE、MoCA、CDR",
    },
    {
        "theme": "脑血管病二级预防 — 抗血小板（阿司匹林/氯吡格雷）、他汀强化、血压目标管理、颈动脉狭窄随访",
        "domains": "神经内科、卒中门诊、心脑血管内科",
        "ops": "query_records+add_record+schedule_follow_up, add_record+update_patient, list_patients+add_record",
        "score_hint": "LDL-C、血压达标率",
    },
    {
        "theme": "神经重症监护 — 颅内压监测与控制、昏迷评分（GCS/FOUR量表）、脑疝早期识别、神经保护",
        "domains": "神经ICU、神经外科ICU、急诊重症",
        "ops": "create_patient+add_record, add_record+update_record+postpone_task, add_record+schedule_follow_up",
        "score_hint": "GCS、FOUR、ICP数值",
    },
    {
        "theme": "周围神经与神经肌肉疾病 — 糖尿病周围神经病变、格林-巴利综合征、重症肌无力危象、NCS/EMG解读",
        "domains": "神经内科、肌电图室、神经重症",
        "ops": "create_patient+add_record+schedule_follow_up, query_records+add_record, update_patient+add_record",
        "score_hint": "MRC肌力分级、QMG评分",
    },
    {
        "theme": "神经肿瘤与术后管理 — 胶质瘤/脑膜瘤术后随访、替莫唑胺化疗毒性、放疗反应、KPS评分、癫痫控制",
        "domains": "神经肿瘤科、神经外科、放疗科",
        "ops": "add_record+schedule_follow_up, update_patient+add_record+export_records, create_patient+add_record",
        "score_hint": "KPS、RANO标准",
    },
]

# ── LLM callers ────────────────────────────────────────────────────────────────

def _build_prompt(batch: dict, n: int) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the given batch."""
    if "score_hint" in batch:
        # Neuro/cerebrovascular specialty batch — use Chinese prompts
        user_prompt = NEURO_BATCH_PROMPT_TEMPLATE_ZH.format(n=n, **batch)
        return NEURO_SYSTEM_PROMPT_ZH, user_prompt
    return SYSTEM_PROMPT, BATCH_PROMPT_TEMPLATE.format(n=n, **batch)


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
    parser.add_argument("--no-codex", action="store_true",
                        help="Skip codex even if available")
    parser.add_argument("--no-claude", action="store_true",
                        help="Skip Claude API/CLI even if available")
    parser.add_argument("--claude-cli", action="store_true",
                        help="Use `claude -p` CLI instead of Anthropic SDK (no API key needed, "
                             "run from a normal terminal outside Claude Code)")
    parser.add_argument("--cases-per-batch", type=int, default=10,
                        help="Cases to request per batch per model (default: 10)")
    parser.add_argument("--rounds", type=int, default=1,
                        help="Repeat the full BASE_BATCHES set N times (default: 1)")
    parser.add_argument("--extra-neuro-specialty-batches", type=int, default=0,
                        metavar="N",
                        help="Append N 神经/脑血管专科 batches (0-10, default: 0)")
    parser.add_argument("--neuro-cerebro-only", action="store_true",
                        help="Skip BASE_BATCHES; use only NEURO_CEREBRO_SPECIALTY_BATCHES "
                             "(combine with --extra-neuro-specialty-batches to limit count)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print first batch prompt and exit without calling LLMs")
    parser.add_argument("--out", default=str(OUT_PATH),
                        help="Output file path")
    args = parser.parse_args()

    no_codex = args.no_codex or args.codex_only is False and args.claude_only
    no_claude = args.no_claude or args.codex_only

    has_claude_cli = args.claude_cli and not no_claude
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY")) and not no_claude and not args.claude_cli
    has_codex = not no_codex and not args.claude_only

    if not has_claude_cli and not has_anthropic and not has_codex:
        print("ERROR: No LLM available. Use --claude-cli, set ANTHROPIC_API_KEY, or ensure 'codex' is in PATH.", file=sys.stderr)
        sys.exit(1)

    # Build the active batch list
    neuro_count = min(max(args.extra_neuro_specialty_batches, 0), len(NEURO_CEREBRO_SPECIALTY_BATCHES))
    neuro_batches = NEURO_CEREBRO_SPECIALTY_BATCHES[:neuro_count] if neuro_count else []

    if args.neuro_cerebro_only:
        # --neuro-cerebro-only: skip base batches entirely; default to all 10 if --extra-neuro-specialty-batches not set
        if neuro_count == 0:
            neuro_batches = NEURO_CEREBRO_SPECIALTY_BATCHES
        active_batches = neuro_batches
        rounds = 1  # rounds only applies to base batches
    else:
        active_batches = BATCHES * args.rounds + neuro_batches

    if args.dry_run:
        first = active_batches[0]
        sys_prompt, user_prompt = _build_prompt(first, args.cases_per_batch)
        print("=== DRY RUN: First batch prompt ===")
        print(sys_prompt)
        print()
        print(user_prompt)
        return

    models = []
    if has_claude_cli:
        models.append("claude-cli")
    if has_anthropic:
        models.append("claude")
    if has_codex:
        models.append("codex")

    total_batches = len(active_batches)
    print(f"Models: {', '.join(models)}")
    print(f"Batches: {total_batches} × {args.cases_per_batch} cases per model")
    if not args.neuro_cerebro_only and args.rounds > 1:
        print(f"  (base {len(BATCHES)} batches × {args.rounds} rounds + {len(neuro_batches)} neuro specialty)")
    elif neuro_batches:
        print(f"  ({len(BATCHES)} base + {len(neuro_batches)} 神经/脑血管专科 batches)")
    print(f"Target total: {total_batches * args.cases_per_batch * len(models)} cases")
    print()

    all_cases: list[dict] = []
    global_id = 1

    for batch_idx, batch in enumerate(active_batches):
        sys_prompt, user_prompt = _build_prompt(batch, args.cases_per_batch)
        is_neuro = "score_hint" in batch
        tag = "🧠 " if is_neuro else "  "
        print(f"{tag}Batch {batch_idx + 1:2d}/{total_batches}  theme: {batch['theme'][:60]}")

        for model in models:
            print(f"           [{model}] calling...", end=" ", flush=True)
            t0 = time.time()
            try:
                if model == "claude-cli":
                    raw = call_claude_cli(user_prompt, sys_prompt)
                elif model == "claude":
                    raw = call_claude_api(user_prompt, sys_prompt)
                else:
                    raw = call_codex(user_prompt, sys_prompt)

                source_label = "claude" if model == "claude-cli" else model
                parsed = parse_cases(raw, source_label, batch_idx, global_id)
                global_id += len(parsed)
                all_cases.extend(parsed)
                elapsed = time.time() - t0
                print(f"{len(parsed)} cases ({elapsed:.1f}s)")
            except Exception as exc:
                print(f"FAILED: {exc}")

        # Small delay between batches to avoid rate limits
        if batch_idx < total_batches - 1:
            time.sleep(1)

    print()
    print(f"Total cases generated: {len(all_cases)}")

    out_path = _versioned_path(Path(args.out))
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
