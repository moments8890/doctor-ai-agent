# scripts/patient_sim/report.py
"""Report generation — markdown + JSON output."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List


def generate_markdown(
    results: List[Dict[str, Any]],
    patient_llm: str,
    system_llm: str,
    server_url: str,
) -> str:
    """Generate a markdown report from simulation results."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Patient Simulation Report — {now}",
        "",
        f"**Patient LLM:** {patient_llm} | **System LLM:** {system_llm} | **Server:** {server_url}",
        "",
        "| Persona | Turns | DB | Extraction | Quality | Result |",
        "|---------|-------|----|------------|---------|--------|",
    ]

    for r in results:
        db = "PASS" if r["db_pass"] else "FAIL"
        ext_count = sum(1 for v in r.get("extraction_results", {}).values() if v.get("pass"))
        ext_total = len(r.get("extraction_results", {}))
        ext = f"{ext_count}/{ext_total}" if ext_total else "N/A"
        quality = f"{r['quality_score']}/10" if r.get("quality_score") is not None else "—"
        result = "PASS" if r["passed"] else "FAIL"
        err = f" ({r['error'][:40]}...)" if r.get("error") else ""
        lines.append(f"| {r['persona_id']} {r['persona_name']} | {r['turns']} | {db} | {ext} | {quality} | {result}{err} |")

    lines.append("")

    # Detail sections
    for r in results:
        lines.append(f"## {r['persona_id']} {r['persona_name']}")
        lines.append("")

        if r.get("error"):
            lines.append(f"**Error:** {r['error']}")
            lines.append("")

        if r.get("db_errors"):
            lines.append("**DB Errors:**")
            for e in r["db_errors"]:
                lines.append(f"- {e}")
            lines.append("")

        # Extraction table
        if r.get("extraction_results"):
            lines.append("**Extracted Facts:**")
            lines.append("")
            lines.append("| Field | Expected | Got | Match |")
            lines.append("|-------|----------|-----|-------|")
            for fld, info in r["extraction_results"].items():
                exp = ", ".join(info["expected"])
                got = info["got"][:60]
                match = "YES" if info["pass"] else "NO"
                lines.append(f"| {fld} | {exp} | {got} | {match} |")
            lines.append("")

        # Quality
        if r.get("quality_detail"):
            d = r["quality_detail"]
            lines.append(f"**Quality Score:** {d.get('score', '?')}/10")
            lines.append(f"  - Completeness: {d.get('completeness', '?')}")
            lines.append(f"  - Appropriateness: {d.get('appropriateness', '?')}")
            lines.append(f"  - Communication: {d.get('communication', '?')}")
            if d.get("explanation"):
                lines.append(f"  - {d['explanation']}")
            lines.append("")

        # Conversation
        if r.get("conversation"):
            lines.append("<details><summary>Conversation</summary>")
            lines.append("")
            for t in r["conversation"]:
                speaker = "System" if t["role"] == "assistant" else "Patient"
                lines.append(f"> **{speaker}:** {t['content']}")
                lines.append("")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)


def generate_json(
    results: List[Dict[str, Any]],
    patient_llm: str,
    system_llm: str,
    server_url: str,
) -> str:
    """Generate a JSON report."""
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "patient_llm": patient_llm,
        "system_llm": system_llm,
        "server_url": server_url,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
        },
        "results": results,
    }
    return json.dumps(report, ensure_ascii=False, indent=2)
