from __future__ import annotations

from typing import Dict, List


def diff_guideline_snapshots(old_sections: Dict[str, str], new_sections: Dict[str, str]) -> List[Dict[str, str]]:
    """Compare section text and emit impact-scored change summaries."""
    changes: List[Dict[str, str]] = []
    all_keys = sorted(set(old_sections) | set(new_sections))
    for key in all_keys:
        old = old_sections.get(key)
        new = new_sections.get(key)
        if old is None and new is not None:
            changes.append({
                "section": key,
                "change_type": "added",
                "impact": "moderate",
                "summary": "New recommendation section added",
            })
            continue
        if old is not None and new is None:
            changes.append({
                "section": key,
                "change_type": "removed",
                "impact": "high",
                "summary": "Section removed; requires clinician review",
            })
            continue
        if old != new:
            impact = "critical" if any(token in (new or "") for token in ["禁忌", "contraindication", "avoid"]) else "low"
            changes.append({
                "section": key,
                "change_type": "updated",
                "impact": impact,
                "summary": "Section content changed",
            })
    return changes
