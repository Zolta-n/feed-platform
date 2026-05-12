"""Unit tests for the classify pipeline stage."""
import uuid
import pytest
from niche.core.pipeline.classify import classify, _match_company_tags
from niche.core.models.types import Item, WatchlistEntry


def make_item(title="", body="", topic_tag=None, region_tag=None):
    return Item(
        id=str(uuid.uuid4()),
        feed_id="test-feed",
        url="https://example.com/item",
        url_hash=uuid.uuid4().hex,
        title=title,
        body_raw=body,
        topic_tag=topic_tag,
        region_tag=region_tag,
        fetched_at="2026-04-28T10:00:00+00:00",
    )


def test_company_tag_matching_by_name():
    watchlist = [
        WatchlistEntry(id="acme-brake", name="AcmeBrake", aliases=["Acme Brake"]),
    ]
    tags = _match_company_tags("AcmeBrake announces new product line", watchlist)
    assert "acme-brake" in tags


def test_company_tag_matching_by_alias():
    watchlist = [
        WatchlistEntry(id="acme-brake", name="AcmeBrake", aliases=["Acme B."]),
    ]
    tags = _match_company_tags("Acme B. releases quarterly results", watchlist)
    assert "acme-brake" in tags


def test_company_tag_no_match():
    watchlist = [
        WatchlistEntry(id="acme-brake", name="AcmeBrake"),
    ]
    tags = _match_company_tags("Completely unrelated article about pasta", watchlist)
    assert "acme-brake" not in tags


def test_classify_stub_preserves_default_topic(bundle):
    items = [make_item(topic_tag="tier1")]
    result = classify(items, bundle, classifier=None)
    assert result[0].topic_tag == "tier1"


def test_classify_removes_invalid_topic(bundle):
    items = [make_item(topic_tag="invalid_topic_xyz")]
    result = classify(items, bundle, classifier=None)
    assert result[0].topic_tag is None


def test_classify_adds_company_tags(bundle):
    """AcmeBrake is in the test-fixture watchlist."""
    items = [make_item(title="AcmeBrake reports strong Q1", body="AcmeBrake GmbH sales grew")]
    result = classify(items, bundle, classifier=None)
    assert "acme-brake" in result[0].company_tags
