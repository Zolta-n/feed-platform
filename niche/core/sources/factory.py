"""
Source factory — maps source_type strings to adapter classes (EP2, EP6).

Adding a new source type = one adapter class + one entry in SOURCE_REGISTRY.
Adding a new source instance = one line in sources.yaml (no code change).
"""
from __future__ import annotations

import logging
from typing import Any

from ..models.types import FeedBundle, SourceConfig
from .base import Source
from .gdelt import GDELTSource
from .google_news import GoogleNewsSource
from .regulatory import RegulatorySource
from .rss import RSSSource
from .scraper import ScraperSource
from .stub import StubSource

logger = logging.getLogger(__name__)

SOURCE_REGISTRY: dict[str, type] = {
    "rss": RSSSource,
    "gdelt": GDELTSource,
    "google_news": GoogleNewsSource,
    "scraper": ScraperSource,
    "regulatory": RegulatorySource,
    "stub": StubSource,
}


def build_source(cfg: SourceConfig, bundle: FeedBundle | None = None) -> Source:
    """Instantiate a single source adapter from its SourceConfig."""
    cls = SOURCE_REGISTRY.get(cfg.source_type)
    if cls is None:
        logger.warning(
            "Unknown source type '%s' for source '%s'; using StubSource",
            cfg.source_type, cfg.id,
        )
        cls = StubSource

    kwargs: dict[str, Any] = {
        "source_id": cfg.id,
        "name": cfg.name,
        "url": cfg.url,
        "default_region": cfg.default_region,
        "default_topic": cfg.default_topic,
        **cfg.extra,
    }

    # For search-based sources, inject taxonomy query terms from the bundle (EP1)
    if bundle and cfg.source_type in ("gdelt", "google_news"):
        topic_labels = [t.label for t in bundle.taxonomy.topics]
        watchlist_names = [w.name for w in bundle.watchlist if w.enabled]
        kwargs.setdefault("query_terms", topic_labels + watchlist_names[:10])

    return cls(**{k: v for k, v in kwargs.items() if v is not None or k == "url"})


def build_sources(
    source_configs: list[SourceConfig],
    bundle: FeedBundle | None = None,
) -> list[Source]:
    """Build all enabled source adapters from a list of SourceConfig objects."""
    sources = []
    for cfg in source_configs:
        if not cfg.enabled:
            continue
        try:
            source = build_source(cfg, bundle)
            sources.append(source)
        except Exception as exc:
            logger.error("Failed to build source '%s': %s", cfg.id, exc)
    return sources
