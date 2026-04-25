"""Dedup detection tests — chief_complaint similarity AND episode signals.

Spec §5a: same complaint text after a doctor decision or status advance
is by definition a NEW clinical episode, never a duplicate. The episode
signals override similarity even at very high scores.

Three bands by similarity:
  ≥ 0.7         auto_merge (with episode signals clear)
  [0.5, 0.7)    patient_prompt
  < 0.5         no dedup
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_high_similarity_clear_signals_returns_same_episode():
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.85),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=False,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛",
            target_complaint="头疼",
            signals=signals,
        )
    assert result.same_episode is True
    assert result.band == "auto_merge"


@pytest.mark.asyncio
async def test_high_similarity_but_treatment_event_returns_new_episode():
    # Treatment event since last → patient came back about a complication
    # or a related-but-distinct issue. Never auto-merge.
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.85),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=True,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="头疼", signals=signals,
        )
    assert result.same_episode is False


@pytest.mark.asyncio
async def test_high_similarity_but_status_change_returns_new_episode():
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.85),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=False,
            status_change_since_last=True,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="头疼", signals=signals,
        )
    assert result.same_episode is False


@pytest.mark.asyncio
async def test_high_similarity_but_over_24h_returns_new_episode():
    # 24h+ gap = different episode regardless of text similarity.
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.85),
    ):
        signals = EpisodeSignals(
            hours_since_last=25.0,
            treatment_event_since_last=False,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="头疼", signals=signals,
        )
    assert result.same_episode is False


@pytest.mark.asyncio
async def test_band_in_ambiguous_range_returns_prompt():
    # 0.6 is in [0.5, 0.7) — match enough to suspect, not enough to merge
    # without checking with the patient.
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.6),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=False,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="头晕", signals=signals,
        )
    assert result.same_episode is True
    assert result.band == "patient_prompt"


@pytest.mark.asyncio
async def test_low_similarity_returns_no_dedup():
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.3),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=False,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="腿肿", signals=signals,
        )
    assert result.same_episode is False
    assert result.band == "none"
