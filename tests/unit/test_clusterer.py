"""Unit tests for the rule-based clusterer."""
import uuid
import pytest
from niche.core.clusterer.rule_based import cluster_items
from niche.core.models.types import Item


def make_item(topic_tag, company_tags=None, score=1.0):
    return Item(
        id=str(uuid.uuid4()),
        feed_id="test-feed",
        url=f"https://example.com/{uuid.uuid4().hex[:8]}",
        url_hash=uuid.uuid4().hex,
        topic_tag=topic_tag,
        company_tags=company_tags or [],
        relevance_score=score,
        summary="Test summary",
        fetched_at="2026-04-28T10:00:00+00:00",
    )


def test_empty_items():
    from niche.core.bundle_loader import load_bundle
    import os
    bundle = load_bundle(os.path.abspath("feeds/test-fixture"))
    clusters = cluster_items([], bundle)
    assert clusters == []


def test_clusters_by_topic(bundle):
    items = (
        [make_item("tier1") for _ in range(3)]
        + [make_item("oem") for _ in range(2)]
        + [make_item("regulation") for _ in range(2)]
    )
    clusters = cluster_items(items, bundle)
    assert len(clusters) >= 1
    # Total items across clusters should equal input items
    all_ids = {iid for c in clusters for iid in c.item_ids}
    assert all_ids == {i.id for i in items}


def test_cluster_count_within_bounds(bundle):
    items = (
        [make_item("tier1", score=2.0) for _ in range(5)]
        + [make_item("oem", score=1.5) for _ in range(5)]
        + [make_item("regulation", score=1.0) for _ in range(5)]
        + [make_item("technology", score=0.8) for _ in range(5)]
    )
    clusters = cluster_items(items, bundle)
    assert 1 <= len(clusters) <= 5


def test_cluster_labels_not_empty(bundle):
    items = [make_item("tier1") for _ in range(3)]
    clusters = cluster_items(items, bundle)
    for c in clusters:
        assert c.label, "Cluster label should not be empty"
