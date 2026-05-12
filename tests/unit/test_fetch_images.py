from __future__ import annotations

from datetime import datetime, timezone

import pytest

from niche.core.models.types import Item
from niche.core.pipeline.fetch_images import (
    _absolutize,
    _extract_og_image,
    fetch_og_images,
)


def _item(image_url: str | None = None, url: str = "https://example.com/a") -> Item:
    return Item(
        id="i1", feed_id="f1", url=url, url_hash="h", title_hash="th",
        title="T", title_translated=None, body_raw="B", body_translated=None,
        summary=None, why_it_matters=None,
        source_id="s1", source_name="s1", source_language="en",
        topic_tag=None, item_type=None, region_tag=None, company_tags=[],
        translation_failed=False, translation_provider=None,
        relevance_score=0.0, published_at=None,
        fetched_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        run_id="r1", word_count=0, read_time_min=0.0,
        is_duplicate=False, duplicate_of=None, image_url=image_url,
    )


# --- _extract_og_image ---

def test_extracts_og_image():
    html = '<html><head><meta property="og:image" content="https://cdn.example.com/x.jpg"></head></html>'
    assert _extract_og_image(html, "https://example.com/a") == "https://cdn.example.com/x.jpg"


def test_falls_back_to_twitter_image_when_no_og_image():
    html = '<html><head><meta name="twitter:image" content="https://cdn.example.com/tw.jpg"></head></html>'
    assert _extract_og_image(html, "https://example.com/a") == "https://cdn.example.com/tw.jpg"


def test_og_image_preferred_over_twitter_image():
    html = """<html><head>
      <meta property="og:image" content="https://cdn.example.com/og.jpg">
      <meta name="twitter:image" content="https://cdn.example.com/tw.jpg">
    </head></html>"""
    assert _extract_og_image(html, "https://example.com/a") == "https://cdn.example.com/og.jpg"


def test_returns_none_when_no_image_meta():
    html = '<html><head><title>No image here</title></head></html>'
    assert _extract_og_image(html, "https://example.com/a") is None


def test_resolves_relative_image_url():
    html = '<html><head><meta property="og:image" content="/static/hero.jpg"></head></html>'
    assert _extract_og_image(html, "https://example.com/articles/123") == "https://example.com/static/hero.jpg"


def test_resolves_protocol_relative_image_url():
    html = '<html><head><meta property="og:image" content="//cdn.example.com/hero.jpg"></head></html>'
    assert _extract_og_image(html, "https://example.com/articles/123") == "https://cdn.example.com/hero.jpg"


def test_og_image_url_alias_works():
    """Some sites use og:image:url instead of og:image."""
    html = '<html><head><meta property="og:image:url" content="https://cdn.example.com/x.jpg"></head></html>'
    assert _extract_og_image(html, "https://example.com/a") == "https://cdn.example.com/x.jpg"


def test_malformed_html_returns_none():
    # BeautifulSoup is forgiving; this should still parse cleanly to None
    assert _extract_og_image("<<>not really html<<", "https://example.com/a") is None


def test_empty_content_attribute_returns_none():
    html = '<html><head><meta property="og:image" content=""></head></html>'
    assert _extract_og_image(html, "https://example.com/a") is None


# --- _absolutize ---

def test_absolutize_passes_through_absolute_url():
    assert _absolutize("https://cdn.example.com/x.jpg", "https://example.com/") == "https://cdn.example.com/x.jpg"


def test_absolutize_resolves_relative():
    assert _absolutize("/x.jpg", "https://example.com/foo/bar") == "https://example.com/x.jpg"


def test_absolutize_drops_non_http_schemes():
    """data:, javascript:, etc. should be rejected."""
    assert _absolutize("data:image/png;base64,...", "https://example.com/") is None
    assert _absolutize("javascript:void(0)", "https://example.com/") is None


# --- fetch_og_images ---

def test_skips_items_that_already_have_image_url(monkeypatch):
    """Items with image_url=set should pass through untouched, no HTTP fetched."""
    item = _item(image_url="https://existing.example.com/img.jpg")
    # If anything tried to make an HTTP call, the test would slow down — assert no calls instead.
    called = []
    monkeypatch.setattr(
        "niche.core.pipeline.fetch_images._fetch_one",
        lambda url: called.append(url) or None,
    )
    result = fetch_og_images([item])
    assert result[0].image_url == "https://existing.example.com/img.jpg"
    assert called == []


def test_populates_image_url_from_fetch(monkeypatch):
    item = _item(image_url=None, url="https://news.example.com/articles/abc")
    monkeypatch.setattr(
        "niche.core.pipeline.fetch_images._fetch_one",
        lambda url: "https://cdn.example.com/abc.jpg",
    )
    result = fetch_og_images([item])
    assert result[0].image_url == "https://cdn.example.com/abc.jpg"


def test_failed_fetches_leave_image_url_none(monkeypatch):
    item = _item(image_url=None, url="https://broken.example.com/a")
    monkeypatch.setattr(
        "niche.core.pipeline.fetch_images._fetch_one",
        lambda url: None,
    )
    result = fetch_og_images([item])
    assert result[0].image_url is None


def test_empty_list_returns_empty():
    assert fetch_og_images([]) == []


def test_exception_in_fetch_is_swallowed(monkeypatch):
    """A raised exception during fetch must not break the pipeline."""
    item = _item(image_url=None)

    def boom(url):
        raise RuntimeError("network melted")

    monkeypatch.setattr("niche.core.pipeline.fetch_images._fetch_one", boom)
    result = fetch_og_images([item])
    assert result[0].image_url is None
