from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from niche.core.models.types import Item
from niche.core.pipeline.cluster import cluster


def _make_item(
    idx: int,
    topic_tag: str | None,
    company_tags: list[str] | None = None,
    relevance_score: float = 1.0,
) -> Item:
    now = datetime.now(timezone.utc)
    return Item(
        id=f"c-{idx}", feed_id="test-fixture", url=f"https://ex.com/{idx}",
        url_hash=f"h{idx}", title_hash=f"th{idx}", title=f"Article {idx}",
        title_translated=None, body_raw="", body_translated=None,
        summary=f"Summary {idx}.", why_it_matters="Matters.",
        source_id="src", source_name="S", source_language="en",
        topic_tag=topic_tag, item_type="brief", region_tag=None,
        company_tags=company_tags or [],
        translation_failed=False, translation_provider=None,
        relevance_score=relevance_score, published_at=None,
        fetched_at=now, run_id="run-001", word_count=5, read_time_min=1.0,
        is_duplicate=False, duplicate_of=None,
    )


# --- rule-based grouping ---

def test_same_topic_same_company_cluster_together(monkeypatch, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    items = [
        _make_item(0, "technology", ["acme-brake"]),
        _make_item(1, "technology", ["acme-brake"]),
        _make_item(2, "market", []),
        _make_item(3, "market", []),
    ]
    clusters = cluster(items, bundle)
    # technology+acme-brake items should be in the same cluster
    tech_acme_cluster = next(
        c for c in clusters if "c-0" in c.item_ids and "c-1" in c.item_ids
    )
    assert tech_acme_cluster is not None


def test_different_topics_go_to_different_clusters(monkeypatch, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    items = [
        _make_item(0, "technology", []),
        _make_item(1, "technology", []),
        _make_item(2, "market", []),
        _make_item(3, "market", []),
    ]
    clusters = cluster(items, bundle)
    # c-0 and c-2 must not be in the same cluster
    for c in clusters:
        assert not ("c-0" in c.item_ids and "c-2" in c.item_ids)


def test_singleton_merged_into_catchall(monkeypatch, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    items = [
        _make_item(0, "technology", []),
        _make_item(1, "technology", []),
        _make_item(2, "market", []),  # singleton topic → catch-all
    ]
    clusters = cluster(items, bundle)
    all_item_ids = [iid for c in clusters for iid in c.item_ids]
    # all items must appear somewhere
    assert set(all_item_ids) == {"c-0", "c-1", "c-2"}


def test_cluster_count_within_target(monkeypatch, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    items = [_make_item(i, "technology" if i % 2 == 0 else "market") for i in range(20)]
    clusters = cluster(items, bundle)
    assert 1 <= len(clusters) <= 5


def test_empty_list_returns_empty(monkeypatch, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cluster([], bundle) == []


def test_clusters_ordered_by_relevance(monkeypatch, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    items = [
        _make_item(0, "technology", [], relevance_score=0.5),
        _make_item(1, "technology", [], relevance_score=0.5),
        _make_item(2, "market", [], relevance_score=2.0),
        _make_item(3, "market", [], relevance_score=2.0),
    ]
    clusters = cluster(items, bundle)
    # First cluster should contain the high-relevance market items
    assert clusters[0].item_ids[0] in {"c-2", "c-3"}


def test_all_item_ids_present(monkeypatch, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    items = [_make_item(i, "technology") for i in range(6)]
    clusters = cluster(items, bundle)
    all_ids = {iid for c in clusters for iid in c.item_ids}
    expected_ids = {f"c-{i}" for i in range(6)}
    assert all_ids == expected_ids


# --- Sonnet label path ---

def test_sonnet_labels_used_when_api_key_set(monkeypatch, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    items = [
        _make_item(0, "technology", []),
        _make_item(1, "technology", []),
        _make_item(2, "market", []),
        _make_item(3, "market", []),
    ]
    sonnet_resp = MagicMock()
    sonnet_resp.content = [MagicMock(text='{"labels": ["Tech Trends", "Market Moves"]}')]
    sonnet_resp.usage = MagicMock(
        input_tokens=200, output_tokens=30,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = sonnet_resp

    with patch("anthropic.Anthropic", return_value=mock_client):
        clusters = cluster(items, bundle)

    labels = {c.label for c in clusters}
    assert "Tech Trends" in labels or "Market Moves" in labels


def test_sonnet_failure_falls_back_to_topic_label(monkeypatch, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    items = [
        _make_item(0, "technology", []),
        _make_item(1, "technology", []),
    ]
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Sonnet unavailable")

    with patch("anthropic.Anthropic", return_value=mock_client):
        clusters = cluster(items, bundle)

    # Label should be the topic_tag value (fallback)
    assert any("technology" in c.label.lower() for c in clusters)
