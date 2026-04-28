from __future__ import annotations

import logging

from niche.core.models.types import SourceConfig
from niche.core.sources.base import Source
from niche.core.sources.stub import StubSource

logger = logging.getLogger(__name__)

SOURCE_REGISTRY: dict[str, type] = {
    "stub": StubSource,
    # rss, gdelt, google_news, scraper, regulatory added in M2
}


def build_sources(sources_config: list[SourceConfig]) -> list[Source]:
    sources = []
    for cfg in sources_config:
        if not cfg.enabled:
            continue
        adapter_cls = SOURCE_REGISTRY.get(cfg.source_type)
        if adapter_cls is None:
            logger.warning("Unknown source type %r for source %r — skipping", cfg.source_type, cfg.id)
            continue
        sources.append(adapter_cls(source_id=cfg.id, feed_id=cfg.feed_id))
    return sources
