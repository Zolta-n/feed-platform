"""Unit tests for the ranker formula."""
import pytest
from niche.core.ranker.formula import compute_score
from niche.core.models.types import Item
import uuid


def make_item(**kwargs):
    defaults = {
        "id": str(uuid.uuid4()),
        "feed_id": "test-feed",
        "url": "https://example.com/test",
        "url_hash": "abc123",
        "topic_tag": "tier1",
        "item_type": "report",
        "region_tag": "europe",
        "company_tags": [],
        "relevance_score": 0.0,
        "summary": "Test summary",
        "published_at": "2026-04-28T10:00:00+00:00",
        "fetched_at": "2026-04-28T10:00:00+00:00",
    }
    defaults.update(kwargs)
    return Item(**defaults)


def test_basic_score():
    item = make_item(topic_tag="tier1")
    score = compute_score(
        item=item,
        topic_weights={"tier1": 1.5, "oem": 1.0},
        region_weights={"europe": 1.2},
        company_boosts={},
        feedback_signals={},
        keyword_boosts=[],
        source_weight=1.0,
    )
    assert score > 0


def test_topic_weight_affects_score():
    item = make_item(topic_tag="tier1")
    low = compute_score(item, {"tier1": 0.5}, {}, {}, {}, [], 1.0)
    high = compute_score(item, {"tier1": 2.0}, {}, {}, {}, [], 1.0)
    assert high > low


def test_company_boost_elevates_item():
    item = make_item(company_tags=["acme-brake"])
    no_boost = compute_score(item, {"tier1": 1.0}, {}, {}, {}, [], 1.0)
    with_boost = compute_score(item, {"tier1": 1.0}, {}, {"acme-brake": 2.0}, {}, [], 1.0)
    assert with_boost > no_boost


def test_thumbs_signal_modifies_score():
    item = make_item(topic_tag="tier1")
    base = compute_score(item, {"tier1": 1.0}, {}, {}, {}, [], 1.0)
    up_signal = compute_score(item, {"tier1": 1.0}, {}, {}, {"tier1": 0.3}, [], 1.0)
    down_signal = compute_score(item, {"tier1": 1.0}, {}, {}, {"tier1": -0.3}, [], 1.0)
    assert up_signal > base
    assert down_signal < base


def test_thumbs_signal_capped():
    item = make_item(topic_tag="tier1")
    # Signal > 0.5 should be capped at 0.5
    big_signal = compute_score(item, {"tier1": 1.0}, {}, {}, {"tier1": 10.0}, [], 1.0)
    capped_signal = compute_score(item, {"tier1": 1.0}, {}, {}, {"tier1": 0.5}, [], 1.0)
    assert abs(big_signal - capped_signal) < 0.001


def test_keyword_boost_multiplies_score():
    item = make_item(title="brake actuator system", summary="new brake actuator announced")
    base = compute_score(item, {"tier1": 1.0}, {}, {}, {}, [], 1.0)
    boosted = compute_score(item, {"tier1": 1.0}, {}, {}, {},
                             [{"term": "brake actuator", "weight": 2.0}], 1.0)
    assert boosted > base


def test_source_weight_affects_score():
    item = make_item()
    low = compute_score(item, {"tier1": 1.0}, {}, {}, {}, [], source_weight=0.5)
    high = compute_score(item, {"tier1": 1.0}, {}, {}, {}, [], source_weight=1.5)
    assert high > low
