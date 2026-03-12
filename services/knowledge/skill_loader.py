"""Specialty skill loader — loads Markdown skill files per specialty.

Inspired by OpenClaw's SKILL.md model: each specialty has a directory under
``skills/`` with Markdown files that are injected into LLM prompts.

Structure::

    skills/
    ├── _default/              # shared baseline (always loaded)
    │   ├── structuring.md
    │   └── routing_hints.md
    ├── cardiology/
    │   ├── structuring.md
    │   ├── clinical_signals.md
    │   └── routing_hints.md
    └── neurology/
        ├── structuring.md
        └── clinical_signals.md

Each file has YAML frontmatter (name, description, type, specialty) followed
by Markdown content.  The content is injected into LLM prompts as supplementary
context.

Usage::

    from services.knowledge.skill_loader import load_skills, get_structuring_skill

    # Load all skills for a specialty
    skills = load_skills("cardiology")

    # Get just the structuring skill (most common use)
    structuring = get_structuring_skill("cardiology")
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from utils.log import log

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILLS_DIR = _ROOT / "skills"

# Cache: specialty → (loaded_at_mono, list_of_skills)
_CACHE: Dict[str, tuple] = {}
_CACHE_TTL: float = float(os.environ.get("SKILLS_CACHE_TTL", "300"))  # 5 min


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Skill:
    """A single loaded skill with its content and metadata."""

    name: str
    description: str
    skill_type: str        # "structuring" | "routing" | "clinical_signals"
    specialty: str          # "cardiology", "neurology", "_default"
    content: str            # Markdown body (without frontmatter)
    file_path: str          # Source file for debugging

    @property
    def token_estimate(self) -> int:
        """Rough CJK+Latin token estimate (~1.5 chars per token for Chinese)."""
        return max(1, len(self.content) * 2 // 3)


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def _parse_skill_file(path: Path) -> Optional[Skill]:
    """Parse a single .md skill file into a Skill object."""
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        log(f"[skills] failed to read {path}")
        return None

    meta: Dict[str, str] = {}
    body = raw

    fm_match = _FRONTMATTER_RE.match(raw)
    if fm_match:
        body = raw[fm_match.end():]
        for line in fm_match.group(1).splitlines():
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip()] = val.strip()

    body = body.strip()
    if not body:
        return None

    return Skill(
        name=meta.get("name", path.stem),
        description=meta.get("description", ""),
        skill_type=meta.get("type", path.stem),
        specialty=meta.get("specialty", path.parent.name),
        content=body,
        file_path=str(path),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_skills(specialty: Optional[str] = None) -> List[Skill]:
    """Load all skills for a specialty (plus _default baseline).

    Results are cached for ``SKILLS_CACHE_TTL`` seconds.

    Args:
        specialty: Specialty name matching a subdirectory of ``skills/``.
                   If None or empty, only ``_default`` skills are loaded.

    Returns:
        List of Skill objects, _default first then specialty-specific.
    """
    cache_key = specialty or "_default"

    entry = _CACHE.get(cache_key)
    if entry and time.monotonic() - entry[0] < _CACHE_TTL:
        return entry[1]

    skills: List[Skill] = []

    # Always load _default baseline.
    default_dir = _SKILLS_DIR / "_default"
    if default_dir.is_dir():
        for md in sorted(default_dir.glob("*.md")):
            skill = _parse_skill_file(md)
            if skill:
                skills.append(skill)

    # Load specialty-specific skills (if different from _default).
    if specialty and specialty != "_default":
        spec_dir = _SKILLS_DIR / _normalize_specialty(specialty)
        if spec_dir.is_dir():
            for md in sorted(spec_dir.glob("*.md")):
                skill = _parse_skill_file(md)
                if skill:
                    skills.append(skill)

    _CACHE[cache_key] = (time.monotonic(), skills)

    if skills:
        total_tokens = sum(s.token_estimate for s in skills)
        log(f"[skills] loaded {len(skills)} skills for '{cache_key}' (~{total_tokens} tokens)")

    return skills


def get_skills_by_type(
    specialty: Optional[str] = None,
    skill_type: str = "structuring",
) -> List[Skill]:
    """Load skills of a specific type for a specialty.

    Args:
        specialty: Specialty name (or None for defaults only).
        skill_type: Filter by type: "structuring", "routing", "clinical_signals".
    """
    return [s for s in load_skills(specialty) if s.skill_type == skill_type]


def get_structuring_skill(specialty: Optional[str] = None) -> Optional[str]:
    """Convenience: return combined structuring skill content for a specialty.

    Returns None if no structuring skills exist.
    """
    skills = get_skills_by_type(specialty, "structuring")
    if not skills:
        return None
    return "\n\n".join(s.content for s in skills)


def get_clinical_signals(specialty: Optional[str] = None) -> Optional[str]:
    """Return combined clinical signal rules for a specialty."""
    skills = get_skills_by_type(specialty, "clinical_signals")
    if not skills:
        return None
    return "\n\n".join(s.content for s in skills)


def get_routing_hints(specialty: Optional[str] = None) -> Optional[str]:
    """Return combined routing hint content for a specialty."""
    skills = get_skills_by_type(specialty, "routing")
    if not skills:
        return None
    return "\n\n".join(s.content for s in skills)


def list_specialties() -> List[str]:
    """Return a list of specialty names that have skill directories."""
    if not _SKILLS_DIR.is_dir():
        return []
    return sorted(
        d.name for d in _SKILLS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def invalidate_cache(specialty: Optional[str] = None) -> None:
    """Clear skill cache (call after editing skill files)."""
    if specialty:
        _CACHE.pop(specialty, None)
    else:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SPECIALTY_ALIASES: Dict[str, str] = {
    "心内科": "cardiology",
    "心血管内科": "cardiology",
    "神经外科": "neurology",
    "神经内科": "neurology",
    "脑外科": "neurology",
    "内分泌科": "endocrinology",
    "肿瘤科": "oncology",
    "骨科": "orthopedics",
    "呼吸内科": "pulmonology",
    "消化内科": "gastroenterology",
    "泌尿外科": "urology",
    "普外科": "general_surgery",
    "妇产科": "obstetrics",
    "儿科": "pediatrics",
    "眼科": "ophthalmology",
    "耳鼻喉科": "ent",
    "皮肤科": "dermatology",
    "精神科": "psychiatry",
    "急诊科": "emergency",
    "ICU": "icu",
    "重症医学科": "icu",
}


def _normalize_specialty(raw: str) -> str:
    """Normalize a Chinese or English specialty name to a directory name."""
    stripped = (raw or "").strip()
    if not stripped:
        return "_default"
    # Try alias first.
    alias = _SPECIALTY_ALIASES.get(stripped)
    if alias:
        return alias
    # Already a valid directory name.
    return stripped.lower().replace(" ", "_").replace("-", "_")
