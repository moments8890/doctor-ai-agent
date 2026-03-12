"""Unit tests for services.observability.routing_metrics."""

from __future__ import annotations

import pytest

from services.observability import routing_metrics


@pytest.fixture(autouse=True)
def _reset_counters():
    """Ensure counters are clean before and after every test."""
    routing_metrics.reset()
    yield
    routing_metrics.reset()


# ── record ──────────────────────────────────────────────────────────────

class TestRecord:
    def test_single_increment(self):
        routing_metrics.record("fast:add_record")
        m = routing_metrics.get_metrics()
        assert m["total_routed"] == 1
        assert m["by_intent"]["fast:add_record"] == 1

    def test_multiple_increments(self):
        for _ in range(5):
            routing_metrics.record("fast:add_record")
        m = routing_metrics.get_metrics()
        assert m["total_routed"] == 5
        assert m["by_intent"]["fast:add_record"] == 5

    def test_different_labels_independent(self):
        routing_metrics.record("fast:add_record")
        routing_metrics.record("fast:query_records")
        routing_metrics.record("fast:query_records")
        m = routing_metrics.get_metrics()
        assert m["by_intent"]["fast:add_record"] == 1
        assert m["by_intent"]["fast:query_records"] == 2
        assert m["total_routed"] == 3


# ── get_metrics ─────────────────────────────────────────────────────────

class TestGetMetrics:
    def test_correct_totals(self):
        routing_metrics.record("fast:add_record")
        routing_metrics.record("fast:add_record")
        routing_metrics.record("llm")
        m = routing_metrics.get_metrics()
        assert m["total_routed"] == 3
        assert m["fast_hits"] == 2
        assert m["llm_hits"] == 1

    def test_fast_hit_rate_pct(self):
        # 3 fast, 1 llm => 75.0%
        for _ in range(3):
            routing_metrics.record("fast:greeting")
        routing_metrics.record("llm")
        m = routing_metrics.get_metrics()
        assert m["fast_hit_rate_pct"] == 75.0

    def test_by_intent_sorted(self):
        routing_metrics.record("llm")
        routing_metrics.record("fast:z_intent")
        routing_metrics.record("fast:a_intent")
        m = routing_metrics.get_metrics()
        keys = list(m["by_intent"].keys())
        assert keys == sorted(keys), "by_intent keys must be sorted"


# ── reset ───────────────────────────────────────────────────────────────

class TestReset:
    def test_clears_all_counters(self):
        routing_metrics.record("fast:add_record")
        routing_metrics.record("llm")
        routing_metrics.reset()
        m = routing_metrics.get_metrics()
        assert m["total_routed"] == 0
        assert m["fast_hits"] == 0
        assert m["llm_hits"] == 0
        assert m["by_intent"] == {}

    def test_fast_hit_rate_zero_after_reset(self):
        routing_metrics.record("fast:add_record")
        routing_metrics.reset()
        m = routing_metrics.get_metrics()
        assert m["fast_hit_rate_pct"] == 0.0


# ── mixed labels ────────────────────────────────────────────────────────

class TestMixedLabels:
    def test_mixed_fast_and_llm(self):
        routing_metrics.record("fast:add_record")
        routing_metrics.record("fast:query_records")
        routing_metrics.record("fast:greeting")
        routing_metrics.record("llm")
        routing_metrics.record("llm")
        m = routing_metrics.get_metrics()
        assert m["fast_hits"] == 3
        assert m["llm_hits"] == 2
        assert m["total_routed"] == 5
        assert m["fast_hit_rate_pct"] == 60.0

    def test_all_fast_hit_rate_100(self):
        routing_metrics.record("fast:a")
        routing_metrics.record("fast:b")
        m = routing_metrics.get_metrics()
        assert m["fast_hit_rate_pct"] == 100.0

    def test_all_llm_hit_rate_0(self):
        routing_metrics.record("llm")
        routing_metrics.record("llm")
        m = routing_metrics.get_metrics()
        assert m["fast_hit_rate_pct"] == 0.0
        assert m["llm_hits"] == 2

    def test_non_standard_label_counted_in_total(self):
        """Labels that are neither 'fast:*' nor 'llm' still count toward total."""
        routing_metrics.record("unknown_label")
        routing_metrics.record("fast:x")
        m = routing_metrics.get_metrics()
        assert m["total_routed"] == 2
        assert m["fast_hits"] == 1
        assert m["llm_hits"] == 0
        # hit rate = 1/2 = 50%
        assert m["fast_hit_rate_pct"] == 50.0


# ── empty state ─────────────────────────────────────────────────────────

class TestEmptyState:
    def test_empty_get_metrics(self):
        m = routing_metrics.get_metrics()
        assert m["total_routed"] == 0
        assert m["fast_hits"] == 0
        assert m["llm_hits"] == 0
        assert m["fast_hit_rate_pct"] == 0.0
        assert m["by_intent"] == {}

    def test_reset_on_empty_is_noop(self):
        routing_metrics.reset()
        m = routing_metrics.get_metrics()
        assert m["total_routed"] == 0
