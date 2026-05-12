"""Regulatory feed source adapter.

Thin subtype of RSSSource or ScraperSource. Items automatically get
default_topic applied to 'regulation' if not set in sources.yaml (EP1 —
the regulatory_body_code field is opaque; never interpreted here).
"""
from __future__ import annotations

import logging
from typing import Optional

from ..models.types import RawItem
from .rss import RSSSource
from .scraper import ScraperSource

logger = logging.getLogger(__name__)


class RegulatorySource:
    """Wrapper that delegates to RSS or scraper depending on config."""

    def __init__(
        self,
        source_id: str,
        name: str,
        url: Optional[str] = None,
        fetch_mode: str = "rss",  # "rss" or "scraper"
        regulatory_body_code: Optional[str] = None,  # opaque; not interpreted here
        default_topic: str = "regulation",
        **kwargs,
    ) -> None:
        self.source_id = source_id
        self.name = name
        kwargs["default_topic"] = default_topic
        if fetch_mode == "scraper":
            self._delegate = ScraperSource(
                source_id=source_id, url=url or "", name=name, **kwargs
            )
        else:
            self._delegate = RSSSource(
                source_id=source_id, url=url or "", name=name, **kwargs
            )

    def fetch(self) -> list[RawItem]:
        items = self._delegate.fetch()
        # Ensure regulation topic is set in extras for items that don't have one
        for item in items:
            if not item.extra.get("default_topic"):
                item.extra["default_topic"] = "regulation"
        return items


class StubSource:
    """Always returns an empty list. Used for test-fixture and unknown types."""

    def __init__(self, source_id: str, name: str = "", **kwargs) -> None:
        self.source_id = source_id
        self.name = name

    def fetch(self) -> list[RawItem]:
        return []
