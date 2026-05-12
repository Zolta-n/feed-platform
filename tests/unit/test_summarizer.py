from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from niche.core.models.types import Item
from niche.core.pipeline.summarize import _summarize_stub, summarize


@pytest.fixture
def item(bundle) -> Item:
    now = datetime.now(timezone.utc)
    return Item(
        id="s-001", feed_id="test-fixture", url="https://example.com/a",
        url_hash="hh", title_hash="th",
        title="Industry report on new actuator technology",
        title_translated=None,
        body_raw="A major supplier announced a new brake-by-wire actuator platform targeting OEM adoption by 2027.",
        body_translated=None, summary=None, why_it_matters=None,
        source_id="stub-source-1", source_name="Stub", source_language="en",
        topic_tag="technology", item_type="brief", region_tag=None, company_tags=[],
        translation_failed=False, translation_provider=None,
        relevance_score=1.0, published_at=None, fetched_at=now,
        run_id="run-001", word_count=0, read_time_min=0.0,
        is_duplicate=False, duplicate_of=None,
    )


def _make_usage(input_tokens=100, output_tokens=60, cache_read=400, cache_write=0):
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.cache_read_input_tokens = cache_read
    u.cache_creation_input_tokens = cache_write
    return u


def _make_response(text: str):
    r = MagicMock()
    r.content = [MagicMock(text=text)]
    r.usage = _make_usage()
    return r


# --- stub fallback ---

def test_stub_fallback_no_api_key(monkeypatch, item, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = summarize([item], bundle)
    assert len(result) == 1
    assert result[0].summary is not None
    assert result[0].why_it_matters is not None


def test_stub_sets_read_time_floor(monkeypatch, item, bundle):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = summarize([item], bundle)
    assert result[0].read_time_min >= 1.0


def test_stub_directly(item, bundle):
    result = _summarize_stub([item], bundle)
    assert len(result) == 1
    assert result[0].read_time_min >= 1.0


# --- LLM path ---

def test_llm_v2_shape_produces_json_bullets_and_takeaway(monkeypatch, item, bundle):
    """v2 prompt returns key_points + takeaway → stored as JSON list in summary, takeaway in why_it_matters."""
    import json as _json
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    resp = _make_response(
        '{"key_points": ["First key point about the deal.", '
        '"Second point with a number 42.", '
        '"Third point about timing."], '
        '"takeaway": "Tier-2 BBW suppliers should monitor this."}'
    )
    mock_client = MagicMock()
    mock_client.messages.create.return_value = resp

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = summarize([item], bundle)

    assert len(result) == 1
    bullets = _json.loads(result[0].summary)
    assert bullets == [
        "First key point about the deal.",
        "Second point with a number 42.",
        "Third point about timing.",
    ]
    assert result[0].why_it_matters == "Tier-2 BBW suppliers should monitor this."
    assert result[0].word_count > 0


def test_llm_v1_shape_backward_compat(monkeypatch, item, bundle):
    """Older {summary, why_it_matters} JSON still parses (kept for safety during migration)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    resp = _make_response('{"summary": "Two-sentence factual summary here.", "why_it_matters": "One sentence significance."}')
    mock_client = MagicMock()
    mock_client.messages.create.return_value = resp

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = summarize([item], bundle)

    assert len(result) == 1
    assert result[0].summary == "Two-sentence factual summary here."
    assert result[0].why_it_matters == "One sentence significance."


def test_read_time_floor_applied(monkeypatch, item, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Very short bullets → raw word_count / 200 < 1.0 → floor kicks in
    resp = _make_response('{"key_points": ["Short."], "takeaway": "Brief."}')
    mock_client = MagicMock()
    mock_client.messages.create.return_value = resp

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = summarize([item], bundle)

    assert result[0].read_time_min >= 1.0


def test_retry_on_bad_json(monkeypatch, item, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    bad = _make_response("not json at all")
    good = _make_response('{"key_points": ["Recovered point."], "takeaway": "It matters."}')
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [bad, good]

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = summarize([item], bundle)

    assert len(result) == 1
    import json as _json
    assert _json.loads(result[0].summary) == ["Recovered point."]
    assert mock_client.messages.create.call_count == 2


def test_both_attempts_fail_excludes_item(monkeypatch, item, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    bad = _make_response("unparseable")
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [bad, bad]

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = summarize([item], bundle)

    # Item excluded because summary could not be generated
    assert result == []


def test_records_cost_to_repo(monkeypatch, item, bundle, repo):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    resp = _make_response('{"key_points": ["Point."], "takeaway": "It matters."}')
    mock_client = MagicMock()
    mock_client.messages.create.return_value = resp

    with patch("anthropic.Anthropic", return_value=mock_client):
        summarize([item], bundle, repo, "run-001")

    assert repo.get_daily_cost_usd("test-fixture") > 0


def test_multiple_items_processed(monkeypatch, bundle):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    now = datetime.now(timezone.utc)
    items = []
    for i in range(3):
        items.append(Item(
            id=f"item-{i}", feed_id="test-fixture", url=f"https://ex.com/{i}",
            url_hash=f"h{i}", title_hash=f"t{i}", title=f"Title {i}",
            title_translated=None, body_raw=f"Body {i}", body_translated=None,
            summary=None, why_it_matters=None,
            source_id="stub-source-1", source_name="Stub", source_language="en",
            topic_tag="technology", item_type="brief", region_tag=None, company_tags=[],
            translation_failed=False, translation_provider=None,
            relevance_score=1.0, published_at=None, fetched_at=now,
            run_id="run-001", word_count=0, read_time_min=0.0,
            is_duplicate=False, duplicate_of=None,
        ))

    good = _make_response('{"key_points": ["Point one.", "Point two."], "takeaway": "Matters."}')
    mock_client = MagicMock()
    mock_client.messages.create.return_value = good

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = summarize(items, bundle)

    assert len(result) == 3
