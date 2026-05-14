from __future__ import annotations

from niche.core.models.types import FeedConfig
from niche.core.sources.factory import _slugify, dynamic_sources_from_watchlist


def _config(search_context: str | None = "brake") -> FeedConfig:
    return FeedConfig(
        feed_id="test-feed",
        name="Test",
        tagline="t",
        accent_color="#000",
        logo_path=None,
        ui_languages=("en",),
        default_ui_language="en",
        timezone="UTC",
        daily_run_time="05:30",
        from_email="x@example.com",
        search_context=search_context,
    )


class _FakeRepo:
    """Minimal repo stand-in for testing dynamic source generation."""

    def __init__(self, entries):
        self._entries = entries

    def get_watchlist_entries(self, feed_id: str, enabled_only: bool = True):
        # Mimic Repository: skip disabled when enabled_only=True.
        rows = [
            e for e in self._entries
            if e.get("feed_id") == feed_id
            and (not enabled_only or e.get("enabled", 1))
        ]
        return rows


def _entry(**kw):
    base = {
        "id": kw.get("id", "id-1"),
        "feed_id": "test-feed",
        "entry_type": "keyword",
        "name": "Sensify",
        "role": "technology",
        "boost": 1.5,
        "enabled": 1,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------

def test_keyword_entry_produces_google_news_source():
    repo = _FakeRepo([_entry(name="Sensify", boost=2.0, role="tier1")])
    sources = dynamic_sources_from_watchlist(repo, _config(search_context="brake"))
    assert len(sources) == 1
    s = sources[0]
    assert s.id == "gnews-kw-sensify"
    assert s.source_type == "google_news"
    assert "Sensify+brake" in s.url or "Sensify%20brake" in s.url
    assert s.source_weight == 2.0
    assert s.default_topic == "tier1"
    assert s.enabled is True


def test_company_entries_are_ignored():
    repo = _FakeRepo([
        _entry(name="Brembo", entry_type="company"),
        _entry(name="Sensify", entry_type="keyword"),
    ])
    sources = dynamic_sources_from_watchlist(repo, _config())
    assert len(sources) == 1
    assert sources[0].name == "Google News: Sensify"


def test_disabled_entries_excluded():
    """Repository's enabled_only=True filters at the DB layer; the helper trusts it."""
    repo = _FakeRepo([
        _entry(name="On", enabled=1),
        _entry(name="Off", enabled=0),
    ])
    sources = dynamic_sources_from_watchlist(repo, _config())
    assert [s.name for s in sources] == ["Google News: On"]


def test_empty_watchlist_returns_empty():
    repo = _FakeRepo([])
    assert dynamic_sources_from_watchlist(repo, _config()) == []


def test_role_falls_back_to_technology_when_invalid():
    repo = _FakeRepo([_entry(name="X", role="not-a-real-topic")])
    sources = dynamic_sources_from_watchlist(repo, _config())
    assert sources[0].default_topic == "technology"


def test_missing_boost_defaults_to_one():
    repo = _FakeRepo([_entry(name="X", boost=None)])
    sources = dynamic_sources_from_watchlist(repo, _config())
    assert sources[0].source_weight == 1.0


def test_empty_search_context_produces_name_only_query():
    repo = _FakeRepo([_entry(name="iBooster")])
    sources = dynamic_sources_from_watchlist(repo, _config(search_context=""))
    assert "q=iBooster&" in sources[0].url


def test_none_search_context_produces_name_only_query():
    repo = _FakeRepo([_entry(name="iBooster")])
    sources = dynamic_sources_from_watchlist(repo, _config(search_context=None))
    assert "q=iBooster&" in sources[0].url


def test_url_encodes_special_characters_in_name():
    repo = _FakeRepo([_entry(name="A&B & C")])
    sources = dynamic_sources_from_watchlist(repo, _config(search_context="brake"))
    # quote_plus encodes & as %26 and spaces as +
    assert "A%26B" in sources[0].url
    assert "+%26+C+brake" in sources[0].url


def test_duplicate_slugs_are_deduplicated():
    repo = _FakeRepo([
        _entry(id="a", name="Brembo Sensify"),
        _entry(id="b", name="brembo sensify"),  # different casing → same slug
    ])
    sources = dynamic_sources_from_watchlist(repo, _config())
    assert len(sources) == 1


def test_empty_name_is_skipped():
    repo = _FakeRepo([_entry(name="   ")])
    sources = dynamic_sources_from_watchlist(repo, _config())
    assert sources == []


def test_slug_stability():
    """Same name → same source_id across runs (so DB upsert is idempotent)."""
    assert _slugify("Brembo Sensify") == _slugify("Brembo Sensify")
    assert _slugify("Brembo Sensify") == "brembo-sensify"
    assert _slugify("iBooster 2.0!") == "ibooster-2-0"
    assert _slugify("   spaces   ") == "spaces"


def test_no_repo_returns_empty():
    """Defensive: caller passing None for repo (e.g. test scenarios) doesn't crash."""
    assert dynamic_sources_from_watchlist(None, _config()) == []


def test_repo_failure_does_not_crash():
    class _BrokenRepo:
        def get_watchlist_entries(self, *_args, **_kw):
            raise RuntimeError("DB down")
    assert dynamic_sources_from_watchlist(_BrokenRepo(), _config()) == []
