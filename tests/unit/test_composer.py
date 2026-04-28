from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from niche.core.models.types import Cluster, Item
from niche.core.pipeline.compose import _DIGEST_MAX_ITEMS, _DIGEST_MIN_ITEMS, _DIGEST_TARGET_MINUTES, _MIN_ITEMS_PER_TOPIC, compose


def _make_item(idx: int, read_time_min: float = 1.0, relevance_score: float = 1.0) -> Item:
    now = datetime.now(timezone.utc)
    return Item(
        id=f"d-{idx}", feed_id="test-fixture", url=f"https://ex.com/{idx}",
        url_hash=f"h{idx}", title_hash=f"th{idx}", title=f"Article {idx}",
        title_translated=None, body_raw="", body_translated=None,
        summary="Summary.", why_it_matters="Matters.",
        source_id="src", source_name="S", source_language="en",
        topic_tag="technology", item_type="brief", region_tag=None, company_tags=[],
        translation_failed=False, translation_provider=None,
        relevance_score=relevance_score, published_at=None, fetched_at=now,
        run_id="run-001", word_count=5, read_time_min=read_time_min,
        is_duplicate=False, duplicate_of=None,
    )


def _make_cluster(label: str, item_ids: list[str], display_order: int = 0) -> Cluster:
    return Cluster(label=label, item_ids=item_ids, display_order=display_order)


# --- item count bounds ---

def test_digest_item_count_within_bounds(bundle):
    items = [_make_item(i, read_time_min=1.0) for i in range(40)]
    clusters = [_make_cluster("All", [f"d-{i}" for i in range(40)])]
    digest = compose(items, clusters, bundle, "run-001")
    assert _DIGEST_MIN_ITEMS <= digest.item_count <= _DIGEST_MAX_ITEMS


def test_digest_target_read_time_approximately_15(bundle):
    items = [_make_item(i, read_time_min=1.0) for i in range(40)]
    clusters = [_make_cluster("All", [f"d-{i}" for i in range(40)])]
    digest = compose(items, clusters, bundle, "run-001")
    # With 1.0 min/item, should stop around 15 items (after reaching 15 min)
    assert 12.0 <= digest.total_read_time_min <= 30.0


def test_digest_minimum_10_items_even_if_budget_met_early(bundle):
    # 5-minute items: budget met at item 3, but floor is 10
    items = [_make_item(i, read_time_min=5.0) for i in range(20)]
    clusters = [_make_cluster("All", [f"d-{i}" for i in range(20)])]
    digest = compose(items, clusters, bundle, "run-001")
    assert digest.item_count >= _DIGEST_MIN_ITEMS


def test_digest_few_items_includes_all(bundle):
    items = [_make_item(i, read_time_min=1.0) for i in range(5)]
    clusters = [_make_cluster("All", [f"d-{i}" for i in range(5)])]
    digest = compose(items, clusters, bundle, "run-001")
    assert digest.item_count == 5


def test_digest_empty_items(bundle):
    digest = compose([], [], bundle, "run-001")
    assert digest.item_count == 0


# --- cluster coverage ---

def test_cluster_coverage_includes_one_item_per_cluster(bundle):
    # 2 clusters of 5 items each
    items_a = [_make_item(i, read_time_min=1.0, relevance_score=float(10 - i)) for i in range(5)]
    items_b = [_make_item(i + 10, read_time_min=1.0, relevance_score=float(10 - i)) for i in range(5)]
    items = items_a + items_b

    clusters = [
        _make_cluster("Cluster A", [f"d-{i}" for i in range(5)], 0),
        _make_cluster("Cluster B", [f"d-{i + 10}" for i in range(5)], 1),
    ]
    digest = compose(items, clusters, bundle, "run-001")

    selected = set(digest.item_ids)
    # At least one item from cluster A
    assert any(f"d-{i}" in selected for i in range(5))
    # At least one item from cluster B
    assert any(f"d-{i + 10}" in selected for i in range(5))


# --- digest metadata ---

def test_digest_has_correct_feed_id(bundle):
    items = [_make_item(i) for i in range(5)]
    clusters = [_make_cluster("All", [f"d-{i}" for i in range(5)])]
    digest = compose(items, clusters, bundle, "run-001")
    assert digest.feed_id == "test-fixture"


def test_digest_run_id_matches(bundle):
    items = [_make_item(i) for i in range(5)]
    clusters = [_make_cluster("All", [f"d-{i}" for i in range(5)])]
    digest = compose(items, clusters, bundle, "my-run-id")
    assert digest.run_id == "my-run-id"


def test_digest_cluster_map_populated(bundle):
    items = [_make_item(i) for i in range(5)]
    clusters = [_make_cluster("Tech", [f"d-{i}" for i in range(5)])]
    digest = compose(items, clusters, bundle, "run-001")
    assert len(digest.cluster_map) == 1
    assert digest.cluster_map[0]["label"] == "Tech"


def test_digest_max_items_not_exceeded(bundle):
    items = [_make_item(i, read_time_min=0.1) for i in range(50)]
    clusters = [_make_cluster("All", [f"d-{i}" for i in range(50)])]
    digest = compose(items, clusters, bundle, "run-001")
    assert digest.item_count <= _DIGEST_MAX_ITEMS


# --- per-topic minimum ---

def test_per_topic_minimum_guaranteed(bundle):
    topics = ["technology", "market", "north", "south"]
    items = []
    for t_idx, topic in enumerate(topics):
        for i in range(5):
            item = replace(_make_item(t_idx * 10 + i, read_time_min=1.0), topic_tag=topic)
            items.append(item)
    clusters = [_make_cluster("All", [item.id for item in items])]
    digest = compose(items, clusters, bundle, "run-001")
    selected = set(digest.item_ids)
    for topic in topics:
        count = sum(1 for iid in selected if items[[i.id for i in items].index(iid)].topic_tag == topic)
        assert count >= _MIN_ITEMS_PER_TOPIC, f"topic={topic} has only {count} items in digest"


def test_per_topic_minimum_graceful_when_fewer_available(bundle):
    # Only 2 items with topic "market" exist — expect exactly 2 in digest, no error
    items_tech = [_make_item(i, read_time_min=1.0) for i in range(10)]  # topic_tag="technology"
    items_market = [replace(_make_item(100 + i, read_time_min=1.0), topic_tag="market") for i in range(2)]
    items = items_tech + items_market
    clusters = [_make_cluster("All", [item.id for item in items])]
    digest = compose(items, clusters, bundle, "run-001")
    selected = set(digest.item_ids)
    market_count = sum(1 for iid in selected if items[[i.id for i in items].index(iid)].topic_tag == "market")
    assert market_count == 2


def test_per_topic_minimum_respects_max_items(bundle):
    # 15 topics × 5 items = 75 items; 3 per topic = 45 minimum, which exceeds _DIGEST_MAX_ITEMS=30
    items = []
    for t_idx in range(15):
        for i in range(5):
            item = replace(_make_item(t_idx * 10 + i, read_time_min=0.1), topic_tag=f"topic{t_idx}")
            items.append(item)
    clusters = [_make_cluster("All", [item.id for item in items])]
    digest = compose(items, clusters, bundle, "run-001")
    assert digest.item_count <= _DIGEST_MAX_ITEMS
