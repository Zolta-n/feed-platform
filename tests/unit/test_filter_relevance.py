from __future__ import annotations

import re
from datetime import datetime, timezone

from niche.core.models.types import FiltersConfig, FiltersRule, Item, RawItem
from niche.core.pipeline.filter_relevance import filter_items, filter_relevance


def _raw(title: str, body: str = "") -> RawItem:
    return RawItem(
        source_id="src-1",
        url="https://example.invalid/a",
        title=title,
        body=body,
        language="en",
        published_at=None,
        fetched_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
    )


def _rule(phrases: list[str], match_fields: list[str]) -> FiltersRule:
    compiled = tuple(re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE) for p in phrases)
    return FiltersRule(
        phrases=tuple(phrases),
        match_fields=tuple(match_fields),
        compiled=compiled,
    )


def test_no_filters_returns_input_unchanged():
    items = [_raw("anything")]
    survivors, stats = filter_relevance(items, None)
    assert survivors == items
    assert stats == {}


def test_empty_filter_config_is_noop():
    cfg = FiltersConfig(block=None, require_any=None)
    items = [_raw("anything")]
    survivors, stats = filter_relevance(items, cfg)
    assert survivors == items
    assert stats == {}


def test_block_drops_matching_item():
    cfg = FiltersConfig(
        block=_rule(["transit bus"], ["title"]),
        require_any=None,
    )
    items = [
        _raw("New transit bus brake system"),
        _raw("Passenger car brake recall"),
    ]
    survivors, stats = filter_relevance(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].title == "Passenger car brake recall"
    assert stats["blocked"] == 1
    assert stats["require_missed"] == 0


def test_require_any_drops_when_no_phrase_matches():
    cfg = FiltersConfig(
        block=None,
        require_any=_rule(["brake", "ABS"], ["title", "body"]),
    )
    items = [
        _raw("Tariffs hit Toyota profit", "Financial news about earnings"),
        _raw("New brake actuator", "details"),
    ]
    survivors, stats = filter_relevance(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].title == "New brake actuator"
    assert stats["require_missed"] == 1


def test_word_boundary_prevents_substring_false_positive():
    """'bus' must not match 'business' or 'robust'."""
    cfg = FiltersConfig(
        block=_rule(["bus"], ["title"]),
        require_any=None,
    )
    items = [
        _raw("Robust business model for brake suppliers"),
        _raw("New transit bus contract"),
    ]
    survivors, stats = filter_relevance(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].title == "Robust business model for brake suppliers"
    assert stats["blocked"] == 1


def test_case_insensitive_matching():
    cfg = FiltersConfig(
        block=None,
        require_any=_rule(["ABS"], ["title", "body"]),
    )
    items = [
        _raw("New braking tech", "abs system upgrade"),
        _raw("Unrelated news", "no relevant terms here"),
    ]
    survivors, stats = filter_relevance(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].title == "New braking tech"


def test_block_match_fields_title_only_ignores_body():
    cfg = FiltersConfig(
        block=_rule(["truck"], ["title"]),
        require_any=None,
    )
    items = [
        _raw("Passenger car brake test", "compared against a truck system"),
        _raw("Heavy truck brake article", "body"),
    ]
    survivors, stats = filter_relevance(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].title == "Passenger car brake test"
    assert stats["blocked"] == 1


def test_require_match_fields_title_and_body():
    cfg = FiltersConfig(
        block=None,
        require_any=_rule(["brake"], ["title", "body"]),
    )
    items = [
        _raw("Tier-1 announcement", "details about brake actuator production"),
        _raw("Tier-1 announcement", "details about plant expansion"),
    ]
    survivors, stats = filter_relevance(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].body == "details about brake actuator production"
    assert stats["require_missed"] == 1


def test_block_wins_over_require():
    cfg = FiltersConfig(
        block=_rule(["transit bus"], ["title"]),
        require_any=_rule(["brake"], ["title", "body"]),
    )
    item = _raw("New transit bus brake design")
    survivors, stats = filter_relevance([item], cfg)
    assert survivors == []
    assert stats["blocked"] == 1
    assert stats["require_missed"] == 0


def test_sample_cap_at_20_per_rule():
    cfg = FiltersConfig(
        block=_rule(["motorcycle"], ["title"]),
        require_any=None,
    )
    items = [_raw(f"motorcycle review {i}") for i in range(30)]
    survivors, stats = filter_relevance(items, cfg)
    assert survivors == []
    assert stats["blocked"] == 30
    assert len([s for s in stats["samples"] if s["rule"] == "block"]) == 20


