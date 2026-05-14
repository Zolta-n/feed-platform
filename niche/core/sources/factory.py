from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from niche.core.models.types import FeedConfig, SourceConfig
from niche.core.sources.base import Source
from niche.core.sources.gdelt import GDELTSource
from niche.core.sources.google_news import GoogleNewsSource
from niche.core.sources.regulatory import RegulatorySource
from niche.core.sources.rss import RSSSource
from niche.core.sources.scraper import ScraperSource
from niche.core.sources.stub import StubSource

logger = logging.getLogger(__name__)

_VALID_TOPICS = {"tier1", "oem", "regulation", "technology"}

SOURCE_REGISTRY: dict[str, type] = {
    "stub": StubSource,
    "rss": RSSSource,
    "gdelt": GDELTSource,
    "google_news": GoogleNewsSource,
    "scraper": ScraperSource,
    "regulatory": RegulatorySource,
}


def build_sources(sources_config: list[SourceConfig], repo=None) -> list[Source]:
    sources = []
    for cfg in sources_config:
        if not cfg.enabled:
            continue
        adapter_cls = SOURCE_REGISTRY.get(cfg.source_type)
        if adapter_cls is None:
            logger.warning("Unknown source type %r for source %r — skipping", cfg.source_type, cfg.id)
            continue
        if cfg.source_type == "stub":
            sources.append(adapter_cls(source_id=cfg.id, feed_id=cfg.feed_id))
        else:
            sources.append(adapter_cls(cfg, repo))
    return sources


def dynamic_sources_from_watchlist(repo, feed_config: FeedConfig) -> list[SourceConfig]:
    """Generate Google News SourceConfigs from watchlist keyword entries.

    Each enabled watchlist entry with entry_type='keyword' becomes a fresh
    Google News query. Query shape: "{name} {feed_config.search_context}"
    (context is appended to scope vague terms like "Sensify" or "iBooster").
    Companies (entry_type='company') are skipped — they keep their boost-only
    behavior via the ranker.
    """
    if repo is None:
        return []
    try:
        entries = repo.get_watchlist_entries(feed_config.feed_id, enabled_only=True)
    except Exception as exc:
        logger.warning("watchlist read failed (%s) — no dynamic sources", exc)
        return []

    context = (feed_config.search_context or "").strip()
    sources: list[SourceConfig] = []
    seen_ids: set[str] = set()

    for entry in entries:
        if entry["entry_type"] != "keyword":
            continue
        name = (entry["name"] or "").strip()
        if not name:
            continue

        query = f"{name} {context}".strip() if context else name
        slug = _slugify(name)
        source_id = f"gnews-kw-{slug}"
        if source_id in seen_ids:
            logger.warning("duplicate watchlist slug %s — skipping second entry", source_id)
            continue
        seen_ids.add(source_id)

        role = entry["role"] if entry["role"] in _VALID_TOPICS else "technology"
        boost = float(entry["boost"]) if entry["boost"] is not None else 1.0

        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        )
        sources.append(SourceConfig(
            id=source_id,
            feed_id=feed_config.feed_id,
            source_type="google_news",
            url=url,
            name=f"Google News: {name}",
            default_region=None,
            default_topic=role,
            source_weight=boost,
            enabled=True,
        ))
    return sources


def _slugify(name: str) -> str:
    """Produce a stable, source_id-safe slug from a watchlist entry name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "unnamed"
