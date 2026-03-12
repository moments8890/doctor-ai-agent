"""Tests for services.knowledge.skill_loader — specialty skill loading."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from services.knowledge.skill_loader import (
    Skill,
    _normalize_specialty,
    _parse_skill_file,
    get_clinical_signals,
    get_routing_hints,
    get_skills_by_type,
    get_structuring_skill,
    invalidate_cache,
    list_specialties,
    load_skills,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_cache()
    yield
    invalidate_cache()


# ── _normalize_specialty ─────────────────────────────────────────────────────


def test_normalize_chinese_specialty():
    assert _normalize_specialty("心内科") == "cardiology"
    assert _normalize_specialty("神经外科") == "neurology"
    assert _normalize_specialty("内分泌科") == "endocrinology"


def test_normalize_english_specialty():
    assert _normalize_specialty("cardiology") == "cardiology"
    assert _normalize_specialty("Neurology") == "neurology"


def test_normalize_empty():
    assert _normalize_specialty("") == "_default"
    assert _normalize_specialty(None) == "_default"


def test_normalize_unknown():
    assert _normalize_specialty("SomeSpecialty") == "somespecialty"


# ── _parse_skill_file ───────────────────────────────────────────────────────


def test_parse_skill_file(tmp_path: Path):
    md = tmp_path / "test.md"
    md.write_text(textwrap.dedent("""\
        ---
        name: test-skill
        description: A test skill
        type: structuring
        specialty: cardiology
        ---

        # Test Skill Content

        Some rules here.
    """))
    skill = _parse_skill_file(md)
    assert skill is not None
    assert skill.name == "test-skill"
    assert skill.description == "A test skill"
    assert skill.skill_type == "structuring"
    assert skill.specialty == "cardiology"
    assert "# Test Skill Content" in skill.content
    assert "Some rules here." in skill.content


def test_parse_skill_file_no_frontmatter(tmp_path: Path):
    md = tmp_path / "plain.md"
    md.write_text("# Just content\nNo frontmatter.")
    skill = _parse_skill_file(md)
    assert skill is not None
    assert skill.name == "plain"
    assert skill.content == "# Just content\nNo frontmatter."


def test_parse_skill_file_empty(tmp_path: Path):
    md = tmp_path / "empty.md"
    md.write_text("---\nname: empty\n---\n")
    skill = _parse_skill_file(md)
    assert skill is None  # empty body → skip


def test_parse_skill_file_missing(tmp_path: Path):
    skill = _parse_skill_file(tmp_path / "nonexistent.md")
    assert skill is None


# ── load_skills ─────────────────────────────────────────────────────────────


def test_load_default_skills():
    """Loading with no specialty should include _default skills."""
    skills = load_skills()
    default_names = [s.name for s in skills if s.specialty == "_default"]
    assert len(default_names) >= 1  # at least structuring.md


def test_load_cardiology_skills():
    skills = load_skills("cardiology")
    names = [s.name for s in skills]
    assert "cardiology-structuring" in names
    assert "cardiology-clinical-signals" in names
    # Also includes defaults.
    assert any(s.specialty == "_default" for s in skills)


def test_load_neurology_skills():
    skills = load_skills("neurology")
    names = [s.name for s in skills]
    assert "neurology-structuring" in names


def test_load_chinese_specialty():
    skills = load_skills("心内科")
    names = [s.name for s in skills]
    assert "cardiology-structuring" in names


def test_load_nonexistent_specialty():
    """Unknown specialty should still return _default skills."""
    skills = load_skills("dermatology_advanced")
    default_only = all(s.specialty == "_default" for s in skills)
    assert default_only


def test_load_skills_cached():
    """Second call should hit cache."""
    s1 = load_skills("cardiology")
    s2 = load_skills("cardiology")
    assert s1 is s2  # same list object → cache hit


def test_invalidate_cache():
    load_skills("cardiology")
    invalidate_cache("cardiology")
    s2 = load_skills("cardiology")
    # After invalidation, a new list is loaded.
    assert isinstance(s2, list)


# ── get_skills_by_type ──────────────────────────────────────────────────────


def test_get_skills_by_type_structuring():
    skills = get_skills_by_type("cardiology", "structuring")
    assert all(s.skill_type == "structuring" for s in skills)
    assert len(skills) >= 2  # default + cardiology


def test_get_skills_by_type_clinical_signals():
    skills = get_skills_by_type("cardiology", "clinical_signals")
    assert all(s.skill_type == "clinical_signals" for s in skills)
    assert len(skills) >= 1


# ── Convenience functions ───────────────────────────────────────────────────


def test_get_structuring_skill():
    content = get_structuring_skill("cardiology")
    assert content is not None
    assert "STEMI" in content or "PCI" in content


def test_get_structuring_skill_default_only():
    content = get_structuring_skill()
    assert content is not None
    assert "ASR" in content  # from default structuring.md


def test_get_structuring_skill_unknown():
    content = get_structuring_skill("unknown_specialty_xyz")
    assert content is not None  # still returns default


def test_get_clinical_signals():
    signals = get_clinical_signals("cardiology")
    assert signals is not None
    assert "胸痛" in signals or "STEMI" in signals


def test_get_clinical_signals_none():
    """No clinical signals for unknown specialty without signals."""
    signals = get_clinical_signals("_default")
    assert signals is None  # _default has no clinical_signals.md


def test_get_routing_hints():
    hints = get_routing_hints()
    assert hints is not None
    assert "create_patient" in hints


# ── list_specialties ────────────────────────────────────────────────────────


def test_list_specialties():
    specs = list_specialties()
    assert "_default" in specs
    assert "cardiology" in specs
    assert "neurology" in specs


# ── Skill.token_estimate ────────────────────────────────────────────────────


def test_skill_token_estimate():
    skill = Skill(
        name="t",
        description="",
        skill_type="structuring",
        specialty="_default",
        content="一二三四五六七八九十" * 10,  # 100 Chinese chars
        file_path="",
    )
    # ~1.5 chars per token for CJK → ~67 tokens for 100 chars
    assert 50 <= skill.token_estimate <= 80
