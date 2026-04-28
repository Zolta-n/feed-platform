from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable

import httpx
from bs4 import BeautifulSoup

from niche.core.models.types import RawItem, SourceConfig
from niche.core.sources.retry import fetch_with_retry

logger = logging.getLogger(__name__)


class ScraperSource:
    """CSS-selector-driven HTML scraper for press room pages."""

    def __init__(
        self,
        config: SourceConfig,
        repo,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._repo = repo
        self._sleep_fn = sleep_fn
        self.source_id = config.id

    def fetch(self) -> list[RawItem]:
        if not self._config.item_selector or not self._config.title_selector or not self._config.link_selector:
            logger.warning("source=%s missing required selectors, skipping", self.source_id)
            return []
        try:
            items = fetch_with_retry(
                self._do_fetch,
                self.source_id,
                sleep_fn=self._sleep_fn,
            )
            self._repo.update_source_health(
                self.source_id, self._config.feed_id, success=True, error_message=None
            )
            return items
        except Exception as exc:
            logger.error("source=%s all retries exhausted: %s", self.source_id, exc)
            self._repo.update_source_health(
                self.source_id, self._config.feed_id, success=False, error_message=str(exc)
            )
            return []

    def _do_fetch(self) -> list[RawItem]:
        response = httpx.get(self._config.url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        now = datetime.now(timezone.utc)
        items: list[RawItem] = []
        for block in soup.select(self._config.item_selector):
            link_el = block.select_one(self._config.link_selector)
            title_el = block.select_one(self._config.title_selector)
            if not link_el or not title_el:
                continue
            url = link_el.get("href", "").strip()
            if not url:
                continue
            title = title_el.get_text(strip=True)
            published = _parse_date(block, self._config.date_selector) if self._config.date_selector else None
            items.append(RawItem(
                source_id=self.source_id,
                url=url,
                title=title,
                body="",
                language="en",
                published_at=published,
                fetched_at=now,
            ))
        return items


def _parse_date(block, selector: str) -> datetime | None:
    el = block.select_one(selector)
    if not el:
        return None
    date_str = el.get("datetime") or el.get_text(strip=True)
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
