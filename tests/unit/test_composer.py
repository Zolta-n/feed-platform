"""Unit tests for the digest compose stage."""
import uuid
import pytest
from niche.core.pipeline.compose import compose, MIN_ITEMS, MAX_ITEMS, TARGET_READ_TIME
from niche.core.models.types import Cluster, Item


def make_item(score=1.0, read_time=1.0, topic="tier1"):
    return Item(
        id=str(uuid.uuid4()),
        feed_id="test-feed",
        url=f"https://example.com/{uuid.uuid4().hex[:8]}",
        url_hash=uuid.uuid4().hex,
        topic_tag=topic,
        relevance_score=score,
        summary="Test summary.",
        read_time_min=read_time,
        fetched_at="2026-04-28T10:00:00+00:00",
    )


def make_cluster(items, label="Cluster A"):
    return Cluster(label=label, item_ids=[i.id for i in items])


def test_compose_basic(bundle):
    items = [make_item(score=float(i), read_time=1.0) for i in range(20, 0, -1)]
    clusters = [make_cluster(items[:5]), make_cluster(items[5:10])]
    digest = compose(items, clusters, bundle, run_id="run-1", date="2026-04-28")
    assert digest.feed_id == bundle.config.feed_id
    assert digest.date == "2026-04-28"
    assert MIN_ITEMS <= digest.item_count <= MAX_ITEMS
    assert len(digest.item_ids) == digest.item_count


def test_compose_respects_read_time_target(bundle):
    # 40 items at 1 min each — should stop around 15 items or MIN_ITEMS
    items = [make_item(read_time=1.0) for _ in range(40)]
    clusters = [make_cluster(items[:5])]
    digest = compose(items, clusters, bundle)
    assert digest.total_read_time_min >= min(MIN_ITEMS * 1.0, TARGET_READ_TIME - 1)


def test_compose_cluster_representation(bundle):
    items_a = [make_item(score=2.0) for _ in range(2)]
    items_b = [make_item(score=0.1) for _ in range(2)]
    all_items = items_a + items_b
    clusters = [
        make_cluster(items_a, "Cluster A"),
        make_cluster(items_b, "Cluster B"),
    ]
    digest = compose(all_items, clusters, bundle)
    # At least one item from each cluster should be in the digest
    digest_id_set = set(digest.item_ids)
    for cluster in clusters:
        assert any(iid in digest_id_set for iid in cluster.item_ids), \
            f"No items from {cluster.label!r} in digest"


def test_compose_items_sorted_by_score(bundle):
    items = [make_item(score=float(i)) for i in range(10, 0, -1)]
    clusters = [make_cluster(items)]
    digest = compose(items, clusters, bundle)
    # Item IDs in digest should be in descending score order
    score_map = {i.id: i.relevance_score for i in items}
    scores = [score_map[iid] for iid in digest.item_ids if iid in score_map]
    assert scores == sorted(scores, reverse=True)
