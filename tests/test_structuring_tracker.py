"""Tests for services.observability.structuring_tracker."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import List

import pytest

from services.observability.structuring_tracker import (
    CorrectionEvent,
    FieldAttribution,
    StructuringMeta,
    attribute_content,
    attribute_tags,
    log_correction_event,
    log_structuring_event,
)


# ── FieldAttribution ─────────────────────────────────────────────────────────


def test_field_attribution_defaults():
    fa = FieldAttribution(field_name="content")
    assert fa.source == "unknown"
    assert fa.confidence == 1.0
    assert fa.detail is None


def test_field_attribution_custom():
    fa = FieldAttribution(
        field_name="tags",
        source="verbatim",
        confidence=0.85,
        detail="4/5 tags found in text",
    )
    d = asdict(fa)
    assert d["field_name"] == "tags"
    assert d["source"] == "verbatim"
    assert d["confidence"] == 0.85


# ── StructuringMeta ──────────────────────────────────────────────────────────


def test_structuring_meta_defaults():
    meta = StructuringMeta()
    assert meta.provider == ""
    assert meta.skills_injected == []
    assert meta.compression_ratio == 0.0


def test_structuring_meta_compute_derived():
    meta = StructuringMeta(
        input_length=1000,
        output_length=600,
    )
    meta.compute_derived()
    assert meta.compression_ratio == 0.6


def test_structuring_meta_compute_derived_zero_input():
    meta = StructuringMeta(input_length=0, output_length=0)
    meta.compute_derived()
    assert meta.compression_ratio == 0.0


def test_structuring_meta_with_attributions():
    meta = StructuringMeta(
        provider="ollama",
        model="qwen2.5:14b",
        latency_ms=1200,
        attributions=[
            FieldAttribution(field_name="content", source="verbatim", confidence=0.8),
            FieldAttribution(field_name="tags", source="inferred", confidence=0.6),
        ],
    )
    assert len(meta.attributions) == 2
    assert meta.attributions[0].source == "verbatim"


# ── CorrectionEvent ─────────────────────────────────────────────────────────


def test_correction_event_identical():
    evt = CorrectionEvent(
        record_id=1,
        doctor_id="d1",
        old_content="患者胸痛2小时",
        new_content="患者胸痛2小时",
    )
    evt.compute_diff()
    assert evt.edit_distance == 0.0


def test_correction_event_different():
    evt = CorrectionEvent(
        record_id=1,
        doctor_id="d1",
        old_content="患者胸痛2小时",
        new_content="患者胸闷3天，伴气短",
    )
    evt.compute_diff()
    assert 0.0 < evt.edit_distance <= 1.0


def test_correction_event_completely_different():
    evt = CorrectionEvent(
        record_id=1,
        doctor_id="d1",
        old_content="AAAA",
        new_content="ZZZZ",
    )
    evt.compute_diff()
    assert evt.edit_distance > 0.5


def test_correction_event_tag_diff():
    evt = CorrectionEvent(
        record_id=1,
        doctor_id="d1",
        old_content="x",
        new_content="x",
        old_tags=["胸痛", "高血压"],
        new_tags=["胸痛", "糖尿病", "心衰"],
    )
    evt.compute_diff()
    assert evt.tags_added == 2   # 糖尿病, 心衰
    assert evt.tags_removed == 1  # 高血压


def test_correction_event_empty_tags():
    evt = CorrectionEvent(
        record_id=1,
        doctor_id="d1",
        old_content="x",
        new_content="y",
    )
    evt.compute_diff()
    assert evt.tags_added == 0
    assert evt.tags_removed == 0


# ── attribute_content ────────────────────────────────────────────────────────


def test_attribute_content_verbatim():
    """High similarity → verbatim source."""
    original = "患者张三，男，45岁，主诉胸痛2小时"
    structured = "患者张三，男，45岁，主诉胸痛2小时。"
    attr = attribute_content(original, structured)
    assert attr.source == "verbatim"
    assert attr.confidence > 0.6


def test_attribute_content_inferred():
    """Low similarity → inferred source."""
    original = "患者说他最近一直头痛，吃了点药好了一些，然后又开始痛了"
    structured = "患者主诉间歇性头痛，用药后暂时缓解，近日复发。"
    attr = attribute_content(original, structured)
    assert attr.source == "inferred"


def test_attribute_content_with_skills():
    """Low similarity but skills injected → skill source."""
    original = "头疼三天了"
    structured = "患者主诉头痛3天。根据NIHSS评分标准进行神经系统评估。"
    attr = attribute_content(original, structured, skill_names=["neurology-structuring"])
    assert attr.source == "skill"


def test_attribute_content_empty():
    attr = attribute_content("", "")
    assert attr.source == "unknown"


# ── attribute_tags ───────────────────────────────────────────────────────────


def test_attribute_tags_all_verbatim():
    tags = ["胸痛", "高血压", "阿司匹林"]
    text = "患者高血压病史，今日胸痛2小时，已服阿司匹林"
    attr = attribute_tags(tags, text)
    assert attr.source == "verbatim"
    assert attr.confidence == 1.0


def test_attribute_tags_mixed():
    tags = ["胸痛", "急性冠脉综合征", "PCI"]
    text = "患者胸痛2小时，需要PCI介入"
    attr = attribute_tags(tags, text)
    # 2/3 verbatim → "verbatim"
    assert attr.source == "verbatim"
    assert 0.5 < attr.confidence <= 1.0


def test_attribute_tags_mostly_inferred():
    tags = ["急性STEMI", "左前降支闭塞", "心源性休克"]
    text = "胸口疼得厉害"
    attr = attribute_tags(tags, text)
    assert attr.source == "inferred"


def test_attribute_tags_empty():
    attr = attribute_tags([], "some text")
    assert attr.source == "unknown"
    assert attr.confidence == 0.0


# ── log_structuring_event (in test mode = no-op) ────────────────────────────


def test_log_structuring_event_noop_in_test():
    """In test mode (PYTEST_CURRENT_TEST set), logging is a no-op."""
    meta = StructuringMeta(
        provider="ollama",
        latency_ms=500,
        input_length=100,
        output_length=80,
    )
    # Should not raise, even though no real log file exists.
    log_structuring_event("d1", meta)


def test_log_correction_event_noop_in_test():
    """In test mode, correction logging is a no-op."""
    log_correction_event("d1", 42, "old", "new")


# ── Serialization ───────────────────────────────────────────────────────────


def test_attribution_serializable():
    """FieldAttribution should be JSON-serializable via asdict."""
    fa = FieldAttribution(
        field_name="content",
        source="verbatim",
        confidence=0.9,
        detail="sim=0.91",
    )
    j = json.dumps(asdict(fa), ensure_ascii=False)
    assert "verbatim" in j


def test_meta_with_attributions_serializable():
    meta = StructuringMeta(
        provider="deepseek",
        attributions=[
            FieldAttribution(field_name="content", source="inferred"),
        ],
    )
    payload = {
        "provider": meta.provider,
        "attributions": [asdict(a) for a in meta.attributions],
    }
    j = json.dumps(payload, ensure_ascii=False)
    assert "inferred" in j
