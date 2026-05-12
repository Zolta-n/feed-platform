from __future__ import annotations

import re
from datetime import datetime, timezone

from niche.core.models.types import FiltersConfig, FiltersRule, RawItem
from niche.core.pipeline.filter_relevance import filter_relevance


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
