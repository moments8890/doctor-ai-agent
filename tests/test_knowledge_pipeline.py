from __future__ import annotations

from datetime import datetime

from services.knowledge.guideline_diff import diff_guideline_snapshots
from services.knowledge.crawl import crawl_knowledge_source, crawl_knowledge_sources
from services.knowledge.curation import curate_knowledge_documents
from services.knowledge.digest import build_knowledge_digest
from services.knowledge.grounding import build_chat_grounding_bundle
from services.knowledge.models import KnowledgeClaim, KnowledgeSource
from services.knowledge.ranker import rank_knowledge_claims


def _source() -> KnowledgeSource:
    return KnowledgeSource(
        source_id="src-a",
        source_type="guideline",
        title="Cardio Guide",
        publisher="Society",
        trust_tier=3,
        url="https://example.org/guideline",
    )


def test_crawl_source_is_deterministic_and_checkpoint_moves() -> None:
    checkpoint = datetime(2026, 1, 1, 0, 0, 0)
    docs, next_cp = crawl_knowledge_source(_source(), checkpoint, limit=2)
    assert len(docs) == 2
    assert docs[0].document_id.startswith("src-a-")
    assert next_cp > checkpoint


def test_crawl_multiple_sources() -> None:
    checkpoint = datetime(2026, 1, 1, 0, 0, 0)
    docs = crawl_knowledge_sources([_source(), _source()], checkpoint, limit_per_source=1)
    assert len(docs) == 2


def test_curation_dedupes() -> None:
    checkpoint = datetime(2026, 1, 1, 0, 0, 0)
    docs, _ = crawl_knowledge_source(_source(), checkpoint, limit=2)
    docs[1].title = docs[0].title
    docs[1].published_at = docs[0].published_at
    accepted, rejected, summary = curate_knowledge_documents(_source(), docs)
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert summary["duplicates"] == 1


def test_rank_digest_and_grounding() -> None:
    now = datetime(2026, 3, 1, 0, 0, 0)
    claims = [
        KnowledgeClaim(
            claim_id="c1",
            document_id="d1",
            statement="Use BNP trend with symptoms",
            specialty="cardiology",
            evidence_level="high",
            confidence=0.9,
            published_at=datetime(2026, 2, 20, 0, 0, 0),
            citation_url="https://example.org/c1",
        ),
        KnowledgeClaim(
            claim_id="c2",
            document_id="d2",
            statement="Older low confidence claim",
            specialty="cardiology",
            evidence_level="low",
            confidence=0.5,
            published_at=datetime(2025, 1, 1, 0, 0, 0),
            citation_url="https://example.org/c2",
        ),
    ]
    ranked = rank_knowledge_claims(claims, specialty="cardiology", now=now)
    assert ranked[0].claim.claim_id == "c1"

    digest = build_knowledge_digest(ranked, top_k=2)
    assert "Knowledge Digest" in digest
    assert "Safety note" in digest

    bundle = build_chat_grounding_bundle("How to triage?", ranked, limit=2)
    assert "Grounding for" in bundle["context_message"]
    assert len(bundle["snippets"]) == 2


def test_guideline_diff_detects_added_removed_updated() -> None:
    old = {"s1": "old text", "s2": "keep"}
    new = {"s2": "keep", "s1": "new text", "s3": "added"}
    changes = diff_guideline_snapshots(old, new)
    kinds = {c["change_type"] for c in changes}
    assert "updated" in kinds
    assert "added" in kinds
