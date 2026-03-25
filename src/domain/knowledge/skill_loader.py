# src/domain/knowledge/skill_loader.py
"""Skill file loader — reads specialty-specific markdown skills with YAML frontmatter."""
from __future__ import annotations

import os
import time
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from utils.log import log

SKILLS_DIR = Path(__file__).parent / "skills"


class SkillType(str, Enum):
    routing = "routing"
    clinical_signals = "clinical_signals"
    diagnosis = "diagnosis"


_SPECIALTY_ALIASES: Dict[str, str] = {
    "神经外科": "neurology",
    "神经内科": "neurology",
    "心内科": "cardiology",
    "心脏科": "cardiology",
}

_skill_cache: Dict[str, Tuple[Dict[SkillType, str], float]] = {}


def _cache_ttl() -> int:
    try:
        return int(os.environ.get("SKILLS_CACHE_TTL", "300"))
    except (TypeError, ValueError):
        return 300


def _resolve_specialty(specialty: str) -> str:
    """Resolve Chinese aliases to English directory names."""
    return _SPECIALTY_ALIASES.get(specialty, specialty)


def _parse_skill_file(path: Path) -> Tuple[Optional[SkillType], str]:
    """Parse a skill markdown file. Returns (skill_type, body_content)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text

    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, text

    skill_type_str = meta.get("type", "")
    try:
        skill_type = SkillType(skill_type_str)
    except ValueError:
        skill_type = None

    body = parts[2].strip()
    return skill_type, body


def load_skills(specialty: str) -> Dict[SkillType, str]:
    """Load all skills for a specialty (+ _default). Cached with TTL."""
    resolved = _resolve_specialty(specialty)
    now = time.time()

    if resolved in _skill_cache:
        cached, ts = _skill_cache[resolved]
        if now - ts < _cache_ttl():
            return cached

    skills: Dict[SkillType, str] = {}

    # Load _default skills first
    default_dir = SKILLS_DIR / "_default"
    if default_dir.is_dir():
        for f in sorted(default_dir.glob("*.md")):
            if f.name == "README.md":
                continue
            stype, body = _parse_skill_file(f)
            if stype and body:
                skills[stype] = body

    # Load specialty skills (override/merge with defaults)
    specialty_dir = SKILLS_DIR / resolved
    if specialty_dir.is_dir():
        for f in sorted(specialty_dir.glob("*.md")):
            if f.name == "README.md":
                continue
            stype, body = _parse_skill_file(f)
            if stype and body:
                if stype in skills:
                    # Merge: default + specialty
                    skills[stype] = skills[stype] + "\n\n" + body
                else:
                    skills[stype] = body

    _skill_cache[resolved] = (skills, now)
    return skills


def get_skill(specialty: str, skill_type: SkillType) -> Optional[str]:
    """Get a single skill's content body."""
    skills = load_skills(specialty)
    return skills.get(skill_type)



def get_clinical_signals(specialty: str) -> Optional[str]:
    """Return {specialty}/clinical_signals.md content."""
    return get_skill(specialty, SkillType.clinical_signals)


def get_diagnosis_skill(specialty: str) -> Optional[str]:
    """Return {specialty}/diagnosis.md content."""
    return get_skill(specialty, SkillType.diagnosis)


def get_routing_hints(specialty: str) -> Optional[str]:
    """Return routing hints (specialty or _default)."""
    return get_skill(specialty, SkillType.routing)


def list_specialties() -> List[str]:
    """List available specialty directories (excluding _default)."""
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(
        d.name for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name != "_default" and not d.name.startswith(".")
    )


def invalidate_cache() -> None:
    """Clear the skill cache."""
    _skill_cache.clear()
