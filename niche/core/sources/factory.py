from __future__ import annotations

import logging

from niche.core.models.types import SourceConfig
from niche.core.sources.base import Source
from niche.core.sources.gdelt import GDELTSource
from niche.core.sources.google_news import GoogleNewsSource
from niche.core.sources.regulatory import RegulatorySource
from niche.core.sources.rss import RSSSource
from niche.core.sources.scraper import ScraperSource
from niche.core.sources.stub import StubSource

logger = logging.getLogger(__name__)

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
