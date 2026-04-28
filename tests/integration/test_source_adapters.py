from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from niche.core.models.types import SourceConfig

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def _source_cfg(source_type: str, url: str = "https://stub.invalid/feed", **kwargs) -> SourceConfig:
    return SourceConfig(
        id=f"test-{source_type}",
        feed_id="test-fixture",
        source_type=source_type,
        url=url,
        name=f"Test {source_type}",
        default_region=None,
        default_topic=None,
        source_weight=1.0,
        enabled=True,
        item_selector=kwargs.get("item_selector"),
        title_selector=kwargs.get("title_selector"),
        link_selector=kwargs.get("link_selector"),
        date_selector=kwargs.get("date_selector"),
    )


def _mock_repo():
    repo = MagicMock()
    repo.update_source_health = MagicMock()
    return repo


def _http_response(text: str, status_code: int = 200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# RSSSource
# ---------------------------------------------------------------------------

class TestRSSSource:
    def test_happy_path_returns_items(self):
        from niche.core.sources.rss import RSSSource

        xml = open(os.path.join(FIXTURES, "rss_sample.xml")).read()
        repo = _mock_repo()
        source = RSSSource(_source_cfg("rss"), repo)

        with patch("httpx.get", return_value=_http_response(xml)):
            items = source.fetch()

        assert len(items) == 3
        assert all(i.url.startswith("https://rss.stub.invalid") for i in items)
        assert all(i.source_id == "test-rss" for i in items)
        repo.update_source_health.assert_called_once_with(
            "test-rss", "test-fixture", success=True, error_message=None
        )

    def test_failure_returns_empty_and_updates_health(self):
        from niche.core.sources.rss import RSSSource
        import httpx

        repo = _mock_repo()
        source = RSSSource(_source_cfg("rss"), repo, sleep_fn=lambda _: None)

        with patch("httpx.get", side_effect=httpx.RequestError("connection refused")):
            items = source.fetch()

        assert items == []
        call = repo.update_source_health.call_args
        assert call.kwargs["success"] is False
        assert call.kwargs["error_message"] is not None

    def test_retry_succeeds_on_third_attempt(self):
        from niche.core.sources.rss import RSSSource
        import httpx

        xml = open(os.path.join(FIXTURES, "rss_sample.xml")).read()
        repo = _mock_repo()
        source = RSSSource(_source_cfg("rss"), repo, sleep_fn=lambda _: None)

        side_effects = [
            httpx.RequestError("attempt 1"),
            httpx.RequestError("attempt 2"),
            _http_response(xml),
        ]
        with patch("httpx.get", side_effect=side_effects):
            items = source.fetch()

        assert len(items) == 3
        repo.update_source_health.assert_called_once_with(
            "test-rss", "test-fixture", success=True, error_message=None
        )


# ---------------------------------------------------------------------------
# GoogleNewsSource
# ---------------------------------------------------------------------------

class TestGoogleNewsSource:
    def test_happy_path_returns_items(self):
        from niche.core.sources.google_news import GoogleNewsSource

        xml = open(os.path.join(FIXTURES, "google_news_sample.xml")).read()
        repo = _mock_repo()
        source = GoogleNewsSource(_source_cfg("google_news"), repo)

        with patch("httpx.get", return_value=_http_response(xml)):
            items = source.fetch()

        assert len(items) == 3
        assert all(i.source_id == "test-google_news" for i in items)
        repo.update_source_health.assert_called_once_with(
            "test-google_news", "test-fixture", success=True, error_message=None
        )

    def test_failure_returns_empty(self):
        from niche.core.sources.google_news import GoogleNewsSource
        import httpx

        repo = _mock_repo()
        source = GoogleNewsSource(_source_cfg("google_news"), repo, sleep_fn=lambda _: None)

        with patch("httpx.get", side_effect=httpx.RequestError("timeout")):
            items = source.fetch()

        assert items == []
        assert repo.update_source_health.call_args.kwargs["success"] is False


# ---------------------------------------------------------------------------
# RegulatorySource
# ---------------------------------------------------------------------------

class TestRegulatorySource:
    def test_happy_path_returns_items(self):
        from niche.core.sources.regulatory import RegulatorySource

        xml = open(os.path.join(FIXTURES, "regulatory_sample.xml")).read()
        repo = _mock_repo()
        source = RegulatorySource(_source_cfg("regulatory"), repo)

        with patch("httpx.get", return_value=_http_response(xml)):
            items = source.fetch()

        assert len(items) == 2
        assert all(i.source_id == "test-regulatory" for i in items)

    def test_failure_returns_empty(self):
        from niche.core.sources.regulatory import RegulatorySource
        import httpx

        repo = _mock_repo()
        source = RegulatorySource(_source_cfg("regulatory"), repo, sleep_fn=lambda _: None)

        with patch("httpx.get", side_effect=httpx.RequestError("timeout")):
            items = source.fetch()

        assert items == []


# ---------------------------------------------------------------------------
# GDELTSource
# ---------------------------------------------------------------------------

class TestGDELTSource:
    def test_happy_path_returns_items(self):
        from niche.core.sources.gdelt import GDELTSource

        payload = open(os.path.join(FIXTURES, "gdelt_sample.json")).read()
        repo = _mock_repo()
        source = GDELTSource(_source_cfg("gdelt"), repo)

        with patch("httpx.get", return_value=_http_response(payload)):
            items = source.fetch()

        assert len(items) == 3
        assert all(i.source_id == "test-gdelt" for i in items)
        repo.update_source_health.assert_called_once_with(
            "test-gdelt", "test-fixture", success=True, error_message=None
        )

    def test_failure_returns_empty(self):
        from niche.core.sources.gdelt import GDELTSource
        import httpx

        repo = _mock_repo()
        source = GDELTSource(_source_cfg("gdelt"), repo, sleep_fn=lambda _: None)

        with patch("httpx.get", side_effect=httpx.RequestError("timeout")):
            items = source.fetch()

        assert items == []


# ---------------------------------------------------------------------------
# ScraperSource
# ---------------------------------------------------------------------------

class TestScraperSource:
    def test_happy_path_returns_items(self):
        from niche.core.sources.scraper import ScraperSource

        html = open(os.path.join(FIXTURES, "scraper_sample.html")).read()
        repo = _mock_repo()
        cfg = _source_cfg(
            "scraper",
            url="https://scraper.stub.invalid/press",
            item_selector="article.press-item",
            title_selector=".press-title",
            link_selector=".press-link",
            date_selector=".press-date",
        )
        source = ScraperSource(cfg, repo)

        with patch("httpx.get", return_value=_http_response(html)):
            items = source.fetch()

        assert len(items) == 3
        assert items[0].url == "https://scraper.stub.invalid/press/1"
        assert "joint venture" in items[0].title.lower()

    def test_failure_returns_empty(self):
        from niche.core.sources.scraper import ScraperSource
        import httpx

        repo = _mock_repo()
        cfg = _source_cfg(
            "scraper",
            item_selector="article.press-item",
            title_selector=".press-title",
            link_selector=".press-link",
        )
        source = ScraperSource(cfg, repo, sleep_fn=lambda _: None)

        with patch("httpx.get", side_effect=httpx.RequestError("timeout")):
            items = source.fetch()

        assert items == []

    def test_missing_selectors_returns_empty(self):
        from niche.core.sources.scraper import ScraperSource

        html = open(os.path.join(FIXTURES, "scraper_sample.html")).read()
        repo = _mock_repo()
        cfg = _source_cfg("scraper")  # no selectors
        source = ScraperSource(cfg, repo)

        with patch("httpx.get", return_value=_http_response(html)):
            items = source.fetch()

        assert items == []
