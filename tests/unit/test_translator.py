from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from niche.core.models.types import Item
from niche.core.pipeline.translate import translate


def _make_item(lang: str = "en", idx: int = 0) -> Item:
    now = datetime.now(timezone.utc)
    return Item(
        id=f"t-{idx}", feed_id="test-fixture", url=f"https://ex.com/{idx}",
        url_hash=f"h{idx}", title_hash=f"th{idx}",
        title="Aktuelle Meldung" if lang != "en" else "Current news",
        title_translated=None,
        body_raw="Körper des Artikels." if lang != "en" else "Article body.",
        body_translated=None, summary=None, why_it_matters=None,
        source_id="src", source_name="S", source_language=lang,
        topic_tag=None, item_type=None, region_tag=None, company_tags=[],
        translation_failed=False, translation_provider=None,
        relevance_score=0.0, published_at=None, fetched_at=now,
        run_id="run-001", word_count=0, read_time_min=0.0,
        is_duplicate=False, duplicate_of=None,
    )


def _make_deepl_result(text: str):
    r = MagicMock()
    r.text = text
    return r


def _make_haiku_usage():
    u = MagicMock()
    u.input_tokens = 80
    u.output_tokens = 30
    u.cache_read_input_tokens = 0
    u.cache_creation_input_tokens = 0
    return u


# --- English passthrough ---

def test_english_items_are_not_translated(monkeypatch, bundle):
    monkeypatch.setenv("DEEPL_API_KEY", "deepl-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-key")
    item = _make_item("en")
    mock_deepl = MagicMock()

    with patch("deepl.Translator", return_value=mock_deepl):
        result = translate([item], bundle)

    assert len(result) == 1
    assert result[0].translation_provider is None
    mock_deepl.translate_text.assert_not_called()


def test_mixed_list_english_passthrough(monkeypatch, bundle):
    monkeypatch.setenv("DEEPL_API_KEY", "deepl-key")
    en_item = _make_item("en", idx=0)
    de_item = _make_item("de", idx=1)

    mock_deepl = MagicMock()
    mock_deepl.translate_text.return_value = [
        _make_deepl_result("Translated title"),
        _make_deepl_result("Translated body"),
    ]

    with patch("deepl.Translator", return_value=mock_deepl):
        result = translate([en_item, de_item], bundle)

    assert len(result) == 2
    en_result = next(r for r in result if r.id == "t-0")
    de_result = next(r for r in result if r.id == "t-1")
    assert en_result.translation_provider is None
    assert de_result.translation_provider == "deepl"


# --- DeepL success ---

def test_deepl_translates_non_english(monkeypatch, bundle):
    monkeypatch.setenv("DEEPL_API_KEY", "deepl-key")
    item = _make_item("de")

    mock_deepl = MagicMock()
    mock_deepl.translate_text.return_value = [
        _make_deepl_result("Current news title"),
        _make_deepl_result("Current article body."),
    ]

    with patch("deepl.Translator", return_value=mock_deepl):
        result = translate([item], bundle)

    assert len(result) == 1
    assert result[0].title_translated == "Current news title"
    assert result[0].body_translated == "Current article body."
    assert result[0].translation_provider == "deepl"
    assert not result[0].translation_failed


# --- DeepL failure → Haiku fallback ---

def test_deepl_failure_falls_back_to_haiku(monkeypatch, bundle):
    monkeypatch.setenv("DEEPL_API_KEY", "deepl-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-key")
    item = _make_item("de")

    mock_deepl = MagicMock()
    mock_deepl.translate_text.side_effect = Exception("DeepL quota exceeded")

    haiku_resp = MagicMock()
    haiku_resp.content = [MagicMock(text='{"title": "Haiku title", "body": "Haiku body."}')]
    haiku_resp.usage = _make_haiku_usage()
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create.return_value = haiku_resp

    with patch("deepl.Translator", return_value=mock_deepl):
        with patch("anthropic.Anthropic", return_value=mock_anthropic):
            result = translate([item], bundle)

    assert result[0].translation_provider == "haiku"
    assert result[0].title_translated == "Haiku title"
    assert not result[0].translation_failed


def test_no_deepl_key_falls_back_to_haiku(monkeypatch, bundle):
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-key")
    item = _make_item("de")

    haiku_resp = MagicMock()
    haiku_resp.content = [MagicMock(text='{"title": "Haiku title", "body": "Haiku body."}')]
    haiku_resp.usage = _make_haiku_usage()
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create.return_value = haiku_resp

    with patch("anthropic.Anthropic", return_value=mock_anthropic):
        result = translate([item], bundle)

    assert result[0].translation_provider == "haiku"


# --- Both fail ---

def test_both_fail_marks_translation_failed(monkeypatch, bundle):
    monkeypatch.setenv("DEEPL_API_KEY", "deepl-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-key")
    item = _make_item("de")

    mock_deepl = MagicMock()
    mock_deepl.translate_text.side_effect = Exception("network error")

    haiku_resp = MagicMock()
    haiku_resp.content = [MagicMock(text="not valid json")]
    haiku_resp.usage = _make_haiku_usage()
    mock_anthropic = MagicMock()
    mock_anthropic.messages.create.return_value = haiku_resp

    with patch("deepl.Translator", return_value=mock_deepl):
        with patch("anthropic.Anthropic", return_value=mock_anthropic):
            result = translate([item], bundle)

    assert result[0].translation_failed is True
    assert result[0].translation_provider is None


def test_no_keys_marks_translation_failed(monkeypatch, bundle):
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    item = _make_item("de")

    result = translate([item], bundle)

    assert result[0].translation_failed is True
