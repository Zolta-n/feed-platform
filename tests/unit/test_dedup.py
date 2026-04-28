from __future__ import annotations

from datetime import datetime, timezone

import pytest

from niche.core.models.types import RawItem
from niche.core.pipeline.dedup import dedup, _url_hash, _title_hash


def _raw(url: str, title: str, source_id: str = "src-1") -> RawItem:
    return RawItem(
        source_id=source_id,
        url=url,
        title=title,
        body="body text",
        language="en",
        published_at=None,
        fetched_at=datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# URL hash dedup
# ---------------------------------------------------------------------------

def test_url_hash_dedup_same_url():
    raw = [_raw("https://example.invalid/a", "Title A")]
    existing = {_url_hash("https://example.invalid/a")}
    items = dedup(raw, existing, set(), [], "feed1", "run1")
    assert items[0].is_duplicate


def test_url_hash_dedup_tracking_params_stripped():
    raw = [_raw("https://example.invalid/a?utm_source=twitter&utm_medium=social", "Title A")]
    existing = {_url_hash("https://example.invalid/a")}
    items = dedup(raw, existing, set(), [], "feed1", "run1")
    assert items[0].is_duplicate


def test_url_hash_no_false_positive():
    raw = [_raw("https://example.invalid/b", "Title B")]
    existing = {_url_hash("https://example.invalid/a")}
    items = dedup(raw, existing, set(), [], "feed1", "run1")
    assert not items[0].is_duplicate


def test_url_hash_dedup_within_batch():
    raw = [
        _raw("https://example.invalid/a", "Title A"),
        _raw("https://example.invalid/a?ref=feed", "Title A again"),
    ]
    items = dedup(raw, set(), set(), [], "feed1", "run1")
    assert not items[0].is_duplicate
    assert items[1].is_duplicate


# ---------------------------------------------------------------------------
# Title hash dedup
# ---------------------------------------------------------------------------

def test_title_hash_dedup_same_title_different_url():
    raw = [_raw("https://mirror.invalid/a", "Brake actuator study published")]
    existing_title_hashes = {_title_hash("Brake actuator study published")}
    items = dedup(raw, set(), existing_title_hashes, [], "feed1", "run1")
    assert items[0].is_duplicate


def test_title_hash_dedup_case_insensitive():
    raw = [_raw("https://mirror.invalid/a", "BRAKE ACTUATOR STUDY PUBLISHED")]
    existing_title_hashes = {_title_hash("brake actuator study published")}
    items = dedup(raw, set(), existing_title_hashes, [], "feed1", "run1")
    assert items[0].is_duplicate


def test_title_hash_no_false_positive():
    raw = [_raw("https://example.invalid/new", "A completely different headline")]
    existing_title_hashes = {_title_hash("Brake actuator study published")}
    items = dedup(raw, set(), existing_title_hashes, [], "feed1", "run1")
    assert not items[0].is_duplicate


def test_title_hash_dedup_within_batch():
    raw = [
        _raw("https://source1.invalid/a", "EV braking market outlook 2026"),
        _raw("https://source2.invalid/a", "EV braking market outlook 2026"),
    ]
    items = dedup(raw, set(), set(), [], "feed1", "run1")
    assert not items[0].is_duplicate
    assert items[1].is_duplicate


# ---------------------------------------------------------------------------
# Fuzzy title dedup
# ---------------------------------------------------------------------------

def test_fuzzy_dedup_near_duplicate():
    raw = [_raw("https://example.invalid/new", "Brake actuator reliability study is published")]
    recent_titles = ["Brake actuator reliability study published"]
    items = dedup(raw, set(), set(), recent_titles, "feed1", "run1")
    assert items[0].is_duplicate


def test_fuzzy_dedup_below_threshold():
    raw = [_raw("https://example.invalid/new", "Something completely unrelated")]
    recent_titles = ["Brake actuator reliability study published"]
    items = dedup(raw, set(), set(), recent_titles, "feed1", "run1")
    assert not items[0].is_duplicate


def test_fuzzy_dedup_within_batch():
    raw = [
        _raw("https://s1.invalid/a", "Tier-1 supplier secures new actuator contract"),
        _raw("https://s2.invalid/b", "Tier-1 supplier secures new actuator contracts"),  # near-dupe
    ]
    items = dedup(raw, set(), set(), [], "feed1", "run1")
    assert not items[0].is_duplicate
    assert items[1].is_duplicate


# ---------------------------------------------------------------------------
# Item field population
# ---------------------------------------------------------------------------

def test_items_have_correct_feed_id():
    raw = [_raw("https://example.invalid/a", "Some title")]
    items = dedup(raw, set(), set(), [], "my-feed", "run1")
    assert items[0].feed_id == "my-feed"


def test_title_hash_populated_on_item():
    raw = [_raw("https://example.invalid/a", "Some title")]
    items = dedup(raw, set(), set(), [], "feed1", "run1")
    assert items[0].title_hash == _title_hash("Some title")


def test_source_name_populated():
    raw = [_raw("https://example.invalid/a", "Title", source_id="src-42")]
    items = dedup(raw, set(), set(), [], "feed1", "run1", source_names={"src-42": "My Source"})
    assert items[0].source_name == "My Source"


def test_non_duplicate_not_flagged():
    raw = [_raw(f"https://example.invalid/{i}", f"Title {i}") for i in range(5)]
    items = dedup(raw, set(), set(), [], "feed1", "run1")
    assert all(not i.is_duplicate for i in items)


def test_twenty_items_known_pattern():
    """10 unique + 5 URL dupes + 5 title dupes = 20 items, 10 flagged."""
    unique = [_raw(f"https://u.invalid/{i}", f"Unique title {i}") for i in range(10)]
    url_dupes = [_raw(f"https://u.invalid/{i}", f"Different title for {i}") for i in range(5)]
    title_dupes = [_raw(f"https://t.invalid/{i}", f"Unique title {i}") for i in range(5)]

    all_raw = unique + url_dupes + title_dupes
    items = dedup(all_raw, set(), set(), [], "feed1", "run1")

    assert len(items) == 20
    duped = [i for i in items if i.is_duplicate]
    assert len(duped) == 10
