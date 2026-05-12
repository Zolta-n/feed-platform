"""Unit tests for the deduplication pipeline stage."""
import datetime
import pytest
from niche.core.models.types import RawItem
from niche.core.pipeline.dedup import dedup, _url_hash, _title_hash


def make_raw(url, title="Test title", source_id="test-source", body="body text"):
    return RawItem(
        source_id=source_id,
        url=url,
        title=title,
        body=body,
        language="en",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        fetched_at=datetime.datetime.now(datetime.timezone.utc),
    )


def test_dedup_empty():
    items = dedup([], "test-feed", set(), set(), [])
    assert items == []


def test_dedup_no_duplicates():
    raw = [
        make_raw("https://example.com/a"),
        make_raw("https://example.com/b"),
        make_raw("https://example.com/c"),
    ]
    items = dedup(raw, "test-feed", set(), set(), [])
    assert len(items) == 3
    assert all(not i.is_duplicate for i in items)


def test_dedup_url_hash_duplicate():
    url = "https://example.com/duplicate"
    existing_hash = _url_hash(url)
    raw = [make_raw(url, title="Some title")]
    items = dedup(raw, "test-feed", {existing_hash}, set(), [])
    assert len(items) == 1
    assert items[0].is_duplicate is True


def test_dedup_title_hash_duplicate():
    title = "This is a duplicate title"
    existing_hash = _title_hash(title)
    raw = [make_raw("https://example.com/unique", title=title)]
    items = dedup(raw, "test-feed", set(), {existing_hash}, [])
    assert len(items) == 1
    assert items[0].is_duplicate is True


def test_dedup_fuzzy_match():
    recent_titles = [("existing-id", "Breaking: Major automotive announcement from Bosch")]
    raw = [make_raw(
        "https://example.com/new",
        title="Breaking: Major automotive announcement from Bosch Corp"
    )]
    items = dedup(raw, "test-feed", set(), set(), recent_titles)
    assert len(items) == 1
    assert items[0].is_duplicate is True
    assert items[0].duplicate_of == "existing-id"


def test_dedup_intra_batch_url_dedup():
    url = "https://example.com/same"
    raw = [make_raw(url, title="Title A"), make_raw(url, title="Title B")]
    items = dedup(raw, "test-feed", set(), set(), [])
    assert len(items) == 2
    unique = [i for i in items if not i.is_duplicate]
    dupes = [i for i in items if i.is_duplicate]
    assert len(unique) == 1
    assert len(dupes) == 1


def test_dedup_tracking_param_normalization():
    url1 = "https://example.com/article?utm_source=google&utm_medium=cpc"
    url2 = "https://example.com/article?utm_campaign=spring"
    # Both should normalize to the same URL
    assert _url_hash(url1) == _url_hash(url2)


def test_dedup_sets_feed_id():
    raw = [make_raw("https://example.com/a")]
    items = dedup(raw, "my-feed", set(), set(), [])
    assert items[0].feed_id == "my-feed"


def test_dedup_sets_run_id():
    raw = [make_raw("https://example.com/a")]
    items = dedup(raw, "my-feed", set(), set(), [], run_id="run-123")
    assert items[0].run_id == "run-123"
