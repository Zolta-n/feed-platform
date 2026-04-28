from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from niche.core.models.types import Item
from niche.core.pipeline.rank import rank
from niche.core.ranker.formula import score_item


def _make_item(
    idx: int = 0,
    topic_tag: str = "technology",
    company_tags: list[str] | None = None,
    source_id: str = "stub-source-1",
    published_at: datetime | None = None,
    title: str = "Generic article headline",
    body_raw: str = "",
) -> Item:
    now = datetime.now(timezone.utc)
    return Item(
        id=f"item-{idx}", feed_id="test-fixture", url=f"https://ex.com/{idx}",
        url_hash=f"h{idx}", title_hash=f"th{idx}", title=title,
        title_translated=None, body_raw=body_raw, body_translated=None,
        summary="Summary.", why_it_matters="Matters.",
        source_id=source_id, source_name="S", source_language="en",
        topic_tag=topic_tag, item_type="brief", region_tag=None,
        company_tags=company_tags or [],
        translation_failed=False, translation_provider=None,
        relevance_score=0.0, published_at=published_at, fetched_at=now,
        run_id="run-001", word_count=5, read_time_min=1.0,
        is_duplicate=False, duplicate_of=None,
    )


# --- score_item formula ---

def test_higher_source_weight_scores_higher():
    item = _make_item()
    s1 = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0)
    s2 = score_item(item, source_weight=2.0, topic_weight=1.0, company_boost=1.0)
    assert s2 > s1


def test_higher_topic_weight_scores_higher():
    item = _make_item()
    s1 = score_item(item, source_weight=1.0, topic_weight=0.5, company_boost=1.0)
    s2 = score_item(item, source_weight=1.0, topic_weight=2.0, company_boost=1.0)
    assert s2 > s1


def test_company_boost_elevates_score():
    item = _make_item()
    s1 = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0)
    s2 = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=2.0)
    assert s2 > s1


def test_thumbs_up_increases_score():
    item = _make_item()
    s_base = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0, thumbs_signal=0.0)
    s_up = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0, thumbs_signal=0.3)
    assert s_up > s_base


def test_thumbs_down_decreases_score():
    item = _make_item()
    s_base = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0, thumbs_signal=0.0)
    s_down = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0, thumbs_signal=-0.3)
    assert s_down < s_base


def test_keyword_block_returns_none():
    item = _make_item(title="Blocked keyword article", body_raw="contains forbidden term")
    result = score_item(
        item, source_weight=1.0, topic_weight=1.0, company_boost=1.0,
        keyword_blocks=["forbidden term"],
    )
    assert result is None


def test_keyword_block_no_match_returns_score():
    item = _make_item(title="Normal article")
    result = score_item(
        item, source_weight=1.0, topic_weight=1.0, company_boost=1.0,
        keyword_blocks=["forbidden"],
    )
    assert result is not None


def test_keyword_boost_factor_elevates():
    item = _make_item()
    s1 = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0, keyword_boost_factor=1.0)
    s2 = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0, keyword_boost_factor=2.0)
    assert s2 == pytest.approx(s1 * 2.0, rel=1e-6)


def test_recent_item_scores_higher_than_old():
    now = datetime.now(timezone.utc)
    recent = _make_item(published_at=now - timedelta(hours=1))
    old = _make_item(published_at=now - timedelta(days=7))
    s_recent = score_item(recent, source_weight=1.0, topic_weight=1.0, company_boost=1.0)
    s_old = score_item(old, source_weight=1.0, topic_weight=1.0, company_boost=1.0)
    assert s_recent > s_old


def test_no_published_at_uses_fallback():
    item = _make_item(published_at=None)
    result = score_item(item, source_weight=1.0, topic_weight=1.0, company_boost=1.0)
    assert result is not None
    assert result >= 0.0


def test_score_never_negative():
    item = _make_item()
    result = score_item(
        item, source_weight=1.0, topic_weight=1.0, company_boost=1.0, thumbs_signal=-0.5
    )
    assert result >= 0.0


# --- rank() integration ---

def test_rank_sorts_descending(bundle):
    now = datetime.now(timezone.utc)
    items = [
        _make_item(idx=0, source_id="stub-source-1", published_at=now - timedelta(days=2)),
        _make_item(idx=1, source_id="stub-source-1", published_at=now - timedelta(hours=1)),
    ]
    result = rank(items, bundle)
    # More recent item should rank higher (all else equal)
    assert result[0].published_at > result[1].published_at


def test_rank_keyword_block_removes_item(bundle):
    item_ok = _make_item(idx=0, title="Normal headline")
    item_blocked = _make_item(idx=1, title="Blocked content here", body_raw="some blocked stuff")
    prefs = {"keyword_blocks": ["blocked content"]}
    result = rank([item_ok, item_blocked], bundle, preferences=prefs)
    ids = [i.id for i in result]
    assert "item-0" in ids
    assert "item-1" not in ids


def test_rank_company_boost_elevates_item(bundle):
    now = datetime.now(timezone.utc)
    item_no_company = _make_item(idx=0, company_tags=[], published_at=now)
    item_with_company = _make_item(idx=1, company_tags=["acme-brake"], published_at=now)
    result = rank([item_no_company, item_with_company], bundle)
    # acme-brake has boost=1.5 in test-fixture watchlist
    assert result[0].id == "item-1"


def test_rank_sets_relevance_score(bundle):
    item = _make_item()
    result = rank([item], bundle)
    assert result[0].relevance_score > 0.0


def test_rank_empty_list(bundle):
    assert rank([], bundle) == []