def test_stats_sample_shape():
    cfg = FiltersConfig(
        block=_rule(["lorry"], ["title"]),
        require_any=_rule(["brake"], ["title", "body"]),
    )
    items = [
        _raw("Big lorry shipment"),
        _raw("Random unrelated news"),
        _raw("Brake update"),
    ]
    survivors, stats = filter_relevance(items, cfg)
    assert len(survivors) == 1
    block_samples = [s for s in stats["samples"] if s["rule"] == "block"]
    req_samples = [s for s in stats["samples"] if s["rule"] == "require_missed"]
    assert block_samples[0] == {"title": "Big lorry shipment", "matched": "lorry", "rule": "block"}
    assert req_samples[0] == {"title": "Random unrelated news", "matched": None, "rule": "require_missed"}


# ---------------------------------------------------------------------------
# filter_items — post-translate path used by the rolling pool merge
# ---------------------------------------------------------------------------

def _item(
    title: str = "",
    title_translated: str | None = None,
    body_raw: str = "",
    body_translated: str | None = None,
) -> Item:
    return Item(
        id="item-1",
        feed_id="feed",
        url="https://example.invalid/x",
        url_hash="h1",
        title_hash="h2",
        title=title,
        title_translated=title_translated,
        body_raw=body_raw,
        body_translated=body_translated,
        summary=None,
        why_it_matters=None,
        source_id="src-1",
        source_name="Src",
        source_language="en",
        topic_tag=None,
        item_type=None,
        region_tag=None,
        company_tags=[],
        translation_failed=False,
        translation_provider=None,
        relevance_score=0.0,
        published_at=None,
        fetched_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
        run_id="run-1",
        word_count=0,
        read_time_min=0.0,
        is_duplicate=False,
        duplicate_of=None,
    )


def test_filter_items_uses_title_translated_when_set():
    cfg = FiltersConfig(
        block=None,
        require_any=_rule(["brake"], ["title", "body"]),
    )
    items = [
        _item(title="China meldet E-Auto-Wachstum", title_translated="China reports EV growth"),
        _item(title="Etwas anderes", title_translated="Brake actuator news"),
    ]
    survivors, stats = filter_items(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].title_translated == "Brake actuator news"
    assert stats["require_missed"] == 1


def test_filter_items_uses_body_translated_when_set():
    cfg = FiltersConfig(
        block=None,
        require_any=_rule(["brake"], ["title", "body"]),
    )
    items = [
        _item(
            title="Original",
            title_translated="Tier-1 announcement",
            body_raw="original body without brake",
            body_translated="details about brake actuator",
        ),
        _item(
            title="X", title_translated="Tier-1 update",
            body_raw="original mentions brake", body_translated="translated body, no relevant term",
        ),
    ]
    survivors, stats = filter_items(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].body_translated == "details about brake actuator"


def test_filter_items_falls_back_to_title_when_no_translation():
    cfg = FiltersConfig(
        block=None,
        require_any=_rule(["brake"], ["title", "body"]),
    )
    items = [
        _item(title="Brake recall report", title_translated=None),
        _item(title="Other news", title_translated=None),
    ]
    survivors, _ = filter_items(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].title == "Brake recall report"


def test_filter_items_no_filters_returns_unchanged():
    items = [_item(title="anything")]
    survivors, stats = filter_items(items, None)
    assert survivors == items
    assert stats == {}


def test_filter_items_block_uses_translated_title():
    cfg = FiltersConfig(
        block=_rule(["transit bus"], ["title"]),
        require_any=None,
    )
    items = [
        _item(title="Linienbus Bremstest", title_translated="New transit bus brake test"),
        _item(title="PKW-Bremsen", title_translated="Passenger car brake recall"),
    ]
    survivors, stats = filter_items(items, cfg)
    assert len(survivors) == 1
    assert survivors[0].title_translated == "Passenger car brake recall"
    assert stats["blocked"] == 1


def test_filter_items_block_wins_over_require():
    cfg = FiltersConfig(
        block=_rule(["transit bus"], ["title"]),
        require_any=_rule(["brake"], ["title", "body"]),
    )
    item = _item(title_translated="New transit bus brake system")
    survivors, stats = filter_items([item], cfg)
    assert survivors == []
    assert stats["blocked"] == 1
