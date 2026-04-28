from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from niche.core.models.types import Item
from niche.core.pipeline.classify import (
    _classify_region,
    _classify_stub,
    _tag_companies,
    classify,
)


@pytest.fixture
def item(bundle) -> Item:
    now = datetime.now(timezone.utc)
    return Item(
        id="item-001",
        feed_id="test-fixture",
        url="https://example.com/article",
        url_hash="aabbcc",
        title_hash="ddeeff",
        title="New technology announcement from north region",
        title_translated=None,
        body_raw="Details about a northern technology development.",
        body_translated=None,
        summary=None,
        why_it_matters=None,
        source_id="stub-source-1",
        source_name="Stub Source",
        source_language="en",
        topic_tag=None,
        item_type=None,
        region_tag=None,
        company_tags=[],
        translation_failed=False,
        translation_provider=None,
        relevance_score=0.0,
        published_at=None,
        fetched_at=now,
        run_id="run-001",
        word_count=0,
        read_time_min=0.0,
        is_duplicate=False,
        duplicate_of=None,
    )


@pytest.fixture
def dup_item(item) -> Item:
    return replace(item, id="item-dup", is_duplicate=True)


def _make_usage(input_tokens=50, output_tokens=10, cache_read=200, cache_write=0):
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.cache_read_input_tokens = cache_read
    u.cache_creation_input_tokens = cache_write
    return u


def _make_response(text: str, usage=None):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = usage or _make_usage()
    return resp


# --- stub fallback ---

def test_stub_fallback_no_api_key(monkeypatch, item, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = classify([item], bundle)
    assert len(result) == 1
    assert result[0].topic_tag == bundle.taxonomy.topics[0].id
    assert result[0].item_type == bundle.taxonomy.item_types[0].id


def test_stub_excludes_duplicates(monkeypatch, dup_item, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = classify([dup_item], bundle)
    assert result == []


def test_classify_stub_directly(item, bundle):
    result = _classify_stub([item], bundle)
    assert len(result) == 1
    assert result[0].topic_tag == "technology"
    assert result[0].item_type == "brief"


# --- LLM path with mock ---

def test_classify_llm_sets_topic_and_type(monkeypatch, item, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    topic_resp = _make_response('{"topic": "technology"}')
    type_resp = _make_response('{"item_type": "deep"}')

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [topic_resp, type_resp]

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = classify([item], bundle)

    assert len(result) == 1
    assert result[0].topic_tag == "technology"
    assert result[0].item_type == "deep"


def test_classify_llm_unknown_topic_falls_back_to_none(monkeypatch, item, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    topic_resp = _make_response('{"topic": "nonexistent"}')
    type_resp = _make_response('{"item_type": "brief"}')

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [topic_resp, type_resp]

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = classify([item], bundle)

    assert result[0].topic_tag is None


def test_classify_llm_invalid_json_falls_back_to_none(monkeypatch, item, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    topic_resp = _make_response("not json at all")
    type_resp = _make_response('{"item_type": "brief"}')

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [topic_resp, type_resp]

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = classify([item], bundle)

    assert result[0].topic_tag is None


def test_classify_llm_records_cost(monkeypatch, item, bundle, repo):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    topic_resp = _make_response('{"topic": "technology"}', _make_usage(50, 10, 200, 0))
    type_resp = _make_response('{"item_type": "brief"}', _make_usage(30, 5, 100, 0))

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [topic_resp, type_resp]

    with patch("anthropic.Anthropic", return_value=mock_client):
        classify([item], bundle, repo, "run-001")

    total = repo.get_daily_cost_usd("test-fixture")
    assert total > 0


def test_classify_llm_excludes_duplicates(monkeypatch, dup_item, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_client = MagicMock()

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = classify([dup_item], bundle)

    assert result == []
    mock_client.messages.create.assert_not_called()


# --- pure helpers ---

def test_classify_region_north(item, bundle):
    region = _classify_region(item, bundle)
    assert region == "north"


def test_classify_region_no_match(item, bundle):
    item_no_region = replace(item, title="Generic article", body_raw="No location here.")
    region = _classify_region(item_no_region, bundle)
    assert region is None


def test_tag_companies_matches_name(bundle):
    now = datetime.now(timezone.utc)
    item = Item(
        id="x", feed_id="test-fixture", url="u", url_hash="h", title_hash="th",
        title="AcmeBrake announces new product",
        title_translated=None, body_raw="", body_translated=None,
        summary=None, why_it_matters=None,
        source_id="s", source_name="S", source_language="en",
        topic_tag=None, item_type=None, region_tag=None, company_tags=[],
        translation_failed=False, translation_provider=None,
        relevance_score=0.0, published_at=None, fetched_at=now,
        run_id="r", word_count=0, read_time_min=0.0,
        is_duplicate=False, duplicate_of=None,
    )
    tags = _tag_companies(item, bundle)
    assert "acme-brake" in tags


def test_tag_companies_matches_alias(bundle):
    now = datetime.now(timezone.utc)
    item = Item(
        id="x", feed_id="test-fixture", url="u", url_hash="h", title_hash="th",
        title="FT1 expands brake-by-wire operations",
        title_translated=None, body_raw="", body_translated=None,
        summary=None, why_it_matters=None,
        source_id="s", source_name="S", source_language="en",
        topic_tag=None, item_type=None, region_tag=None, company_tags=[],
        translation_failed=False, translation_provider=None,
        relevance_score=0.0, published_at=None, fetched_at=now,
        run_id="r", word_count=0, read_time_min=0.0,
        is_duplicate=False, duplicate_of=None,
    )
    tags = _tag_companies(item, bundle)
    assert "fake-tier1-co" in tags


def test_tag_companies_no_match(bundle):
    now = datetime.now(timezone.utc)
    item = Item(
        id="x", feed_id="test-fixture", url="u", url_hash="h", title_hash="th",
        title="Completely unrelated headline",
        title_translated=None, body_raw="No company names here.", body_translated=None,
        summary=None, why_it_matters=None,
        source_id="s", source_name="S", source_language="en",
        topic_tag=None, item_type=None, region_tag=None, company_tags=[],
        translation_failed=False, translation_provider=None,
        relevance_score=0.0, published_at=None, fetched_at=now,
        run_id="r", word_count=0, read_time_min=0.0,
        is_duplicate=False, duplicate_of=None,
    )
    tags = _tag_companies(item, bundle)
    assert tags == []


def test_tag_companies_multiple(bundle):
    now = datetime.now(timezone.utc)
    item = Item(
        id="x", feed_id="test-fixture", url="u", url_hash="h", title_hash="th",
        title="AcmeBrake partners with FakeTier1Co on new platform",
        title_translated=None, body_raw="", body_translated=None,
        summary=None, why_it_matters=None,
        source_id="s", source_name="S", source_language="en",
        topic_tag=None, item_type=None, region_tag=None, company_tags=[],
        translation_failed=False, translation_provider=None,
        relevance_score=0.0, published_at=None, fetched_at=now,
        run_id="r", word_count=0, read_time_min=0.0,
        is_duplicate=False, duplicate_of=None,
    )
    tags = _tag_companies(item, bundle)
    assert "acme-brake" in tags
    assert "fake-tier1-co" in tags
